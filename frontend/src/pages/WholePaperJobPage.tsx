import { useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { AppHeader } from '@/components/app/AppHeader'
import { Panel } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Spinner } from '@/components/ui/Spinner'
import { WholePaperReport } from '@/components/manuscript/WholePaperReport'
import { JobSourceRecovery } from '@/components/manuscript/JobSourceRecovery'
import { WorkflowStepper, type WorkflowStage } from '@/components/manuscript/WorkflowStepper'
import { ReferenceReview } from '@/components/manuscript/ReferenceReview'
import { ClaimList } from '@/components/manuscript/ClaimExtractionPreview'
import { useVerificationJob } from '@/hooks/useVerificationJob'
import { wholePaperError } from '@/services/wholePaperErrors'
import { ROUTES } from '@/constants'
import type { ParsedDTO } from '@/types/manuscript'

export default function WholePaperJobPage() {
  const { jobId = '' } = useParams()
  const location = useLocation()
  const [view, setView] = useState<{ id: string; stage: WorkflowStage }>({ id: jobId, stage: 'report' })
  const stage = view.id === jobId ? view.stage : 'report'
  const job = useVerificationJob(jobId)
  const fileName = (location.state as { manuscriptFileName?: unknown } | null)?.manuscriptFileName
  const fileLabel = typeof fileName === 'string' ? fileName : undefined
  if (!/^job_[0-9a-f]{32}$/.test(jobId)) return <Panel>Invalid job ID.</Panel>
  const parsed: ParsedDTO | null = job.data ? { manuscript: { id: job.data.manuscript_id, title: job.data.manuscript_title ?? null, content_hash: null }, paragraphs: job.data.paragraphs, references: job.data.references, citation_callouts: job.data.citation_callouts, citation_contexts: [] } : null
  return <div className="min-w-0 space-y-5">
    <AppHeader title="Verification Report" description={fileLabel ?? 'Evidence and processing results from your saved local task.'} actions={<Link className="text-sm text-primary" to={ROUTES.APP_MANUSCRIPTS}>New manuscript</Link>} />
    <WorkflowStepper current={stage} completed={job.data ? ['upload', 'references', 'claims', 'verification'] : []} allowed={job.data ? ['upload', 'references', 'claims', 'verification', 'report'] : ['report']} onSelect={next => setView({ id: jobId, stage: next })} />
    <p className="text-xs text-text-muted">{job.connection}{job.data ? ' · ' + job.data.status.replaceAll('_', ' ') : ''}</p>
    {job.isPending && <Panel><Spinner /> Reading saved job…</Panel>}
    {job.error && <Panel><p role="alert" className="text-warning">{wholePaperError(job.error)}</p><Button className="mt-3" variant="outline" onClick={() => void job.refetch()}>Reconnect</Button></Panel>}
    {job.data && <>
      {stage === 'upload' && <Panel className="space-y-3"><h2 className="font-semibold">Saved manuscript structure</h2><p className="break-all text-sm">{fileLabel ?? 'Manuscript ID: ' + job.data.manuscript_id}</p><p className="text-sm text-text-secondary">{job.data.paragraphs.length} paragraphs · {job.data.references.length} references. The original PDF is not retained by manuscript parsing.</p><details className="text-xs text-text-muted"><summary className="cursor-pointer">Recorded title</summary>{job.data.manuscript_title ?? 'Unavailable'} · not independently verified</details><Button size="sm" onClick={() => setView({ id: jobId, stage: 'report' })}>Back to Report</Button></Panel>}
      {stage === 'references' && <Panel className="space-y-4"><h2 className="font-semibold">Review References</h2><p className="text-xs text-text-muted">Read-only identities from this saved job. Recover missing sources in Report.</p><ReferenceReview references={job.data.references} /><Button size="sm" onClick={() => setView({ id: jobId, stage: 'report' })}>Back to Report</Button></Panel>}
      {stage === 'claims' && parsed && <Panel className="space-y-4"><h2 className="font-semibold">Saved claims</h2><ClaimList parsed={parsed} claims={job.data.claims} /><Button size="sm" onClick={() => setView({ id: jobId, stage: 'report' })}>Back to Report</Button></Panel>}
      {stage === 'verification' && <Panel className="space-y-3"><h2 className="font-semibold">Verification task created</h2><p className="text-sm">{job.data.coverage.total_pairs} planned pairs · {job.data.status.replaceAll('_', ' ')}.</p><p className="text-xs text-text-muted">This saved job cannot be recreated from step navigation. Continue or recover its eligible tasks in Report.</p><Button size="sm" onClick={() => setView({ id: jobId, stage: 'report' })}>Back to Report</Button></Panel>}
      <section hidden={stage !== 'report'} aria-label="Verification report"><WholePaperReport job={job.data} fileLabel={fileLabel} recovery={ids => <JobSourceRecovery key={jobId} job={job.data!} refresh={job.refresh} acceptSnapshot={job.acceptSnapshot} referenceIds={ids} />} /></section>
    </>}
  </div>
}
