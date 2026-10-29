import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AppHeader } from '@/components/app/AppHeader'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { ClaimExtractionPreview } from '@/components/manuscript/ClaimExtractionPreview'
import { ReferenceReview } from '@/components/manuscript/ReferenceReview'
import { WorkflowStepper, type WorkflowStage } from '@/components/manuscript/WorkflowStepper'
import { PdfPicker } from '@/components/manuscript/PdfPicker'
import { DiagnosticDetails } from '@/components/manuscript/DiagnosticDetails'
import { RecentLocalJobs } from '@/components/manuscript/RecentLocalJobs'
import { extractClaims, getUploadLimits, parseManuscript, resolveReferences, validatePdf } from '@/services/manuscriptService'
import { buildJobCreateRequest, executablePairCount } from '@/services/manuscriptBridge'
import { createVerificationJob } from '@/services/verificationJobService'
import { wholePaperError } from '@/services/wholePaperErrors'
import { wholePaperJobPath } from '@/constants'
import type { ExtractionResult, ParseResponse } from '@/types/manuscript'

export default function WholePaperVerifyPage() {
  const navigate = useNavigate()
  const limits = useQuery({ queryKey: ['manuscript-upload-limits'], queryFn: ({ signal }) => getUploadLimits(signal), retry: false })
  const [file, setFile] = useState<File | null>(null)
  const [parsed, setParsed] = useState<ParseResponse | null>(null)
  const [extraction, setExtraction] = useState<ExtractionResult | null>(null)
  const [stage, setStage] = useState<WorkflowStage>('upload')
  const [busy, setBusy] = useState<string | null>(null)
  const [sourceUploads, setSourceUploads] = useState<Record<string, boolean>>({})
  const [error, setError] = useState<string | null>(null)
  const [confirmedPartial, setConfirmedPartial] = useState(false)
  const [referencesResolved, setReferencesResolved] = useState(false)
  const [referencesReviewed, setReferencesReviewed] = useState(false)
  const [claimsReviewed, setClaimsReviewed] = useState(false)
  const action = useRef(false)
  const [recent] = useState<string[]>(() => {
    try { const ids: unknown = JSON.parse(localStorage.getItem('researchguard-recent-jobs') ?? '[]'); return Array.isArray(ids) ? ids.filter((id): id is string => typeof id === 'string' && /^job_[0-9a-f]{32}$/.test(id)).slice(0, 8) : [] } catch { return [] }
  })
  const working = !!busy || Object.values(sourceUploads).some(Boolean)
  const pairs = extraction ? executablePairCount(extraction) : 0
  const ready = !!extraction && ['completed', 'partial'].includes(extraction.status) && pairs > 0
  const allowed: WorkflowStage[] = ['upload', ...(parsed ? ['references' as const] : []), ...(referencesReviewed ? ['claims' as const] : []), ...(claimsReviewed && ready ? ['verification' as const] : [])]
  const completed: WorkflowStage[] = [...(parsed ? ['upload' as const] : []), ...(referencesReviewed ? ['references' as const] : []), ...(claimsReviewed ? ['claims' as const] : [])]
  async function perform(step: string, operation: () => Promise<void>) {
    if (action.current || Object.values(sourceUploads).some(Boolean)) return
    action.current = true; setBusy(step); setError(null)
    try { await operation() } catch (e) { setError(wholePaperError(e)) } finally { action.current = false; setBusy(null) }
  }
  function replace(next: File | null = null) {
    if (working) return
    setFile(next); setParsed(null); setExtraction(null); setReferencesResolved(false); setReferencesReviewed(false)
    setClaimsReviewed(false); setConfirmedPartial(false); setSourceUploads({}); setError(null); setStage('upload')
  }
  async function extract() {
    if (action.current || Object.values(sourceUploads).some(Boolean) || !parsed || !referencesReviewed) return
    setExtraction(null); setClaimsReviewed(false); setConfirmedPartial(false)
    await perform('extract', async () => setExtraction(await extractClaims(parsed)))
  }
  async function startVerification() {
    if (!parsed || !extraction || !referencesReviewed || !claimsReviewed || !ready || (extraction.status === 'partial' && !confirmedPartial)) return
    await perform('create', async () => {
      const job = await createVerificationJob(buildJobCreateRequest(parsed, extraction))
      try { localStorage.setItem('researchguard-recent-jobs', JSON.stringify([job.job_id, ...recent.filter(id => id !== job.job_id)].slice(0, 8))) } catch { /* Backend owns the report. */ }
      navigate(wholePaperJobPath(job.job_id), { state: { manuscriptFileName: file?.name } })
    })
  }
  return <div className="min-w-0 space-y-5">
    <AppHeader title="Whole-paper verification" description="Prepare your manuscript, review its citations, and inspect evidence-backed results." />
    <WorkflowStepper current={stage} completed={completed} allowed={allowed} busy={working} onSelect={next => { if (!working && allowed.includes(next)) { setStage(next); setError(null) } }} />
    {parsed && <div className="flex min-w-0 flex-wrap items-center justify-between gap-3 text-sm">
      <div className="min-w-0"><p className="break-all font-medium">{file?.name ?? 'Parsed manuscript'}</p><p className="text-xs text-text-muted">Parsed · {parsed.parsed.references.length} references</p></div>
      <Button variant="ghost" size="sm" disabled={working} onClick={() => replace()}>Replace PDF</Button>
    </div>}
    {error && <p role="alert" className="rounded-lg border border-danger/30 p-3 text-sm text-danger">{error}</p>}
    {stage === 'upload' && <Panel className="space-y-4">
      <h2 className="text-lg font-semibold">Upload Manuscript</h2>
      {parsed ? <><Badge variant="success">Parsed</Badge><p className="text-sm text-text-secondary">{file?.name} · {parsed.parsed.references.length} references</p><DiagnosticDetails records={parsed.diagnostics} label="parsing diagnostics" /><Button onClick={() => setStage('references')}>Review References</Button></> : <>
        <PdfPicker label="Manuscript PDF" file={file} disabled={working} onChange={replace} />
        {limits.isPending ? <p className="text-xs text-text-muted">Reading PDF limit…</p> : limits.error ? <p role="alert" className="text-sm">{wholePaperError(limits.error)} <Button size="sm" variant="outline" onClick={() => void limits.refetch()}>Reconnect</Button></p> : <p className="text-xs text-text-muted">PDF limit: {((limits.data?.manuscript_max_bytes ?? 0) / 1024 / 1024).toFixed(1)} MB</p>}
        <Button loading={busy === 'parse'} disabled={working || !file || !limits.data} onClick={() => void perform('parse', async () => {
          const invalid = validatePdf(file, limits.data!.manuscript_max_bytes); if (invalid) throw new Error(invalid)
          const result = await parseManuscript(file!); setParsed(result); setStage('references')
          setBusy('resolve'); setParsed(await resolveReferences(result)); setReferencesResolved(true)
        })}>{busy === 'parse' ? 'Parsing manuscript…' : 'Parse manuscript'}</Button>
      </>}
    </Panel>}
    {stage === 'references' && parsed && <Panel className="space-y-4">
      <h2 className="text-lg font-semibold">Review References</h2>
      {!referencesResolved ? <><p className="text-sm text-text-secondary">{parsed.parsed.references.length} references found. Resolve their identities before review.</p><Button disabled={working} loading={busy === 'resolve'} onClick={() => void perform('resolve', async () => {
        setParsed(await resolveReferences(parsed)); setReferencesResolved(true); setReferencesReviewed(false); setClaimsReviewed(false); setExtraction(null); setConfirmedPartial(false)
      })}>Resolve references</Button><DiagnosticDetails records={parsed.diagnostics} heading="Warnings" /></> : <>
        <ReferenceReview references={parsed.parsed.references} diagnostics={parsed.diagnostics} allowSources onSourceBusy={(id, value) => setSourceUploads(old => ({ ...old, [id]: value }))}><p className="break-words text-xs">Original parsed title (not independently verified): {parsed.parsed.manuscript.title ?? 'Unavailable'}</p></ReferenceReview>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4"><p className="text-xs text-text-muted">Continuing confirms your review; unfinished sources are checked during verification.</p><Button disabled={working} onClick={() => { setReferencesReviewed(true); setStage('claims') }}>Continue to Claims</Button></div>
      </>}
    </Panel>}
    {stage === 'claims' && parsed && referencesReviewed && <Panel className="space-y-4">
      {!extraction ? <><h2 className="text-lg font-semibold">Review Claims</h2><Button loading={busy === 'extract'} disabled={working} onClick={() => void extract()}>{busy === 'extract' ? 'Extracting claims…' : 'Extract claims'}</Button></> : <>
        <ClaimExtractionPreview parsed={parsed.parsed} extraction={extraction} />
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4"><Button variant="ghost" size="sm" disabled={working} onClick={() => void extract()}>Extract again · API fees may apply</Button><Button disabled={working || !ready} onClick={() => { setClaimsReviewed(true); setStage('verification') }}>Continue to Verification</Button></div>
      </>}
    </Panel>}
    {stage === 'verification' && parsed && extraction && claimsReviewed && <Panel className="space-y-4">
      <h2 className="text-lg font-semibold">Start Verification</h2>
      <p className="font-medium">{pairs} Claim–Reference pairs ready</p>
      {extraction.status === 'partial' && <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1 shrink-0" checked={confirmedPartial} disabled={working} onChange={event => setConfirmedPartial(event.target.checked)} />I reviewed the extraction coverage gaps and want to continue.</label>}
      <Button disabled={working || !ready || (extraction.status === 'partial' && !confirmedPartial)} loading={busy === 'create'} onClick={() => void startVerification()}>Start Verification</Button>
    </Panel>}
    <RecentLocalJobs ids={recent} />
  </div>
}
