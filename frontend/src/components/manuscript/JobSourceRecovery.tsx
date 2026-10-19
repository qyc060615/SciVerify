import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { getUploadLimits, validatePdf } from '@/services/manuscriptService'
import { uploadManualSource } from '@/services/verificationService'
import { resumeVerificationJob, acquireJobSource } from '@/services/verificationJobService'
import { wholePaperError } from '@/services/wholePaperErrors'
import { extractDoi } from '@/lib/doi'
import { ApiResponseError } from '@/services/api'
import type { Reference } from '@/types/manuscript'
import type { JobTask, VerificationJob } from '@/types/verification-job'

type Props = { job: VerificationJob; refresh: () => Promise<VerificationJob>; acceptSnapshot: (job: VerificationJob) => void }
function doiOf(ref?: Reference): string | null {
  if (!ref?.doi) return null
  const canonical = ref.doi.trim().replace(/^doi:\s*/i, '').replace(/^https?:\/\/(?:dx\.)?doi\.org\/\s*/i, '').trim().replace(/[.,;]+$/, '')
  if (!/^10\.\d{4,9}\/\S+$/.test(canonical)) return null
  try { return extractDoi(ref.doi) } catch { return null }
}
function needsSource(task: JobTask) {
  return task.resume_available && (task.state === 'blocked_source' || (task.state === 'failed' && task.reason_code?.startsWith('SOURCE_DURABILITY_')))
}
function eligibleReferences(job: VerificationJob, doi: string) {
  return job.references.filter(ref => doiOf(ref) === doi && job.tasks.some(t => t.reference_id === ref.id && needsSource(t)))
}
function SourceRecovery({ job, doi, refresh, acceptSnapshot }: Props & { doi: string }) {
  const limits = useQuery({ queryKey: ['manuscript-upload-limits'], queryFn: ({ signal }) => getUploadLimits(signal), retry: false })
  const [file, setFile] = useState<File | null>(null)
  const [uploaded, setUploaded] = useState<{ hash: string; revision: number; referenceIds: string[] } | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const working = useRef(false)
  const refs = eligibleReferences(job, doi)
  async function perform(operation: () => Promise<void>) {
    if (working.current) return
    working.current = true; setBusy(true); setMessage(null)
    try { await operation() } catch (error) {
      setMessage(wholePaperError(error))
      if (error instanceof ApiResponseError && error.status === 409) {
        try { const latest = await refresh(); setUploaded(old => old ? { ...old, revision: latest.revision, referenceIds: eligibleReferences(latest, doi).map(r => r.id) } : null) } catch { /* Keep last confirmed state. */ }
      }
    } finally { working.current = false; setBusy(false) }
  }
  return <Panel className="space-y-3">
    <h3 className="font-medium">Recover cited source</h3>
    <p className="text-sm">{refs[0]?.title ?? refs[0]?.raw_text ?? doi}</p>
    <p className="text-sm text-text-muted">DOI: {doi} · {refs.length} recoverable reference IDs</p>
    <p className="text-sm text-text-secondary">Upload the matching reference PDF. The current job and completed results are preserved.</p>
    <label className="block text-sm">Source PDF for {doi}<input className="mt-2 block w-full" type="file" accept="application/pdf,.pdf" disabled={busy} onChange={e => { setFile(e.target.files?.[0] ?? null); setUploaded(null); setMessage(null) }} /></label>
    {limits.data && <p className="text-xs text-text-muted">Source limit: {(limits.data.source_max_bytes / 1024 / 1024).toFixed(1)} MB</p>}
    {limits.error && <p role="alert">{wholePaperError(limits.error)}</p>}
    <Button variant="outline" disabled={busy || !file || !limits.data} onClick={() => void perform(async () => {
      const invalid = validatePdf(file, limits.data!.source_max_bytes); if (invalid) throw new Error(invalid)
      const result = await uploadManualSource(doi, file!)
      if (result?.status !== 'accepted' || result.doi !== doi || !/^[0-9a-f]{64}$/.test(result.raw_content_sha256)) throw new Error('The upload did not return a valid accepted source hash.')
      const latest = await refresh()
      setUploaded({ hash: result.raw_content_sha256, revision: latest.revision, referenceIds: eligibleReferences(latest, doi).map(r => r.id) })
      setMessage('Source saved. Review the reference selection, then confirm resume.')
    })}>{busy ? 'Working…' : 'Upload source PDF'}</Button>
    {uploaded && <div className="space-y-3">
      <p className="text-xs text-text-muted">Reviewed revision: {uploaded.revision}</p>
      {refs.map(ref => <label key={ref.id} className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={busy} checked={uploaded.referenceIds.includes(ref.id)} onChange={e => setUploaded({ ...uploaded, referenceIds: e.target.checked ? [...uploaded.referenceIds, ref.id] : uploaded.referenceIds.filter(id => id !== ref.id) })} />Resume reference {ref.id}</label>)}
      <p className="text-sm text-warning">Resuming these references may call paid verification and embedding APIs.</p>
      <Button disabled={busy || uploaded.referenceIds.length === 0} onClick={() => void perform(async () => {
        const latest = await refresh()
        if (latest.revision !== uploaded.revision) {
          setUploaded({ ...uploaded, revision: latest.revision, referenceIds: eligibleReferences(latest, doi).map(r => r.id) })
          throw new Error('The job changed. Review the latest recoverable references and confirm resume again.')
        }
        const eligible = new Set(eligibleReferences(latest, doi).map(r => r.id))
        const selected = uploaded.referenceIds.filter(id => eligible.has(id))
        if (!selected.length) throw new Error('These references are no longer recoverable in the current state.')
        const resumed = await resumeVerificationJob(job.job_id, { expected_revision: latest.revision, reference_ids: selected, source_hashes: Object.fromEntries(selected.map(id => [id, uploaded.hash])), retry_failed: selected.some(id => latest.tasks.some(t => t.reference_id === id && t.state === 'failed')) })
        acceptSnapshot(resumed); setUploaded(null); setFile(null); setMessage('Resume accepted for the selected references.')
      })}>Resume selected references</Button>
    </div>}
    {message && <p role="status" className="text-sm text-warning">{message}</p>}
  </Panel>
}

