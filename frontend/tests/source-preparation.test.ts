import { beforeEach, expect, it, vi } from 'vitest'
import { waitFor } from '@testing-library/react'
import { prepareReferenceSource, uploadReferenceSource, type PreparedSource } from '@/services/sourceService'
import { ApiResponseError } from '@/services/api'
import fixture from './fixtures/manuscript.json'
import type { Reference } from '@/types/manuscript'

const api = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('@/services/api', async original => ({ ...await original<object>(), apiClient: api }))
const reference = fixture.parse_response.parsed.references[0] as Reference
const hash = 'a'.repeat(64)
const absent: PreparedSource = { reference_id: reference.id, state: 'not_cached', reason_code: 'SOURCE_NOT_CACHED', retryable: true, retrieval_status: null, format: null, raw_content_sha256: null, source: null }
const available: PreparedSource = { ...absent, state: 'available', reason_code: 'SOURCE_PERSISTED', format: 'pdf', raw_content_sha256: hash }
const signal = () => new AbortController().signal
beforeEach(() => vi.clearAllMocks())

it('checks persisted local files first and never downloads a local hit', async () => {
  api.post.mockResolvedValue({ data: available })
  expect(await prepareReferenceSource(reference, signal())).toEqual(available)
  expect(api.post).toHaveBeenCalledTimes(1)
  expect(api.post).toHaveBeenCalledWith('/api/sources/prepare', { reference, retrieve: false }, expect.objectContaining({ signal: expect.any(AbortSignal) }))
})

it('uses reference-aware acquisition including candidates and server durability confirmation', async () => {
  api.post.mockResolvedValueOnce({ data: absent }).mockResolvedValueOnce({ data: available })
  expect((await prepareReferenceSource(reference, signal())).state).toBe('available')
  expect(api.post.mock.calls.map(call => call[0])).toEqual(['/api/sources/prepare', '/api/sources/prepare'])
  expect(api.post.mock.calls[1][1]).toEqual({ reference, retrieve: true })
})

it('a successful DOI response without durable storage never becomes available', async () => {
  api.post.mockResolvedValueOnce({ data: absent }).mockResolvedValueOnce({ data: { ...available, raw_content_sha256: null } })
  const result = await prepareReferenceSource(reference, signal())
  expect(result.state).toBe('failed'); expect(result.raw_content_sha256).toBeNull()
  expect(result.reason_code).toBe('SOURCE_PERSISTENCE_UNCONFIRMED')
})

it('URL-only prefetch sends the actual reference without a Job or fabricated DOI', async () => {
  const urlRef = { ...reference, doi: null, url: 'https://www.fda.gov/media/123/download' }
  api.post.mockResolvedValueOnce({ data: absent }).mockResolvedValueOnce({ data: available })
  await prepareReferenceSource(urlRef, signal())
  expect(api.post.mock.calls.map(call => call[0])).toEqual(['/api/sources/prepare', '/api/sources/prepare'])
  expect(api.post.mock.calls[1][1]).toEqual({ reference: urlRef, retrieve: true })
})

it('identity attention does not launch a download', async () => {
  api.post.mockResolvedValue({ data: { ...absent, state: 'needs_attention', reason_code: 'REFERENCE_AMBIGUOUS' } })
  expect((await prepareReferenceSource(reference, signal())).state).toBe('needs_attention')
  expect(api.post).toHaveBeenCalledTimes(1)
})

it.each(['metadata_only', 'full_text_unavailable', 'parsing_failure', 'provider_error'])('retains real %s retrieval failure without automatic retries', async status => {
  api.post.mockResolvedValueOnce({ data: absent }).mockResolvedValueOnce({ data: { ...absent, state: 'unavailable', retrieval_status: status, candidates: [{ url: 'https://example.org/candidate', reason: status, attempted: true }] } })
  const result = await prepareReferenceSource(reference, signal())
  expect(result.state).toBe('unavailable'); expect(result.retrieval_status).toBe(status)
  expect(result.candidates?.[0].url).toBe('https://example.org/candidate')
  expect(api.post).toHaveBeenCalledTimes(2)
})

it('network/provider failure is retryable and has no invented hash', async () => {
  api.post.mockResolvedValueOnce({ data: absent }).mockRejectedValueOnce(new ApiResponseError('not exposed', 503))
  const result = await prepareReferenceSource(reference, signal())
  expect(result).toMatchObject({ state: 'failed', retryable: true, raw_content_sha256: null, reason_code: 'SOURCE_NETWORK_OR_PROVIDER_ERROR' })
})

