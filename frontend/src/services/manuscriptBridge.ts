import type { ExtractionRequest, ExtractionResult, JobCreateRequest, ParseResponse } from '@/types/manuscript'

export function buildExtractionRequest(response: ParseResponse): ExtractionRequest {
  return { schema_version: response.schema_version, scope: response.scope, offset_unit: response.offset_unit, parsed: response.parsed }
}

export function buildJobCreateRequest(response: ParseResponse, extraction: ExtractionResult): JobCreateRequest {
  // Mirrors M3B from_request(): outer parse diagnostics are display-only.
  // No offset conversion, attribution, text cleanup or fingerprint recomputation.
  return { parsed: { ...response.parsed, manuscript: { ...response.parsed.manuscript, content_locator: 'submitted:client-structure' }, diagnostics: [] }, extraction }
}

export function executablePairCount(extraction: ExtractionResult): number {
  return extraction.claims.filter(c => c.attribution_status === 'resolved').reduce((n, c) => n + c.reference_ids.length, 0)
}

export function codePointSlice(text: string, start: number, end: number): string {
  return Array.from(text).slice(start, end).join('')
}
