import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReferenceReview } from '@/components/manuscript/ReferenceReview'
import fixture from './fixtures/manuscript.json'
import { apiClient } from '@/services/api'
import type { Reference } from '@/types/manuscript'
const actions = vi.hoisted(() => ({ status: vi.fn(), prepare: vi.fn(), upload: vi.fn(), limits: vi.fn() }))
vi.mock('@/services/sourceService', async original => ({ ...await original<object>(), checkReferenceSource: actions.status, prepareReferenceSource: actions.prepare }))
vi.mock('@/services/verificationService', () => ({ uploadManualSource: actions.upload }))
vi.mock('@/services/manuscriptService', async original => ({ ...await original<object>(), getUploadLimits: actions.limits }))
const hash = 'e'.repeat(64)
const absent = { reference_id: 'r3', state: 'not_cached', reason_code: 'SOURCE_NOT_CACHED', retryable: true, retrieval_status: null, source: null, raw_content_sha256: null, format: null }
const missing = { ...absent, state: 'unavailable', reason_code: 'SOURCE_FULL_TEXT_UNAVAILABLE' }
const available = { ...absent, state: 'available', raw_content_sha256: hash, format: 'pdf' }
function mount(reference = fixture.parse_response.parsed.references[0] as Reference, automatic = true, onClick?: () => void) {
  render(<div onClick={onClick}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}><ReferenceReview references={[reference]} allowSources={automatic} /></QueryClientProvider></div>)
}
beforeEach(() => { vi.clearAllMocks(); actions.status.mockResolvedValue(absent); actions.prepare.mockResolvedValue(missing); actions.limits.mockResolvedValue({ manuscript_max_bytes: 1000, source_max_bytes: 1000 }) })
afterEach(cleanup)

it('unknown remote full text is not mislabeled missing or available', async () => {
  mount(undefined, false)
  await screen.findByText('Full text: Not checked')
  expect(screen.queryByText(/Full text: Available/)).toBeNull()
  expect(screen.queryByRole('button', { name: 'Upload file' })).toBeNull()
  fireEvent.click(screen.getByText('More details'))
  expect(screen.queryByRole('button', { name: 'Add Source' })).toBeNull()
  expect(actions.prepare).not.toHaveBeenCalled()
})

it('verified existing files hide the upload action and expose their actual hash', async () => {
  actions.prepare.mockResolvedValue(available)
  mount(); await screen.findByText('Full text: Available locally (PDF)')
  expect(screen.queryByRole('button', { name: 'Add Source' })).toBeNull()
  expect(screen.queryByRole('button', { name: 'Upload file' })).toBeNull()
  expect(screen.getByText('SHA-256: ' + hash)).toBeTruthy()
})

it('preuploads against the exact DOI and confirms real cache status before success', async () => {
  const ref = fixture.parse_response.parsed.references[0] as Reference
  let saved = false
  actions.status.mockImplementation(async () => saved ? available : absent)
  actions.upload.mockImplementation(async () => { saved = true; return { status: 'accepted', doi: ref.doi, raw_content_sha256: hash, identity_match: 'doi' } })
  const localStorageWrite = vi.spyOn(Storage.prototype, 'setItem')
  mount(); await screen.findByText('Full text: Unavailable')
  fireEvent.click(screen.getByRole('button', { name: 'Upload file' }))
  const pdf = new File(['%PDF'], 'reference.pdf', { type: 'application/pdf' })
  fireEvent.change(await screen.findByLabelText('Source PDF for ' + ref.doi), { target: { files: [pdf] } })
  await screen.findByText(/PDF saved and verified/)
  expect(actions.upload).toHaveBeenCalledWith(ref.doi, pdf)
  expect(actions.status).toHaveBeenCalledTimes(1)
  expect(screen.getByText('Full text: Available locally (PDF)')).toBeTruthy()
  expect(localStorageWrite).not.toHaveBeenCalled()
  localStorageWrite.mockRestore()
})

