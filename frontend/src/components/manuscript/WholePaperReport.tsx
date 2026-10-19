import { Panel } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import type { BadgeVariant } from '@/components/ui/Badge'
import type { DomainVerdict, JobTask, VerificationJob } from '@/types/verification-job'
import { codePointSlice } from '@/services/manuscriptBridge'
import { ReferenceReview } from '@/components/manuscript/ReferenceReview'

const verdicts: Record<DomainVerdict, { label: string; variant: BadgeVariant }> = {
  SUPPORTED: { label: 'Supported', variant: 'success' }, PARTIALLY_SUPPORTED: { label: 'Partially supported', variant: 'warning' },
  OVERSTATED: { label: 'Overstated', variant: 'warning' }, CONTRADICTED: { label: 'Contradicted', variant: 'danger' }, INSUFFICIENT: { label: 'Insufficient evidence', variant: 'muted' },
}
function safeUrl(value: string | null): string | undefined {
  try { const u = new URL(value ?? ''); return ['http:', 'https:'].includes(u.protocol) && !u.username && !u.password ? u.href : undefined } catch { return undefined }
}
function PairCard({ task, job }: { task: JobTask; job: VerificationJob }) {
  const ref = job.references.find(r => r.id === task.reference_id)
  const result = task.pair_outcome?.verification
  const completed = task.state === 'completed' && result?.processing_status === 'completed'
  const verdict = completed && result.verdict ? verdicts[result.verdict] : undefined
  const binding = task.source_binding
  const provenance = binding?.provenance
  const locator = binding?.locator
  const sourceUrl = safeUrl(provenance?.final_url ?? locator?.value ?? null)
  const identities = { EXACT_IDENTITY: 'Exact', PROBABLE_SAME_WORK: 'Probable Same Work', IDENTITY_UNCERTAIN: 'Uncertain', IDENTITY_CONFLICT: 'Conflict' }
  return <div className="space-y-3 rounded-lg border border-border bg-surface p-4" data-testid="pair-card">
    <p className="text-sm font-medium">{ref?.title ?? ref?.raw_text ?? task.reference_id}</p>
    <p className="text-sm text-text-muted">{locator?.kind === 'url' ? `URL Source: ${locator.value}` : `DOI Source: ${binding?.doi ?? ref?.doi ?? 'Identity not resolved'}`}</p>
    {provenance && <div className="space-y-1 text-sm">
      <p>Identity: {identities[provenance.identity]} · Full Text: {task.source_version ? 'Available' : 'Unavailable'}</p>
      {provenance.identity === 'PROBABLE_SAME_WORK' && <p className="text-warning">The retrieved document is probably the same study, but may differ from the version originally cited. This is not an exact identity match.</p>}
      {provenance.retrieved_title && <p>Retrieved title: {provenance.retrieved_title}</p>}
      {provenance.publication_date && <p>Publication / update date: {provenance.publication_date}</p>}
      {provenance.retrieved_at && <p>Retrieved at: {provenance.retrieved_at}</p>}
      <p className="break-all">Retrieved version / content hash: {provenance.retrieved_version ?? task.source_version ?? 'Unavailable'}</p>
      {sourceUrl && <a className="break-all text-primary" href={sourceUrl} target="_blank" rel="noreferrer">Actual source URL: {sourceUrl}</a>}
      {provenance.warnings.map(w => <p key={w} className="text-warning">{w === 'HISTORICAL_VERSION_UNCONFIRMED' ? 'Historical Version Unconfirmed: current content may differ from the cited historical document.' : w}</p>)}
    </div>}
    <div className="flex flex-wrap items-center gap-2"><Badge>Task: {task.state.replaceAll('_', ' ')}</Badge>{verdict && <Badge variant={verdict.variant}>{verdict.label}</Badge>}{completed && result.confidence != null && <span className="text-xs text-text-muted">Confidence: {(result.confidence * 100).toFixed(0)}%</span>}</div>
    {!completed && <p className="text-sm text-warning">{task.reason_code === 'DOI_MISSING' ? 'Reference identity is unresolved in this saved job. No scientific verdict was produced; this does not mean the claim is incorrect.' : task.state === 'blocked_source' ? 'A matching full-text source is required. No scientific verdict was produced; this does not mean the claim is incorrect.' : task.state === 'failed' ? 'Processing failed. No scientific verdict was produced.' : 'Verification has not completed.'}</p>}
    {completed && result.explanation && <p className="text-sm leading-relaxed">{result.explanation}</p>}
    {task.reason_code && <p className="text-xs text-text-muted">Reason: {task.reason_code}</p>}
    {result?.evidence_chunks.map(chunk => {
      const identity = chunk.metadata.source_identity_status === 'confirmed' ? 'confirmed' : chunk.metadata.source_identity_status === 'uncertain' ? 'uncertain' : 'unknown'
      const url = safeUrl(chunk.source_url)
      const versionLabel = chunk.metadata.content_hash_kind === 'raw_bytes' ? 'Raw source version' : chunk.metadata.content_hash_kind === 'parsed_chunks' ? 'Parsed source version' : 'Source version'
      return <details key={chunk.id} className="rounded-lg border border-border-subtle p-3 text-sm">
        <summary className="cursor-pointer">Evidence · {chunk.section ?? 'Body'}{chunk.page != null ? ` · Page ${chunk.page}` : ''} · Identity: {identity}</summary>
        <p className="mt-3 whitespace-pre-wrap leading-relaxed">{chunk.text}</p>
        <p className="mt-3 text-xs text-text-muted">Source DOI: {task.source_binding?.doi ?? ref?.doi ?? 'unknown'}</p>
        {url && <a className="break-all text-primary hover:underline" href={url} target="_blank" rel="noreferrer">Open source</a>}
        {chunk.retrieval_score != null && <p>Retrieval score: {chunk.retrieval_score}</p>}
        <p className="break-all text-xs text-text-muted">Chunk: {chunk.id}</p>
        <p className="break-all text-xs text-text-muted">{versionLabel}: {task.source_version ?? 'unknown'}</p>
        {typeof chunk.metadata.parsed_content_fingerprint === 'string' && <p className="break-all text-xs text-text-muted">Parsed fingerprint: {chunk.metadata.parsed_content_fingerprint}</p>}
      </details>
    })}
    <details className="text-xs text-text-muted"><summary className="cursor-pointer">Technical details &amp; traceability</summary>
      <p className="break-all">Claim: {task.claim_id} · Reference: {task.reference_id}</p>
      <p>Processing: {result?.processing_status ?? task.state} · Attempt: {task.attempt}</p>
      <p className="break-all">Source: {task.source_binding?.source_document_id ?? 'unavailable'} · Version: {task.source_version ?? 'unavailable'}</p>
      <p>Trace method: {result?.traceability?.method ?? 'none'}</p>
      {result?.traceability?.warnings.map((w, i) => <p key={i}>{w}</p>)}
      <p className="break-all">Evidence IDs: {result?.traceability?.evidence_ids.join(', ') ?? 'none'}</p>
    </details>
  </div>
}

