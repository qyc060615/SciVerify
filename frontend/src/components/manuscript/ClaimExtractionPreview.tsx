import { Badge } from '@/components/ui/Badge'
import { Panel } from '@/components/ui/Card'
import { codePointSlice } from '@/services/manuscriptBridge'
import type { ExtractionResult, ParsedDTO } from '@/types/manuscript'

export function ClaimExtractionPreview({ parsed, extraction }: { parsed: ParsedDTO; extraction: ExtractionResult }) {
  return <div className="space-y-4">
    <Panel className="space-y-3">
      <h2 className="text-lg font-semibold">Review extracted claims</h2>
      <Badge variant={extraction.status === 'completed' ? 'success' : 'warning'}>Extraction: {extraction.status}</Badge>
      <p className="text-sm text-text-secondary">{extraction.contexts.length} contexts · {extraction.claims.length} claims · {extraction.claims.filter(c => c.attribution_status === 'resolved').length} resolved · {extraction.claims.filter(c => c.attribution_status === 'ambiguous').length} ambiguous · {extraction.claims.filter(c => c.attribution_status === 'unresolved').length} unresolved</p>
      <p className="text-sm text-text-secondary">{extraction.context_results.filter(c => c.status === 'failed').length} failed contexts · {extraction.context_results.filter(c => c.status === 'skipped').length} skipped contexts</p>
      {extraction.status !== 'completed' && <p className="text-warning">Extraction has coverage gaps. Review every unresolved or failed context before continuing.</p>}
      {extraction.claims.length === 0 && <p>No claims were accepted. No verification tasks can be started.</p>}
      {[...extraction.diagnostics, ...extraction.context_results.flatMap(c => c.diagnostics)].map((d, i) => <p key={i} className="text-sm text-warning">{d.code}: {d.safe_message}</p>)}
    </Panel>
    {extraction.claims.map(claim => {
      const paragraph = parsed.paragraphs.find(p => p.id === claim.paragraph_id)
      return <Panel key={claim.id} className="space-y-3">
        <p className="font-medium leading-relaxed">{claim.text}</p>
        <Badge variant={claim.attribution_status === 'resolved' ? 'primary' : 'warning'}>Attribution: {claim.attribution_status ?? 'unknown'}</Badge>
        <div className="text-sm text-text-secondary">{claim.reference_ids.map(id => {
          const ref = parsed.references.find(r => r.id === id)
          return <p key={id}>{ref?.title ?? ref?.raw_text ?? id} · DOI: {ref?.doi ?? 'missing'}</p>
        })}</div>
        <details className="text-sm"><summary className="cursor-pointer text-primary">View original paragraph and citation spans</summary>
          <p className="mt-2 whitespace-pre-wrap leading-relaxed">{paragraph?.text}</p>
          <p className="text-text-muted">{paragraph?.section ?? 'Body'}{paragraph?.page != null ? ` · Page ${paragraph.page}` : ''}</p>
          {claim.source_spans.map((s, i) => <p key={i}>Source [{s.start}, {s.end}): {codePointSlice(paragraph?.text ?? '', s.start, s.end)}</p>)}
          {claim.citation_callout_ids.map(id => <p key={id}>Citation: {parsed.citation_callouts.find(c => c.id === id)?.text ?? id}</p>)}
        </details>
      </Panel>
    })}
  </div>
}
