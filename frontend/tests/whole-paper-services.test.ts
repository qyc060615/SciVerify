import { beforeEach, expect, it, vi } from 'vitest'
import { ApiResponseError, apiClient } from '@/services/api'
import { extractClaims, parseManuscript, getUploadLimits } from '@/services/manuscriptService'
import { uploadManualSource } from '@/services/verificationService'
import { createVerificationJob, resumeVerificationJob } from '@/services/verificationJobService'
import { buildJobCreateRequest } from '@/services/manuscriptBridge'
import type { ExtractionResult, ParseResponse } from '@/types/manuscript'
import fixture from './fixtures/manuscript.json'

beforeEach(() => vi.restoreAllMocks())
it('uses the existing multipart parse endpoint and backend upload bounds', async () => {
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: fixture.parse_response })
  const file = new File(['%PDF'], 'paper.pdf')
  await parseManuscript(file)
  expect(post).toHaveBeenCalledWith('/api/manuscripts/parse', expect.any(FormData), { headers: { 'Content-Type': undefined } })
  expect((post.mock.calls[0][1] as FormData).get('file')).toBe(file)
  vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { manuscript_max_bytes: 12, source_max_bytes: 24 } })
  expect(await getUploadLimits()).toEqual({ manuscript_max_bytes: 12, source_max_bytes: 24 })
})
it.each([502, 503, 504])('preserves a legal structured extraction result on provider failure HTTP %i', async status => {
  const partial = { ...fixture.job_request.extraction, status: 'partial' }
  vi.spyOn(apiClient, 'post').mockRejectedValue(new ApiResponseError('safe', status, partial))
  expect(await extractClaims(fixture.parse_response as ParseResponse)).toEqual(partial)
})
it('does not treat arbitrary provider bodies as extraction results', async () => {
  vi.spyOn(apiClient, 'post').mockRejectedValue(new ApiResponseError('safe', 503, { prompt: 'secret', status: 'failed' }))
  await expect(extractClaims(fixture.parse_response as ParseResponse)).rejects.toThrow('safe')
})
it('returns the actual accepted hash from the existing manual-upload API', async () => {
  const accepted = { status: 'accepted', doi: '10.1234/source', raw_content_sha256: 'd'.repeat(64), identity_match: 'doi' }
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: accepted })
  const file = new File(['%PDF'], 'source.pdf')
  expect(await uploadManualSource('10.1234/source', file)).toEqual(accepted)
  const form = post.mock.calls[0][1] as FormData
  expect(form.get('doi')).toBe('10.1234/source'); expect(form.get('file')).toBe(file)
})
it('creates and resumes via original durable job APIs with unchanged fingerprint', async () => {
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { job_id: 'job_a' } })
  await createVerificationJob(buildJobCreateRequest(fixture.parse_response as ParseResponse, fixture.job_request.extraction as ExtractionResult))
  expect(post).toHaveBeenCalledWith('/api/verification/jobs', fixture.job_request)
  const request = { expected_revision: 12, reference_ids: ['r4'], source_hashes: { r4: 'd'.repeat(64) } }
  await resumeVerificationJob('job_a', request)
  expect(post).toHaveBeenCalledWith('/api/verification/jobs/job_a/resume', request)
})
