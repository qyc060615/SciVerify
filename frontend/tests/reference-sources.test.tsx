import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReferenceReview } from '@/components/manuscript/ReferenceReview'
import fixture from './fixtures/manuscript.json'
import type { Reference } from '@/types/manuscript'
const actions = vi.hoisted(() => ({ status: vi.fn(), upload: vi.fn(), limits: vi.fn() }))
vi.mock('@/services/sourceService', async original => ({ ...await original<object>(), getLocalSourceStatus: actions.status }))
vi.mock('@/services/verificationService', () => ({ uploadManualSource: actions.upload }))
vi.mock('@/services/manuscriptService', async original => ({ ...await original<object>(), getUploadLimits: actions.limits }))
const hash = 'e'.repeat(64)
const absent = { availability: 'not_cached', remote_status: 'not_checked', raw_content_sha256: null, format: null }
const available = { availability: 'available', remote_status: 'not_checked', raw_content_sha256: hash, format: 'pdf' }
function mount(reference = fixture.parse_response.parsed.references[0] as Reference) {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}><ReferenceReview references={[reference]} allowSources /></QueryClientProvider>)
}
beforeEach(() => { vi.clearAllMocks(); actions.status.mockResolvedValue(absent); actions.limits.mockResolvedValue({ manuscript_max_bytes: 1000, source_max_bytes: 1000 }) })
afterEach(cleanup)

it('unknown remote full text is not mislabeled missing or available', async () => {
  mount()
  await screen.findByText('Full text: Not checked')
  expect(screen.queryByText(/Full text: Available/)).toBeNull()
  expect(screen.queryByRole('button', { name: 'Upload PDF' })).toBeNull()
  fireEvent.click(screen.getByText('Source details · Add Source'))
  expect(screen.getByRole('button', { name: 'Add Source' })).toBeTruthy()
  expect(screen.getByText(/Automatic full-text retrieval has not run/)).toBeTruthy()
})

it('verified existing files hide the upload action and expose their actual hash', async () => {
  actions.status.mockResolvedValue(available)
  mount(); await screen.findByText('Full text: Available locally (PDF)')
  expect(screen.queryByRole('button', { name: 'Add Source' })).toBeNull()
  expect(screen.queryByRole('button', { name: 'Upload PDF' })).toBeNull()
  expect(screen.getByText('SHA-256: ' + hash)).toBeTruthy()
})

it('preuploads against the exact DOI and confirms real cache status before success', async () => {
  const ref = fixture.parse_response.parsed.references[0] as Reference
  let saved = false
  actions.status.mockImplementation(async () => saved ? available : absent)
  actions.upload.mockImplementation(async () => { saved = true; return { status: 'accepted', doi: ref.doi, raw_content_sha256: hash, identity_match: 'doi' } })
  const localStorageWrite = vi.spyOn(Storage.prototype, 'setItem')
  mount(); await screen.findByText('Full text: Not checked')
  fireEvent.click(screen.getByText('Source details · Add Source'))
  fireEvent.click(screen.getByRole('button', { name: 'Add Source' }))
  const pdf = new File(['%PDF'], 'reference.pdf', { type: 'application/pdf' })
  fireEvent.change(await screen.findByLabelText('Source PDF for ' + ref.doi), { target: { files: [pdf] } })
  await waitFor(() => expect(screen.getByRole('button', { name: 'Upload PDF' })).toHaveProperty('disabled', false))
  fireEvent.click(screen.getByRole('button', { name: 'Upload PDF' }))
  await screen.findByText(/PDF saved and verified/)
  expect(actions.upload).toHaveBeenCalledWith(ref.doi, pdf)
  expect(actions.status).toHaveBeenCalledTimes(2)
  expect(screen.getByText('Full text: Available locally (PDF)')).toBeTruthy()
  expect(localStorageWrite).not.toHaveBeenCalled()
  localStorageWrite.mockRestore()
})

it('an accepted receipt without a confirmed file never becomes an available source', async () => {
  const ref = fixture.parse_response.parsed.references[0] as Reference
  actions.upload.mockResolvedValue({ status: 'accepted', doi: ref.doi, raw_content_sha256: hash })
  mount(); await screen.findByText('Full text: Not checked')
  fireEvent.click(screen.getByText('Source details · Add Source'))
  fireEvent.click(screen.getByRole('button', { name: 'Add Source' }))
  fireEvent.change(await screen.findByLabelText('Source PDF for ' + ref.doi), { target: { files: [new File(['%PDF'], 'ref.pdf')] } })
  await waitFor(() => expect(screen.getByRole('button', { name: 'Upload PDF' })).toHaveProperty('disabled', false))
  fireEvent.click(screen.getByRole('button', { name: 'Upload PDF' }))
  await screen.findByText(/saved file could not be confirmed/)
  expect(screen.queryByText(/Full text: Available/)).toBeNull()
})

it('URL-only references explain the manual-upload limit rather than fabricating DOI bindings', async () => {
  mount({ ...fixture.parse_response.parsed.references[0], doi: null, url: 'https://example.org/paper' } as Reference)
  await screen.findByText('Full text: Not checked')
  fireEvent.click(screen.getByText('Source details'))
  expect(screen.getByText(/Manual PDF validation currently requires a DOI/)).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Add Source' })).toBeNull()
})
