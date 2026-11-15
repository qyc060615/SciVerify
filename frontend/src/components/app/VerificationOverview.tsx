import { cn } from '@/lib/cn'
import { computeVerificationSummary } from '@/lib/dashboard-selectors'
import { getVerdictConfig, VERDICT_KEYS } from '@/constants/verdicts'
import type { VerdictKey } from '@/constants/verdicts'
import type { DashboardStats, VerificationResult } from '@/types/verification'
import { Panel } from '@/components/ui/Card'

export interface VerificationOverviewProps {
  stats: DashboardStats
  records: VerificationResult[]
  className?: string
}

const summaryRows = [
  { key: 'totalRuns', label: 'Total runs' },
  { key: 'evidenceAligned', label: 'Evidence aligned' },
  { key: 'needsReview', label: 'Needs review' },
  { key: 'evidenceConflicts', label: 'Evidence conflicts' },
  { key: 'citationIssues', label: 'Citation issues' },
] as const

export function VerificationOverview({
  stats,
  records,
  className,
}: VerificationOverviewProps) {
  const counts: Record<VerdictKey, number> = {
    SUPPORTS: stats.supports,
    OVERSTATED: stats.overstated,
    CONTRADICTS: stats.contradicts,
    INSUFFICIENT: stats.insufficient,
    FABRICATED: stats.fabricated,
  }

  const maxCount = Math.max(...VERDICT_KEYS.map((key) => counts[key]), 1)
  const summary = computeVerificationSummary(stats, records)

  return (
    <Panel padding="lg" className={cn('w-full', className)}>
      <div>
        <h2 className="text-sm font-semibold text-text-primary">
          Verification overview
        </h2>
        <p className="mt-1 text-xs text-text-muted">
          Distribution of verification outcomes
        </p>
      </div>

      <div className="mt-5 space-y-3.5">
        {VERDICT_KEYS.map((key) => {
          const config = getVerdictConfig(key)
          const count = counts[key]
          const widthPercent =
            count === 0 ? 0 : Math.round((count / maxCount) * 100)

          return (
            <div
              key={key}
              className="grid grid-cols-[5.5rem_minmax(0,1fr)_1.75rem] items-center gap-3 sm:grid-cols-[6.25rem_minmax(0,1fr)_1.75rem]"
            >
              <span
                className={cn(
                  'text-xs font-medium leading-tight',
                  config.textClass,
                )}
              >
                {config.label}
              </span>
              <div
                className="h-2.5 overflow-hidden rounded-sm bg-surface-elevated"
                role="img"
                aria-label={`${config.label}: ${count}`}
              >
                <div
                  className={cn(
                    'h-full rounded-sm transition-all duration-300 motion-reduce:transition-none',
                    config.barClass,
                    count === 0 && 'opacity-0',
                  )}
                  style={{
                    width: `${Math.max(widthPercent, count > 0 ? 10 : 0)}%`,
                  }}
                />
              </div>
              <span className="text-right text-xs font-semibold tabular-nums text-text-primary">
                {count}
              </span>
            </div>
          )
        })}
      </div>

      {stats.total === 0 ? (
        <p className="mt-4 text-xs text-text-muted">
          No verification runs yet. Start your first check to populate this
          overview.
        </p>
      ) : null}

      <div className="mt-7 border-t border-border/70 pt-5">
        <h3 className="text-sm font-semibold text-text-primary">
          Verification summary
        </h3>
        <dl className="mt-3 grid grid-cols-[minmax(0,1fr)_2.5rem] gap-x-4 gap-y-2 sm:grid-cols-[minmax(0,1fr)_3rem]">
          {summaryRows.map((row) => (
            <div key={row.key} className="contents">
              <dt className="text-xs text-text-secondary">{row.label}</dt>
              <dd className="text-right text-xs font-semibold tabular-nums text-text-primary">
                {summary[row.key]}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </Panel>
  )
}
