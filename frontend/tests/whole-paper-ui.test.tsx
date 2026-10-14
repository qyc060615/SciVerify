import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import WholePaperVerifyPage from '@/pages/WholePaperVerifyPage'
import WholePaperJobPage from '@/pages/WholePaperJobPage'
import { WholePaperReport } from '@/components/manuscript/WholePaperReport'
import { WholePaperRoute } from '@/routes/WholePaperRoute'
import { ApiResponseError } from '@/services/api'
import { jobFixture, jobId } from './fixtures/job'
import fixture from './fixtures/manuscript.json'

const services = vi.hoisted(() => ({ parse: vi.fn(), extract: vi.fn(), limits: vi.fn(), create: vi.fn(), get: vi.fn(), resume: vi.fn(), demo: vi.fn() }))
vi.mock('@/services/manuscriptService', async importOriginal => ({ ...await importOriginal<object>(), parseManuscript: services.parse, extractClaims: services.extract, getUploadLimits: services.limits }))
vi.mock('@/services/verificationJobService', async importOriginal => ({ ...await importOriginal<object>(), createVerificationJob: services.create, getVerificationJob: services.get, resumeVerificationJob: services.resume }))
vi.mock('@/lib/demo-mode', () => ({ isLocalDemoMode: services.demo }))

function app(path = '/app/manuscripts') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  const rendered = render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes>
    <Route element={<WholePaperRoute />}><Route path="/app/manuscripts" element={<WholePaperVerifyPage />} /><Route path="/app/manuscripts/jobs/:jobId" element={<WholePaperJobPage />} /></Route>
    <Route path="/app/verify" element={<p>Single claim verification</p>} />
  </Routes></MemoryRouter></QueryClientProvider>)
  return { ...rendered, client }
}
beforeEach(() => {
  vi.clearAllMocks(); localStorage.clear(); services.demo.mockReturnValue(true)
  services.limits.mockResolvedValue({ manuscript_max_bytes: 100, source_max_bytes: 100 })
  services.parse.mockResolvedValue(fixture.parse_response); services.extract.mockResolvedValue(fixture.job_request.extraction)
  services.create.mockResolvedValue(jobFixture()); services.get.mockResolvedValue(jobFixture())
})
afterEach(cleanup)

