import { Check, Circle, Loader2, X } from 'lucide-react'
import { cn } from '@/lib/cn'
import type { TimelineStepStatus } from '@/types'

export interface ProgressStepProps {
  step: number
  title: string
  description?: string
  status: TimelineStepStatus
  isLast?: boolean
  className?: string
}

const statusStyles: Record<
  TimelineStepStatus,
  { icon: typeof Circle; container: string; iconClass: string }
> = {
  pending: {
    icon: Circle,
    container: 'border-border bg-surface text-text-muted',
    iconClass: 'text-text-muted',
  },
  active: {
    icon: Loader2,
    container: 'border-primary bg-primary-muted text-primary',
    iconClass: 'animate-spin text-primary',
  },
  completed: {
    icon: Check,
    container: 'border-success/30 bg-success/10 text-success',
    iconClass: 'text-success',
  },
  error: {
    icon: X,
    container: 'border-danger/30 bg-danger/10 text-danger',
    iconClass: 'text-danger',
  },
}

export function ProgressStep({
  step,
  title,
  description,
  status,
  isLast = false,
  className,
}: ProgressStepProps) {
  const meta = statusStyles[status]
  const Icon = meta.icon

  return (
    <div className={cn('flex gap-4', className)}>
      <div className="flex flex-col items-center">
        <span
          className={cn(
            'flex h-8 w-8 items-center justify-center rounded-full border text-xs font-semibold',
            meta.container,
          )}
        >
          {status === 'pending' ? (
            step
          ) : (
            <Icon className={cn('h-4 w-4', meta.iconClass)} />
          )}
        </span>
        {!isLast ? <span className="mt-2 w-px flex-1 bg-border" /> : null}
      </div>
      <div className={cn('pb-6', isLast && 'pb-0')}>
        <p className="text-sm font-medium text-text-primary">{title}</p>
        {description ? (
          <p className="mt-1 text-sm text-text-secondary">{description}</p>
        ) : null}
      </div>
    </div>
  )
}
