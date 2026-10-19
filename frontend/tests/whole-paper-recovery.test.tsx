import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { JobSourceRecovery } from '@/components/manuscript/JobSourceRecovery'
import { ApiResponseError } from '@/services/api'
import { jobFixture, jobId } from './fixtures/job'
import type { VerificationJob } from '@/types/verification-job'

const actions = vi.hoisted(() => ({ upload: vi.fn(), resume: vi.fn(), limits: vi.fn(), acquire: vi.fn() }))
vi.mock('@/services/verificationService', () => ({ uploadManualSource: actions.upload }))
vi.mock('@/services/verificationJobService', () => ({ resumeVerificationJob: actions.resume, acquireJobSource: actions.acquire }))
vi.mock('@/services/manuscriptService', async original => ({ ...await original<object>(), getUploadLimits: actions.limits }))
const hash = 'd'.repeat(64)
function recoveryJob() {
  const job = jobFixture()
  job.references = job.references.map(r => r.id === 'r4' ? { ...r, doi: '10.1234/source' } : r)
  return job
}
function renderRecovery(job = recoveryJob()) {
  const refresh = vi.fn().mockResolvedValue(job)
  const acceptSnapshot = vi.fn()
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><JobSourceRecovery job={job} refresh={refresh} acceptSnapshot={acceptSnapshot} /></QueryClientProvider>)
  return { refresh, acceptSnapshot }
}
async function upload() {
  const input = await screen.findByLabelText('Source PDF for 10.1234/source')
  fireEvent.change(input, { target: { files: [new File(['%PDF-source'], 'source.pdf', { type: 'application/pdf' })] } })
  await waitFor(() => expect((screen.getByRole('button', { name: 'Upload source PDF' }) as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: 'Upload source PDF' }))
  await screen.findByRole('button', { name: 'Resume selected references' })
}
beforeEach(() => {
  vi.clearAllMocks(); actions.limits.mockResolvedValue({ manuscript_max_bytes: 100, source_max_bytes: 100 })
  actions.upload.mockResolvedValue({ status: 'accepted', doi: '10.1234/source', raw_content_sha256: hash, identity_match: 'doi' })
  actions.resume.mockResolvedValue({ ...recoveryJob(), status: 'running', revision: 7 })
})
afterEach(cleanup)

it('passes real uploaded hash under Reference ID and never reruns a completed reference', async () => {
  const { acceptSnapshot } = renderRecovery(); await upload()
  expect(actions.resume).not.toHaveBeenCalled()
  const button = screen.getByRole('button', { name: 'Resume selected references' })
  fireEvent.click(button); fireEvent.click(button)
  await waitFor(() => expect(actions.resume).toHaveBeenCalledTimes(1))
  expect(actions.resume).toHaveBeenCalledWith(jobId, { expected_revision: 6, reference_ids: ['r4'], source_hashes: { r4: hash }, retry_failed: false })
  expect(acceptSnapshot).toHaveBeenCalled()
})
it('maps one DOI to multiple explicitly selected reference IDs', async () => {
  const job = recoveryJob(); job.references.push({ ...job.references[1], id: 'r6', doi: '10.1234/source' }); job.tasks.push({ ...job.tasks[1], task_key: 'task_6', reference_id: 'r6' })
  renderRecovery(job); await upload(); fireEvent.click(screen.getByRole('button', { name: 'Resume selected references' }))
  await waitFor(() => expect(actions.resume).toHaveBeenCalledWith(jobId, expect.objectContaining({ reference_ids: ['r4', 'r6'], source_hashes: { r4: hash, r6: hash } })))
})
it('refreshes on revision conflict and requires another explicit confirmation', async () => {
  actions.resume.mockRejectedValueOnce(new ApiResponseError('conflict', 409, { detail: { code: 'JOB_REVISION_CONFLICT' } }))
  const { refresh } = renderRecovery(); await upload()
  refresh.mockResolvedValueOnce(recoveryJob()).mockResolvedValue({ ...recoveryJob(), revision: 8 })
  fireEvent.click(screen.getByRole('button', { name: 'Resume selected references' }))
  await screen.findByText(/job changed.*confirm the recovery again/)
  expect(actions.resume).toHaveBeenCalledTimes(1)
  expect(screen.getByText('Reviewed revision: 8')).toBeTruthy()
})
it('does not silently resume when the revision changed before submission', async () => {
  const { refresh } = renderRecovery(); await upload(); refresh.mockResolvedValue({ ...recoveryJob(), revision: 8 })
  fireEvent.click(screen.getByRole('button', { name: 'Resume selected references' }))
  await screen.findByText(/confirm resume again/); expect(actions.resume).not.toHaveBeenCalled()
})
it('shows a pinned source hash conflict without automatic retries', async () => {
  actions.resume.mockRejectedValue(new ApiResponseError('conflict', 409, { detail: { code: 'JOB_SOURCE_VERSION_CONFLICT' } }))
  renderRecovery(); await upload(); fireEvent.click(screen.getByRole('button', { name: 'Resume selected references' }))
  await screen.findByText(/does not match the version pinned/); expect(actions.resume).toHaveBeenCalledTimes(1)
})
it.each([null, 'invalid', 'See 10.1234/source'])('does not offer upload for a missing or invalid DOI', doi => {
  const job = jobFixture(); job.references = job.references.map(r => r.id === 'r4' ? { ...r, doi } : r)
  renderRecovery(job); expect(screen.queryByRole('button', { name: 'Upload source PDF' })).toBeNull()
})
it('uses explicit retry_failed for verifier failure rather than pretending a PDF is missing', async () => {
  const job: VerificationJob = jobFixture(); job.tasks = [ { ...job.tasks[0], state: 'failed', resume_available: true, reason_code: 'VERIFIER_EXECUTION_FAILURE', pair_outcome: null } ]
  renderRecovery(job); expect(screen.queryByRole('button', { name: 'Upload source PDF' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Retry reference r3' }))
  await waitFor(() => expect(actions.resume).toHaveBeenCalledWith(jobId, { expected_revision: 6, reference_ids: ['r3'], retry_failed: true }))
})

it('acquires a URL document first and requires separate explicit paid resume confirmation', async () => {
  const job = recoveryJob(); job.references = job.references.map(r => r.id === 'r4' ? { ...r, doi: null, url: 'https://www.fda.gov/media/123/download' } : r)
  actions.acquire.mockResolvedValue({ status: 'accepted', raw_content_sha256: hash, source: {} })
  const { acceptSnapshot } = renderRecovery(job)
  expect(screen.queryByRole('button', { name: 'Upload source PDF' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Fetch URL source' }))
  await screen.findByRole('button', { name: 'Confirm resume URL reference' })
  expect(actions.acquire).toHaveBeenCalledWith(jobId, 'r4', 6)
  expect(actions.resume).not.toHaveBeenCalled()
  expect(screen.getByText(/Historical version is unconfirmed/)).toBeTruthy()
  const button = screen.getByRole('button', { name: 'Confirm resume URL reference' })
  fireEvent.click(button); fireEvent.click(button)
  await waitFor(() => expect(actions.resume).toHaveBeenCalledTimes(1))
  expect(actions.resume).toHaveBeenCalledWith(jobId, { expected_revision: 6, reference_ids: ['r4'], source_hashes: { r4: hash } })
  expect(acceptSnapshot).toHaveBeenCalled()
})
