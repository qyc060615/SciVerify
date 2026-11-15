import type { VerdictKey } from '@/constants/verdicts'
import type { DashboardStats, VerificationResult } from '@/types/verification'

/** All non-SUPPORTS verdicts require user attention. */
export const NEEDS_REVIEW_VERDICTS: VerdictKey[] = [
  'OVERSTATED',
  'CONTRADICTS',
  'INSUFFICIENT',
  'FABRICATED',
]

export function sortRecordsByDate(
  records: VerificationResult[],
): VerificationResult[] {
  return [...records].sort(
    (a, b) =>
      new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
  )
}

export function computeAverageConfidence(
  records: VerificationResult[],
): number | null {
  if (records.length === 0) {
    return null
  }

  const total = records.reduce((sum, record) => sum + record.confidence, 0)
  return Math.round((total / records.length) * 10) / 10
}

export function countNeedsReview(records: VerificationResult[]): number {
  return records.filter((record) =>
    NEEDS_REVIEW_VERDICTS.includes(record.verdict),
  ).length
}

export function getNeedsReviewRecords(
  records: VerificationResult[],
  limit = 5,
): VerificationResult[] {
  return sortRecordsByDate(records)
    .filter((record) => NEEDS_REVIEW_VERDICTS.includes(record.verdict))
    .slice(0, limit)
}

export function getMostRecentRecord(
  records: VerificationResult[],
): VerificationResult | undefined {
  return sortRecordsByDate(records)[0]
}

export function getRecentRecords(
  records: VerificationResult[],
  limit = 5,
): VerificationResult[] {
  return sortRecordsByDate(records).slice(0, limit)
}

export interface VerificationSummaryMetrics {
  totalRuns: number
  evidenceAligned: number
  needsReview: number
  evidenceConflicts: number
  citationIssues: number
}

export function computeVerificationSummary(
  stats: DashboardStats,
  records: VerificationResult[],
): VerificationSummaryMetrics {
  return {
    totalRuns: stats.total,
    evidenceAligned: stats.supports,
    needsReview: countNeedsReview(records),
    evidenceConflicts: stats.contradicts,
    citationIssues: stats.fabricated,
  }
}
