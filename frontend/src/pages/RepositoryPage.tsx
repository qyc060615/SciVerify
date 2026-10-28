import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Library, Search } from 'lucide-react'
import { AppHeader } from '@/components/app/AppHeader'
import { Panel } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Spinner } from '@/components/ui/Spinner'
import { wholePaperJobPath } from '@/constants'
import { getRepository } from '@/services/repositoryService'

const availabilityLabels = { available: 'Available · Hash verified', missing: 'File missing', corrupt: 'Hash mismatch', unavailable: 'File unreadable' }
function sourceLink(value: string | null): string | null {
  if (!value) return null
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null } catch { return null }
}

export default function RepositoryPage() {
  const [search, setSearch] = useState('')
  const [type, setType] = useState('all')
  const repository = useQuery({ queryKey: ['local-literature-repository'], queryFn: ({ signal }) => getRepository(signal), retry: false })
  const records = repository.data?.records ?? []
  const query = search.trim().toLowerCase()
  const filtered = records.filter(row => (type === 'all' || row.literature_type === type)
    && ((row.title ?? '').toLowerCase().includes(query) || (row.doi ?? '').toLowerCase().includes(query)))
  return <div className="min-w-0 space-y-6">
    <AppHeader title="Repository" description="Browse literature stored in your local research workspace."
      actions={<Button variant="outline" size="sm" loading={repository.isFetching} onClick={() => void repository.refetch()}>Refresh library</Button>} />
    <Panel className="space-y-2 text-sm text-text-secondary">
      <p className="font-medium text-text-primary">Local Literature Repository</p>
      <p>Reference files are stored by the backend and shared across tasks. Each row describes a stored source version; availability is checked against its actual file and SHA-256 when the library loads.</p>
      <p>PDF and HTML are listed separately. Parsed manuscript text and job-only citations are not saved PDFs and are excluded. Original manuscript PDFs are not retained. Availability may change after a check; refresh to check again.</p>
    </Panel>
    <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-text-secondary" role="status">
      {repository.isPending ? <span className="flex items-center gap-2"><Spinner size="sm" />Loading literature…</span>
        : repository.isError ? <span>Library could not be refreshed</span>
        : <><span>{records.length} literature records</span><span>{records.filter(row => row.availability === 'available').length} available</span><span>{filtered.length} shown</span></>}
    </div>
    <div className="grid min-w-0 gap-3 sm:grid-cols-[minmax(0,1fr)_12rem]">
      <Input label="Search title or DOI" placeholder="Search literature" leftIcon={<Search className="h-4 w-4" />} value={search} onChange={e => setSearch(e.target.value)} />
      <Select label="Literature type" value={type} onChange={e => setType(e.target.value)} options={[{ value: 'all', label: 'All types' }, { value: 'Reference', label: 'Reference' }, { value: 'Manuscript', label: 'Manuscript' }]} />
    </div>
    {repository.isError && <Panel><p role="alert" className="text-warning">Could not read the local literature library. Check that the backend is running and its source storage is readable, then refresh. Previously displayed availability is not a current check.</p></Panel>}
    {repository.data?.warnings.map(warning => <Panel key={warning}><p role="status" className="text-warning">{warning}</p></Panel>)}
    {!repository.isPending && !repository.isError && (filtered.length ? <ul className="space-y-3" aria-label="Literature records">
      {filtered.map(row => <li key={row.id}>
        <Panel className="min-w-0 space-y-3">
          <h2 className="break-words text-base font-semibold text-text-primary [overflow-wrap:anywhere]">{row.title || 'Title unavailable'}</h2>
          {row.doi && <p className="break-all text-sm text-text-secondary">{row.doi}</p>}
          <div className="flex flex-wrap gap-2"><Badge>{row.literature_type}</Badge><Badge>{row.source_type}{row.source_type === 'Other' ? ' · ' + row.format.toUpperCase() : ''}</Badge><Badge variant={row.availability === 'available' ? 'success' : 'warning'}>{availabilityLabels[row.availability]}</Badge></div>
          <details className="min-w-0 text-sm text-text-secondary">
            <summary className="cursor-pointer text-primary">View literature details</summary>
            <dl className="mt-3 space-y-3">
              <div><dt className="text-text-muted">Stored version · SHA-256</dt><dd className="break-all font-mono text-xs">{row.raw_content_sha256}</dd></div>
              <div><dt className="text-text-muted">Source</dt><dd className="break-all">{sourceLink(row.source_url) ? <a className="text-primary underline" href={sourceLink(row.source_url)!} target="_blank" rel="noreferrer">{row.source_url}</a> : 'No external source link recorded.'}</dd></div>
              <div><dt className="text-text-muted">Related tasks · exact stored version</dt><dd>{row.related_job_ids.length ? <ul className="space-y-1">{row.related_job_ids.map(id => <li key={id}><Link className="break-all text-primary underline" to={wholePaperJobPath(id)}>{id}</Link></li>)}</ul> : 'No associated task recorded.'}</dd></div>
            </dl>
          </details>
        </Panel>
      </li>)}
    </ul> : <Panel className="space-y-2 py-8 text-center"><Library className="mx-auto h-6 w-6 text-text-muted" /><h2 className="font-medium text-text-primary">{records.length ? 'No matching literature' : 'No stored literature found'}</h2><p className="text-sm text-text-secondary">{type === 'Manuscript' ? 'Original manuscript PDFs are not retained by the current parser.' : records.length ? 'Try a different title, DOI or literature type.' : 'Reference PDFs and HTML saved by this backend will appear here. No sample records are added.'}</p></Panel>)}
  </div>
}
