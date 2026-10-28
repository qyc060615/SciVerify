import { useQueries } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { wholePaperJobPath } from '@/constants'
import { getVerificationJob } from '@/services/verificationJobService'

export function RecentLocalJobs({ ids }: { ids: string[] }) {
  const [expanded, setExpanded] = useState(false)
  const jobs = useQueries({ queries: ids.map(id => ({ queryKey: ['recent-local-job', id], queryFn: ({ signal }: { signal: AbortSignal }) => getVerificationJob(id, signal), enabled: expanded, retry: false, staleTime: 30000 })) })
  if (!ids.length) return null
  return <details onToggle={event => setExpanded(event.currentTarget.open)} className="rounded-xl border border-border bg-surface px-4 py-3 text-sm"><summary className="cursor-pointer font-medium text-text-secondary">Recent local jobs · {ids.length}</summary>
    <ul className="mt-3 divide-y divide-border">{ids.map((id, index) => <li key={id} className="min-w-0 py-3"><Link className="block break-words text-primary [overflow-wrap:anywhere]" to={wholePaperJobPath(id)}>{jobs[index].data?.manuscript_title ? 'Recorded title: ' + jobs[index].data.manuscript_title : id}</Link><p className="mt-1 break-all text-xs text-text-muted">{jobs[index].data?.status.replaceAll('_', ' ') ?? (jobs[index].isPending ? 'Reading saved task…' : 'Task metadata unavailable')} · {id}</p></li>)}</ul>
  </details>
}
