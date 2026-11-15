import { cn } from '@/lib/cn'
import {
  getVerdictConfig,
  type VerdictKey,
} from '@/constants/verdicts'

export interface VerdictBadgeProps {
  verdict: VerdictKey
  size?: 'sm' | 'md'
  showIcon?: boolean
  className?: string
}

export function VerdictBadge({
  verdict,
  size = 'md',
  showIcon = true,
  className,
}: VerdictBadgeProps) {
  const config = getVerdictConfig(verdict)
  const Icon = config.icon

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border font-medium',
        config.bgClass,
        config.borderClass,
        config.textClass,
        size === 'sm' ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-xs',
        className,
      )}
    >
      {showIcon ? <Icon className={size === 'sm' ? 'h-3 w-3' : 'h-3.5 w-3.5'} /> : null}
      {config.label}
    </span>
  )
}
