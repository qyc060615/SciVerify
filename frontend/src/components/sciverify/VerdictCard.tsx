import { cn } from '@/lib/cn'
import {
  getVerdictConfig,
  type VerdictKey,
} from '@/constants/verdicts'
import { VerdictBadge } from '@/components/sciverify/VerdictBadge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'

export interface VerdictCardProps {
  verdict: VerdictKey
  title?: string
  summary?: string
  confidence?: number
  className?: string
}

export function VerdictCard({
  verdict,
  title,
  summary,
  confidence,
  className,
}: VerdictCardProps) {
  const config = getVerdictConfig(verdict)
  const Icon = config.icon

  return (
    <Card
      className={cn(
        'overflow-hidden ring-1 ring-inset',
        config.ringClass,
        config.borderClass,
        className,
      )}
    >
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <span
              className={cn(
                'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border',
                config.bgClass,
                config.borderClass,
              )}
            >
              <Icon className={cn('h-5 w-5', config.textClass)} />
            </span>
            <div>
              <CardTitle>{title ?? 'Verification Result'}</CardTitle>
              <CardDescription>{summary ?? config.description}</CardDescription>
            </div>
          </div>
          <VerdictBadge verdict={verdict} />
        </div>
      </CardHeader>
      {confidence !== undefined ? (
        <CardContent className="pt-4">
          <p className="text-xs text-text-muted">
            Confidence score:{' '}
            <span className="font-medium text-text-primary">{confidence}%</span>
          </p>
        </CardContent>
      ) : null}
    </Card>
  )
}
