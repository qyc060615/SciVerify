import { useRef, useState, type ReactNode } from 'react'
import { Panel } from '@/components/ui/Card'
import { Badge, type BadgeVariant } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import type { DomainVerdict, JobTask, VerificationJob, EvidenceChunk } from '@/types/verification-job'
import { codePointSlice } from '@/services/manuscriptBridge'
import { ReferenceReview } from './ReferenceReview'
import { DiagnosticDetails } from './DiagnosticDetails'
import { recoverableReferenceIds } from '@/services/sourceRecovery'

const verdicts: Record<DomainVerdict, { label: string; variant: BadgeVariant }> = {
  SUPPORTED: { label: 'Supported', variant: 'success' }, PARTIALLY_SUPPORTED: { label: 'Partially supported', variant: 'warning' },
  OVERSTATED: { label: 'Overstated', variant: 'warning' }, CONTRADICTED: { label: 'Contradicted', variant: 'danger' }, INSUFFICIENT: { label: 'Insufficient evidence', variant: 'muted' },
}
function pairVerdict(task: JobTask) {
  const result = task.pair_outcome?.verification
  return task.state === 'completed' && result?.processing_status === 'completed' && result.verdict ? verdicts[result.verdict] : undefined
}
function PairStatus({ task, prefix = '' }: { task: JobTask; prefix?: string }) {
  const verdict = pairVerdict(task)
  const label = verdict?.label ?? (task.state === 'blocked_source' ? 'Source Required' : task.state === 'failed' ? 'Processing Failed' : task.state === 'running' ? 'Processing' : 'Not Verified')
  return <Badge variant={verdict?.variant ?? 'muted'} className={verdict && task.pair_outcome?.verification.verdict === 'OVERSTATED' ? 'border-orange-400/20 bg-orange-400/10 text-orange-400' : undefined}>{prefix}{label}</Badge>
}
function safeUrl(value: string | null): string | undefined {
  try { const url = new URL(value ?? ''); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : undefined } catch { return undefined }
}
function Evidence({ chunk, task, first }: { chunk: EvidenceChunk; task: JobTask; first: boolean }) {
  const url = safeUrl(chunk.source_url)
  const identity = chunk.metadata.source_identity_status === 'confirmed' ? 'confirmed' : chunk.metadata.source_identity_status === 'uncertain' ? 'uncertain' : 'unknown'
  return <details open={first} className="min-w-0 rounded-lg bg-surface-elevated/50 p-3 text-sm">
    <summary className="cursor-pointer font-medium">Evidence · {chunk.section ?? 'Body'}{chunk.page != null ? ' · Page ' + chunk.page : ''} · Identity: {identity}</summary>
    <blockquote className="mt-3 whitespace-pre-wrap break-words leading-relaxed [overflow-wrap:anywhere]">{chunk.text}</blockquote>
    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-secondary">{url && <a className="break-all text-primary underline" href={url} target="_blank" rel="noreferrer">Open source</a>}{chunk.retrieval_score != null && Number.isFinite(chunk.retrieval_score) && <span>Retrieval score: {chunk.retrieval_score}</span>}</div>
    <details className="mt-2 text-xs text-text-muted"><summary className="cursor-pointer">Evidence identifiers</summary><p className="break-all">Chunk: {chunk.id}</p><p className="break-all">Source Document ID: {chunk.source_document_id}</p><p className="break-all">Source version: {task.source_version ?? 'unknown'}</p>{typeof chunk.metadata.parsed_content_fingerprint === 'string' && <p className="break-all">Parsed fingerprint: {chunk.metadata.parsed_content_fingerprint}</p>}<pre className="mt-2 whitespace-pre-wrap break-all">{JSON.stringify(chunk.metadata, null, 2)}</pre></details>
  </details>
}
function PairCard({ task, job }: { task: JobTask; job: VerificationJob }) {
  const refIndex = job.references.findIndex(ref => ref.id === task.reference_id)
  const ref = job.references[refIndex]
  const result = task.pair_outcome?.verification
  const completed = task.state === 'completed' && result?.processing_status === 'completed'
  const provenance = task.source_binding?.provenance
  const sourceUrl = safeUrl(provenance?.final_url ?? provenance?.source_url ?? task.source_binding?.locator?.value ?? null)
  const identities = { EXACT_IDENTITY: 'Exact', PROBABLE_SAME_WORK: 'Probable Same Work', IDENTITY_UNCERTAIN: 'Uncertain', IDENTITY_CONFLICT: 'Conflict' }
  const confidence = result?.confidence
  return <article className="min-w-0 space-y-3 border-t border-border pt-4" data-testid="pair-card">
    <h3 className="break-words text-sm font-medium [overflow-wrap:anywhere]">{refIndex >= 0 ? 'R' + (refIndex + 1) + ' · ' : ''}{ref?.title ?? ref?.raw_text ?? task.reference_id}</h3>
    <p className="break-all text-xs text-text-muted">{task.source_binding?.locator?.kind === 'url' ? 'URL Source: ' + task.source_binding.locator.value : 'DOI Source: ' + (task.source_binding?.doi ?? ref?.doi ?? 'Identity not resolved')}</p>
    <div className="flex flex-wrap items-center gap-2"><PairStatus task={task} />{pairVerdict(task) && typeof confidence === 'number' && Number.isFinite(confidence) && confidence >= 0 && confidence <= 1 && <span className="text-xs text-text-muted">Confidence: {(confidence * 100).toFixed(0)}%</span>}</div>
    {!completed && <p className="text-sm text-text-secondary">{task.reason_code === 'DOI_MISSING' ? 'Reference identity is unresolved in this saved job. No scientific verdict was produced; this does not mean the claim is incorrect.' : task.state === 'blocked_source' ? 'Source Required · A matching full-text source is required. No scientific verdict was produced; this does not mean the claim is incorrect.' : task.state === 'failed' ? 'Processing failed. No scientific verdict was produced.' : 'Verification has not completed.'}</p>}
    {completed && result.explanation && <p className="break-words text-sm leading-relaxed [overflow-wrap:anywhere]">{result.explanation}</p>}
    {provenance && <p className="text-xs text-text-secondary">Identity: {identities[provenance.identity]} · {task.source_version ? 'Source version recorded' : 'No source version recorded'}</p>}
    {provenance?.identity === 'PROBABLE_SAME_WORK' && <p className="text-xs text-warning">The retrieved document is probably the same study, but may differ from the version originally cited. This is not an exact identity match.</p>}
    {provenance?.warnings.includes('HISTORICAL_VERSION_UNCONFIRMED') && <p className="text-xs text-warning">Historical Version Unconfirmed: current content may differ from the cited historical document.</p>}
    {sourceUrl && <a className="block break-all text-xs text-primary" href={sourceUrl} target="_blank" rel="noreferrer">Actual source URL: {sourceUrl}</a>}
    {!!result?.evidence_chunks.length && <div className="space-y-2">{!completed && <p className="text-xs text-text-muted">Retained evidence · processing incomplete</p>}{result.evidence_chunks.map((chunk, index) => <Evidence key={chunk.id} chunk={chunk} task={task} first={index === 0} />)}</div>}
    <details className="min-w-0 text-xs text-text-muted"><summary className="cursor-pointer">Technical details &amp; traceability</summary>
      <div className="mt-2 space-y-2 break-words [overflow-wrap:anywhere]"><p>Claim: {task.claim_id} · Reference: {task.reference_id}</p><p>Processing: {result?.processing_status ?? task.state} · Attempt: {task.attempt}</p><p>Reason: {task.reason_code ?? 'None'}</p><p>Source Document ID: {task.source_binding?.source_document_id ?? 'unavailable'}</p><p>Source version: {task.source_version ?? 'unavailable'}</p><p>Expected raw hash: {task.expected_raw_hash ?? 'None'}</p><p>Trace method: {result?.traceability?.method ?? 'none'}</p>{result?.traceability?.warnings.map((warning, i) => <p key={i}>{warning}</p>)}<p>Evidence IDs: {result?.traceability?.evidence_ids.join(', ') ?? 'none'}</p>
        {provenance && <><p>Retrieved title: {provenance.retrieved_title ?? 'Not recorded'}</p><p>Publication / update date: {provenance.publication_date ?? 'Not recorded'}</p><p>Retrieved at: {provenance.retrieved_at ?? 'Not recorded'}</p><p>Retrieved version / content hash: {provenance.retrieved_version ?? task.source_version ?? 'Unavailable'}</p>{provenance.warnings.map((warning, i) => <p key={i}>{warning}</p>)}<p>{provenance.match_evidence.join(' · ')}</p></>}
        <pre className="whitespace-pre-wrap break-all">{JSON.stringify({ binding: task.source_binding, traceability: result?.traceability, legacy_verdict: task.pair_outcome?.legacy_verdict, last_error_code: task.last_error_code }, null, 2)}</pre>
      </div>
    </details>
  </article>
}

