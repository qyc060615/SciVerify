import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import SettingsPage from '@/pages/SettingsPage'
import * as service from '@/services/settingsService'
import type { ApiSettings } from '@/services/settingsService'

const auth = vi.hoisted(() => ({ user: { email: 'local@example.invalid' }, profile: { full_name: 'Local researcher' }, isLocalDemo: true, signOut: vi.fn() }))
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => auth }))
vi.mock('@/hooks/useUserDisplayName', () => ({ useUserDisplayName: () => 'Local researcher' }))
vi.mock('@/services/settingsService', () => ({ getApiSettings: vi.fn(), saveApiConnection: vi.fn(), testApiConnection: vi.fn(), getSystemStatus: vi.fn(), refreshSystemStatus: vi.fn() }))
const fixture: ApiSettings = {
  revision: 0, restart_required: false, management_token: 'local-test-token', services: [{
    id: 'llm', label: 'LLM Provider', purpose: 'Shared by extraction and verification.',
    fields: [{ name: 'provider', label: 'Provider protocol', kind: 'select', options: ['none', 'openai-compatible'] }, { name: 'base_url', label: 'Base URL', kind: 'url', options: [] }, { name: 'model', label: 'Model ID', kind: 'text', options: [] }],
    values: { provider: 'openai-compatible', base_url: 'https://example.org/v1', model: 'old-model', connection_source: 'self' },
    has_key: true, has_own_key: true, supports_key: true, share_options: [], paid_test: true,
    pending_restart: false, active_model: 'old-model', active_base_url: 'https://example.org/v1', active_has_key: true,
  }],
}
function mount() { return render(<MemoryRouter><SettingsPage /></MemoryRouter>) }
async function openApi() {
  fireEvent.click(screen.getByRole('tab', { name: 'API' }))
  fireEvent.click(await screen.findByText('LLM Provider'))
}
beforeEach(() => {
  vi.clearAllMocks(); auth.isLocalDemo = true
  vi.mocked(service.getApiSettings).mockResolvedValue(structuredClone(fixture))
  vi.mocked(service.getSystemStatus).mockResolvedValue([
    { id: 'backend', label: 'FastAPI Backend', state: 'ok', message: 'API responded.', scope: 'HTTP only' },
    { id: 'grobid', label: 'GROBID Parser', state: 'failed', message: 'Parser is unavailable.', scope: 'Health check' },
    { id: 'llm', label: 'LLM Provider', state: 'unknown', message: 'Not checked.', scope: 'No inference' },
    { id: 'paperqa', label: 'PaperQA2 Model', state: 'unknown', message: 'Not checked.', scope: 'No inference' },
    { id: 'embedding', label: 'Embedding Provider', state: 'unknown', message: 'Not checked.', scope: 'No inference' },
  ])
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('Settings tabs and account', () => {
  it('shows ordered tabs, defaults to ACCOUNT and does not fetch service settings', () => {
    mount()
    expect(screen.getAllByRole('tab').map(tab => tab.textContent)).toEqual(['ACCOUNT', 'SYSTEM STATUS', 'API'])
    expect(screen.getByRole('tab', { name: 'ACCOUNT' }).getAttribute('aria-selected')).toBe('true')
    expect(screen.getByLabelText('Full name')).toHaveProperty('readOnly', true)
    expect(screen.getByLabelText('Email')).toHaveProperty('value', 'local@example.invalid')
    expect(screen.queryByRole('button', { name: 'Logout' })).toBeNull()
    expect(service.getApiSettings).not.toHaveBeenCalled()
  })
  it('keeps normal account logout and prevents remote API administration', async () => {
    auth.isLocalDemo = false
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'Logout' }))
    await waitFor(() => expect(auth.signOut).toHaveBeenCalledOnce())
    fireEvent.click(screen.getByRole('tab', { name: 'API' }))
    expect(screen.getByText(/API administration is available in Local Demo/)).toBeTruthy()
    expect(service.getApiSettings).not.toHaveBeenCalled()
  })
  it('supports keyboard tabs and retains API drafts across tab changes', async () => {
    mount(); await openApi()
    fireEvent.change(screen.getByLabelText('Model ID'), { target: { value: 'draft-model' } })
    fireEvent.click(screen.getByRole('tab', { name: 'ACCOUNT' }))
    fireEvent.click(screen.getByRole('tab', { name: 'API' }))
    expect(screen.getByLabelText('Model ID')).toHaveProperty('value', 'draft-model')
    fireEvent.keyDown(screen.getByRole('tab', { name: 'API' }), { key: 'Home' })
    expect(screen.getByRole('tab', { name: 'ACCOUNT' }).getAttribute('aria-selected')).toBe('true')
  })
})

describe('System status stays compact and explicit', () => {
  it('shows passed, failed and unknown with a single explicit refresh', async () => {
    vi.mocked(service.refreshSystemStatus).mockResolvedValue([])
    mount()
    fireEvent.click(screen.getByRole('tab', { name: 'SYSTEM STATUS' }))
    await screen.findByText('FastAPI Backend')
    expect(screen.getByRole('img', { name: 'Passed' })).toBeTruthy()
    expect(screen.getByRole('img', { name: 'Failed' })).toBeTruthy()
    expect(screen.queryByText('LLM Provider')).toBeNull()
    expect(screen.queryByText('PaperQA2 Model')).toBeNull()
    expect(screen.queryByText('Embedding Provider')).toBeNull()
    expect(screen.queryByRole('img', { name: 'Not checked' })).toBeNull()
    expect(service.refreshSystemStatus).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Refresh', exact: true }))
    await waitFor(() => expect(service.refreshSystemStatus).toHaveBeenCalledWith('local-test-token'))
    expect(service.testApiConnection).not.toHaveBeenCalled()
  })
})

