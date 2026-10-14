import { apiClient } from './api'
import { env } from '@/lib/env'
import type { JobCreateRequest } from '@/types/manuscript'
import type { ResumeRequest, VerificationJob } from '@/types/verification-job'

const path = (id: string) => `/api/verification/jobs/${encodeURIComponent(id)}`
export async function createVerificationJob(request: JobCreateRequest): Promise<VerificationJob> {
  return (await apiClient.post<VerificationJob>('/api/verification/jobs', request)).data
}
export async function getVerificationJob(id: string, signal?: AbortSignal): Promise<VerificationJob> {
  return (await apiClient.get<VerificationJob>(path(id), { signal })).data
}
export async function resumeVerificationJob(id: string, request: ResumeRequest): Promise<VerificationJob> {
  return (await apiClient.post<VerificationJob>(`${path(id)}/resume`, request)).data
}
export function jobStreamUrl(id: string, after: number): string {
  return `${env.apiBaseUrl.replace(/\/$/, '')}${path(id)}/stream?after=${after}`
}
