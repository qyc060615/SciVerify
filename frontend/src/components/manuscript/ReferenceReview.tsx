import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { PdfPicker } from './PdfPicker'
import { getUploadLimits, validatePdf } from '@/services/manuscriptService'
import { uploadManualSource } from '@/services/verificationService'
import { getLocalSourceStatus, referenceLocator } from '@/services/sourceService'
import { wholePaperError } from '@/services/wholePaperErrors'
import type { Reference } from '@/types/manuscript'

function ReferenceSource({ reference, onBusy }: { reference: Reference; onBusy?: (id: string, busy: boolean) => void }) {
  const locator = referenceLocator(reference)
  const client = useQueryClient()
  const status = useQuery({ queryKey: ['local-source', locator?.kind, locator?.value], queryFn: ({ signal }) => getLocalSourceStatus(locator!, signal), enabled: !!locator, retry: false, staleTime: 0 })
  const [adding, setAdding] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const active = useRef(false)
  const limits = useQuery({ queryKey: ['manuscript-upload-limits'], queryFn: ({ signal }) => getUploadLimits(signal), enabled: adding, retry: false })
  const available = !status.isFetching && !status.isError && status.data?.availability === 'available' && /^[a-f0-9]{64}$/.test(status.data.raw_content_sha256 ?? '') && ['pdf', 'html'].includes(status.data.format ?? '')
  async function upload() {
    if (active.current || !reference.doi || !limits.data) return
    const invalid = validatePdf(file, limits.data.source_max_bytes)
    if (invalid) { setMessage(invalid); return }
    active.current = true; setBusy(true); onBusy?.(reference.id, true); setMessage('')
    try {
      const receipt = await uploadManualSource(reference.doi, file!)
      if (receipt.status !== 'accepted' || receipt.doi.toLowerCase() !== reference.doi.toLowerCase() || !/^[a-f0-9]{64}$/.test(receipt.raw_content_sha256)) throw new Error('The backend did not confirm a matching saved source.')
      const checked = await status.refetch()
      if (checked.isError || checked.data?.availability !== 'available' || checked.data.raw_content_sha256 !== receipt.raw_content_sha256) throw new Error('Upload accepted, but the saved file could not be confirmed. Check local source availability before relying on it.')
      setMessage('PDF saved and verified in the local source store. Verification can reuse this DOI source.'); setFile(null); setAdding(false)
      void client.invalidateQueries({ queryKey: ['local-literature-repository'] })
    } catch (error) { setMessage(wholePaperError(error)) }
    finally { active.current = false; setBusy(false); onBusy?.(reference.id, false) }
  }
  return <div className="space-y-2">
    <p className={'text-xs ' + (available ? 'text-success' : 'text-text-muted')}>{available ? 'Full text: Available locally (' + status.data!.format!.toUpperCase() + ')' : status.isFetching ? 'Checking local source…' : 'Full text: Not checked'}</p>
    <details className="text-xs text-text-secondary"><summary className="cursor-pointer text-primary">Source details{!available && reference.doi ? ' · Add Source' : ''}</summary>
      <div className="mt-3 space-y-3">
        {available ? <p className="break-all font-mono">SHA-256: {status.data!.raw_content_sha256}</p> : <>
          <p>{status.isError ? 'Local source status could not be read.' : 'No usable local copy has been confirmed.'} Automatic full-text retrieval has not run; you may continue without uploading.</p>
          {reference.doi ? !adding && <Button size="sm" variant="outline" onClick={() => setAdding(true)}>Add Source</Button> : <p>Manual PDF validation currently requires a DOI. URL sources can be fetched and recovered from the task report.</p>}
        </>}
        {adding && !available && <div className="space-y-3">
          <PdfPicker label={'Source PDF for ' + reference.doi} file={file} disabled={busy} onChange={setFile} />
          {limits.data && <p>PDF limit: {(limits.data.source_max_bytes / 1024 / 1024).toFixed(1)} MB</p>}
          {limits.error && <p role="alert">{wholePaperError(limits.error)}</p>}
          <Button size="sm" disabled={busy || !file || !limits.data} loading={busy} onClick={() => void upload()}>Upload PDF</Button>
        </div>}
      </div>
    </details>
    {message && <p role="status" className="text-xs text-text-secondary">{message}</p>}
  </div>
}

