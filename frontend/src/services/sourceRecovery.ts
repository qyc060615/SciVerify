import { extractDoi } from '@/lib/doi'
import type { Reference } from '@/types/manuscript'
import type { JobTask, VerificationJob } from '@/types/verification-job'

export function sourceDoi(ref?: Reference): string | null {
  if (!ref?.doi) return null
  const canonical = ref.doi.trim().replace(/^doi:\s*/i, '').replace(/^https?:\/\/(?:dx\.)?doi\.org\/\s*/i, '').trim().replace(/[.,;]+$/, '')
  if (!/^10\.\d{4,9}\/\S+$/.test(canonical)) return null
  try { return extractDoi(ref.doi) } catch { return null }
}

export function needsSource(task: JobTask) {
  return task.resume_available && (task.state === 'blocked_source' || (task.state === 'failed' && task.reason_code?.startsWith('SOURCE_DURABILITY_')))
}

export function recoverableReferenceIds(job: VerificationJob): string[] {
  return job.references.filter(ref => job.tasks.some(task => task.reference_id === ref.id && task.resume_available && (
    (needsSource(task) && (!!sourceDoi(ref) || (!ref.doi && !!(ref.resolution?.source_url || ref.url)))) ||
    (!needsSource(task) && ['pending', 'failed'].includes(task.state) && !!sourceDoi(ref))
  ))).map(ref => ref.id)
}
