import { Badge } from '@/components/ui/Badge'
import type { Reference } from '@/types/manuscript'

export function ReferenceReview({ references }: { references: Reference[] }) {
  const matched = references.filter(r => r.resolution?.status === 'resolved').length
  const websites = references.filter(r => r.resolution?.status === 'non_doi_source').length
  return <div className="space-y-4">
    <p>{references.length} references · {matched} DOI identities ready · {websites} URL-based sources · {references.length - matched - websites} unresolved</p>
    <p className="text-sm text-text-secondary">Identity resolution finds the cited source. It does not verify a scientific claim or guarantee full text.</p>
    {references.map((ref, i) => {
      const result = ref.resolution
      return <div key={ref.id} className="space-y-2 rounded-lg border border-border p-3 text-sm">
        <p className="font-medium">{i + 1}. {ref.title ?? ref.raw_text}</p>
        <Badge variant={result?.status === 'resolved' ? 'success' : 'warning'}>{result?.status ?? 'unresolved'}</Badge>
        <p>Original DOI: {result?.original_doi ?? 'Not provided'} · Resolved DOI: {result?.resolved_doi ?? 'Unresolved'}</p>
        <p>Provider: {result?.provider ?? 'None'} · Source type: {result?.source_type ?? 'unknown'}</p>
        {result?.source_url && <p className="break-all">Original source URL: {result.source_url}</p>}
        {result?.status === 'non_doi_source' && <p className="text-warning">URL source discovered. Verification will attempt document retrieval and identity checks. The historical cited version is not yet confirmed.</p>}
        {result?.match_reason === 'VERSION_UNCERTAIN' && <p className="text-warning">A compatible preprint candidate may be retrieved for further identity checks. A probable match will keep its version warnings and will not replace the original citation.</p>}
        {result?.match_reason && <p>{result.match_reason}</p>}
        {!!result?.diagnostics.length && <p className="text-warning">{result.diagnostics.join(' · ')}</p>}
        {!!result?.candidates.length && <details><summary className="cursor-pointer text-primary">Matching evidence and candidates</summary>{result.candidates.map((c, j) => <div key={`${c.provider}-${c.doi}-${j}`} className="mt-2 space-y-1 border-t border-border pt-2">
          <p>{c.title} · {c.doi}</p><p>{c.authors.join(', ')} · {c.years.join(', ')} · {c.journal ?? 'Unknown journal'} · {c.publication_type ?? 'Unknown type'}</p>
          <p>Identity match score: {(c.match_confidence * 100).toFixed(0)}% · {c.rejection_reason ?? 'Identity criteria met'}</p><p>{c.evidence.join(' · ')}</p>
        </div>)}</details>}
      </div>
    })}
  </div>
}
