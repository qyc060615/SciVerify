import { useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { AppHeader } from '@/components/app/AppHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { ROUTES, wholePaperJobPath } from '@/constants'
import { isLocalDemoMode } from '@/lib/demo-mode'
import { readManuscriptHistory } from '@/services/localManuscriptHistory'
import { getVerificationJob } from '@/services/verificationJobService'
import { wholePaperError } from '@/services/wholePaperErrors'
import type { BadgeVariant } from '@/components/ui/Badge'
import type { JobState, VerificationJob } from '@/types/verification-job'

const statuses: Record<JobState, { label: string; variant: BadgeVariant }> = {
  pending: { label: 'Pending', variant: 'muted' },
  running: { label: 'Running', variant: 'primary' },
  waiting_for_source: { label: 'Waiting for sources', variant: 'warning' },
  partially_completed: { label: 'Partially completed', variant: 'warning' },
  completed: { label: 'Completed', variant: 'success' },
  failed: { label: 'Failed', variant: 'danger' },
  interrupted: { label: 'Interrupted', variant: 'warning' },
}

function historyStatus({ status, coverage }: VerificationJob): JobState {
  return coverage.total_pairs > 0 && coverage.completed_pairs === coverage.total_pairs
    ? 'completed'
    : status
}

function loadHistory() {
  try {
    return { entries: readManuscriptHistory(), unavailable: false }
  } catch {
    return { entries: [], unavailable: true }
  }
}

function ManuscriptHistory() {
  const [{ entries, unavailable }] = useState(loadHistory)
  const jobs = useQueries({
    queries: entries.map(({ id }) => ({
      queryKey: ['manuscript-history', id],
      queryFn: ({ signal }: { signal: AbortSignal }) => getVerificationJob(id, signal),
      retry: false,
    })),
  })

  if (unavailable) {
    return <Panel><p role="alert">Could not read the whole-paper history stored in this browser.</p></Panel>
  }
  if (entries.length === 0) {
    return <Panel padding="lg" className="space-y-2 text-center">
      <p className="font-medium">No whole-paper verification tasks yet.</p>
      <p className="text-sm text-text-secondary">Tasks started in this browser will appear here.</p>
    </Panel>
  }

  return <ul className="grid gap-3">
    {entries.map(({ id, fileName }, index) => {
      const job = jobs[index]
      const status = job.data ? statuses[historyStatus(job.data)] : undefined
      return <li key={id}>
        <Panel padding="md" className="space-y-2">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <h2 className="min-w-0 break-words text-base font-semibold">
              <Link className="text-primary hover:underline" to={wholePaperJobPath(id)} state={{ manuscriptFileName: fileName }}>
                {job.data?.manuscript_title || fileName || 'Manuscript task'}
              </Link>
            </h2>
            {status && <Badge variant={status.variant}>{status.label}</Badge>}
          </div>
          <p className="break-all text-xs text-text-muted">{id}</p>
          {job.isPending && <p role="status" className="text-sm text-text-muted">Reading task…</p>}
          {job.isError && <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm text-warning">{wholePaperError(job.error)}</p>
            <Button size="sm" variant="outline" onClick={() => void job.refetch()} disabled={job.isFetching}>Retry</Button>
          </div>}
        </Panel>
      </li>
    })}
  </ul>
}

export default function HistoryPage() {
  const localDemo = isLocalDemoMode()
  return <div className="min-w-0 space-y-5">
    <AppHeader
      title="Whole-paper history"
      description="Review manuscript verification tasks started in this browser."
      actions={localDemo ? <Link className="text-sm font-medium text-primary hover:underline" to={ROUTES.APP_MANUSCRIPTS}>New manuscript</Link> : undefined}
    />
    {localDemo ? <ManuscriptHistory /> : <Panel>Whole-paper history is available in the local workspace.</Panel>}
  </div>
}
