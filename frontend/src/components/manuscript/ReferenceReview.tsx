import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useQueries, useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query'
import { Button } from '@/components/ui/Button'
import { PdfPicker } from './PdfPicker'
import { getUploadLimits, validatePdf } from '@/services/manuscriptService'
import { checkReferenceSource, prepareReferenceSource, referenceLocator, referenceSourceKey, sourceAvailable, uploadReferenceSource, type PreparedSource } from '@/services/sourceService'
import { wholePaperError } from '@/services/wholePaperErrors'
import type { Diagnostic, Reference } from '@/types/manuscript'
import { DiagnosticDetails } from './DiagnosticDetails'

type SourceQuery = UseQueryResult<PreparedSource>
function ReferenceItem({ reference: ref, index, status, automatic, anchors, onBusy }: { reference: Reference; index: number; status: SourceQuery; automatic: boolean; anchors: boolean; onBusy?: (id: string, busy: boolean) => void }) {
  const result = ref.resolution
  const client = useQueryClient()
  const details = useRef<HTMLDetailsElement>(null)
  const active = useRef(false)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const [adding, setAdding] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const limits = useQuery({ queryKey: ['manuscript-upload-limits'], queryFn: ({ signal }) => getUploadLimits(signal), enabled: adding, retry: false })
  const confirmed = !status.isFetching && !status.isError && sourceAvailable(status.data)
  const missing = !status.isFetching && (status.isError || ['unavailable', 'failed'].includes(status.data?.state ?? ''))
  const attention = !status.isFetching && status.data?.state === 'needs_attention'
  const canUpload = !!ref.doi || !!((ref.resolution?.source_url || ref.url) && ref.title && ref.title.trim().split(/\s+/).length >= 6)
  const reliable = !ref.resolution || ['resolved', 'non_doi_source'].includes(ref.resolution.status)
  function add() { setAdding(true); if (details.current) details.current.open = true }
  async function upload() {
    if (active.current || !limits.data) return
    const invalid = validatePdf(file, limits.data.source_max_bytes)
    if (invalid) { setMessage(invalid); return }
    active.current = true; setBusy(true); onBusy?.(ref.id, true); setMessage('')
    try {
      const hash = await uploadReferenceSource(ref, file!)
      if (!mounted.current) return
      if (!/^[a-f0-9]{64}$/.test(hash)) throw new Error('The upload did not return a valid source hash.')
      const checked = await checkReferenceSource(ref)
      if (!mounted.current) return
      if (!sourceAvailable(checked) || checked.raw_content_sha256 !== hash) throw new Error('Upload accepted, but the matching saved file could not be confirmed. Retry the local source check.')
      client.setQueryData(referenceSourceKey(ref, automatic), checked)
      const target = referenceLocator(ref)
      void client.invalidateQueries({ predicate: query => {
        if (query.queryKey[0] !== 'reference-source' || query.queryKey[2] === JSON.stringify(ref)) return false
        try {
          const other = referenceLocator(JSON.parse(String(query.queryKey[2])) as Reference)
          return !!target && other?.kind === target.kind && (target.kind === 'doi' ? other.value.toLowerCase() === target.value.toLowerCase() : other.value === target.value)
        } catch { return false }
      } })
      setMessage('PDF saved and verified in the local source store.'); setFile(null); setAdding(false)
      void client.invalidateQueries({ queryKey: ['local-literature-repository'] })
    } catch (error) { if (mounted.current) setMessage(wholePaperError(error)) }
    finally { active.current = false; if (mounted.current) { setBusy(false); onBusy?.(ref.id, false) } }
  }
  const label = status.isFetching ? 'Preparing full text' : confirmed ? 'Full text available' : missing ? 'Full text unavailable' : attention ? 'Needs Attention' : 'Full text not checked'
  return <article id={anchors ? 'reference-' + encodeURIComponent(ref.id) : undefined} className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] gap-x-3 py-3 text-sm">
    <p className="break-words font-medium [overflow-wrap:anywhere]">R{index + 1} · {ref.title ?? ref.raw_text}</p>
    <div className="flex flex-col items-end gap-1">
      <span role="status" aria-label={label} className={'text-lg ' + (confirmed ? 'text-success' : missing ? 'text-danger' : attention ? 'text-warning' : 'text-text-muted')}>{status.isFetching ? '…' : confirmed ? '✓' : missing ? '×' : attention ? '!' : '—'}</span>
      {automatic && missing && reliable && canUpload && <Button size="sm" variant="outline" disabled={busy} onClick={add}>Upload PDF</Button>}
      {automatic && missing && (status.isError || status.data?.retryable) && <Button size="sm" variant="ghost" disabled={busy} onClick={() => void status.refetch()}>Retry</Button>}
    </div>
    <details ref={details} className="col-span-2 mt-1 min-w-0 text-xs text-text-secondary"><summary className="cursor-pointer text-primary">More details</summary><div className="mt-2 space-y-2 break-words [overflow-wrap:anywhere]">
            <p>Reference ID: {ref.id}</p><p>Original reference: {ref.raw_text}</p>
            <p>{ref.authors.join(', ')} · {ref.year ?? 'Year unavailable'} · {ref.journal ?? 'Journal unavailable'}</p>
            <p>DOI: {ref.doi ?? 'Not recorded'}</p><p>Identity status: {result?.status ?? 'Not reviewed'}</p>
            <p>Original DOI: {(result ? result.original_doi : ref.doi) ?? 'Not provided'} · Resolved DOI: {result?.resolved_doi ?? 'Unresolved'}</p>
            <p>Provider: {result?.provider ?? 'None'} · Source type: {result?.source_type ?? 'unknown'}</p>
            <p>Original source URL: {ref.url ?? 'Not recorded'}</p><p>Discovered source URL: {result?.source_url ?? 'Not recorded'}</p>
            {result?.status === 'non_doi_source' && <p>URL source discovered. Verification will attempt document retrieval and identity checks. The historical cited version is not yet confirmed.</p>}
            {result?.match_reason === 'VERSION_UNCERTAIN' && <p>A compatible preprint candidate may be retrieved for further identity checks. A probable match will keep its version warnings and will not replace the original citation.</p>}
            <p>{result?.match_reason}</p>
            {result?.candidates.map((candidate, i) => <div key={i} className="space-y-1 border-t border-border pt-2"><p>{candidate.title} · {candidate.doi}</p><p>{candidate.authors.join(', ')} · {candidate.years.join(', ')} · {candidate.provider}</p><p>{candidate.journal} · {candidate.publication_type}</p><p>Identity match score: {Number.isFinite(candidate.match_confidence) ? (candidate.match_confidence * 100).toFixed(0) + '%' : 'Unavailable'} · {candidate.rejection_reason ?? 'Identity criteria met'}</p><p>{candidate.evidence.join(' · ')}</p></div>)}
      <p>Full text: {confirmed ? 'Available locally (' + status.data!.format!.toUpperCase() + ')' : status.isFetching ? 'Preparing' : missing ? 'Unavailable' : attention ? 'Needs Attention' : 'Not checked'}</p>
      {status.data && <><p>Preparation result: {status.data.reason_code}</p><p>Retrieval status: {status.data.retrieval_status ?? 'Not run'}</p><p>Full-text provider: {status.data.source?.provider ?? 'None'}</p>{status.data.source?.url && <p className="break-all">Full-text source URL: {status.data.source.url}</p>}{status.data.source?.provenance?.warnings?.map(warning => <p key={warning}>{warning}</p>)}</>}
      {confirmed && <p className="break-all font-mono">SHA-256: {status.data!.raw_content_sha256}</p>}
      {automatic && !confirmed && !status.isFetching && !missing && reliable && canUpload && !adding && <Button size="sm" variant="outline" onClick={add}>Add Source</Button>}
      {automatic && !confirmed && !canUpload && <p>A reliable DOI or a sufficiently specific cited title and URL is required to validate a manual PDF.</p>}
      {adding && !confirmed && <div className="space-y-3">
        <PdfPicker label={'Source PDF for ' + (ref.doi ?? ref.id)} file={file} disabled={busy} onChange={setFile} />
        {limits.data && <p>PDF limit: {(limits.data.source_max_bytes / 1024 / 1024).toFixed(1)} MB</p>}
        {limits.error && <p role="alert">{wholePaperError(limits.error)}</p>}
        <Button size="sm" disabled={busy || !file || !limits.data} loading={busy} onClick={() => void upload()}>Save PDF</Button>
      </div>}
      {message && <p role="status">{message}</p>}
    </div></details>
  </article>
}