export function WholePaperReport({ job, fileLabel, recovery }: { job: VerificationJob; fileLabel?: string; recovery?: (referenceIds: string[]) => ReactNode }) {
  const coverage = job.coverage
  const recoveryPanel = useRef<HTMLDetailsElement>(null)
  const [selectedReferences, setSelectedReferences] = useState<string[] | null>(null)
  const [showReferences, setShowReferences] = useState(false)
  const recoverable = recoverableReferenceIds(job)
  function showRecovery(ids: string[]) {
    setSelectedReferences(ids)
    if (recoveryPanel.current) {
      recoveryPanel.current.open = true
      recoveryPanel.current.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
    }
  }
  return <div className="min-w-0 space-y-4">
    <Panel className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold">Verification overview</h2><Badge variant={job.status === 'running' ? 'primary' : job.status === 'failed' ? 'danger' : 'default'}>{job.status.replaceAll('_', ' ')}</Badge></div>
      <p className="break-words text-sm [overflow-wrap:anywhere]">{fileLabel || 'Saved job ' + job.job_id.slice(0, 16) + '…'}</p>
      <p className="text-sm">{job.claims.length} claims · {coverage.completed_pairs}/{coverage.total_pairs} pairs processed</p>
      {coverage.total_pairs > 0 ? <progress className="h-1.5 w-full accent-primary" value={coverage.completed_pairs} max={coverage.total_pairs} aria-label="Completed Claim–Reference pairs" /> : <p className="text-sm">No executable pairs. Completion percentage is not applicable.</p>}
      {coverage.total_pairs > 0 && <p className="text-xs text-text-muted">Processing progress does not indicate scientific support.</p>}
      {!coverage.coverage_complete && (coverage.ambiguous_claims + coverage.unresolved_claims + coverage.failed_extraction_contexts + coverage.skipped_extraction_contexts > 0) && <p className="text-xs text-warning">Extraction or attribution coverage is incomplete. Review affected claims and diagnostics.</p>}
      {recovery && recoverable.length > 0 && <div className="space-y-2"><p className="text-sm text-warning">{recoverable.length} references need source recovery or a processing retry.</p><div className="flex flex-wrap gap-2">{recoverable.map(id => <Button key={id} size="sm" variant="outline" onClick={() => showRecovery([id])}>Recover R{job.references.findIndex(ref => ref.id === id) + 1}</Button>)}</div></div>}
      {job.runtime_error_code && <p role="alert" className="text-sm text-warning">The worker could not finish this step. Committed results remain visible.</p>}
    </Panel>
    {recovery && recoverable.length > 0 && <details ref={recoveryPanel} className="min-w-0 rounded-xl border border-border p-4"><summary className="cursor-pointer text-sm text-primary" onClick={() => setSelectedReferences(null)}>Source recovery</summary><div className="mt-3">{recovery(selectedReferences ?? recoverable)}</div></details>}
    <div className="space-y-3" aria-label="Claim results">
      {job.claims.map((claim, index) => {
        const tasks = job.tasks.filter(task => task.claim_id === claim.id)
        const paragraph = job.paragraphs.find(item => item.id === claim.paragraph_id)
        const single = tasks.length === 1 ? tasks[0] : undefined
        const multipleReferences = new Set([...claim.reference_ids, ...tasks.map(task => task.reference_id)]).size > 1
        const opinion = single && !multipleReferences && pairVerdict(single) ? single.pair_outcome?.verification.explanation : null
        const blocked = job.attribution_blocked.find(item => item.claim_id === claim.id)
        return <article key={claim.id} className="min-w-0 space-y-2 rounded-xl border border-border bg-surface px-4 py-3" data-testid="claim-result">
          <div className="flex flex-wrap items-start justify-between gap-2"><h2 className="text-xs font-semibold text-text-muted">Claim {String(index + 1).padStart(2, '0')}</h2>
            <div className="flex min-w-0 flex-wrap justify-end gap-1.5" aria-label="Pair verdicts">
              {!tasks.length ? <Badge variant="warning">Needs Attention</Badge> : tasks.length > 3 ? <Badge>{tasks.length} reference results</Badge> : tasks.map(task => <PairStatus key={task.task_key} task={task} prefix={multipleReferences ? 'R' + (job.references.findIndex(ref => ref.id === task.reference_id) + 1) + ': ' : ''} />)}
            </div>
          </div>
          <p className="break-words text-sm font-medium leading-relaxed [overflow-wrap:anywhere]">{claim.text}</p>
          {opinion && <p className="line-clamp-2 whitespace-pre-wrap break-words text-sm text-text-secondary [overflow-wrap:anywhere]">{opinion}</p>}
          {!tasks.length && <p className="text-sm text-text-secondary">{claim.attribution_status === 'ambiguous' ? 'Citation attribution is ambiguous.' : claim.attribution_status === 'unresolved' ? 'Citation attribution is unresolved.' : 'No executable reference pairs were recorded.'}</p>}
          {tasks.some(task => task.state === 'blocked_source') && <p className="text-sm text-text-secondary">Source Required{recovery && tasks.some(task => recoverable.includes(task.reference_id)) && <> · <button type="button" className="text-primary underline" onClick={() => showRecovery(tasks.filter(task => recoverable.includes(task.reference_id)).map(task => task.reference_id))}>Add or recover source</button></>}</p>}
          <details className="min-w-0 text-sm text-text-secondary"><summary className="cursor-pointer text-xs text-primary">More details</summary><div className="mt-3 space-y-3">
            {tasks.map(task => <PairCard key={task.task_key} task={task} job={job} />)}
            <details className="text-xs"><summary className="cursor-pointer">Original context &amp; attribution</summary><div className="mt-2 space-y-2 break-words [overflow-wrap:anywhere]"><p>Attribution status: {claim.attribution_status ?? 'unknown'}</p>{blocked && <p>Recorded reason: {blocked.reason_code}</p>}<p className="whitespace-pre-wrap">{paragraph?.text}</p><p>{paragraph?.section ?? 'Body'}{(claim.page ?? paragraph?.page) != null ? ' · Page ' + (claim.page ?? paragraph?.page) : ''}</p>{claim.source_spans.map((span, i) => <p key={i}>Span [{span.start}, {span.end}): {codePointSlice(paragraph?.text ?? '', span.start, span.end)}</p>)}{claim.citation_callout_ids.map(id => <p key={id}>Citation: {job.citation_callouts.find(call => call.id === id)?.text ?? id}</p>)}{claim.reference_ids.map(id => { const ref = job.references.find(item => item.id === id); return <p key={id}>{id}: {ref?.title ?? ref?.raw_text ?? 'Not recorded'}</p> })}</div></details>
          </div></details>
        </article>
      })}
      {!job.claims.length && <p className="text-sm text-text-muted">No accepted claims in this snapshot.</p>}
    </div>
    <details className="min-w-0 rounded-xl border border-border bg-surface p-4 text-xs text-text-muted"><summary className="cursor-pointer text-sm">Technical Details &amp; Diagnostics</summary>
      <div className="mt-3 space-y-3 break-words [overflow-wrap:anywhere]"><p>Job ID: {job.job_id} · Revision: {job.revision}</p><p>Recorded manuscript title (not independently verified): {job.manuscript_title ?? 'Unavailable'}</p><p>Manuscript ID: {job.manuscript_id}</p><p>Input fingerprint: {job.extraction_metadata.input_fingerprint}</p><p>Worker diagnostic: {job.runtime_error_code ?? 'None'}</p>
        <p>{coverage.blocked_source_pairs} blocked pairs · {coverage.failed_pairs} failed pairs · {coverage.pending_pairs} pending pairs · {coverage.running_pairs} running pairs</p>
        <p>Coverage gaps: {coverage.ambiguous_claims} ambiguous claims · {coverage.unresolved_claims} unresolved claims · {coverage.failed_extraction_contexts} failed contexts · {coverage.skipped_extraction_contexts} skipped contexts.</p>
        <details onToggle={event => setShowReferences(event.currentTarget.open)}><summary className="cursor-pointer">References &amp; identity diagnostics</summary>{showReferences && <div className="mt-3"><ReferenceReview references={job.references} anchors /></div>}</details>
        <DiagnosticDetails records={job.extraction_diagnostics?.length ? job.extraction_diagnostics : job.context_results.flatMap(context => context.diagnostics)} heading="Extraction Diagnostics">{job.attribution_blocked.map(item => <p key={item.claim_id}>{item.claim_id}: {item.reason_code}</p>)}{job.context_results.map(context => <div key={context.context_id}><p>Context {context.context_id}: {context.status}</p>{context.diagnostics.map((d, i) => <p key={i}>{d.code}: {d.safe_message}</p>)}{context.rejected_proposals.map(proposal => <p key={proposal.proposal_index}>Proposal {proposal.proposal_index}: {proposal.reason_code}</p>)}</div>)}</DiagnosticDetails>
      </div>
    </details>
  </div>
}