function UrlSourceRecovery({ job, referenceId, refresh, acceptSnapshot }: Props & { referenceId: string }) {
  const [accepted, setAccepted] = useState<{ hash: string; revision: number } | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const active = useRef(false)
  const ref = job.references.find(r => r.id === referenceId)
  async function acquireOrResume(resume: boolean) {
    if (active.current) return
    active.current = true; setBusy(true); setMessage(null)
    try {
      const latest = await refresh()
      if (latest.revision !== (resume ? accepted?.revision : job.revision)) throw new Error('The job changed. Review the refreshed report before continuing.')
      if (!resume) {
        const result = await acquireJobSource(job.job_id, referenceId, latest.revision)
        if (result.status !== 'accepted' || !/^[a-f0-9]{64}$/.test(result.raw_content_sha256 ?? '')) throw new Error(`Source not accepted: ${result.detail ?? result.status}`)
        setAccepted({ hash: result.raw_content_sha256!, revision: latest.revision })
        setMessage('Source cached. Historical version is unconfirmed. Confirm resume separately to run scientific verification.')
      } else if (accepted) {
        acceptSnapshot(await resumeVerificationJob(job.job_id, { expected_revision: latest.revision, reference_ids: [referenceId], source_hashes: { [referenceId]: accepted.hash } }))
        setAccepted(null)
      }
    } catch (error) { setAccepted(null); setMessage(wholePaperError(error)) }
    finally { active.current = false; setBusy(false) }
  }
  return <Panel className="space-y-3">
    <h3 className="font-medium">Recover URL source</h3><p>{ref?.title ?? referenceId}</p>
    <p className="break-all text-sm">{ref?.resolution?.source_url ?? ref?.url}</p>
    <p className="text-sm">Fetch the official document and validate its identity. This step does not run scientific verification.</p>
    <Button disabled={busy} variant="outline" onClick={() => void acquireOrResume(false)}>Fetch URL source</Button>
    {accepted && <><p className="break-all text-xs">Content hash: {accepted.hash}</p><p className="text-warning">Resume may incur embedding and verification API fees.</p><Button disabled={busy} onClick={() => void acquireOrResume(true)}>Confirm resume URL reference</Button></>}
    {message && <p role="status" className="text-warning">{message}</p>}
  </Panel>
}

export function JobSourceRecovery(props: Props) {
  const { job, refresh, acceptSnapshot } = props
  const groups = [...new Set(job.references.filter(r => job.tasks.some(t => t.reference_id === r.id && needsSource(t))).map(doiOf).filter((doi): doi is string => doi !== null))]
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const active = useRef(false)
  const processingRefs = [...new Set(job.tasks.filter(t => t.resume_available && !needsSource(t) && ['pending', 'failed'].includes(t.state) && doiOf(job.references.find(r => r.id === t.reference_id)) !== null).map(t => t.reference_id))]
    .filter(id => !job.tasks.some(t => t.reference_id === id && needsSource(t)))
  async function retry(referenceId: string) {
    if (active.current) return
    active.current = true; setBusy(true); setMessage(null)
    try {
      const latest = await refresh()
      if (latest.revision !== job.revision) throw new Error('The job changed. Review the refreshed report and confirm retry again.')
      const resumed = await resumeVerificationJob(job.job_id, { expected_revision: latest.revision, reference_ids: [referenceId], retry_failed: latest.tasks.some(t => t.reference_id === referenceId && t.state === 'failed') })
      acceptSnapshot(resumed)
    } catch (error) { setMessage(wholePaperError(error)); if (error instanceof ApiResponseError && error.status === 409) { try { await refresh() } catch { /* Preserve report. */ } } }
    finally { active.current = false; setBusy(false) }
  }
  return <div className="space-y-4">
    {groups.map(doi => <SourceRecovery key={job.job_id + doi} {...props} doi={doi} />)}
    {job.references.filter(r => !r.doi && (r.resolution?.source_url || r.url) && job.tasks.some(t => t.reference_id === r.id && needsSource(t))).map(r => <UrlSourceRecovery key={r.id} {...props} referenceId={r.id} />)}
    {processingRefs.length > 0 && <Panel className="space-y-3"><h2 className="font-semibold">Continue or retry processing</h2><p className="text-sm text-warning">This retries eligible unfinished tasks using their pinned sources. It may incur API fees; completed pairs are not rerun.</p>{processingRefs.map(id => <Button key={id} className="mr-2" variant="outline" disabled={busy} onClick={() => void retry(id)}>Retry reference {id}</Button>)}{message && <p role="alert" className="text-warning">{message}</p>}</Panel>}
  </div>
}
