import { apiClient } from './api'
import type { QueryClient } from '@tanstack/react-query'
import type { Reference } from '@/types/manuscript'
import { uploadManualSource } from './verificationService'

export interface LocalSourceStatus { availability: 'available' | 'not_cached'; remote_status: 'not_checked'; raw_content_sha256: string | null; format: 'pdf' | 'html' | null }
export function referenceLocator(reference: Reference): { kind: 'doi' | 'url'; value: string } | null {
  if (reference.doi) return { kind: 'doi', value: reference.doi }
  const url = reference.resolution?.source_url || reference.url
  return url ? { kind: 'url', value: url } : null
}
export async function getLocalSourceStatus(locator: { kind: 'doi' | 'url'; value: string }, signal?: AbortSignal): Promise<LocalSourceStatus> {
  return (await apiClient.post<LocalSourceStatus>('/api/sources/status', locator, { signal })).data
}

export interface SourceCandidate {
  locator?: { kind: 'doi' | 'url'; value: string } | null
  doi?: string | null; url?: string; urls?: string[]; title?: string | null
  authors?: string[]; years?: number[]; provider?: string; state?: string
  reason?: string | null; attempted?: boolean; full_text_obtained?: boolean
  raw_content_sha256?: string | null; diagnostics?: string[]
  downloads?: SourceCandidate[]
}
export interface PreparedSource {
  candidates?: SourceCandidate[]
  identity?: 'CONFIRMED' | 'POSSIBLE' | 'PROBABLE' | 'UNCERTAIN' | 'CANDIDATE_FOUND' | 'CONFLICT' | 'UNAVAILABLE'
  full_text_obtained?: boolean
  reference_id: string
  state: 'available' | 'not_cached' | 'unavailable' | 'needs_attention' | 'failed'
  reason_code: string
  retryable: boolean
  retrieval_status: string | null
  format: 'pdf' | 'html' | null
  raw_content_sha256: string | null
  source: { url?: string | null; provider: string; cache_hit?: boolean; identity_status?: string; provenance?: { warnings?: string[]; identity?: string } | null } | null
}

export function referenceSourceKey(reference: Reference, automatic: boolean) {
  return ['reference-source', automatic ? 'prepare' : 'check', JSON.stringify(reference)] as const
}

export function invalidateChangedReferenceSources(client: QueryClient, previous: Reference[], next: Reference[]) {
  const old = new Map(previous.map(reference => [reference.id, JSON.stringify(reference)]))
  const changed = new Set(next.filter(reference => old.get(reference.id) !== JSON.stringify(reference)).map(reference => reference.id))
  return client.invalidateQueries({ refetchType: 'none', predicate: query => {
    if (query.queryKey[0] !== 'reference-source') return false
    try { return changed.has((JSON.parse(String(query.queryKey[2])) as Reference).id) } catch { return false }
  } })
}

export function sourceAvailable(source?: PreparedSource) {
  return source?.state === 'available' && /^[a-f0-9]{64}$/.test(source.raw_content_sha256 ?? '') && ['pdf', 'html'].includes(source.format ?? '')
}

// Only a completed acquisition failure or explicit identity conflict permits repair.
// Candidate/version warnings alone do not establish that retrieval failed.
export function sourceNeedsUpload(source?: PreparedSource) {
  if (!source) return false
  if (source.identity === 'CONFLICT' || source.reason_code === 'SOURCE_IDENTITY_CONFLICT') return true
  if (sourceAvailable(source)) return false
  return ['unavailable', 'failed'].includes(source.state) || source.state === 'available'
}

// Presentation only: never rewrite the backend identity or acquisition result.
export function referenceSourceDisplay({ data, isFetching, isError }: { data?: PreparedSource; isFetching: boolean; isError: boolean }) {
  const preparing = isFetching
  const conflict = data?.identity === 'CONFLICT' || data?.reason_code === 'SOURCE_IDENTITY_CONFLICT'
  const ready = !preparing && !isError && sourceAvailable(data) && !sourceNeedsUpload(data)
  const missing = !preparing && (isError || sourceNeedsUpload(data))
  // Known issues that require a reliable locator or reference association.
  // Candidate discovery and identity/version warnings do not imply manual work.
  const attention = !preparing && !ready && !missing && data?.state === 'needs_attention' && [
    'SOURCE_LOCATOR_MISSING', 'SOURCE_IDENTITY_OR_URL_INVALID', 'SOURCE_REFERENCE_ASSOCIATION_UNCONFIRMED',
  ].includes(data.reason_code)
  const candidate = !preparing && !ready && !missing && !attention && (data?.identity === 'CANDIDATE_FOUND' || !!data?.candidates?.length)
  const identityUncertain = ready && (data?.identity === 'UNCERTAIN' || (!data?.identity && data?.source?.identity_status === 'uncertain'))
  const label = preparing ? 'Preparing Full Text'
    : ready ? 'Full Text Ready' + (identityUncertain ? ' · Identity Uncertain' : '')
      : missing ? conflict ? 'Source Identity Conflict' : 'Full Text Unavailable'
        : attention ? 'Needs Attention' : candidate ? 'Candidate Found' : 'Full Text Not Checked'
  return {
    ready, missing, attention, preparing, identityUncertain, label,
    mark: preparing ? '…' : ready ? '✓' : missing ? '×' : attention || candidate ? '!' : '—',
    color: ready ? 'text-success' : missing ? 'text-danger' : attention || candidate ? 'text-warning' : 'text-text-muted',
  }
}

