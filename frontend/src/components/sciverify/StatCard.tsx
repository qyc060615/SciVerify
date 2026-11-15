import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { getVerdictConfig, type VerdictKey } from '@/constants/verdicts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'

export interface StatCardProps {
  label: string
  value: string | number
  description?: string
  trend?: string
  icon?: ReactNode
  accent?: VerdictKey | 'total'
  className?: string
}

export function StatCard({
  label,
  value,
  description,
  trend,
  icon,
  accent = 'total',
  className,
}: StatCardProps) {
  const hasFooter = Boolean(description || trend)
  const accentConfig =
    accent === 'total' ? null : getVerdictConfig(accent)

  return (
    <Card
      className={cn(
        'flex h-full min-h-[9rem] flex-col transition-all duration-200 motion-reduce:transition-none',
        'hover:-translate-y-0.5 hover:border-border/80 hover:shadow-md motion-reduce:hover:translate-y-0',
        accentConfig?.borderClass,
        className,
      )}
    >
      <CardHeader className="flex flex-1 flex-col gap-0 p-5 pb-0">
        <div className="flex min-h-[2.5rem] items-start gap-2.5">
          {icon ? (
            <span
              className={cn(
                'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border bg-surface-elevated',
                accentConfig
                  ? cn(accentConfig.borderClass, accentConfig.textClass)
                  : 'border-border/80 text-primary',
              )}
            >
              {icon}
            </span>
          ) : null}
          <p className="min-h-[2.5rem] pt-0.5 text-xs font-semibold uppercase leading-snug tracking-wide text-text-muted">
            {label}
          </p>
        </div>
        <CardTitle className="mt-auto pt-4 text-3xl font-semibold tabular-nums leading-none tracking-tight text-text-primary">
          {value}
        </CardTitle>
      </CardHeader>
      {hasFooter ? (
        <CardContent className="mt-3 p-5 pt-0">
          {description ? (
            <p className="text-xs leading-relaxed text-text-muted">{description}</p>
          ) : null}
          {trend ? (
            <p className="mt-1 text-xs font-medium text-success">{trend}</p>
          ) : null}
        </CardContent>
      ) : (
        <div className="pb-5" aria-hidden />
      )}
    </Card>
  )
}
