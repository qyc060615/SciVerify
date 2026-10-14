import { apiClient, ApiResponseError } from './api'
import { buildExtractionRequest } from './manuscriptBridge'
import type { ExtractionResult, ParseResponse, UploadLimits } from '@/types/manuscript'

export async function getUploadLimits(signal?: AbortSignal): Promise<UploadLimits> {
  return (await apiClient.get<UploadLimits>('/api/manuscripts/limits', { signal })).data
}
export function validatePdf(file: File | null, maxBytes: number): string | null {
  if (!file || file.size === 0) return 'Choose a non-empty PDF file.'
  if (!file.name.toLowerCase().endsWith('.pdf') || (file.type && file.type !== 'application/pdf')) return 'Choose a PDF file.'
  if (file.size > maxBytes) return `The PDF exceeds the backend limit (${(maxBytes / 1024 / 1024).toFixed(1)} MB).`
  return null
}
export async function parseManuscript(file: File): Promise<ParseResponse> {
  const form = new FormData(); form.append('file', file)
  return (await apiClient.post<ParseResponse>('/api/manuscripts/parse', form, { headers: { 'Content-Type': undefined } })).data
}
function isExtractionResult(value: unknown): value is ExtractionResult {
  const result = value as ExtractionResult | null
  return !!result && ['completed', 'partial', 'failed', 'skipped'].includes(result.status) && typeof result.manuscript_id === 'string'
    && Array.isArray(result.claims) && Array.isArray(result.contexts) && Array.isArray(result.context_results) && Array.isArray(result.diagnostics)
    && typeof result.metadata?.input_fingerprint === 'string'
}
export async function extractClaims(parsed: ParseResponse): Promise<ExtractionResult> {
  try {
    return (await apiClient.post<ExtractionResult>('/api/manuscripts/extract-claims', buildExtractionRequest(parsed))).data
  } catch (error) {
    if (error instanceof ApiResponseError && [502, 503, 504].includes(error.status ?? 0) && isExtractionResult(error.data)) return error.data
    throw error
  }
}
