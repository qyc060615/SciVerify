import { cn } from '@/lib/cn'

export interface ScoreBarProps {
  label: string
  value: number
  className?: string
}

export function ScoreBar({ label, value, className }: ScoreBarProps) {
  const clampedValue = Math.min(100, Math.max(0, value))
  const filledBlocks = Math.round(clampedValue / 10)
  const emptyBlocks = 10 - filledBlocks

  return (
    <div className={cn('space-y-2', className)}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm text-text-secondary">{label}</span>
        <span className="text-sm font-medium tabular-nums text-text-primary">
          {clampedValue}%
        </span>
      </div>
      <div
        className="font-mono text-sm tracking-tight text-primary"
        role="img"
        aria-label={`${label}: ${clampedValue}%`}
      >
        <span aria-hidden>{'█'.repeat(filledBlocks)}</span>
        <span className="text-text-muted" aria-hidden>
          {'░'.repeat(emptyBlocks)}
        </span>
        <span className="sr-only">{clampedValue} percent</span>
      </div>
    </div>
  )
}