it('an accepted receipt without a confirmed file never becomes an available source', async () => {
  const ref = fixture.parse_response.parsed.references[0] as Reference
  actions.upload.mockResolvedValue({ status: 'accepted', doi: ref.doi, raw_content_sha256: hash })
  mount(); await screen.findByText('Full text: Unavailable')
  fireEvent.click(screen.getByRole('button', { name: 'Upload file' }))
  fireEvent.change(await screen.findByLabelText('Source PDF for ' + ref.doi), { target: { files: [new File(['%PDF'], 'ref.pdf')] } })
  await screen.findByText(/saved file could not be confirmed/)
  expect(screen.queryByText(/Full text: Available/)).toBeNull()
})

it('URL-only references explain the manual-upload limit rather than fabricating DOI bindings', async () => {
  mount({ ...fixture.parse_response.parsed.references[0], doi: null, url: 'https://example.org/paper' } as Reference)
  await screen.findByText('Full text: Unavailable')
  fireEvent.click(screen.getByText('More details'))
  expect(screen.getByText(/A reliable DOI or a sufficiently specific/)).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Add Source' })).toBeNull()
})

it('shows compact unknown availability without inferring success from a DOI', async () => {
  mount(undefined, false)
  await screen.findByRole('status', { name: 'Full text not checked' })
  expect(screen.getByText('1 References · 0 available · 0 missing')).toBeTruthy()
  const details = screen.getByText('More details').closest('details')!
  expect(details.open).toBe(false)
  expect(within(details).getByText(/^DOI:/)).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Add Source' })).toBeNull()
  expect(screen.queryByRole('status', { name: 'Full text available' })).toBeNull()
  expect(document.querySelector('[class*="overflow-y-auto"]')).toBeNull()
})

it('counts availability only after the local file check finishes', async () => {
  let finish!: (value: typeof available) => void
  actions.prepare.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  mount()
  expect(screen.getByRole('status', { name: 'Preparing full text' })).toBeTruthy()
  expect(screen.getByText('1 References · 0 available · 0 missing · 1 preparing')).toBeTruthy()
  finish(available)
  await screen.findByRole('status', { name: 'Full text available' })
  expect(screen.getByText('1 References · 1 available · 0 missing')).toBeTruthy()
})

it('a failed preparation has a direct retry and does not invent available full text', async () => {
  actions.prepare.mockResolvedValueOnce({ ...missing, state: 'failed' }).mockResolvedValue(available)
  mount()
  await screen.findByRole('status', { name: 'Full text unavailable' })
  expect(screen.getByRole('button', { name: 'Upload file' }).closest('details')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  await screen.findByRole('status', { name: 'Full text available' })
  expect(actions.prepare).toHaveBeenCalledTimes(2)
})

it('returning to completed reference review does not automatically prepare or download again', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const reference = fixture.parse_response.parsed.references[0] as Reference
  actions.prepare.mockResolvedValue(available)
  const view = (show: boolean) => <QueryClientProvider client={client}>{show && <ReferenceReview references={[reference]} allowSources />}</QueryClientProvider>
  const mounted = render(view(true))
  await screen.findByRole('status', { name: 'Full text available' })
  mounted.rerender(view(false)); mounted.rerender(view(true))
  await screen.findByRole('status', { name: 'Full text available' })
  expect(actions.prepare).toHaveBeenCalledTimes(1)
})

