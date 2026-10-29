import { DiagnosticDetails } from './DiagnosticDetails'
import { codePointSlice } from '@/services/manuscriptBridge'
import type { Claim, ExtractionResult, ParsedDTO } from '@/types/manuscript'

export function ClaimList({ parsed, claims }: { parsed: ParsedDTO; claims: Claim[] }) {
  return <div className="divide-y divide-border" aria-label="Claim review list">
    {claims.map((claim, index) => {
      const paragraph = parsed.paragraphs.find(p => p.id === claim.paragraph_id)
      return <article key={claim.id} className="min-w-0 space-y-1.5 py-3">
        <div className="flex items-center justify-between gap-3"><h3 className="text-xs font-semibold text-text-muted">Claim {String(index + 1).padStart(2, '0')}</h3><span role="status" aria-label={claim.attribution_status === 'resolved' ? 'Citation Attributed' : 'Needs Attention'} className={claim.attribution_status === 'resolved' ? 'text-success' : 'text-warning'}>{claim.attribution_status === 'resolved' ? '✓' : '!'}</span></div>
        <p className="break-words text-sm font-medium leading-relaxed [overflow-wrap:anywhere]">{claim.text}</p>
        <p className="text-xs text-text-secondary">Reference: {claim.reference_ids.length ? claim.reference_ids.map(id => { const index = parsed.references.findIndex(r => r.id === id); return index >= 0 ? 'R' + (index + 1) : id }).join(', ') : 'No resolved reference'}</p>
        <details className="text-xs text-text-secondary"><summary className="cursor-pointer text-primary">More details</summary>
          <div className="mt-3 space-y-2 break-words [overflow-wrap:anywhere]"><p>Attribution status: {claim.attribution_status ?? 'unknown'}</p>{claim.attribution_status === 'ambiguous' && <p>Citation attribution is ambiguous.</p>}{claim.attribution_status === 'unresolved' && <p>Citation attribution is unresolved.</p>}<p className="whitespace-pre-wrap leading-relaxed">{paragraph?.text}</p><p>{paragraph?.section ?? 'Body'}{paragraph?.page != null ? ' · Page ' + paragraph.page : ''}</p>
            {claim.source_spans.map((span, i) => <p key={i}>Source [{span.start}, {span.end}): {codePointSlice(paragraph?.text ?? '', span.start, span.end)}</p>)}
            {claim.citation_callout_ids.map(id => <p key={id}>Citation: {parsed.citation_callouts.find(call => call.id === id)?.text ?? id}</p>)}
            {claim.reference_ids.map(id => { const ref = parsed.references.find(r => r.id === id); return <p key={id}>{ref?.title ?? ref?.raw_text ?? id} · DOI: {ref?.doi ?? 'missing'}</p> })}
          </div>
        </details>
      </article>
    })}
  </div>
}

export function ClaimExtractionPreview({ parsed, extraction }: { parsed: ParsedDTO; extraction: ExtractionResult }) {
  return <div className="space-y-4">
    <div className="space-y-2"><h2 className="text-lg font-semibold">Review Claims</h2>
      <p className="text-sm">{extraction.claims.length} Claims · {extraction.claims.filter(c => c.attribution_status === 'resolved').length} Resolved · {extraction.claims.filter(c => c.attribution_status !== 'resolved').length} Need Attention</p>
      {extraction.status !== 'completed' && <p className="text-sm text-warning">Extraction has coverage gaps. Review unresolved claims and context diagnostics before continuing.</p>}
      {extraction.claims.length === 0 && <p className="text-sm">No claims were accepted. No executable pairs can be started.</p>}
    </div>
    <ClaimList parsed={parsed} claims={extraction.claims} />
    <DiagnosticDetails records={extraction.diagnostics.length ? extraction.diagnostics : extraction.context_results.flatMap(context => context.diagnostics)} heading="Extraction Diagnostics">
      <p className="text-xs">Extraction status: {extraction.status}</p>
      <p className="text-xs">{extraction.contexts.length} contexts · {extraction.context_results.filter(c => c.status === 'failed').length} failed contexts · {extraction.context_results.filter(c => c.status === 'skipped').length} skipped contexts</p>
      <details><summary className="cursor-pointer text-xs text-primary">Original context results and rejected proposals</summary><div className="mt-2 space-y-2">{extraction.context_results.map(context => <div key={context.context_id} className="break-all text-xs"><p>{context.context_id}: {context.status}</p>{context.diagnostics.map((d, i) => <p key={i}>{d.code}: {d.safe_message}</p>)}{context.rejected_proposals.map(proposal => <p key={proposal.proposal_index}>Proposal {proposal.proposal_index}: {proposal.reason_code}</p>)}</div>)}</div></details>
    </DiagnosticDetails>
  </div>
}
