import { apiClient } from './api'
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

export interface PreparedSource {
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

export function sourceAvailable(source?: PreparedSource) {
  return source?.state === 'available' && /^[a-f0-9]{64}$/.test(source.raw_content_sha256 ?? '') && ['pdf', 'html'].includes(source.format ?? '')
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

type DoiResult = { status: string; detail?: string | null }
const downloads = new Map<string, { promise: Promise<DoiResult>; controller: AbortController; users: number }>()
async function retrieveDoi(doi: string, signal: AbortSignal): Promise<DoiResult> {
  const key = doi.trim().toLowerCase()
  let shared = downloads.get(key)
  if (!shared) {
    const controller = new AbortController()
    const promise = apiClient.post<DoiResult>('/api/papers/retrieve', { doi }, { signal: controller.signal, timeout: 180_000 }).then(result => result.data)
    shared = { controller, promise, users: 0 }
    downloads.set(key, shared)
    void promise.finally(() => { if (downloads.get(key) === shared) downloads.delete(key) }).catch(() => {})
  }
  shared.users++
  let released = false
  const release = () => { if (!released) { released = true; if (--shared.users === 0) shared.controller.abort() } }
  signal.addEventListener('abort', release, { once: true })
  try { const result = await shared.promise; signal.throwIfAborted(); return result }
  finally { signal.removeEventListener('abort', release); release() }
}

export async function prepareReferenceSource(reference: Reference, signal: AbortSignal): Promise<PreparedSource> {
  return limited(signal, async () => {
    const base: PreparedSource = { reference_id: reference.id, state: 'failed', reason_code: 'SOURCE_REQUEST_FAILED', retryable: true, retrieval_status: null, format: null, raw_content_sha256: null, source: null }
    try {
      const local = await checkReferenceSource(reference, signal)
      if (local.state !== 'not_cached') return local
      if (reference.doi) {
        const result = await retrieveDoi(reference.doi, signal)
        if (result.status !== 'success') return { ...base, state: 'unavailable', reason_code: 'SOURCE_' + result.status.toUpperCase(), retrieval_status: result.status }
        const confirmed = await checkReferenceSource(reference, signal)
        return confirmed.state === 'not_cached' ? { ...confirmed, state: 'failed', reason_code: 'SOURCE_PERSISTENCE_UNCONFIRMED', retrieval_status: result.status, retryable: true } : confirmed
      }
      const retrieved = (await apiClient.post<PreparedSource>('/api/sources/prepare', { reference, retrieve: true }, { signal, timeout: 180_000 })).data
      if (retrieved.reference_id !== reference.id) throw new Error('The source acquisition returned another reference.')
      return retrieved
    } catch (error) {
      signal.throwIfAborted()
      const status = (error as { status?: number }).status
      return { ...base, reason_code: status === 404 ? 'SOURCE_NOT_FOUND' : status === 422 || status === 400 ? 'SOURCE_IDENTITY_OR_URL_INVALID' : 'SOURCE_NETWORK_OR_PROVIDER_ERROR', state: status === 422 || status === 400 ? 'needs_attention' : 'failed' }
    }
  })
}

export async function uploadReferenceSource(reference: Reference, file: File): Promise<string> {
  if (reference.doi) {
    const result = await uploadManualSource(reference.doi, file)
    if (result.status !== 'accepted' || result.doi.toLowerCase() !== reference.doi.toLowerCase()) throw new Error('The upload did not confirm the target DOI.')
    return result.raw_content_sha256
  }
  const form = new FormData()
  form.append('reference', JSON.stringify(reference)); form.append('file', file)
  const result = (await apiClient.post<{ status: string; reference_id: string; raw_content_sha256: string }>('/api/sources/manual-reference', form, { headers: { 'Content-Type': undefined } })).data
  if (result.status !== 'accepted' || result.reference_id !== reference.id) throw new Error('The upload did not confirm the target reference.')
  return result.raw_content_sha256
}