export function ReferenceReview({ references, allowSources = false, onSourceBusy, anchors = false, diagnostics = [], children }: { references: Reference[]; allowSources?: boolean; onSourceBusy?: (id: string, busy: boolean) => void; anchors?: boolean; diagnostics?: Diagnostic[]; children?: ReactNode }) {
  const statuses = useQueries({ queries: references.map(reference => ({
    queryKey: referenceSourceKey(reference, allowSources),
    queryFn: ({ signal }: { signal: AbortSignal }) => allowSources ? prepareReferenceSource(reference, signal) : checkReferenceSource(reference, signal),
    retry: false, staleTime: Infinity, gcTime: 30 * 60_000, refetchOnWindowFocus: false, refetchOnMount: false,
  })) })
  const available = statuses.filter(status => !status.isFetching && !status.isError && sourceAvailable(status.data)).length
  const missing = statuses.filter(status => !status.isFetching && (status.isError || ['unavailable', 'failed'].includes(status.data?.state ?? ''))).length
  const attention = statuses.filter(status => !status.isFetching && status.data?.state === 'needs_attention').length
  const preparing = statuses.filter(status => status.isFetching).length
  const warnings: Diagnostic[] = [...diagnostics, ...references.flatMap(ref => (ref.resolution?.diagnostics ?? []).map(code => ({ code, severity: 'warning' as const, entity_id: ref.id, safe_message: code })))]
  return <div className="min-w-0 space-y-3">
    <p className="text-sm font-medium">{references.length} References · {available} available · {missing} missing{attention > 0 ? ' · ' + attention + ' need attention' : ''}{preparing > 0 ? ' · ' + preparing + ' preparing' : ''}</p>
    <div className="divide-y divide-border" aria-label="Reference list">
      {references.map((reference, index) => <ReferenceItem key={reference.id} reference={reference} index={index} status={statuses[index]} automatic={allowSources} anchors={anchors} onBusy={onSourceBusy} />)}
    </div>
    {!references.length && <p className="text-sm text-text-muted">No references recorded.</p>}
    <DiagnosticDetails records={warnings} heading="Warnings">{children}</DiagnosticDetails>
  </div>
}
