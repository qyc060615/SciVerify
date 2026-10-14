import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AppHeader } from '@/components/app/AppHeader'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { ClaimExtractionPreview } from '@/components/manuscript/ClaimExtractionPreview'
import { ReferenceReview } from '@/components/manuscript/ReferenceReview'
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
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirmedPartial, setConfirmedPartial] = useState(false)
  const [referencesResolved, setReferencesResolved] = useState(false)
  const [referencesReviewed, setReferencesReviewed] = useState(false)
  const action = useRef(false)
  const [recent] = useState<string[]>(() => {
    try { const ids: unknown = JSON.parse(localStorage.getItem('researchguard-recent-jobs') ?? '[]'); return Array.isArray(ids) ? ids.filter((id): id is string => typeof id === 'string' && /^job_[0-9a-f]{32}$/.test(id)).slice(0, 8) : [] } catch { return [] }
  })
  async function perform(step: string, operation: () => Promise<void>) {
    if (action.current) return
    action.current = true; setBusy(step); setError(null)
    try { await operation() } catch (e) { setError(wholePaperError(e)) } finally { action.current = false; setBusy(null) }
  }
  const pairs = extraction ? executablePairCount(extraction) : 0
  return <div className="space-y-6">
    <AppHeader title="Whole-paper verification" eyebrow="Local research workspace" description="Parse your manuscript, resolve reference identities, review attributed claims, then verify each cited reference independently." />
    <Panel className="space-y-4">
      <h2 className="text-lg font-semibold">1. Upload your manuscript</h2>
      <p className="text-sm text-text-secondary">Upload the manuscript you want to check, not a cited reference PDF. Parsing uses your local GROBID service.</p>
      {limits.isPending ? <p>Reading backend upload limits…</p> : limits.error ? <p role="alert">{wholePaperError(limits.error)} <Button variant="outline" onClick={() => void limits.refetch()}>Reconnect</Button></p> : <p className="text-sm text-text-muted">PDF limit: {((limits.data?.manuscript_max_bytes ?? 0) / 1024 / 1024).toFixed(1)} MB</p>}
      <label className="block text-sm">Manuscript PDF<input className="mt-2 block w-full" type="file" accept="application/pdf,.pdf" disabled={!!busy} onChange={e => { setFile(e.target.files?.[0] ?? null); setParsed(null); setExtraction(null); setConfirmedPartial(false); setReferencesResolved(false); setReferencesReviewed(false); setError(null) }} /></label>
      <Button loading={busy === 'parse'} disabled={!!busy || !file || !limits.data} onClick={() => void perform('parse', async () => {
        const invalid = validatePdf(file, limits.data!.manuscript_max_bytes); if (invalid) throw new Error(invalid)
        setParsed(await parseManuscript(file!)); setExtraction(null); setReferencesResolved(false); setReferencesReviewed(false)
      })}>Parse manuscript</Button>
    </Panel>
    {error && <p role="alert" className="rounded-lg border border-danger/30 p-4 text-danger">{error}</p>}
    {parsed && <Panel className="space-y-4">
      <h2 className="text-lg font-semibold">2. Resolve and review references</h2>
      <h3>{parsed.parsed.manuscript.title ?? 'Untitled manuscript'}</h3>
      <Badge variant="primary">Parse: {parsed.status}</Badge>
      <p>{parsed.parsed.paragraphs.length} paragraphs · {parsed.parsed.references.length} references · {parsed.parsed.citation_callouts.length} citation callouts</p>
      {parsed.diagnostics.map((d, i) => <p key={i} className="text-sm text-warning">{d.code}: {d.safe_message}</p>)}
      <Button loading={busy === 'resolve'} disabled={!!busy || referencesResolved} onClick={() => void perform('resolve', async () => {
        const enriched = await resolveReferences(parsed)
        setParsed(enriched); setExtraction(null); setConfirmedPartial(false); setReferencesResolved(true); setReferencesReviewed(false)
      })}>Resolve references</Button>
      {referencesResolved && <><ReferenceReview references={parsed.parsed.references} /><Button disabled={!!busy || referencesReviewed} onClick={() => setReferencesReviewed(true)}>Continue with reviewed references</Button><p className="text-sm text-text-secondary">Unresolved identities may remain as coverage gaps. Confirmed DOI sources can continue.</p></>}
    </Panel>}
    {parsed && referencesReviewed && <Panel className="space-y-4">
      <h2 className="text-lg font-semibold">3. Extract citation claims</h2>
      <p className="text-sm text-warning">Claim extraction calls the configured external LLM and may incur API fees. Extraction quality requires your review.</p>
      <Button loading={busy === 'extract'} disabled={!!busy} onClick={() => void perform('extract', async () => { setExtraction(await extractClaims(parsed)); setConfirmedPartial(false) })}>Extract claims</Button>
    </Panel>}
    {parsed && extraction && <>
      <ClaimExtractionPreview parsed={parsed.parsed} extraction={extraction} />
      <Panel className="space-y-4">
        <h2 className="text-lg font-semibold">4. Start verification</h2>
        <p>{pairs} executable Claim–Reference pairs. Ambiguous and unresolved claims remain coverage gaps.</p>
        <p className="text-sm text-warning">Verification may call external LLM, embedding and retrieval services and incur API fees. Completed processing does not mean the claim is supported.</p>
        {extraction.status === 'partial' && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={confirmedPartial} disabled={!!busy} onChange={e => setConfirmedPartial(e.target.checked)} />I reviewed the extraction coverage gaps and want to continue.</label>}
        {pairs === 0 && <p className="text-warning">No executable pairs. Review the manuscript and extraction diagnostics.</p>}
        <Button loading={busy === 'create'} disabled={!!busy || pairs === 0 || !['completed', 'partial'].includes(extraction.status) || (extraction.status === 'partial' && !confirmedPartial)} onClick={() => void perform('create', async () => {
          const job = await createVerificationJob(buildJobCreateRequest(parsed, extraction))
          try { localStorage.setItem('researchguard-recent-jobs', JSON.stringify([job.job_id, ...recent.filter(id => id !== job.job_id)].slice(0, 8))) } catch { /* Job persistence belongs to the backend. */ }
          navigate(wholePaperJobPath(job.job_id))
        })}>Start whole-paper verification</Button>
      </Panel>
    </>}
    {recent.length > 0 && <Panel><h2 className="mb-3 font-semibold">Recent local jobs</h2>{recent.map(id => <Link key={id} className="block break-all text-sm text-primary hover:underline" to={wholePaperJobPath(id)}>{id}</Link>)}</Panel>}
  </div>
}
