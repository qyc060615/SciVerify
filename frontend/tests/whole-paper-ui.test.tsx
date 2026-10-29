import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import WholePaperVerifyPage from '@/pages/WholePaperVerifyPage'
import WholePaperJobPage from '@/pages/WholePaperJobPage'
import { WholePaperReport } from '@/components/manuscript/WholePaperReport'
import { ClaimExtractionPreview } from '@/components/manuscript/ClaimExtractionPreview'
import { WholePaperRoute } from '@/routes/WholePaperRoute'
import { ApiResponseError } from '@/services/api'
import { prepareReferenceSource } from '@/services/sourceService'
import { jobFixture, jobId } from './fixtures/job'
import fixture from './fixtures/manuscript.json'
import type { ExtractionResult, ParseResponse, ReferenceResolution } from '@/types/manuscript'

const services = vi.hoisted(() => ({ parse: vi.fn(), resolve: vi.fn(), extract: vi.fn(), limits: vi.fn(), create: vi.fn(), get: vi.fn(), resume: vi.fn(), demo: vi.fn() }))
vi.mock('@/services/manuscriptService', async importOriginal => ({ ...await importOriginal<object>(), parseManuscript: services.parse, resolveReferences: services.resolve, extractClaims: services.extract, getUploadLimits: services.limits }))
vi.mock('@/services/verificationJobService', async importOriginal => ({ ...await importOriginal<object>(), createVerificationJob: services.create, getVerificationJob: services.get, resumeVerificationJob: services.resume }))
vi.mock('@/services/sourceService', async original => ({ ...await original<object>(), checkReferenceSource: vi.fn().mockResolvedValue({ state: 'not_cached', reason_code: 'SOURCE_NOT_CACHED', raw_content_sha256: null, format: null }), prepareReferenceSource: vi.fn().mockResolvedValue({ state: 'unavailable', reason_code: 'SOURCE_FULL_TEXT_UNAVAILABLE', retryable: true, raw_content_sha256: null, format: null }) }))
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
  await screen.findByRole('button', { name: 'Continue to Claims' })
  expect(screen.queryByRole('button', { name: 'Extract claims' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Claims' }))
  await screen.findByRole('button', { name: 'Extract claims' })
}

function renderReport(job: ReturnType<typeof jobFixture>) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}><WholePaperReport job={job} /></QueryClientProvider>)
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
    await screen.findByText('Review Claims')
    expect(services.extract).toHaveBeenCalledWith(fixture.parse_response)
    fireEvent.click(screen.getByRole('button', { name: 'Continue to Verification' }))
    expect(screen.queryByText(/may call external LLM/)).toBeNull()
    const start = screen.getByRole('button', { name: 'Start Verification' })
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
    fireEvent.click(screen.getByRole('button', { name: 'Extract claims' })); await screen.findByText('Review Claims')
    fireEvent.click(screen.getByRole('button', { name: 'Continue to Verification' }))
    const button = screen.getByRole('button', { name: 'Start Verification' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
    fireEvent.click(screen.getByRole('checkbox')); expect(button.disabled).toBe(false)
  })
  it.each(['failed', 'completed'])('does not start a job with zero valid pairs (%s extraction)', async status => {
    services.extract.mockResolvedValue({ ...fixture.job_request.extraction, status, claims: [] })
    app(); await screen.findByText(/PDF limit/)
    fireEvent.change(screen.getByLabelText('Manuscript PDF'), { target: { files: [new File(['%PDF'], 'paper.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Parse manuscript' })); await resolveAndReview()
    fireEvent.click(screen.getByRole('button', { name: 'Extract claims' })); await screen.findByText('Review Claims')
    expect((screen.getByRole('button', { name: 'Continue to Verification' }) as HTMLButtonElement).disabled).toBe(true)
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
    fireEvent.click(screen.getByRole('button', { name: /^References/ }))
    expect(screen.getByText('5 References · 0 available · 5 missing')).toBeTruthy()
    expect(screen.getByText('Identity status: ambiguous')).toBeTruthy(); expect(screen.getByText('Identity status: provider_error')).toBeTruthy()
    expect(screen.getByText(/will attempt document retrieval and identity checks/)).toBeTruthy(); expect(screen.getAllByText(/OPENALEX_RATE_LIMIT/)[0]).toBeTruthy()
    expect(screen.getByText(/Resolved DOI: 10.1234\/enriched/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Continue to Claims' }))
    fireEvent.click(screen.getByRole('button', { name: 'Extract claims' })); await screen.findByText('Review Claims')
    expect(services.extract).toHaveBeenCalledWith(enriched)
    fireEvent.click(screen.getByRole('button', { name: 'Continue to Verification' }))
    fireEvent.click(screen.getByRole('button', { name: 'Start Verification' })); await screen.findByText('Verification overview')
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
    fireEvent.click(screen.getByRole('button', { name: 'Parse manuscript' })); await screen.findByRole('button', { name: /Resolve references/ })
    const button = screen.getByRole('button', { name: /Resolve references/ })
    expect(button).toHaveProperty('disabled', true)
    fireEvent.click(button); fireEvent.click(button)
    expect(services.resolve).toHaveBeenCalledTimes(1)
    finish(fixture.parse_response); await screen.findByRole('button', { name: 'Continue to Claims' })
    fireEvent.click(screen.getByRole('button', { name: 'Continue to Claims' }))
    fireEvent.click(screen.getByRole('button', { name: 'Extract claims' })); await screen.findByText('Review Claims')
    fireEvent.click(screen.getByRole('button', { name: 'Replace PDF' }))
    fireEvent.change(screen.getByLabelText('Manuscript PDF'), { target: { files: [new File(['%PDF'], 'replacement.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Parse manuscript' }))
    await screen.findByRole('button', { name: 'Continue to Claims' })
    await waitFor(() => expect(screen.queryByText('Review Claims')).toBeNull())
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
    renderReport(jobFixture())
    expect(screen.getAllByTestId('pair-card')).toHaveLength(2)
    expect(screen.getAllByText(/^(R\d+: )?Contradicted$/)[0]).toBeTruthy()
    expect(screen.getByText(/Identity: uncertain/)).toBeTruthy()
    expect(screen.getAllByText(/Confidence:/)).toHaveLength(1)
    expect(screen.queryByText(/FABRICATED/)).toBeNull()
    expect((screen.getByRole('progressbar') as HTMLProgressElement).max).toBe(2)
  })
  it('does not expose a semantic verdict or confidence for failed processing', () => {
    const job = jobFixture(); job.tasks[0].state = 'failed'
    renderReport(job)
    expect(screen.queryAllByText(/^(R\d+: )?Contradicted$/)).toHaveLength(0); expect(screen.queryByText(/Confidence:/)).toBeNull()
    expect(within(screen.getAllByTestId('pair-card')[0]).getByText(/No scientific verdict was produced/)).toBeTruthy()
  })
  it('explains missing DOI as an unresolved identity rather than an incorrect claim', () => {
    const job = jobFixture(); job.tasks[0].state = 'failed'; job.tasks[0].reason_code = 'DOI_MISSING'
    renderReport(job)
    expect(within(screen.getAllByTestId('pair-card')[0]).getByText(/does not mean the claim is incorrect/)).toBeTruthy()
    expect(screen.queryAllByText(/^(R\d+: )?Contradicted$/)).toHaveLength(0)
  })
  it('explains URL-only retrieval limitations in a durable job report', async () => {
    const job = jobFixture(); const task = job.tasks[0]; task.state = 'failed'; task.reason_code = 'DOI_MISSING'
    const ref = job.references.find(r => r.id === task.reference_id)!
    ref.doi = null; ref.resolution = resolution('non_doi_source', { reference_id: ref.id, source_type: 'url', source_url: 'https://www.who.int/speech' })
    renderReport(job)
    expect(screen.getByText(/unresolved in this saved job/)).toBeTruthy()
    fireEvent.click(screen.getByText('Technical Details & Diagnostics'))
    fireEvent.click(screen.getByText('References & identity diagnostics'))
    expect(await screen.findByText(/will attempt document retrieval and identity checks/)).toBeTruthy()
    expect(screen.getByText('References & identity diagnostics')).toBeTruthy()
  })
  it('shows zero pairs and extraction coverage gaps without fake completion', () => {
    const job = jobFixture(); job.tasks = []; job.coverage.total_pairs = 0; job.coverage.skipped_extraction_contexts = 1
    renderReport(job)
    expect(screen.queryByRole('progressbar')).toBeNull(); expect(screen.getByText(/Completion percentage is not applicable/)).toBeTruthy()
    expect(screen.getByText(/1 skipped contexts/)).toBeTruthy()
  })
  it('keeps probable identity and historical version warnings visible beside a verdict', () => {
    const job = jobFixture()
    job.tasks[0].source_binding!.locator = { kind: 'doi', value: '10.1234/local' }
    job.tasks[0].source_binding!.provenance = { identity: 'PROBABLE_SAME_WORK', document_kind: 'ARTICLE_FULL_TEXT', warnings: ['HISTORICAL_VERSION_UNCONFIRMED'], match_evidence: ['AUTHORS_MATCH'], retrieved_title: 'Retrieved manuscript version', final_url: 'https://example.org/manuscript', retrieved_version: 'sha256:' + 'b'.repeat(64) }
    renderReport(job)
    expect(screen.getByText(/Identity: Probable Same Work/)).toBeTruthy()
    expect(screen.getByText(/not an exact identity match/)).toBeTruthy()
    expect(screen.getByText(/current content may differ/)).toBeTruthy()
    expect(screen.getByText(/Retrieved title: Retrieved manuscript version/)).toBeTruthy()
    expect(screen.getAllByText(/^(R\d+: )?Contradicted$/)[0]).toBeTruthy()
  })
  it('keeps runtime diagnostics separate from scientific verdicts', async () => {
    const job = jobFixture(); job.runtime_error_code = 'JOB_STORAGE_ERROR'
    renderReport(job)
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Committed results remain visible'))
    expect(screen.getAllByText(/^(R\d+: )?Contradicted$/)[0]).toBeTruthy()
  })
})


it('step navigation never bypasses reference review, extraction or job creation', async () => {
  app(); await screen.findByText(/PDF limit/)
  expect(screen.getByRole('button', { name: 'Claims', exact: true })).toHaveProperty('disabled', true)
  expect(screen.getByRole('button', { name: 'Verification', exact: true })).toHaveProperty('disabled', true)
  expect(screen.getByRole('button', { name: 'Report', exact: true })).toHaveProperty('disabled', true)
  fireEvent.change(screen.getByLabelText('Manuscript PDF'), { target: { files: [new File(['%PDF'], 'fresh.pdf')] } })
  fireEvent.click(screen.getByRole('button', { name: 'Parse manuscript' }))
  await screen.findByRole('heading', { name: 'Review References' })
  expect(screen.queryByLabelText('Manuscript PDF')).toBeNull()
  await screen.findByRole('button', { name: 'Continue to Claims' })
  expect(screen.getByRole('button', { name: 'Claims', exact: true })).toHaveProperty('disabled', true)
  expect(services.extract).not.toHaveBeenCalled(); expect(services.create).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Replace PDF' }))
  expect(screen.getByLabelText('Manuscript PDF')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'References', exact: true })).toHaveProperty('disabled', true)
})

it('ambiguous claims remain non-executable through review and stage navigation', async () => {
  const result = structuredClone(fixture.job_request.extraction)
  result.status = 'partial'
  result.claims.push({ ...result.claims[0], id: 'ambiguous-claim', text: 'A separate uncertain attribution.', attribution_status: 'ambiguous' })
  services.extract.mockResolvedValue(result)
  app(); await screen.findByText(/PDF limit/)
  fireEvent.change(screen.getByLabelText('Manuscript PDF'), { target: { files: [new File(['%PDF'], 'paper.pdf')] } })
  fireEvent.click(screen.getByRole('button', { name: 'Parse manuscript' })); await resolveAndReview()
  fireEvent.click(screen.getByRole('button', { name: 'Extract claims' }))
  await screen.findByRole('status', { name: 'Needs Attention' })
  fireEvent.click(screen.getByRole('button', { name: 'Continue to Verification' }))
  expect(screen.getByText('2 Claim–Reference pairs ready')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Start Verification' })).toHaveProperty('disabled', true)
  expect(services.create).not.toHaveBeenCalled()
})

it('report shows all claims in order and retains independent pair verdicts', () => {
  const job = structuredClone(jobFixture())
  const next = { ...job.claims[0], id: 'another-claim', text: 'Another claim to inspect separately.', reference_ids: [job.tasks[0].reference_id] }
  job.claims.push(next)
  job.tasks.push({ ...job.tasks[0], task_key: 'another-task', claim_id: next.id, pair_outcome: { ...job.tasks[0].pair_outcome!, verification: { ...job.tasks[0].pair_outcome!.verification, claim_id: next.id, verdict: 'INSUFFICIENT', confidence: null } } })
  renderReport(job)
  const cards = screen.getAllByTestId('claim-result')
  expect(cards).toHaveLength(2)
  expect(screen.queryByRole('navigation', { name: 'Claim navigator' })).toBeNull()
  expect(within(cards[0]).getByLabelText('Pair verdicts').textContent).toContain('R1: Contradicted')
  expect(within(cards[0]).getByLabelText('Pair verdicts').textContent).toContain('R2: Source Required')
  expect(within(cards[1]).getByLabelText('Pair verdicts').textContent).toBe('Insufficient evidence')
  expect(within(cards[0]).getByText('More details').closest('details')?.open).toBe(false)
  expect(within(cards[1]).getByText(next.text)).toBeTruthy()
  expect(within(cards[0]).getByText(job.tasks[0].pair_outcome!.verification.explanation!).closest('details')).toBeTruthy()
  expect(within(cards[1]).getAllByText(job.tasks[2].pair_outcome!.verification.explanation!)[0].closest('details')).toBeNull()
})

it('a saved report can revisit preparation without rerunning extraction or creating jobs', async () => {
  app('/app/manuscripts/jobs/' + jobId)
  await screen.findByText('Verification overview')
  fireEvent.click(screen.getByRole('button', { name: /^Claims/ }))
  expect(screen.getByText('Saved claims')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: /^Verification — completed/ }))
  expect(screen.getByText('Verification task created')).toBeTruthy()
  expect(services.create).not.toHaveBeenCalled(); expect(services.extract).not.toHaveBeenCalled()
})


it.each([null, NaN, Infinity, -0.1, 1.1])('never displays invalid confidence %s', confidence => {
  const job = structuredClone(jobFixture())
  job.tasks[0].pair_outcome!.verification.confidence = confidence
  renderReport(job)
  expect(screen.queryByText(/Confidence:/)).toBeNull()
  expect(screen.getAllByText(/^(R\d+: )?Contradicted$/)[0]).toBeTruthy()
})

it('claim review keeps input order, uses two visual states and folds diagnostics at the bottom', () => {
  const extraction = structuredClone(fixture.job_request.extraction) as ExtractionResult
  extraction.claims = [
    { ...extraction.claims[0], id: 'first', text: 'First claim in extraction order.', attribution_status: 'ambiguous' },
    { ...extraction.claims[0], id: 'second', text: 'Second claim in extraction order.', attribution_status: 'resolved' },
    { ...extraction.claims[0], id: 'third', text: 'Third claim in extraction order.', attribution_status: 'unresolved' },
  ]
  extraction.diagnostics = [{ code: 'TEST_ATTRIBUTION', severity: 'warning', safe_message: 'Review citation attribution.', entity_id: 'first' }]
  render(<ClaimExtractionPreview parsed={fixture.parse_response.parsed as ParseResponse['parsed']} extraction={extraction} />)
  expect(screen.getByText('3 Claims · 1 Resolved · 2 Need Attention')).toBeTruthy()
  const list = screen.getByLabelText('Claim review list')
  const rows = Array.from(list.querySelectorAll('article'))
  expect(rows.map(row => row.querySelector('p')!.textContent)).toEqual(extraction.claims.map(claim => claim.text))
  expect(screen.getAllByRole('status', { name: 'Needs Attention' })).toHaveLength(2)
  expect(screen.getAllByRole('status', { name: 'Citation Attributed' })).toHaveLength(1)
  expect(rows.every(row => !row.querySelector('details')!.open)).toBe(true)
  const diagnostics = screen.getByText('Extraction Diagnostics (1)').closest('details')!
  expect(diagnostics.open).toBe(false)
  expect(list.compareDocumentPosition(diagnostics) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(document.querySelector('[class*="overflow-y-auto"]')).toBeNull()
})

it.each([
  ['pending', 'Not Verified'], ['running', 'Processing'], ['blocked_source', 'Source Required'], ['failed', 'Processing Failed'],
] as const)('shows %s as a processing state without a stale scientific verdict', (state, label) => {
  const job = structuredClone(jobFixture())
  job.tasks = [{ ...job.tasks[0], state }]
  job.claims[0].reference_ids = [job.tasks[0].reference_id]
  renderReport(job)
  const card = screen.getByTestId('claim-result')
  expect(within(card).getByLabelText('Pair verdicts').textContent).toBe(label)
  expect(within(card).queryByText(/Confidence:/)).toBeNull()
  expect(within(card).queryByText('The cited findings contradict this claim.')).toBeNull()
  expect(screen.queryAllByText(/Contradicted/)).toHaveLength(0)
})

it('does not show a scientific verdict when task and result completion disagree', () => {
  const job = structuredClone(jobFixture())
  job.tasks = [job.tasks[0]]
  job.claims[0].reference_ids = [job.tasks[0].reference_id]
  job.tasks[0].pair_outcome!.verification.processing_status = 'failed'
  renderReport(job)
  expect(screen.getByLabelText('Pair verdicts').textContent).toBe('Not Verified')
  expect(screen.queryByText(/Confidence:/)).toBeNull()
})

it('many reference results use a neutral count and keep all independent explanations in details', () => {
  const job = structuredClone(jobFixture())
  job.tasks = Array.from({ length: 4 }, (_, i) => ({ ...job.tasks[0], task_key: 'pair-' + i }))
  renderReport(job)
  expect(screen.getByLabelText('Pair verdicts').textContent).toBe('4 reference results')
  const card = screen.getByTestId('claim-result')
  expect(within(card).getAllByText('The cited findings contradict this claim.')).toHaveLength(4)
  expect(within(card).getAllByText('The cited findings contradict this claim.').every(node => !!node.closest('details'))).toBe(true)
  expect(document.querySelector('[class*="overflow-y-auto"]')).toBeNull()
})

it('a claim without actual tasks stays in folded coverage and outside the report body', () => {
  const job = structuredClone(jobFixture())
  job.tasks = []; job.claims[0].attribution_status = 'ambiguous'
  renderReport(job)
  expect(screen.queryByTestId('claim-result')).toBeNull()
  expect(screen.queryByText('Needs Attention')).toBeNull()
  expect(screen.getByText('1 claims excluded from verification')).toBeTruthy()
  expect(screen.getByText('Attribution: ambiguous').closest('details')?.open).toBe(false)
  expect(screen.queryByText(/Confidence:/)).toBeNull()
})

it('report recovery opens the matching reference above claims without executing resume', async () => {
  const job = structuredClone(jobFixture())
  job.references = job.references.map(ref => ref.id === 'r4' ? { ...ref, doi: '10.1234/recover' } : ref)
  services.get.mockResolvedValue(job)
  app('/app/manuscripts/jobs/' + jobId)
  await screen.findByText('Verification overview')
  const recovery = screen.getByText('Source recovery').closest('details')!
  expect(recovery.open).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: 'Recover R2' }))
  expect(recovery.open).toBe(true)
  expect(screen.getByLabelText('Source PDF for 10.1234/recover')).toBeTruthy()
  expect(recovery.compareDocumentPosition(screen.getByTestId('claim-result')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(services.resume).not.toHaveBeenCalled()
})

it('a completed report without eligible issues has no recovery module', async () => {
  const job = structuredClone(jobFixture())
  job.status = 'completed'; job.tasks = [job.tasks[0]]
  services.get.mockResolvedValue(job)
  app('/app/manuscripts/jobs/' + jobId)
  await screen.findByText('Verification overview')
  expect(screen.queryByText('Source recovery')).toBeNull()
  expect(screen.queryByRole('button', { name: /Recover R/ })).toBeNull()
})

it('one executable pair does not become a claim-wide opinion for a multi-reference claim', () => {
  const job = structuredClone(jobFixture())
  job.tasks = [job.tasks[0]]
  renderReport(job)
  expect(screen.getByLabelText('Pair verdicts').textContent).toBe('R1: Contradicted')
  expect(screen.getByText('The cited findings contradict this claim.').closest('details')).toBeTruthy()
})

it('no scientific verdict also means no displayed confidence', () => {
  const job = structuredClone(jobFixture())
  job.tasks[0].pair_outcome!.verification.verdict = null
  renderReport(job)
  expect(screen.queryByText(/Confidence:/)).toBeNull()
})

it('allows continuing to Claims while a source is unfinished and cancels its UI request', async () => {
  let pending: AbortSignal | undefined
  vi.mocked(prepareReferenceSource).mockImplementationOnce((_reference, signal) => {
    pending = signal
    return new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(signal.reason)))
  })
  app(); await screen.findByText(/PDF limit/)
  fireEvent.change(screen.getByLabelText('Manuscript PDF'), { target: { files: [new File(['%PDF'], 'pending.pdf')] } })
  fireEvent.click(screen.getByRole('button', { name: 'Parse manuscript' }))
  const next = await screen.findByRole('button', { name: 'Continue to Claims' })
  await screen.findByRole('status', { name: 'Preparing full text' })
  expect(next).toHaveProperty('disabled', false)
  fireEvent.click(next)
  await screen.findByRole('button', { name: 'Extract claims' })
  expect(pending?.aborted).toBe(true)
  expect(services.create).not.toHaveBeenCalled()
})