it('does not keep green statuses after a failed refresh', async () => {
  vi.mocked(service.refreshSystemStatus).mockRejectedValue(new Error('Backend unavailable'))
  mount()
  fireEvent.click(screen.getByRole('tab', { name: 'SYSTEM STATUS' }))
  await screen.findByText('FastAPI Backend')
  fireEvent.click(screen.getByRole('button', { name: 'Refresh', exact: true }))
  await screen.findByRole('alert')
  expect(screen.queryByRole('img', { name: 'Passed' })).toBeNull()
  expect(screen.getAllByRole('img', { name: 'Not checked' })).toHaveLength(2)
})

describe('Real configuration form interactions with offline service fixtures', () => {
  it('retains saved keys when blank, clears typed keys on cancel and does not write localStorage', async () => {
    const storage = vi.spyOn(Storage.prototype, 'setItem')
    mount(); await openApi()
    const key = screen.getByLabelText('API Key')
    expect(key).toHaveProperty('type', 'password')
    expect(key).toHaveProperty('value', '')
    fireEvent.change(key, { target: { value: 'newly-typed-secret' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show new API key' }))
    expect(key).toHaveProperty('type', 'text')
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(key).toHaveProperty('value', '')
    expect(key).toHaveProperty('type', 'password')
    expect(storage).not.toHaveBeenCalled()
  })
  it('saves real drafts, keeps inputs on failure and shows restart requirements after success', async () => {
    vi.mocked(service.saveApiConnection).mockRejectedValueOnce(new Error('Save failed; draft kept.'))
    mount(); await openApi()
    fireEvent.change(screen.getByLabelText('Model ID'), { target: { value: 'new-model' } })
    fireEvent.change(screen.getByLabelText('API Key'), { target: { value: 'newly-typed-secret' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }))
    await screen.findByRole('alert')
    expect(screen.getByLabelText('API Key')).toHaveProperty('value', 'newly-typed-secret')
    const next = structuredClone(fixture); next.revision = 1; next.restart_required = true; next.services[0].pending_restart = true; next.services[0].values.model = 'new-model'
    vi.mocked(service.saveApiConnection).mockResolvedValueOnce(next)
    fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }))
    await screen.findByText(/Saved. Restart the backend/)
    expect(service.saveApiConnection).toHaveBeenLastCalledWith('llm', expect.objectContaining({ api_key: 'newly-typed-secret', clear_api_key: false }), 0, 'local-test-token')
    expect(screen.getByLabelText('API Key')).toHaveProperty('value', '')
    expect(screen.getByRole('button', { name: 'Save', exact: true })).toHaveProperty('disabled', true)
  })
  it('requires an explicit charge opt-in and reports the actual test result', async () => {
    vi.mocked(service.testApiConnection).mockResolvedValue({ id: 'llm', state: 'failed', message: 'Authentication rejected.', scope: 'Offline fixture' })
    mount(); await openApi()
    const test = screen.getByRole('button', { name: 'Test connection' })
    expect(test).toHaveProperty('disabled', true)
    fireEvent.click(screen.getByRole('checkbox', { name: /I allow one small model request/ }))
    fireEvent.click(test)
    await screen.findByText('Authentication rejected.')
    expect(service.testApiConnection).toHaveBeenCalledWith('llm', expect.objectContaining({ api_key: undefined, clear_api_key: false }), true, 'local-test-token')
    expect(service.saveApiConnection).not.toHaveBeenCalled()
  })
  it('requires a separate explicit removal action before clearing a key', async () => {
    vi.mocked(service.saveApiConnection).mockResolvedValue(structuredClone(fixture))
    mount(); await openApi()
    fireEvent.click(screen.getByRole('button', { name: 'Remove saved key on Save' }))
    expect(screen.getByLabelText('API Key')).toHaveProperty('disabled', true)
    expect(service.saveApiConnection).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }))
    await waitFor(() => expect(service.saveApiConnection).toHaveBeenCalledWith('llm', expect.objectContaining({ clear_api_key: true, api_key: undefined }), 0, 'local-test-token'))
  })
  it('reuses connections without exposing or resubmitting their keys', async () => {
    const other = structuredClone(fixture.services[0]); other.id = 'paperqa'; other.label = 'PaperQA2 Model'; other.share_options = ['llm']; other.values.model = 'openai/other'
    const data = structuredClone(fixture); data.services.push(other)
    vi.mocked(service.getApiSettings).mockResolvedValue(data)
    mount(); await openApi()
    fireEvent.click(screen.getByText('PaperQA2 Model'))
    const form = screen.getByText('PaperQA2 Model').closest('details')!
    fireEvent.change(within(form).getByLabelText('Provider connection'), { target: { value: 'llm' } })
    expect(within(form).queryByLabelText('API Key')).toBeNull()
    expect(within(form).queryByLabelText('Base URL')).toBeNull()
    expect(within(form).getByLabelText('Model ID')).toHaveProperty('value', 'openai/other')
  })
})
