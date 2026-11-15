import { cn } from '@/lib/cn'
import {
  getVerdictConfig,
  type VerdictKey,
} from '@/constants/verdicts'

export interface ConfidenceBarProps {
  value: number
  verdict?: VerdictKey
  label?: string
  showValue?: boolean
  size?: 'sm' | 'md'
  className?: string
}

export function ConfidenceBar({
  value,
  verdict,
  label = 'Confidence',
  showValue = true,
  size = 'md',
  className,
}: ConfidenceBarProps) {
  const clampedValue = Math.min(100, Math.max(0, value))
  const barClass = verdict
    ? getVerdictConfig(verdict).barClass
    : 'bg-primary'

  return (
    <div className={cn('flex w-full flex-col gap-2', className)}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm text-text-secondary">{label}</span>
        {showValue ? (
          <span className="text-sm font-medium text-text-primary">
            {clampedValue}%
          </span>
        ) : null}
      </div>
      <div
        className={cn(
          'w-full overflow-hidden rounded-full bg-surface-elevated',
          size === 'sm' ? 'h-1.5' : 'h-2.5',
        )}
        role="progressbar"
        aria-valuenow={clampedValue}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
      >
        <div
          className={cn('h-full rounded-full transition-all duration-300', barClass)}
          style={{ width: `${clampedValue}%` }}
        />
      </div>
    </div>
  )
}
