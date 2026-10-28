import { apiClient } from './api'
import type { Reference } from '@/types/manuscript'

export interface LocalSourceStatus { availability: 'available' | 'not_cached'; remote_status: 'not_checked'; raw_content_sha256: string | null; format: 'pdf' | 'html' | null }
export function referenceLocator(reference: Reference): { kind: 'doi' | 'url'; value: string } | null {
  if (reference.doi) return { kind: 'doi', value: reference.doi }
  const url = reference.resolution?.source_url || reference.url
  return url ? { kind: 'url', value: url } : null
}
export async function getLocalSourceStatus(locator: { kind: 'doi' | 'url'; value: string }, signal?: AbortSignal): Promise<LocalSourceStatus> {
  return (await apiClient.post<LocalSourceStatus>('/api/sources/status', locator, { signal })).data
}
