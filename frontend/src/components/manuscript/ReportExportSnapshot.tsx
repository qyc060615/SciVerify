import { useRef, useState, type ReactNode } from 'react'
import { Panel } from '@/components/ui/Card'
import { Badge, type BadgeVariant } from '@/components/ui/Badge'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import type { DomainVerdict, JobTask, VerificationJob, EvidenceChunk } from '@/types/verification-job'
import { codePointSlice } from '@/services/manuscriptBridge'
import { chooseReportDestination, type ReportFormat } from '@/services/reportFileSave'

const verdicts: Record<DomainVerdict, { label: string; variant: BadgeVariant }> = {
  SUPPORTED: { label: 'Supported', variant: 'success' }, PARTIALLY_SUPPORTED: { label: 'Partially supported', variant: 'warning' },
  OVERSTATED: { label: 'Overstated', variant: 'warning' }, CONTRADICTED: { label: 'Contradicted', variant: 'danger' }, INSUFFICIENT: { label: 'Insufficient evidence', variant: 'muted' },
}
function safeUrl(value: string | null): string | undefined {
  try { const url = new URL(value ?? ''); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : undefined } catch { return undefined }
}
function Evidence({ chunk }: { chunk: EvidenceChunk }) {
  const url = safeUrl(chunk.source_url)
  return <div className="min-w-0 rounded-lg bg-surface-elevated/50 p-3 text-sm">
    <p className="font-medium">Evidence from the reference{chunk.section ? ' / ' + chunk.section : ''}{chunk.page != null ? ' / Page ' + chunk.page : ''}</p>
    <blockquote className="mt-3 whitespace-pre-wrap break-words border-l-2 border-primary pl-3 leading-relaxed [overflow-wrap:anywhere]">{chunk.text}</blockquote>
    {chunk.metadata.source_identity_status !== 'confirmed' && <p className="mt-2 text-xs text-warning">The evidence source has not been fully confirmed against the cited reference.</p>}
    {url && <a className="mt-2 inline-block text-xs text-primary underline" href={url} target="_blank" rel="noreferrer">Read source</a>}
  </div>
}
function PairCard({ task, job }: { task: JobTask; job: VerificationJob }) {
  const refIndex = job.references.findIndex(ref => ref.id === task.reference_id)
  const ref = job.references[refIndex]
  const result = task.pair_outcome?.verification
  const completed = task.state === 'completed' && result?.processing_status === 'completed'
  const verdict = completed && result.verdict ? verdicts[result.verdict] : undefined
  const provenance = task.source_binding?.provenance
  const sourceUrl = safeUrl(provenance?.final_url ?? provenance?.source_url ?? task.source_binding?.locator?.value ?? null)
  const confidence = result?.confidence
  return <article className="min-w-0 space-y-3 border-t border-border pt-4" data-testid="pair-card">
    <h3 className="break-words text-sm font-medium [overflow-wrap:anywhere]">{refIndex >= 0 ? 'R' + (refIndex + 1) + ' · ' : ''}{ref?.title ?? ref?.raw_text ?? task.reference_id}</h3>
    <p className="flex flex-wrap items-center gap-2">{!completed && <Badge>{task.state.replaceAll('_', ' ')}</Badge>}{verdict && <Badge variant={verdict.variant}>{verdict.label}</Badge>}{completed && typeof confidence === 'number' && Number.isFinite(confidence) && confidence >= 0 && confidence <= 1 && <span className="text-sm text-text-secondary">Confidence: {(confidence * 100).toFixed(0)}%</span>}</p>
    {!completed && <p className="text-sm text-text-secondary">{task.reason_code === 'DOI_MISSING' ? 'Reference identity is unresolved in this saved job. No scientific verdict was produced; this does not mean the claim is incorrect.' : task.state === 'blocked_source' ? 'Source Required · A matching full-text source is required. No scientific verdict was produced; this does not mean the claim is incorrect.' : task.state === 'failed' ? 'Processing failed. No scientific verdict was produced.' : 'Verification has not completed.'}</p>}
    {completed && result.explanation && <p className="break-words text-sm leading-relaxed [overflow-wrap:anywhere]">{result.explanation}</p>}
    {provenance && ['IDENTITY_UNCERTAIN', 'IDENTITY_CONFLICT'].includes(provenance.identity) && <p className="text-xs text-warning">The retrieved source may not match the cited reference. Treat this evidence with caution.</p>}
    {provenance?.identity === 'PROBABLE_SAME_WORK' && <p className="text-xs text-warning">The retrieved document is probably the same study, but may differ from the version originally cited. This is not an exact identity match.</p>}
    {provenance?.warnings.includes('HISTORICAL_VERSION_UNCONFIRMED') && <p className="text-xs text-warning">Historical Version Unconfirmed: current content may differ from the cited historical document.</p>}
    {provenance?.retrieved_title && provenance.retrieved_title !== ref?.title && <p className="text-xs text-text-secondary">Retrieved title: {provenance.retrieved_title}</p>}
    {sourceUrl && <a className="block break-all text-xs text-primary" href={sourceUrl} target="_blank" rel="noreferrer">Read reference</a>}
    {!!result?.evidence_chunks.length && <div className="space-y-2">{!completed && <p className="text-xs text-text-muted">Retained evidence · processing incomplete</p>}{result.evidence_chunks.map(chunk => <Evidence key={chunk.id} chunk={chunk} />)}</div>}
    {completed && !result.evidence_chunks.length && <p className="text-sm text-text-muted">No supporting passage was saved for this result.</p>}

  </article>
}

