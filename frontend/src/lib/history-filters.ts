import type { VerdictKey } from '@/constants/verdicts'
import type { HistoryDateSort } from '@/types/history'
import type { VerificationResult } from '@/types/verification'

export function matchesHistorySearch(
  record: VerificationResult,
  query: string,
): boolean {
  const normalized = query.trim().toLowerCase()
  if (!normalized) return true

  const haystack = [
    record.claim,
    record.citation,
    record.paperDoi,
    record.paperTitle,
    record.summary,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()

  return haystack.includes(normalized)
}

export function matchesVerdictFilter(
  record: VerificationResult,
  verdictFilter: 'all' | VerdictKey,
): boolean {
  return verdictFilter === 'all' || record.verdict === verdictFilter
}

export function sortHistoryRecords(
  records: VerificationResult[],
  sort: HistoryDateSort,
): VerificationResult[] {
  return [...records].sort((left, right) => {
    const leftTime = new Date(left.createdAt).getTime()
    const rightTime = new Date(right.createdAt).getTime()
    return sort === 'newest' ? rightTime - leftTime : leftTime - rightTime
  })
}

export function filterHistoryRecords(
  records: VerificationResult[],
  options: {
    search: string
    verdictFilter: 'all' | VerdictKey
    sort: HistoryDateSort
  },
): VerificationResult[] {
  return sortHistoryRecords(
    records.filter(
      (record) =>
        matchesHistorySearch(record, options.search) &&
        matchesVerdictFilter(record, options.verdictFilter),
    ),
    options.sort,
  )
}