it('passes each actual reference to backend per-source download coordination', async () => {
  api.post.mockImplementation(async (_url: string, body) => ({ data: { ...(body.retrieve ? available : absent), reference_id: body.reference.id } }))
  const other = { ...reference, id: 'another-ref' }
  expect((await Promise.all([prepareReferenceSource(reference, signal()), prepareReferenceSource(other, signal())])).map(x => x.state)).toEqual(['available', 'available'])
  expect(api.post.mock.calls.filter(call => call[1].retrieve === true)).toHaveLength(2)
  expect(api.post.mock.calls.filter(call => call[1].retrieve === true).map(call => call[1].reference.id)).toEqual([reference.id, other.id])
})

it('ambiguous candidates reach acquisition and uncertain full text is retained', async () => {
  const candidate = { url: 'https://example.org/paper.pdf?version=1&download=true', attempted: false }
  api.post.mockResolvedValueOnce({ data: { ...absent, identity: 'CANDIDATE_FOUND', candidates: [candidate] } })
    .mockResolvedValueOnce({ data: { ...available, identity: 'UNCERTAIN', source: { provider: 'fixture', identity_status: 'uncertain' }, candidates: [{ ...candidate, attempted: true }] } })
  const result = await prepareReferenceSource(reference, signal())
  expect(result.state).toBe('available'); expect(result.identity).toBe('UNCERTAIN')
  expect(result.raw_content_sha256).toBe(hash)
  expect(result.candidates?.[0].url).toBe(candidate.url)
})

it('limits active preparations and cancels queued work before making a request', async () => {
  const finish: (() => void)[] = []
  api.post.mockImplementation((_url, body) => new Promise(resolve => finish.push(() => resolve({ data: { ...available, reference_id: body.reference.id } }))))
  const abort = new AbortController()
  const a = prepareReferenceSource(reference, signal())
  const b = prepareReferenceSource({ ...reference, id: 'second' }, signal())
  const c = prepareReferenceSource({ ...reference, id: 'cancelled' }, abort.signal).catch(error => error)
  await waitFor(() => expect(finish).toHaveLength(2))
  abort.abort(); finish.forEach(resolve => resolve())
  await Promise.all([a, b, c])
  expect(api.post).toHaveBeenCalledTimes(2)
})

it('URL manual upload uses reference association rather than a fake DOI', async () => {
  const urlRef = { ...reference, doi: null, url: 'https://www.fda.gov/document' }
  api.post.mockResolvedValue({ data: { status: 'accepted', reference_id: urlRef.id, raw_content_sha256: hash } })
  const pdf = new File(['%PDF'], 'source.pdf')
  expect(await uploadReferenceSource(urlRef, pdf)).toBe(hash)
  const [url, form] = api.post.mock.calls[0]
  expect(url).toBe('/api/sources/manual-reference')
  expect(JSON.parse(form.get('reference'))).toEqual(urlRef)
  expect(form.get('doi')).toBeNull()
})

it('a response for another reference cannot become available', async () => {
  api.post.mockResolvedValue({ data: { ...available, reference_id: 'wrong-reference' } })
  const result = await prepareReferenceSource(reference, signal())
  expect(result.state).toBe('failed')
  expect(result.raw_content_sha256).toBeNull()
  expect(api.post).toHaveBeenCalledTimes(1)
})


it('manual candidate upload preserves the original reference and explicit target', async () => {
  const ref = { ...reference, doi: null }
  const target = { kind: 'doi' as const, value: '10.1234/selected' }
  api.post.mockResolvedValue({ data: { status: 'accepted', reference_id: ref.id, raw_content_sha256: hash, locator: target } })
  expect(await uploadReferenceSource(ref, new File(['%PDF'], 'source.pdf'), target)).toBe(hash)
  const [url, form] = api.post.mock.calls[0]
  expect(url).toBe('/api/sources/manual-reference')
  expect(JSON.parse(form.get('reference'))).toEqual(ref)
  expect(JSON.parse(form.get('locator'))).toEqual(target)
})


it('manual upload never accepts a receipt for another selected candidate', async () => {
  const ref = { ...reference, doi: null }
  const target = { kind: 'doi' as const, value: '10.1234/selected' }
  api.post.mockResolvedValue({ data: { status: 'accepted', reference_id: ref.id, raw_content_sha256: hash, locator: { kind: 'doi', value: '10.1234/other' } } })
  await expect(uploadReferenceSource(ref, new File(['%PDF'], 'source.pdf'), target)).rejects.toThrow('selected source target')
})
