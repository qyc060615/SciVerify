import { ApiResponseError } from './api'

const messages: Record<string, string> = {
  JOBS_DISABLED: 'Whole-paper jobs are disabled. Enable RESEARCHGUARD_JOBS_ENABLED on your local backend.',
  JOB_NOT_FOUND: 'This job was not found on the local backend.',
  JOBS_LOCAL_ONLY: 'Whole-paper jobs are available only from a local loopback connection.',
  JOB_REVISION_CONFLICT: 'The job changed. Review the refreshed report and confirm the recovery again.',
  JOB_RUNNING: 'This job is already running. Wait for the current attempt to finish.',
  JOB_SOURCE_VERSION_CONFLICT: 'The uploaded source version does not match the version pinned by this job.',
  JOB_SOURCE_HASH_REQUIRED: 'Upload the matching source PDF before resuming this reference.',
  JOB_SOURCE_NOT_ACCEPTED: 'The source is not available in the local source store. Upload it again.',
  JOB_RETRY_LIMIT: 'The retry limit has been reached for these tasks.',
  JOB_SNAPSHOT_CORRUPT: 'The stored job failed its integrity check. Its results cannot be read safely.',
}
export function wholePaperError(error: unknown): string {
  if (error instanceof ApiResponseError) {
    const body = error.data as { detail?: { code?: string } } | undefined
    const code = body?.detail?.code
    if (code && messages[code]) return messages[code]
    if (!error.status) return 'Unable to connect to the local backend. Your last confirmed report is retained.'
    if (error.status === 413) return 'This file or manuscript structure exceeds the backend size limit.'
    if (error.status === 422 || error.status === 400) return 'The backend rejected this file or manuscript structure. Check the PDF and extraction diagnostics.'
    if (error.status >= 500) return 'The local service could not complete this step. Check its configuration and try again.'
    return 'This operation could not be completed.'
  }
  return error instanceof Error ? error.message : 'This operation could not be completed.'
}