export function WholePaperReport({ job }: { job: VerificationJob }) {
  const c = job.coverage
  const percent = c.total_pairs > 0 ? (c.completed_pairs / c.total_pairs) * 100 : 0
  const paragraphs = new Map(job.paragraphs.map(p => [p.id, p]))
  const claims = [...job.claims].sort((a, b) => (paragraphs.get(a.paragraph_id)?.order ?? 0) - (paragraphs.get(b.paragraph_id)?.order ?? 0) || (a.source_spans[0]?.start ?? 0) - (b.source_spans[0]?.start ?? 0))
  return <div className="space-y-5">
    <Panel className="space-y-4">
      <div className="flex flex-wrap justify-between gap-2"><h2 className="font-semibold">Verification overview</h2><Badge variant={job.status === 'running' ? 'primary' : job.status === 'failed' ? 'danger' : 'default'}>{job.status.replaceAll('_', ' ')}</Badge></div>
      <p>{c.total_claims} claims · {c.total_references} references · {c.total_pairs} pairs</p>
      <p className="text-sm">{c.completed_pairs} completed · {c.blocked_source_pairs} blocked · {c.failed_pairs} failed · {c.pending_pairs} pending · {c.running_pairs} running</p>
      {c.total_pairs > 0 ? <><progress className="h-2 w-full accent-primary" value={c.completed_pairs} max={c.total_pairs} aria-label="Completed Claim–Reference pairs" /><p className="text-sm text-text-secondary">{percent.toFixed(0)}% processing completed ({c.completed_pairs}/{c.total_pairs} pairs). Scientific verdicts are shown per pair.</p></> : <p>No executable pairs. Completion percentage is not applicable.</p>}
      {!c.coverage_complete && <p className="text-warning">Coverage is incomplete: {c.ambiguous_claims} ambiguous claims, {c.unresolved_claims} unresolved claims, {c.failed_extraction_contexts} failed contexts, {c.skipped_extraction_contexts} skipped contexts.</p>}
      {c.coverage_complete && <p className="text-text-secondary">Every planned pair finished processing. Review the individual verdicts below.</p>}
      {job.runtime_error_code && <p role="alert" className="text-warning">Worker diagnostic: {job.runtime_error_code}. Committed results remain visible.</p>}
    </Panel>
    {claims.map(claim => {
      const paragraph = paragraphs.get(claim.paragraph_id)
      const tasks = job.tasks.filter(t => t.claim_id === claim.id)
      return <Panel key={claim.id} className="space-y-4">
        <div className="space-y-2"><p className="font-medium leading-relaxed">{claim.text}</p><p className="text-xs text-text-muted">{paragraph?.section ?? 'Body'}{(claim.page ?? paragraph?.page) != null ? ` · Page ${claim.page ?? paragraph?.page}` : ''}</p><Badge variant={claim.attribution_status === 'resolved' ? 'primary' : 'warning'}>Attribution: {claim.attribution_status ?? 'unknown'}</Badge></div>
        <details className="text-sm"><summary className="cursor-pointer text-primary">Original context &amp; references</summary><p className="mt-2 whitespace-pre-wrap">{paragraph?.text}</p>{claim.source_spans.map((s, i) => <p key={i}>Span [{s.start}, {s.end}): {codePointSlice(paragraph?.text ?? '', s.start, s.end)}</p>)}{claim.citation_callout_ids.map(id => <p key={id}>Citation: {job.citation_callouts.find(call => call.id === id)?.text ?? id}</p>)}{claim.reference_ids.map(id => <a key={id} className="mr-2 text-primary" href={`#reference-${encodeURIComponent(id)}`}>{id}</a>)}</details>
        {tasks.map(task => <PairCard key={task.task_key} task={task} job={job} />)}
        {tasks.length === 0 && <p className="text-warning">No executable reference pairs for this claim. Attribution needs review.</p>}
      </Panel>
    })}
    <Panel className="space-y-3"><h2 className="font-semibold">References</h2>{job.references.map(ref => <div key={ref.id} id={`reference-${encodeURIComponent(ref.id)}`} className="scroll-mt-4 border-t border-border pt-3 text-sm"><p>{ref.title ?? ref.raw_text}</p><p className="text-text-muted">{ref.id} · DOI: {ref.doi ?? 'missing'}</p></div>)}</Panel>
    {job.references.some(r => r.resolution) && <Panel className="space-y-3"><h2 className="font-semibold">Reference identity diagnostics</h2><ReferenceReview references={job.references} /></Panel>}
    <Panel className="space-y-3"><h2 className="font-semibold">Coverage gaps &amp; diagnostics</h2>{job.attribution_blocked.map(item => <p key={item.claim_id} className="text-sm text-warning">{item.claim_id}: {item.reason_code}</p>)}{[...(job.extraction_diagnostics ?? []), ...job.context_results.flatMap(r => r.diagnostics)].map((d, i) => <p key={i} className="text-sm text-text-secondary">{d.code}: {d.safe_message}</p>)}{job.context_results.filter(r => r.status !== 'completed').map(r => <p key={r.context_id} className="text-sm text-warning">Context {r.context_id}: {r.status}</p>)}</Panel>
  </div>
}
