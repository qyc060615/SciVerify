import { describe, expect, it } from 'vitest'
import fixture from './fixtures/manuscript.json'
import { buildExtractionRequest, buildJobCreateRequest, codePointSlice, executablePairCount } from '@/services/manuscriptBridge'
import type { ExtractionResult, ParseResponse } from '@/types/manuscript'

const parsed = fixture.parse_response as ParseResponse
const extraction = fixture.job_request.extraction as ExtractionResult

describe('M3A → M3B → M4 contract bridge', () => {
  it('matches the same golden payload validated by backend from_request and job API', () => {
    expect(buildExtractionRequest(parsed)).toEqual(fixture.extraction_request)
    expect(buildJobCreateRequest(parsed, extraction)).toEqual(fixture.job_request)
    expect(parsed.diagnostics.length).toBeGreaterThan(0)
    expect(buildJobCreateRequest(parsed, extraction).parsed.diagnostics).toEqual([])
  })
  it('preserves IDs, text, extraction fingerprint and Unicode code-point spans', () => {
    const request = buildJobCreateRequest(parsed, extraction)
    expect(request.extraction).toBe(extraction)
    expect(request.parsed.paragraphs).toBe(parsed.parsed.paragraphs)
    const call = request.parsed.citation_callouts[0]
    expect(codePointSlice(request.parsed.paragraphs[0].text, call.span.start, call.span.end)).toBe(call.text)
    expect(executablePairCount(extraction)).toBe(2)
  })
  it('does not invent pairs for ambiguous or unresolved attribution', () => {
    expect(executablePairCount({ ...extraction, claims: extraction.claims.map(c => ({ ...c, attribution_status: 'ambiguous' })) })).toBe(0)
  })
})