export function ReferenceReview({ references, allowSources = false, onSourceBusy, anchors = false }: { references: Reference[]; allowSources?: boolean; onSourceBusy?: (id: string, busy: boolean) => void; anchors?: boolean }) {
  const matched = references.filter(r => r.resolution?.status === 'resolved').length
  const websites = references.filter(r => r.resolution?.status === 'non_doi_source').length
  const attention = references.filter(r => !['resolved', 'non_doi_source'].includes(r.resolution?.status ?? '')).length
  return <div className="min-w-0 space-y-3">
    <p className="text-sm font-medium">{references.length} References · {references.filter(r => !!r.doi).length} DOI · {websites} URL</p>
    <p className="text-xs text-text-muted">{matched} DOI identities ready · {websites} URL-based sources · {attention} unresolved. Identity resolution does not guarantee full text.</p>
    {attention > 0 && <p className="text-sm text-warning">{attention} references need attention</p>}
    <div className="max-h-[45dvh] space-y-2 overflow-y-auto overscroll-contain pr-1" aria-label="Reference list">
      {references.map((ref, index) => {
        const result = ref.resolution
        const resolved = result?.status === 'resolved'
        return <article key={ref.id} id={anchors ? 'reference-' + encodeURIComponent(ref.id) : undefined} className="min-w-0 space-y-2 rounded-lg border border-border px-3 py-3 text-sm">
          <p className="break-words font-medium [overflow-wrap:anywhere]">R{index + 1} · {ref.title ?? ref.raw_text}</p>
          <p className="break-all text-xs text-text-secondary">{ref.doi ? 'DOI: ' + ref.doi : result?.source_url || ref.url || 'No DOI or URL recorded'}</p>
          <Badge size="sm" variant={resolved ? 'success' : result?.status === 'non_doi_source' ? 'primary' : 'warning'}>{resolved ? 'Identity resolved' : result?.status === 'non_doi_source' ? 'URL identified' : result?.status?.replaceAll('_', ' ') ?? 'Not reviewed'}</Badge>
          <details className="text-xs text-text-secondary"><summary className="cursor-pointer text-primary">Reference details</summary><div className="mt-2 space-y-2 break-words [overflow-wrap:anywhere]">
            <p>Reference ID: {ref.id}</p><p>Original reference: {ref.raw_text}</p>
            <p>{ref.authors.join(', ')} · {ref.year ?? 'Year unavailable'} · {ref.journal ?? 'Journal unavailable'}</p>
            <p>Original DOI: {(result ? result.original_doi : ref.doi) ?? 'Not provided'} · Resolved DOI: {result?.resolved_doi ?? 'Unresolved'}</p>
            <p>Provider: {result?.provider ?? 'None'} · Source type: {result?.source_type ?? 'unknown'}</p>
            <p>Original source URL: {ref.url ?? 'Not recorded'}</p><p>Discovered source URL: {result?.source_url ?? 'Not recorded'}</p>
            {result?.status === 'non_doi_source' && <p>URL source discovered. Verification will attempt document retrieval and identity checks. The historical cited version is not yet confirmed.</p>}
            {result?.match_reason === 'VERSION_UNCERTAIN' && <p>A compatible preprint candidate may be retrieved for further identity checks. A probable match will keep its version warnings and will not replace the original citation.</p>}
            <p>{result?.match_reason}</p>
            {result?.diagnostics.map((code, i) => <p key={i}>{code}</p>)}
            {result?.candidates.map((candidate, i) => <div key={i} className="space-y-1 border-t border-border pt-2"><p>{candidate.title} · {candidate.doi}</p><p>{candidate.authors.join(', ')} · {candidate.years.join(', ')} · {candidate.provider}</p><p>{candidate.journal} · {candidate.publication_type}</p><p>Identity match score: {Number.isFinite(candidate.match_confidence) ? (candidate.match_confidence * 100).toFixed(0) + '%' : 'Unavailable'} · {candidate.rejection_reason ?? 'Identity criteria met'}</p><p>{candidate.evidence.join(' · ')}</p></div>)}
          </div></details>
          {allowSources && <ReferenceSource reference={ref} onBusy={onSourceBusy} />}
        </article>
      })}
    </div>
  </div>
}
