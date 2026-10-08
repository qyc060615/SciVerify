import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { apiClient } from '@/services/api'
import { SourceRequiredError, uploadManualSource, verifyCitation } from '@/services/verificationService'
import { ManualSourceRecovery } from '@/components/verification/ManualSourceRecovery'
import VerifyPage from '@/pages/VerifyPage'
import type { BackendVerificationResponse } from '@/types/backend-verification'
import type { VerificationFormSchema } from '@/lib/validations/verification'

const helpers = vi.hoisted(() => ({ addRecord: vi.fn(), submitted: {
  claim: 'Treatment reduces risk.', citation: '10.1234/recovery',
  sourceType: 'doi' as const, context: 'Keep this original context.',
} }))
vi.mock('@/services/api', () => ({ apiClient: { post: vi.fn() } }))
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'local-user' } }) }))
vi.mock('@/stores/verificationStore', () => ({ useVerificationStore: (selector: (s: unknown) => unknown) => selector({
  getRecord: () => undefined, addRecord: helpers.addRecord, loading: false, hydrated: true,
}) }))
vi.mock('@/components/app/AppHeader', () => ({ AppHeader: ({ title }: { title: string }) => <h1>{title}</h1> }))
vi.mock('@/components/verification/VerificationForm', () => ({ VerificationForm: ({ onSubmit }: {
  onSubmit: (v: VerificationFormSchema) => void,
}) => <button onClick={() => onSubmit(helpers.submitted)}>Verify original input</button> }))
vi.mock('@/components/verification/VerificationLoading', () => ({ VerificationLoading: () => <p>Loading</p> }))
vi.mock('@/components/verification/VerificationResultView', () => ({ VerificationResultView: () => <p>Normal verification report</p> }))
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }))

const missing: BackendVerificationResponse = {
  status: 'source_required', claim: helpers.submitted.claim, verdict: null,
  paper: { paper_id: '10.1234/recovery', doi: '10.1234/recovery', title: 'Cited paper' },
  source_recovery: { required: true, reason: 'full_text_unavailable', accepts_manual_pdf: true, max_size_bytes: 1024 },
}
const complete: BackendVerificationResponse = { ...missing, source_recovery: null,
  status: 'success', verdict: 'SUPPORTS', confidence: 0.8,
  summary: 'Direct evidence', reasoning: 'The cited source supports the claim.', evidence: [],
}
const post = vi.mocked(apiClient.post)

beforeEach(() => { vi.clearAllMocks(); helpers.addRecord.mockResolvedValue({ saved: true }) })
afterEach(cleanup)

describe('source recovery service contract', () => {
  it('recognizes source_required without manufacturing a semantic report', async () => {
    post.mockResolvedValue({ data: missing })
    await expect(verifyCitation(helpers.submitted)).rejects.toBeInstanceOf(SourceRequiredError)
  })
  it('uploads DOI and PDF with browser-generated multipart boundary', async () => {
    post.mockResolvedValue({ data: { status: 'accepted' } })
    const file = new File(['%PDF-fixture'], '../../escape.pdf', { type: 'application/pdf' })
    await uploadManualSource(missing.paper.doi, file)
    const [route, data, config] = post.mock.calls[0]
    expect(route).toBe('/api/sources/manual')
    expect((data as FormData).get('doi')).toBe(missing.paper.doi)
    expect((data as FormData).get('file')).toBe(file)
    expect(config?.headers?.['Content-Type']).toBeUndefined()
  })
})

describe('recovery UI', () => {
  it.each(['The uploaded PDF does not appear to match DOI 10.1234/recovery.',
    'The PDF could not be read.', 'The cited paper metadata could not be resolved.',
    'The PDF could not be saved locally.'])('shows safe upload failure and allows another PDF: %s', async (message) => {
    post.mockRejectedValueOnce(new Error(message)).mockResolvedValueOnce({ data: { status: 'accepted' } })
    const retry = vi.fn().mockResolvedValue(undefined)
    render(<ManualSourceRecovery response={missing} onAccepted={retry} onCancel={vi.fn()} />)
    const input = screen.getByLabelText('Cited PDF')
    fireEvent.change(input, { target: { files: [new File(['%PDF-wrong'], 'wrong.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload and retry verification' }))
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', message)
    expect(retry).not.toHaveBeenCalled()
    fireEvent.change(input, { target: { files: [new File(['%PDF-correct'], 'correct.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload and retry verification' }))
    await waitFor(() => expect(retry).toHaveBeenCalledOnce())
  })
  it('rejects an oversized PDF before upload', async () => {
    render(<ManualSourceRecovery response={missing} onAccepted={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Cited PDF'), { target: { files: [new File(['x'.repeat(1025)], 'large.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload and retry verification' }))
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Select a non-empty PDF within the upload size limit.')
    expect(post).not.toHaveBeenCalled()
  })
  it('uploads, automatically retries identical claim+DOI, and keeps context in the saved report', async () => {
    post.mockResolvedValueOnce({ data: missing })
      .mockResolvedValueOnce({ data: { status: 'accepted' } })
      .mockResolvedValueOnce({ data: complete })
    render(<MemoryRouter><VerifyPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'Verify original input' }))
    await screen.findByText('The cited paper could not be retrieved automatically.')
    expect(helpers.addRecord).not.toHaveBeenCalled()
    expect(screen.queryByText('Normal verification report')).toBeNull()
    fireEvent.change(screen.getByLabelText('Cited PDF'), { target: { files: [new File(['%PDF-fixture'], 'cited.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload and retry verification' }))
    await waitFor(() => expect(helpers.addRecord).toHaveBeenCalledOnce())
    expect(post.mock.calls.map(c => c[0])).toEqual(['/api/verification/analyze', '/api/sources/manual', '/api/verification/analyze'])
    expect(post.mock.calls[0][1]).toEqual(post.mock.calls[2][1])
    expect(post.mock.calls[2][1]).toEqual({ claim: helpers.submitted.claim, doi: helpers.submitted.citation })
    // Mapper preserves submitted context in the existing report contract.
    expect(JSON.stringify(helpers.addRecord.mock.calls[0][1])).toContain(helpers.submitted.context)
  })
})
