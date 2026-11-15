import { cn } from '@/lib/cn'
import type { TimelineStepStatus } from '@/types'
import { ProgressStep } from '@/components/sciverify/ProgressStep'

export interface VerificationTimelineItem {
  id: string
  title: string
  description?: string
  status: TimelineStepStatus
}

export interface VerificationTimelineProps {
  items: VerificationTimelineItem[]
  className?: string
}

export function VerificationTimeline({
  items,
  className,
}: VerificationTimelineProps) {
  return (
    <div className={cn('rounded-xl border border-border bg-surface p-5', className)}>
      {items.map((item, index) => (
        <ProgressStep
          key={item.id}
          step={index + 1}
          title={item.title}
          description={item.description}
          status={item.status}
          isLast={index === items.length - 1}
        />
      ))}
    </div>
  )
}
