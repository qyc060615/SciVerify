import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { Filter, Search } from 'lucide-react'
import { AppHeader } from '@/components/app/AppHeader'
import { VerificationActivityCard } from '@/components/verification/VerificationActivityCard'
import { filterHistoryRecords } from '@/lib/history-filters'
import { useAuth } from '@/hooks/useAuth'
import { useVerificationStore } from '@/stores/verificationStore'
import { ROUTES } from '@/constants'
import { getVerdictConfig, VERDICT_KEYS } from '@/constants/verdicts'
import type { VerdictKey } from '@/constants/verdicts'
import type { HistoryDateSort } from '@/types/history'
import type { VerificationResult } from '@/types/verification'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { Panel } from '@/components/ui/Card'
import { Spinner } from '@/components/ui/Spinner'

export default function HistoryPage() {
  const { user } = useAuth()
  const records = useVerificationStore((state) => state.records)
  const loading = useVerificationStore((state) => state.loading)
  const error = useVerificationStore((state) => state.error)
  const deleteRecord = useVerificationStore((state) => state.deleteRecord)
  const loadRecords = useVerificationStore((state) => state.loadRecords)

  const [search, setSearch] = useState('')
  const [verdictFilter, setVerdictFilter] = useState<'all' | VerdictKey>('all')
  const [dateSort, setDateSort] = useState<HistoryDateSort>('newest')
  const [recordToDelete, setRecordToDelete] = useState<VerificationResult | null>(
    null,
  )
  const [deleting, setDeleting] = useState(false)

  const filteredRecords = useMemo(
    () =>
      filterHistoryRecords(records, {
        search,
        verdictFilter,
        sort: dateSort,
      }),
    [records, search, verdictFilter, dateSort],
  )

  const handleConfirmDelete = async () => {
    if (!user?.id || !recordToDelete) return

    setDeleting(true)
    try {
      await deleteRecord(user.id, recordToDelete.id)
      toast.success('Verification removed from history.')
      setRecordToDelete(null)
    } catch {
      toast.error('Unable to delete this verification. Please try again.')
    } finally {
      setDeleting(false)
    }
  }

  const handleRetry = () => {
    if (user?.id) {
      void loadRecords(user.id)
    }
  }

  return (
    <div>
      <AppHeader
        title="Verification history"
        description="Review previous verification runs and reopen complete reports."
      />

      <Panel padding="md" className="mb-6">
        <div className="grid gap-4 lg:grid-cols-[1fr_220px_180px]">
          <Input
            label="Search"
            placeholder="Search claims, DOIs, or paper titles..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            leftIcon={<Search className="h-4 w-4" />}
          />
          <div>
            <div className="mb-1.5 flex items-center gap-1.5 text-sm font-medium text-text-primary">
              <Filter className="h-4 w-4 text-text-muted" aria-hidden />
              Verdict filter
            </div>
            <Select
              aria-label="Verdict filter"
              value={verdictFilter}
              onChange={(event) =>
                setVerdictFilter(event.target.value as 'all' | VerdictKey)
              }
              options={[
                { value: 'all', label: 'All verdicts' },
                ...VERDICT_KEYS.map((key) => ({
                  value: key,
                  label: getVerdictConfig(key).label,
                })),
              ]}
            />
          </div>
          <div>
            <div className="mb-1.5 text-sm font-medium text-text-primary">
              Sort by date
            </div>
            <Select
              aria-label="Sort by date"
              value={dateSort}
              onChange={(event) =>
                setDateSort(event.target.value as HistoryDateSort)
              }
              options={[
                { value: 'newest', label: 'Newest' },
                { value: 'oldest', label: 'Oldest' },
              ]}
            />
          </div>
        </div>
      </Panel>

      {loading ? (
        <Panel padding="lg" className="flex flex-col items-center gap-3 text-center">
          <Spinner size="lg" className="text-primary" />
          <p className="text-sm text-text-secondary">Loading verification history...</p>
        </Panel>
      ) : error ? (
        <Panel padding="lg" className="space-y-4 text-center">
          <p className="text-sm text-text-secondary">{error}</p>
          <Button onClick={handleRetry}>Try again</Button>
        </Panel>
      ) : filteredRecords.length === 0 ? (
        <Panel padding="lg" className="space-y-4 text-center">
          <p className="text-sm font-medium text-text-primary">
            {records.length === 0
              ? 'No verification history yet.'
              : 'No records match your search or filter.'}
          </p>
          {records.length === 0 ? (
            <>
              <p className="text-sm text-text-secondary">
                Verify a scientific claim to see your results here.
              </p>
              <Link to={ROUTES.APP_VERIFY}>
                <Button>Start a verification</Button>
              </Link>
            </>
          ) : null}
        </Panel>
      ) : (
        <div className="grid gap-4">
          {filteredRecords.map((record) => (
            <VerificationActivityCard
              key={record.id}
              record={record}
              onDelete={setRecordToDelete}
            />
          ))}
        </div>
      )}

      <Modal
        open={recordToDelete !== null}
        onClose={() => {
          if (!deleting) setRecordToDelete(null)
        }}
        title="Delete verification?"
        description="This removes the stored report from your history. It cannot be undone."
        size="sm"
      >
        <div className="flex flex-wrap justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => setRecordToDelete(null)}
            disabled={deleting}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="danger"
            onClick={() => void handleConfirmDelete()}
            loading={deleting}
          >
            Delete
          </Button>
        </div>
      </Modal>
    </div>
  )
}