export function ReportExportSnapshot({ job, fileLabel, recovery, printMode = false, onRecheck, rechecking = false }: { job: VerificationJob; fileLabel?: string; recovery?: (referenceIds: string[]) => ReactNode; printMode?: boolean; onRecheck?: () => void; rechecking?: boolean }) {
  const [selection, setSelection] = useState('')
  const [includeAnalysis, setIncludeAnalysis] = useState(false)
  const [confirmAnalysis, setConfirmAnalysis] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [exportStage, setExportStage] = useState('')
  const [exportError, setExportError] = useState('')
  const [exportNotice, setExportNotice] = useState('')
  const [exportFormat, setExportFormat] = useState<ReportFormat>('pdf')
  const exportActive = useRef(false)
  async function exportReport() {
    if (exportActive.current) return
    exportActive.current = true
    setExporting(true)
    setExportStage('Choose a save location in the Save As dialog. It may be behind this window.')
    setExportError('')
    setExportNotice('')
    try {
      const destination = await chooseReportDestination(exportFormat, fileLabel || 'Whole-paper-' + job.job_id.slice(0, 16))
      if (!destination) return
      setExportStage(includeAnalysis ? 'Preparing quotations and AI analysis. This can take up to 3 minutes.' : 'Generating the report from saved evidence. No AI processing is required.')
      const { generateWholePaperFile } = await import('@/services/wholePaperPdf')
      const file = await generateWholePaperFile(job, exportFormat, fileLabel, includeAnalysis)
      setExportStage('Saving the report to the selected location...')
      await destination.save(file)
      setExportNotice(destination.downloadFallback
        ? 'Report downloaded. To choose a folder, enable Ask where to save each file in your browser download settings.'
        : 'Report saved to the selected location.')
    } catch {
      setExportError(includeAnalysis ? 'Unable to prepare or save the report. Check the AI service, API balance, backend connection and folder permissions, then retry.' : 'Unable to save the report. Check the backend connection and folder permissions, then retry.')
    } finally {
      exportActive.current = false
      setExporting(false)
      setExportStage('')
    }
  }
  const coverage = job.coverage
  const paragraphs = new Map(job.paragraphs.map(paragraph => [paragraph.id, paragraph]))
  const claims = [...job.claims].sort((a, b) => (paragraphs.get(a.paragraph_id)?.order ?? 0) - (paragraphs.get(b.paragraph_id)?.order ?? 0) || (a.source_spans[0]?.start ?? 0) - (b.source_spans[0]?.start ?? 0))
  const claim = claims.find(item => item.id === selection) ?? claims[0]
  const attention = job.tasks.find(task => task.resume_available && ['blocked_source', 'failed', 'pending'].includes(task.state))
  return <div className="min-w-0 space-y-4">
    <Panel className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold">Verification overview</h2><Badge variant={job.status === 'running' ? 'primary' : job.status === 'failed' ? 'danger' : 'default'}>{job.status.replaceAll('_', ' ')}</Badge></div>
      <p className="break-all text-sm">{fileLabel || job.manuscript_title || "Manuscript verification"}</p>
      <p className="text-sm">{coverage.total_claims} passages / {coverage.total_references} references</p>
      <p className="text-xs text-text-secondary">{coverage.completed_pairs} completed · {coverage.blocked_source_pairs} blocked · {coverage.failed_pairs} failed · {coverage.pending_pairs} pending · {coverage.running_pairs} running</p>
      {coverage.total_pairs > 0 ? <><progress className="h-2 w-full accent-primary" value={coverage.completed_pairs} max={coverage.total_pairs} aria-label="Completed Claim–Reference pairs" /><p className="text-xs text-text-muted">{coverage.completed_pairs}/{coverage.total_pairs} reference checks completed. Each conclusion below is tied to its reference.</p></> : <p className="text-sm">No reference checks could be started. This report does not yet establish whether the manuscript is supported.</p>}
      {(!coverage.coverage_complete && (coverage.ambiguous_claims + coverage.unresolved_claims + coverage.failed_extraction_contexts + coverage.skipped_extraction_contexts > 0)) && <p className="text-xs text-warning">Some passages could not be extracted or linked to references. This report covers only the passages shown below.</p>}
      {coverage.coverage_complete && <p className="text-xs text-text-secondary">Every planned pair finished processing. Review the individual verdicts below.</p>}
      {attention && recovery && <Button size="sm" variant="outline" onClick={() => setSelection(attention.claim_id)}>Review source or processing issues</Button>}
      {job.runtime_error_code && <div role="alert" className="text-sm text-warning">The worker could not finish this step. Committed results remain visible.</div>}
    </Panel>
    <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(13rem,0.36fr)_minmax(0,1fr)]">
      <Panel padding="sm" className="min-w-0 self-start"><h2 className="mb-3 text-sm font-semibold">Claims</h2>
        <nav aria-label="Claim navigator" className="max-h-[25dvh] space-y-1 overflow-y-auto overscroll-contain lg:max-h-[65dvh]">{claims.map((item, index) => {
          const pairs = job.tasks.filter(task => task.claim_id === item.id)
          const issue = pairs.some(task => ['blocked_source', 'failed'].includes(task.state)) || item.attribution_status !== 'resolved'
          return <button key={item.id} type="button" aria-pressed={item.id === claim?.id} onClick={() => setSelection(item.id)} className={'w-full min-w-0 rounded-lg p-3 text-left ' + (item.id === claim?.id ? 'bg-primary-muted text-primary' : 'text-text-secondary hover:bg-surface-hover')}>
            <span className="block text-xs font-semibold">Claim {String(index + 1).padStart(2, '0')}{issue ? ' · Needs attention' : ''}</span><span className="mt-1 line-clamp-2 break-words text-xs [overflow-wrap:anywhere]">{item.text}</span><span className="mt-1 block text-[11px] text-text-muted">{pairs.filter(task => task.state === 'completed').length}/{pairs.length} pairs completed{!pairs.length ? ' · No executable pairs' : ''}</span>
          </button>
        })}{!claims.length && <p className="text-sm text-text-muted">No claims recorded.</p>}</nav>
      </Panel>
      {(printMode ? (claims.length ? claims : [undefined]) : [claim]).map(claim => {
        const tasks = job.tasks.filter(task => task.claim_id === claim?.id)
        const paragraph = claim ? paragraphs.get(claim.paragraph_id) : undefined
        return <Panel key={printMode ? claim?.id ?? 'empty' : 'selected'} className="min-w-0 space-y-4" aria-label="Selected claim details">
        {claim ? <><div className="space-y-2"><h2 className="text-sm font-semibold text-text-muted">Claim {String(claims.indexOf(claim) + 1).padStart(2, '0')} / Original manuscript passage</h2>
          {paragraph && claim.source_spans.length > 0 ? <blockquote className="whitespace-pre-wrap break-words border-l-2 border-primary pl-4 font-medium leading-relaxed [overflow-wrap:anywhere]">{claim.source_spans.map(span => codePointSlice(paragraph.text, span.start, span.end)).filter(Boolean).join(' \u2026 ') || paragraph.text}</blockquote> : <><p className="text-xs text-text-muted">Exact passage location unavailable. Extracted statement:</p><p className="break-words font-medium leading-relaxed">{claim.text}</p></>}
          <p className="text-xs text-text-muted">{paragraph?.section ?? 'Manuscript'}{(claim.page ?? paragraph?.page) != null ? ' / Page ' + (claim.page ?? paragraph?.page) : ''}</p>
          {paragraph && claim.source_spans.length > 0 && claim.source_spans.map(span => codePointSlice(paragraph.text, span.start, span.end)).join(' \u2026 ').trim() !== claim.text.trim() && <p className="text-sm text-text-secondary">Statement checked: {claim.text}</p>}
          {paragraph && <details className="text-sm text-text-secondary" data-export-omit><summary className="cursor-pointer text-primary">Read surrounding paragraph</summary><p className="mt-2 whitespace-pre-wrap leading-relaxed">{paragraph.text}</p></details>}
          {claim.attribution_status !== 'resolved' && <p className="text-sm text-warning">The references for this passage need review.</p>}
        </div>
          {recovery?.(tasks.map(task => task.reference_id))}
          {tasks.map(task => <PairCard key={task.task_key} task={task} job={job} />)}
          {!tasks.length && <p className="text-sm text-text-secondary">No executable reference pairs for this claim. Attribution needs review.</p>}

        </> : <p className="text-sm text-text-muted">No accepted claims in this snapshot.</p>}
      </Panel>
      })}
    </div>
    <details className="rounded-xl border border-border bg-surface p-4"><summary className="cursor-pointer text-sm font-medium">References</summary><div aria-label="Reference list" className="mt-4 space-y-3">{job.references.map((reference, index) => {
      const url = safeUrl(reference.doi ? 'https://doi.org/' + reference.doi : reference.url ?? reference.resolution?.source_url ?? null)
      return <article key={reference.id} id={'reference-' + encodeURIComponent(reference.id)} className="text-sm"><p>R{index + 1} / {reference.raw_text || reference.title || 'Untitled reference'}</p>{url && <a className="text-xs text-primary underline" href={url} target="_blank" rel="noreferrer">Read reference</a>}</article>
    })}</div></details>
    {!printMode && <div className="flex flex-col items-end gap-2">
      {onRecheck && <Button variant="outline" loading={rechecking} disabled={['pending', 'running'].includes(job.status)} onClick={onRecheck} title="Run all saved claim-reference pairs again. Changed results are saved as a new numbered version.">Recheck</Button>}
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={includeAnalysis} disabled={exporting} onChange={event => setIncludeAnalysis(event.target.checked)} /><span>Include AI analysis in export</span></label>
      <div className="flex items-center gap-2">
        <select aria-label="Report file format" className="rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-primary" value={exportFormat} disabled={exporting} onChange={event => setExportFormat(event.target.value as ReportFormat)}>
          <option value="pdf">PDF (.pdf)</option><option value="docx">Word (.docx)</option>
        </select>
        <Button variant="outline" loading={exporting} onClick={() => includeAnalysis ? setConfirmAnalysis(true) : void exportReport()}>{exporting ? (includeAnalysis ? 'Preparing readable report...' : 'Exporting report...') : 'Export report'}</Button>
      </div>
      <Modal open={confirmAnalysis} onClose={() => setConfirmAnalysis(false)} title="Export with AI analysis" description="AI will select quotations and generate analysis. This may take up to 3 minutes. Keep this page open until the report is saved." size="sm">
        <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => setConfirmAnalysis(false)}>Cancel</Button><Button onClick={() => { setConfirmAnalysis(false); void exportReport() }}>Continue export</Button></div>
      </Modal>
      {exporting && <p role="status" className="text-sm text-text-secondary">{exportStage}</p>}
      {exportNotice && <p role="status" className="text-sm text-text-secondary">{exportNotice}</p>}
      {exportError && <p role="alert" className="text-sm text-danger">{exportError}</p>}
    </div>}
  </div>
}