describe('whole-paper upload and review', () => {
  it('requires separate explicit parse/extract/create actions and prevents double job creation', async () => {
    app(); await screen.findByText(/PDF limit/)
    const file = new File(['%PDF-test'], 'manuscript.pdf', { type: 'application/pdf' })
    fireEvent.change(screen.getByLabelText('Manuscript PDF'), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: 'Parse manuscript' }))
    await screen.findByRole('button', { name: 'Extract claims' })
    expect(services.parse).toHaveBeenCalledWith(file); expect(services.extract).not.toHaveBeenCalled(); expect(services.create).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Extract claims' }))
    await screen.findByText('Review extracted claims')
    expect(services.extract).toHaveBeenCalledWith(fixture.parse_response)
    expect(screen.getByText(/may call external LLM/)).toBeTruthy()
    const start = screen.getByRole('button', { name: 'Start whole-paper verification' })
    fireEvent.click(start); fireEvent.click(start)
    await screen.findByText('Verification overview')
    expect(services.create).toHaveBeenCalledTimes(1)
    expect(services.create).toHaveBeenCalledWith(fixture.job_request)
    expect(JSON.parse(localStorage.getItem('researchguard-recent-jobs')!)).toEqual([jobId])
  })
  it.each([new File([], 'empty.pdf'), new File(['%PDF'], 'wrong.txt'), new File(['x'.repeat(101)], 'big.pdf')])('rejects invalid or oversized PDF before any request', async file => {
    app(); await screen.findByText(/PDF limit/)
    fireEvent.change(screen.getByLabelText('Manuscript PDF'), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: 'Parse manuscript' }))
    await screen.findByRole('alert'); expect(services.parse).not.toHaveBeenCalled()
  })
  it('requires confirmation for partial extraction', async () => {
    services.extract.mockResolvedValue({ ...fixture.job_request.extraction, status: 'partial' })
    app(); await screen.findByText(/PDF limit/)
    fireEvent.change(screen.getByLabelText('Manuscript PDF'), { target: { files: [new File(['%PDF'], 'paper.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Parse manuscript' })); await screen.findByRole('button', { name: 'Extract claims' })
    fireEvent.click(screen.getByRole('button', { name: 'Extract claims' })); await screen.findByText('Review extracted claims')
    const button = screen.getByRole('button', { name: 'Start whole-paper verification' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
    fireEvent.click(screen.getByRole('checkbox')); expect(button.disabled).toBe(false)
  })
  it.each(['failed', 'completed'])('does not start a job with zero valid pairs (%s extraction)', async status => {
    services.extract.mockResolvedValue({ ...fixture.job_request.extraction, status, claims: [] })
    app(); await screen.findByText(/PDF limit/)
    fireEvent.change(screen.getByLabelText('Manuscript PDF'), { target: { files: [new File(['%PDF'], 'paper.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Parse manuscript' })); await screen.findByRole('button', { name: 'Extract claims' })
    fireEvent.click(screen.getByRole('button', { name: 'Extract claims' })); await screen.findByText('Review extracted claims')
    expect((screen.getByRole('button', { name: 'Start whole-paper verification' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText(/No executable pairs/)).toBeTruthy(); expect(services.create).not.toHaveBeenCalled()
  })
  it('restores a saved job URL without parse/extract/create', async () => {
    app(`/app/manuscripts/jobs/${jobId}`); await screen.findByText('Verification overview')
    expect(services.get).toHaveBeenCalledWith(jobId, expect.anything())
    expect(services.parse).not.toHaveBeenCalled(); expect(services.extract).not.toHaveBeenCalled(); expect(services.create).not.toHaveBeenCalled()
  })
  it.each([[404, 'JOBS_DISABLED', /jobs are disabled/], [404, 'JOB_NOT_FOUND', /job was not found/], [undefined, '', /Unable to connect/]] as const)('shows actionable backend errors', async (status, code, message) => {
    services.get.mockRejectedValue(new ApiResponseError('secret provider text', status, { detail: { code } }))
    app(`/app/manuscripts/jobs/${jobId}`); await screen.findByText(message)
    expect(screen.queryByText('secret provider text')).toBeNull()
  })
  it('keeps whole-paper routes out of Supabase mode', async () => {
    services.demo.mockReturnValue(false); app(); await screen.findByText('Single claim verification')
    expect(services.get).not.toHaveBeenCalled(); expect(services.parse).not.toHaveBeenCalled()
  })
})

describe('pair-level report contracts', () => {
  it('renders separate pairs, completed contradiction and uncertain HTML evidence without a page', () => {
    render(<WholePaperReport job={jobFixture()} />)
    expect(screen.getAllByTestId('pair-card')).toHaveLength(2)
    expect(screen.getByText('Contradicted')).toBeTruthy()
    expect(screen.getByText(/Identity: uncertain/)).toBeTruthy()
    expect(screen.getAllByText(/Confidence:/)).toHaveLength(1)
    expect(screen.queryByText(/FABRICATED/)).toBeNull()
    expect((screen.getByRole('progressbar') as HTMLProgressElement).max).toBe(2)
  })
  it('does not expose a semantic verdict or confidence for failed processing', () => {
    const job = jobFixture(); job.tasks[0].state = 'failed'
    render(<WholePaperReport job={job} />)
    expect(screen.queryByText('Contradicted')).toBeNull(); expect(screen.queryByText(/Confidence:/)).toBeNull()
    expect(screen.getByText(/No scientific verdict was produced/)).toBeTruthy()
  })
  it('shows zero pairs and extraction coverage gaps without fake completion', () => {
    const job = jobFixture(); job.tasks = []; job.coverage.total_pairs = 0; job.coverage.skipped_extraction_contexts = 1
    render(<WholePaperReport job={job} />)
    expect(screen.queryByRole('progressbar')).toBeNull(); expect(screen.getByText(/Completion percentage is not applicable/)).toBeTruthy()
    expect(screen.getByText(/1 skipped contexts/)).toBeTruthy()
  })
  it('keeps runtime diagnostics separate from scientific verdicts', async () => {
    const job = jobFixture(); job.runtime_error_code = 'JOB_STORAGE_ERROR'
    render(<WholePaperReport job={job} />)
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Committed results remain visible'))
    expect(screen.getByText('Contradicted')).toBeTruthy()
  })
})
