import { Link } from 'react-router-dom'
import { ArrowRight, CheckCircle2 } from 'lucide-react'
import { cn } from '@/lib/cn'
import { countNeedsReview } from '@/lib/dashboard-selectors'
import { VerdictBadge } from '@/components/sciverify/VerdictBadge'
import { ROUTES, verificationReportPath } from '@/constants'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import type { VerificationResult } from '@/types/verification'

export interface NeedsReviewSectionProps {
  records: VerificationResult[]
  needsReviewRecords: VerificationResult[]
  className?: string
}

export function NeedsReviewSection({
  records,
  needsReviewRecords,
  className,
}: NeedsReviewSectionProps) {
  const attentionCount = countNeedsReview(records)

  return (
    <Panel padding="md" className={cn('flex h-full flex-col', className)}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-text-primary">Needs review</h2>
          <p className="mt-1 text-xs text-text-muted">
            {attentionCount > 0
              ? `${attentionCount} ${attentionCount === 1 ? 'claim requires' : 'claims require'} attention`
              : 'No claims require attention'}
          </p>
        </div>
        {attentionCount > 0 ? (
          <Link
            to={ROUTES.APP_HISTORY}
            className="inline-flex shrink-0 items-center gap-1 rounded-sm text-xs font-medium text-primary outline-offset-2 hover:text-primary-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
          >
            View all
            <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </Link>
        ) : null}
      </div>

      {needsReviewRecords.length === 0 ? (
        <div className="mt-5 flex flex-col items-center gap-3 py-6 text-center">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-surface-elevated">
            <CheckCircle2 className="h-4 w-4 text-success" aria-hidden />
          </span>
          <div className="space-y-1">
            <p className="text-sm font-medium text-text-primary">
              No claims require attention
            </p>
            <p className="mx-auto max-w-xs text-sm text-text-secondary">
              All recent verification results are evidence-aligned.
            </p>
          </div>
          <Link to={ROUTES.APP_VERIFY}>
            <Button variant="outline" className="h-9">
              Start Verification
            </Button>
          </Link>
        </div>
      ) : (
        <ul className="mt-4 divide-y divide-border/70">
          {needsReviewRecords.map((record) => (
            <li key={record.id}>
              <Link
                to={verificationReportPath(record.id)}
                className="group -mx-1 block rounded-md px-1 py-2.5 outline-offset-2 transition-colors hover:bg-surface/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary sm:py-2"
                aria-label={`View report: ${record.claim}`}
              >
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-[auto_3.5rem_minmax(0,1fr)] sm:items-center sm:gap-3">
                  <VerdictBadge verdict={record.verdict} size="sm" />
                  <span className="text-sm font-semibold tabular-nums text-text-primary sm:text-right">
                    {record.confidence}%
                  </span>
                  <p className="truncate text-sm text-text-primary group-hover:text-text-primary sm:col-span-1">
                    {record.claim}
                  </p>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}