export async function checkReferenceSource(reference: Reference, signal?: AbortSignal): Promise<PreparedSource> {
  const result = (await apiClient.post<PreparedSource>('/api/sources/prepare', { reference, retrieve: false }, { signal, timeout: 120_000 })).data
  if (result.reference_id !== reference.id) throw new Error('The source check returned another reference.')
  return result
}

// Shared across rows and mounts; at most two preparations run at once.
let running = 0
const waiting: (() => void)[] = []
async function limited<T>(signal: AbortSignal, operation: () => Promise<T>): Promise<T> {
  signal.throwIfAborted()
  await new Promise<void>((resolve, reject) => {
    const start = () => { signal.removeEventListener('abort', cancel); running++; resolve() }
    const cancel = () => { const index = waiting.indexOf(start); if (index >= 0) waiting.splice(index, 1); reject(signal.reason) }
    if (running < 2) start()
    else { waiting.push(start); signal.addEventListener('abort', cancel, { once: true }) }
  })
  try { signal.throwIfAborted(); return await operation() }
  finally { running--; waiting.shift()?.() }
}

export async function prepareReferenceSource(reference: Reference, signal: AbortSignal): Promise<PreparedSource> {
  return limited(signal, async () => {
    const base: PreparedSource = { reference_id: reference.id, state: 'failed', reason_code: 'SOURCE_REQUEST_FAILED', retryable: true, retrieval_status: null, format: null, raw_content_sha256: null, source: null }
    let checked: PreparedSource | undefined
    try {
      const local = await checkReferenceSource(reference, signal)
      checked = local
      if (local.state !== 'not_cached') return local
      const retrieved = (await apiClient.post<PreparedSource>('/api/sources/prepare', { reference, retrieve: true }, { signal, timeout: 180_000 })).data
      if (retrieved.reference_id !== reference.id) throw new Error('The source acquisition returned another reference.')
      if (retrieved.state === 'available' && !sourceAvailable(retrieved)) return { ...retrieved, state: 'failed', reason_code: 'SOURCE_PERSISTENCE_UNCONFIRMED', raw_content_sha256: null, retryable: true }
      return retrieved
    } catch (error) {
      signal.throwIfAborted()
      const status = (error as { status?: number }).status
      return { ...base, candidates: checked?.candidates, identity: checked?.candidates?.length ? 'CANDIDATE_FOUND' : 'UNAVAILABLE', reason_code: status === 404 ? 'SOURCE_NOT_FOUND' : status === 422 || status === 400 ? 'SOURCE_IDENTITY_OR_URL_INVALID' : 'SOURCE_NETWORK_OR_PROVIDER_ERROR', state: status === 422 || status === 400 ? 'needs_attention' : 'failed' }
    }
  })
}

export async function uploadReferenceSource(reference: Reference, file: File, locator?: { kind: 'doi' | 'url'; value: string }): Promise<string> {
  if (reference.doi) {
    const result = await uploadManualSource(reference.doi, file)
    if (result.status !== 'accepted' || result.doi.toLowerCase() !== reference.doi.toLowerCase()) throw new Error('The upload did not confirm the target DOI.')
    return result.raw_content_sha256
  }
  const form = new FormData()
  form.append('reference', JSON.stringify(reference)); form.append('file', file)
  if (locator) form.append('locator', JSON.stringify(locator))
  const result = (await apiClient.post<{ status: string; reference_id: string; raw_content_sha256: string; locator?: { kind: 'doi' | 'url'; value: string } }>('/api/sources/manual-reference', form, { headers: { 'Content-Type': undefined } })).data
  if (result.status !== 'accepted' || result.reference_id !== reference.id) throw new Error('The upload did not confirm the target reference.')
  if (locator && (result.locator?.kind !== locator.kind || result.locator.value !== locator.value)) throw new Error('The upload did not confirm the selected source target.')
  return result.raw_content_sha256
}