it('unmounting consumes the preparation cancellation signal', async () => {
  let signal: AbortSignal | undefined
  actions.prepare.mockImplementation((_ref, currentSignal: AbortSignal) => {
    signal = currentSignal
    return new Promise((_resolve, reject) => currentSignal.addEventListener('abort', () => reject(currentSignal.reason)))
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  const reference = fixture.parse_response.parsed.references[0] as Reference
  const mounted = render(<QueryClientProvider client={client}><ReferenceReview references={[reference]} allowSources /></QueryClientProvider>)
  await screen.findByRole('status', { name: 'Preparing full text' })
  mounted.unmount()
  expect(signal?.aborted).toBe(true)
})

it('an uploaded DOI source refreshes its other reference aliases without retrying unrelated papers', async () => {
  const reference = fixture.parse_response.parsed.references[0] as Reference
  const references = [reference, { ...reference, id: 'same-doi' }, { ...reference, id: 'other-doi', doi: '10.1234/other' }]
  let saved = false
  actions.prepare.mockImplementation(async (ref: Reference) => ({ ...(saved && ref.doi === reference.doi ? available : missing), reference_id: ref.id }))
  actions.status.mockResolvedValue(available)
  actions.upload.mockImplementation(async () => { saved = true; return { status: 'accepted', doi: reference.doi, raw_content_sha256: hash } })
  render(<QueryClientProvider client={new QueryClient()}><ReferenceReview references={references} allowSources /></QueryClientProvider>)
  await waitFor(() => expect(screen.getAllByRole('status', { name: 'Full text unavailable' })).toHaveLength(3))
  fireEvent.click(screen.getAllByRole('button', { name: 'Upload file' })[0])
  fireEvent.change(screen.getAllByLabelText('Source PDF for ' + reference.doi)[0], { target: { files: [new File(['%PDF'], 'source.pdf')] } })
  await waitFor(() => expect(screen.getAllByRole('status', { name: 'Full text available' })).toHaveLength(2))
  expect(actions.prepare.mock.calls.filter(([ref]) => ref.id === 'other-doi')).toHaveLength(1)
})


it('obtained uncertain full text stays visible in yellow with its hash and complete source links', async () => {
  const url = 'https://example.org/paper.pdf?version=preprint&download=complete'
  actions.prepare.mockResolvedValue({ ...available, identity: 'UNCERTAIN', source: { provider: 'fixture', identity_status: 'uncertain', provenance: { warnings: ['VERSION_DATE_DIFFERS'] } }, candidates: [{ url, state: 'accepted', attempted: true }] })
  mount()
  const status = await screen.findByRole('status', { name: 'Full text acquired, identity pending' })
  expect(status.className).toContain('text-warning')
  expect(screen.getByText('SHA-256: ' + hash)).toBeTruthy()
  fireEvent.click(screen.getByText('More details'))
  expect(screen.getByRole('link', { name: url }).getAttribute('href')).toBe(url)
  expect(screen.getByText('VERSION_DATE_DIFFERS')).toBeTruthy()
  expect(screen.queryByRole('status', { name: 'Full text unavailable' })).toBeNull()
})

it('exhausted candidates retain reasons and links while explicit conflicts are red', async () => {
  const url = 'https://example.org/conflict.pdf'
  actions.prepare.mockResolvedValue({ ...missing, state: 'needs_attention', identity: 'CONFLICT', candidates: [{ url, state: 'conflict', reason: 'ARTICLE_DOI_CONFLICT', attempted: true }] })
  mount()
  const status = await screen.findByRole('status', { name: 'Source identity conflict' })
  expect(status.className).toContain('text-danger')
  fireEvent.click(screen.getByText('More details'))
  expect(screen.getByRole('link', { name: url })).toBeTruthy()
  expect(screen.getByText(/ARTICLE_DOI_CONFLICT/)).toBeTruthy()
  expect(screen.queryByText(/^SHA-256:/)).toBeNull()
})


it.each(['POSSIBLE', 'PROBABLE', 'UNCERTAIN'])('%s full text retains warnings without offering upload', async identity => {
  actions.prepare.mockResolvedValue({ ...available, identity, source: { provider: 'fixture', identity_status: 'uncertain' } })
  mount()
  await screen.findByRole('status', { name: 'Full text acquired, identity pending' })
  expect(screen.queryByRole('button', { name: 'Upload file' })).toBeNull()
  expect(screen.getByText('SHA-256: ' + hash)).toBeTruthy()
})

it('identity conflict keeps an immediate correct-PDF upload even for ambiguous metadata', async () => {
  const ref = fixture.parse_response.parsed.references[0] as Reference
  const ambiguous = { ...ref, resolution: { reference_id: ref.id, status: 'ambiguous', match_reason: 'MULTIPLE_IDENTITIES', original_doi: null, resolved_doi: null, matched_title: null, provider: null, source_type: 'unknown', source_url: null, match_confidence: null, candidates: [], diagnostics: [] } } as Reference
  actions.prepare.mockResolvedValue({ ...missing, state: 'needs_attention', identity: 'CONFLICT' })
  mount(ambiguous)
  await screen.findByRole('status', { name: 'Source identity conflict' })
  fireEvent.click(screen.getByRole('button', { name: 'Upload file' }))
  expect(await screen.findByLabelText('Source PDF for ' + ref.doi)).toBeTruthy()
})

it('a candidate-only upload requires an explicit target and never defaults to the first candidate', async () => {
  const ref = { ...fixture.parse_response.parsed.references[0], doi: null } as Reference
  actions.prepare.mockResolvedValue({ ...missing, identity: 'CONFLICT', candidates: [
    { locator: { kind: 'doi', value: '10.1234/one' } }, { locator: { kind: 'url', value: 'https://example.org/two.pdf' } },
  ] })
  mount(ref)
  fireEvent.click(await screen.findByRole('button', { name: 'Upload file' }))
  fireEvent.change(screen.getByLabelText('Source PDF for ' + ref.id), { target: { files: [new File(['%PDF'], 'candidate.pdf')] } })
  const select = await screen.findByLabelText('Source to attach') as HTMLSelectElement
  expect(select.value).toBe('')
  expect(within(select).getAllByRole('option')).toHaveLength(3)
  expect(actions.upload).not.toHaveBeenCalled()
})

it('confirmed work stays green while historical version warnings remain visible', async () => {
  actions.prepare.mockResolvedValue({ ...available, identity: 'CONFIRMED', source: { provider: 'fixture', identity_status: 'confirmed', provenance: { warnings: ['VERSION_DATE_DIFFERS', 'HISTORICAL_VERSION_UNCONFIRMED'] } } })
  mount()
  const status = await screen.findByRole('status', { name: 'Full text available' })
  expect(status.className).toContain('text-success')
  fireEvent.click(screen.getByText('More details'))
  expect(screen.getByText('VERSION_DATE_DIFFERS')).toBeTruthy()
})


it('opens the native PDF picker synchronously without expanding details or uploading on cancel', async () => {
  const bubbled = vi.fn()
  mount(undefined, true, bubbled)
  const button = await screen.findByRole('button', { name: 'Upload file' })
  const ref = fixture.parse_response.parsed.references[0] as Reference
  const input = screen.getByLabelText('Source PDF for ' + ref.doi) as HTMLInputElement
  const picker = vi.spyOn(input, 'click')
  fireEvent.click(button)
  expect(picker).toHaveBeenCalledTimes(1)
  expect(bubbled).not.toHaveBeenCalled()
  expect(input.accept).toBe('.pdf,application/pdf')
  expect(screen.getByText('More details').closest('details')?.open).toBe(false)
  fireEvent.change(input, { target: { files: [] } })
  expect(actions.upload).not.toHaveBeenCalled()
  expect(screen.getByRole('status', { name: 'Full text unavailable' })).toBeTruthy()
})

it.each([
  { ...absent, state: 'needs_attention', identity: 'CANDIDATE_FOUND' },
  { ...absent, state: 'needs_attention', identity: 'UNCERTAIN' },
  { ...absent, state: 'needs_attention', reason_code: 'SOURCE_VERSION_UNCONFIRMED' },
  absent,
])('does not infer upload eligibility from candidate or warning state: %j', async prepared => {
  actions.prepare.mockResolvedValue(prepared)
  mount()
  await waitFor(() => expect(actions.prepare).toHaveBeenCalled())
  await waitFor(() => expect(screen.queryByRole('status', { name: 'Preparing full text' })).toBeNull())
  expect(screen.queryByRole('button', { name: 'Upload file' })).toBeNull()
})

it('keeps failed uploads repairable and allows selecting the same PDF again', async () => {
  actions.upload.mockRejectedValue(new Error('The PDF could not be saved locally.'))
  mount()
  await screen.findByRole('button', { name: 'Upload file' })
  const ref = fixture.parse_response.parsed.references[0] as Reference
  const input = screen.getByLabelText('Source PDF for ' + ref.doi) as HTMLInputElement
  const file = new File(['%PDF'], 'repeat.pdf')
  for (let i = 0; i < 2; i++) {
    fireEvent.change(input, { target: { files: [file] } })
    await waitFor(() => expect(actions.upload).toHaveBeenCalledTimes(i + 1))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Upload file' })).toHaveProperty('disabled', false))
    expect(input.value).toBe('')
  }
  expect(screen.getByText('The PDF could not be saved locally.')).toBeTruthy()
  expect(screen.getByRole('status', { name: 'Full text unavailable' })).toBeTruthy()
})

it('rejects a mismatched persisted hash and blocks duplicate uploads while pending', async () => {
  let finish!: (value: object) => void
  actions.upload.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  actions.status.mockResolvedValue({ ...available, raw_content_sha256: 'f'.repeat(64) })
  mount()
  await screen.findByRole('button', { name: 'Upload file' })
  const ref = fixture.parse_response.parsed.references[0] as Reference
  const input = screen.getByLabelText('Source PDF for ' + ref.doi)
  const file = new File(['%PDF'], 'file.pdf')
  fireEvent.change(input, { target: { files: [file] } })
  await waitFor(() => expect(actions.upload).toHaveBeenCalledTimes(1))
  expect(screen.getByRole('button', { name: 'Upload file' })).toHaveProperty('disabled', true)
  fireEvent.change(input, { target: { files: [file] } })
  expect(actions.upload).toHaveBeenCalledTimes(1)
  finish({ status: 'accepted', doi: ref.doi, raw_content_sha256: hash })
  await screen.findByText(/matching saved file could not be confirmed/)
  expect(screen.queryByRole('status', { name: 'Full text available' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Upload file' })).toHaveProperty('disabled', false)
})

it('uses the URL-only manual API with the original reference identity', async () => {
  const ref = { ...fixture.parse_response.parsed.references[0], doi: null, title: 'A sufficiently specific reference title with six words', url: 'https://example.org/paper.pdf' } as Reference
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { status: 'accepted', reference_id: ref.id, raw_content_sha256: hash } })
  actions.status.mockResolvedValue(available)
  mount(ref)
  fireEvent.click(await screen.findByRole('button', { name: 'Upload file' }))
  const file = new File(['%PDF'], 'url-source.pdf')
  fireEvent.change(screen.getByLabelText('Source PDF for ' + ref.id), { target: { files: [file] } })
  await screen.findByText(/PDF saved and verified/)
  const [route, body] = post.mock.calls[0]
  expect(route).toBe('/api/sources/manual-reference')
  expect(JSON.parse((body as FormData).get('reference') as string)).toEqual(ref)
  expect((body as FormData).get('file')).toBe(file)
  expect(actions.upload).not.toHaveBeenCalled()
  post.mockRestore()
})


it('binds candidate-only files to the explicitly selected locator after file selection', async () => {
  const ref = { ...fixture.parse_response.parsed.references[0], doi: null } as Reference
  const target = { kind: 'url', value: 'https://example.org/selected.pdf' }
  actions.prepare.mockResolvedValue({ ...missing, identity: 'CONFLICT', candidates: [
    { locator: { kind: 'doi', value: '10.1234/other' } }, { locator: target },
  ] })
  actions.status.mockResolvedValue(available)
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { status: 'accepted', reference_id: ref.id, raw_content_sha256: hash, locator: target } })
  mount(ref)
  fireEvent.click(await screen.findByRole('button', { name: 'Upload file' }))
  fireEvent.change(screen.getByLabelText('Source PDF for ' + ref.id), { target: { files: [new File(['%PDF'], 'selected.pdf')] } })
  expect(post).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('Source to attach'), { target: { value: JSON.stringify(target) } })
  fireEvent.click(screen.getByRole('button', { name: 'Confirm source' }))
  await screen.findByText(/PDF saved and verified/)
  expect(JSON.parse((post.mock.calls[0][1] as FormData).get('locator') as string)).toEqual(target)
  expect(screen.getByText('More details').closest('details')?.open).toBe(false)
  post.mockRestore()
})

it.each([new File([], 'empty.pdf'), new File(['%PDF'], 'wrong.txt'), new File(['x'.repeat(1001)], 'large.pdf')])('rejects an invalid Reference PDF before uploading: %s', async file => {
  mount()
  await screen.findByRole('button', { name: 'Upload file' })
  const ref = fixture.parse_response.parsed.references[0] as Reference
  fireEvent.change(screen.getByLabelText('Source PDF for ' + ref.doi), { target: { files: [file] } })
  await waitFor(() => expect(screen.getByRole('button', { name: 'Upload file' })).toHaveProperty('disabled', false))
  expect(actions.upload).not.toHaveBeenCalled()
  expect(screen.getByRole('status', { name: 'Full text unavailable' })).toBeTruthy()
})
