import { Link } from 'react-router-dom'
import { ArrowRight, Trash2 } from 'lucide-react'
import { cn } from '@/lib/cn'
import { getVerdictConfig } from '@/constants/verdicts'
import { VerdictBadge } from '@/components/sciverify/VerdictBadge'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader } from '@/components/ui/Card'
import { verificationReportPath } from '@/constants'
import type { VerificationResult } from '@/types/verification'

export interface VerificationActivityCardProps {
  record: VerificationResult
  className?: string
  onDelete?: (record: VerificationResult) => void
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
  }).format(new Date(value))
}

export function VerificationActivityCard({
  record,
  className,
  onDelete,
}: VerificationActivityCardProps) {
  const verdictLabel = getVerdictConfig(record.verdict).label
  const paperLine =
    record.paperTitle?.trim() ||
    record.paperDoi?.trim() ||
    record.citation.trim()

  return (
    <Card
      className={cn(
        'group transition-all duration-200 motion-reduce:transition-none',
        'hover:-translate-y-0.5 hover:border-border/80 hover:shadow-md motion-reduce:hover:translate-y-0',
        className,
      )}
    >
      <CardHeader className="space-y-4 p-5 pb-0">
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <VerdictBadge verdict={record.verdict} size="sm" />
            <span className="text-sm font-semibold tabular-nums text-text-primary">
              {verdictLabel} · {record.confidence}%
            </span>
          </div>
          {onDelete ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="text-text-muted hover:text-danger"
              aria-label={`Delete verification for ${record.claim}`}
              onClick={() => onDelete(record)}
            >
              <Trash2 className="h-4 w-4" aria-hidden />
            </Button>
          ) : null}
        </div>

        <div className="space-y-3">
          <p className="break-words text-sm font-medium leading-relaxed text-text-primary">
            {record.claim}
          </p>
          <div className="space-y-1 border-l-2 border-border/80 pl-3">
            <p className="break-words text-xs leading-relaxed text-text-secondary">
              {paperLine}
            </p>
            {record.paperDoi && record.paperTitle ? (
              <p className="break-all font-mono text-xs text-text-muted">
                {record.paperDoi}
              </p>
            ) : null}
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-5 pt-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
          <time
            className="text-xs text-text-muted"
            dateTime={record.createdAt}
          >
            {formatDate(record.createdAt)}
          </time>
          <Link
            to={verificationReportPath(record.id)}
            className="inline-flex items-center gap-1.5 rounded-sm text-sm font-medium text-primary outline-offset-2 transition-colors hover:text-primary-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
          >
            View report
            <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </Link>
        </div>
      </CardContent>
    </Card>
  )
}
