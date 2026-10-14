import { Link, useParams } from 'react-router-dom'
import { AppHeader } from '@/components/app/AppHeader'
import { Panel } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Spinner } from '@/components/ui/Spinner'
import { WholePaperReport } from '@/components/manuscript/WholePaperReport'
import { JobSourceRecovery } from '@/components/manuscript/JobSourceRecovery'
import { useVerificationJob } from '@/hooks/useVerificationJob'
import { wholePaperError } from '@/services/wholePaperErrors'
import { ROUTES } from '@/constants'

export default function WholePaperJobPage() {
  const { jobId = '' } = useParams()
  const job = useVerificationJob(jobId)
  if (!/^job_[0-9a-f]{32}$/.test(jobId)) return <Panel>Invalid job ID.</Panel>
  return <div className="space-y-6">
    <AppHeader title={job.data?.manuscript_title ?? 'Whole-paper report'} description="Results and evidence are preserved in the local durable job." actions={<Link className="text-sm text-primary" to={ROUTES.APP_MANUSCRIPTS}>New manuscript</Link>} />
    <p className="flex flex-wrap gap-x-2 text-xs text-text-muted"><span className="break-all">Job: {jobId}</span><span>· {job.connection}{job.data ? ` · Revision ${job.data.revision}` : ''}</span></p>
    {job.isPending && <Panel><Spinner /> Reading saved job…</Panel>}
    {job.error && <Panel><p role="alert" className="text-warning">{wholePaperError(job.error)}</p><Button className="mt-3" variant="outline" onClick={() => void job.refetch()}>Reconnect</Button></Panel>}
    {job.data && <><WholePaperReport job={job.data} /><JobSourceRecovery key={jobId} job={job.data} refresh={job.refresh} acceptSnapshot={job.acceptSnapshot} /></>}
  </div>
}
