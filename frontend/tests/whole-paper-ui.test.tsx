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
import type { ParseResponse, ReferenceResolution } from '@/types/manuscript'

const services = vi.hoisted(() => ({ parse: vi.fn(), resolve: vi.fn(), extract: vi.fn(), limits: vi.fn(), create: vi.fn(), get: vi.fn(), resume: vi.fn(), demo: vi.fn() }))
vi.mock('@/services/manuscriptService', async importOriginal => ({ ...await importOriginal<object>(), parseManuscript: services.parse, resolveReferences: services.resolve, extractClaims: services.extract, getUploadLimits: services.limits }))
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
  services.parse.mockResolvedValue(fixture.parse_response); services.resolve.mockResolvedValue(fixture.parse_response); services.extract.mockResolvedValue(fixture.job_request.extraction)
  services.create.mockResolvedValue(jobFixture()); services.get.mockResolvedValue(jobFixture())
})
afterEach(cleanup)

async function resolveAndReview() {
  await screen.findByRole('button', { name: 'Resolve references' })
  expect(screen.queryByRole('button', { name: 'Extract claims' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Resolve references' }))
  await screen.findByRole('button', { name: 'Continue with reviewed references' })
  fireEvent.click(screen.getByRole('button', { name: 'Continue with reviewed references' }))
  await screen.findByRole('button', { name: 'Extract claims' })
}

function resolution(status: ReferenceResolution['status'], overrides: Partial<ReferenceResolution> = {}): ReferenceResolution {
  return { reference_id: 'r-extra', status, original_doi: null, resolved_doi: null, matched_title: null, provider: null, source_type: 'unknown', source_url: null, match_reason: 'NO_RELIABLE_MATCH', match_confidence: null, diagnostics: [], candidates: [], ...overrides }
}

describe('whole-paper upload and review', () => {
  it('requires separate explicit parse/resolve/review/extract/create actions and prevents double job creation', async () => {
    app(); await screen.findByText(/PDF limit/)
    const file = new File(['%PDF-test'], 'manuscript.pdf', { type: 'application/pdf' })
    fireEvent.change(screen.getByLabelText('Manuscript PDF'), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: 'Parse manuscript' }))
    await resolveAndReview()
    expect(services.parse).toHaveBeenCalledWith(file); expect(services.extract).not.toHaveBeenCalled(); expect(services.create).not.toHaveBeenCalled()
    expect(services.resolve).toHaveBeenCalledWith(fixture.parse_response)
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
    fireEvent.click(screen.getByRole('button', { name: 'Parse manuscript' })); await resolveAndReview()
    fireEvent.click(screen.getByRole('button', { name: 'Extract claims' })); await screen.findByText('Review extracted claims')
    const button = screen.getByRole('button', { name: 'Start whole-paper verification' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
    fireEvent.click(screen.getByRole('checkbox')); expect(button.disabled).toBe(false)
  })
  it.each(['failed', 'completed'])('does not start a job with zero valid pairs (%s extraction)', async status => {
    services.extract.mockResolvedValue({ ...fixture.job_request.extraction, status, claims: [] })
    app(); await screen.findByText(/PDF limit/)
    fireEvent.change(screen.getByLabelText('Manuscript PDF'), { target: { files: [new File(['%PDF'], 'paper.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Parse manuscript' })); await resolveAndReview()
    fireEvent.click(screen.getByRole('button', { name: 'Extract claims' })); await screen.findByText('Review extracted claims')
    expect((screen.getByRole('button', { name: 'Start whole-paper verification' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText(/No executable pairs/)).toBeTruthy(); expect(services.create).not.toHaveBeenCalled()
  })
  it('restores a saved job URL without parse/extract/create', async () => {
    app(`/app/manuscripts/jobs/${jobId}`); await screen.findByText('Verification overview')
    expect(services.get).toHaveBeenCalledWith(jobId, expect.anything())
    expect(services.parse).not.toHaveBeenCalled(); expect(services.extract).not.toHaveBeenCalled(); expect(services.create).not.toHaveBeenCalled()
  })
  it('shares the enriched input through extraction and job creation with partial resolution gaps', async () => {
    const enriched = structuredClone(fixture.parse_response) as ParseResponse
    const original = enriched.parsed.references[0]
    original.resolution = resolution('resolved', { reference_id: original.id, original_doi: original.doi, resolved_doi: original.doi, provider: 'original', source_type: 'doi', match_reason: 'ORIGINAL_DOI_PRESERVED' })
    const found = enriched.parsed.references[1]
    found.doi = '10.1234/enriched'
    found.resolution = resolution('resolved', { reference_id: found.id, resolved_doi: found.doi, provider: 'crossref', source_type: 'doi', match_reason: 'IDENTITY_MATCHED' })
    enriched.parsed.references.push(
      { ...found, id: 'r-ambiguous', title: 'Ambiguous reference', doi: null, resolution: resolution('ambiguous', { reference_id: 'r-ambiguous', match_reason: 'MULTIPLE_IDENTITIES' }) },
      { ...found, id: 'r-url', title: 'WHO speech', doi: null, resolution: resolution('non_doi_source', { reference_id: 'r-url', source_type: 'url', source_url: 'https://www.who.int/speech', diagnostics: ['DISCOVERED_ONLY'] }) },
      { ...found, id: 'r-provider-error', title: 'Provider unavailable', doi: null, resolution: resolution('provider_error', { reference_id: 'r-provider-error', diagnostics: ['OPENALEX_RATE_LIMIT'] }) },
    )
    services.resolve.mockResolvedValue(enriched)
    app(); await screen.findByText(/PDF limit/)
    fireEvent.change(screen.getByLabelText('Manuscript PDF'), { target: { files: [new File(['%PDF'], 'paper.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Parse manuscript' })); await resolveAndReview()
    expect(screen.getByText(/2 DOI identities ready/)).toBeTruthy()
    expect(screen.getByText('ambiguous')).toBeTruthy(); expect(screen.getByText('provider_error')).toBeTruthy()
    expect(screen.getByText(/Discovered only/)).toBeTruthy(); expect(screen.getByText(/OPENALEX_RATE_LIMIT/)).toBeTruthy()
    expect(screen.getByText(/Resolved DOI: 10.1234\/enriched/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Extract claims' })); await screen.findByText('Review extracted claims')
    expect(services.extract).toHaveBeenCalledWith(enriched)
    fireEvent.click(screen.getByRole('button', { name: 'Start whole-paper verification' })); await screen.findByText('Verification overview')
    const submitted = services.create.mock.calls[0][0]
    expect(submitted.parsed.references).toEqual(enriched.parsed.references)
    expect(submitted.extraction.metadata.input_fingerprint).toBe(fixture.job_request.extraction.metadata.input_fingerprint)
    expect(submitted.parsed.references[0].doi).toBe(original.doi)
  })
  it('prevents duplicate resolution and requires a fresh review after reparsing', async () => {
    let finish!: (result: unknown) => void
    services.resolve.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    app(); await screen.findByText(/PDF limit/)
    fireEvent.change(screen.getByLabelText('Manuscript PDF'), { target: { files: [new File(['%PDF'], 'paper.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Parse manuscript' })); await screen.findByRole('button', { name: 'Resolve references' })
    const button = screen.getByRole('button', { name: 'Resolve references' })
    fireEvent.click(button); fireEvent.click(button)
    expect(services.resolve).toHaveBeenCalledTimes(1)
    finish(fixture.parse_response); await screen.findByRole('button', { name: 'Continue with reviewed references' })
    fireEvent.click(screen.getByRole('button', { name: 'Continue with reviewed references' }))
    fireEvent.click(screen.getByRole('button', { name: 'Extract claims' })); await screen.findByText('Review extracted claims')
    fireEvent.click(screen.getByRole('button', { name: 'Parse manuscript' }))
    await waitFor(() => expect(screen.queryByText('Review extracted claims')).toBeNull())
    expect(screen.queryByRole('button', { name: 'Extract claims' })).toBeNull()
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
  it('explains missing DOI as an unresolved identity rather than an incorrect claim', () => {
    const job = jobFixture(); job.tasks[0].state = 'failed'; job.tasks[0].reason_code = 'DOI_MISSING'
    render(<WholePaperReport job={job} />)
    expect(screen.getByText(/does not mean the claim is incorrect/)).toBeTruthy()
    expect(screen.queryByText('Contradicted')).toBeNull()
  })
  it('explains URL-only retrieval limitations in a durable job report', () => {
    const job = jobFixture(); const task = job.tasks[0]; task.state = 'failed'; task.reason_code = 'DOI_MISSING'
    const ref = job.references.find(r => r.id === task.reference_id)!
    ref.doi = null; ref.resolution = resolution('non_doi_source', { reference_id: ref.id, source_type: 'url', source_url: 'https://www.who.int/speech' })
    render(<WholePaperReport job={job} />)
    expect(screen.getByText(/URL evidence retrieval is not supported/)).toBeTruthy()
    expect(screen.getByText('Reference identity diagnostics')).toBeTruthy()
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