it('uses actual tasks, preserves extraction order and original numbers even with mixed attribution', () => {
  const job = structuredClone(jobFixture())
  const original = job.claims[0]
  job.claims = [
    { ...original, id: 'excluded-first', text: 'No task despite resolved attribution.', attribution_status: 'resolved' },
    { ...original, id: 'has-pair', text: 'Ambiguous claim with a real planned pair.', attribution_status: 'ambiguous' },
    { ...original, id: 'excluded-last', text: 'Unresolved and excluded.', attribution_status: 'unresolved' },
    { ...original, id: 'has-pending', text: 'Pending claim still belongs in report.' },
  ]
  job.tasks = [
    { ...job.tasks[1], claim_id: 'has-pair', state: 'blocked_source' },
    { ...job.tasks[0], claim_id: 'has-pending', state: 'pending' },
  ]
  renderReport(job)
  const cards = screen.getAllByTestId('claim-result')
  expect(cards).toHaveLength(2)
  expect(cards[0].textContent).toContain('Claim 02')
  expect(cards[0].textContent).toContain('Ambiguous claim with a real planned pair.')
  expect(cards[1].textContent).toContain('Claim 04')
  expect(cards[1].textContent).toContain('Pending claim still belongs in report.')
  expect(screen.getByText('2 claims excluded from verification')).toBeTruthy()
  expect(screen.getByText('2 claims · 1/2 pairs processed')).toBeTruthy()
  expect(screen.queryByText('Needs Attention')).toBeNull()
  expect(screen.getByText(/No task despite resolved attribution/).closest('details')?.open).toBe(false)
})
