import type { LucideIcon } from 'lucide-react'
import { Bot, Loader2 } from 'lucide-react'
import { cn } from '@/lib/cn'
import type { AgentStatus } from '@/types'
import { Badge } from '@/components/ui/Badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'

const statusConfig: Record<
  AgentStatus,
  { label: string; variant: 'default' | 'primary' | 'success' | 'danger' }
> = {
  idle: { label: 'Waiting', variant: 'default' },
  running: { label: 'Running', variant: 'primary' },
  completed: { label: 'Completed', variant: 'success' },
  error: { label: 'Error', variant: 'danger' },
}

export interface AgentCardProps {
  name: string
  role: string
  status: AgentStatus
  description?: string
  icon?: LucideIcon
  className?: string
}

export function AgentCard({
  name,
  role,
  status,
  description,
  icon: IconOverride,
  className,
}: AgentCardProps) {
  const statusMeta = statusConfig[status]
  const AgentIcon = IconOverride ?? Bot

  return (
    <Card
      className={cn(
        'transition-all duration-200 motion-reduce:transition-none hover:border-border/80',
        className,
      )}
    >
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-lg border border-border bg-surface-elevated">
              {status === 'running' ? (
                <Loader2 className="h-5 w-5 animate-spin text-primary motion-reduce:animate-none" />
              ) : (
                <AgentIcon className="h-5 w-5 text-primary" />
              )}
            </span>
            <div>
              <CardTitle className="text-base">{name}</CardTitle>
              <CardDescription>{role}</CardDescription>
            </div>
          </div>
          <Badge variant={statusMeta.variant}>{statusMeta.label}</Badge>
        </div>
      </CardHeader>
      {description ? (
        <CardContent className="pt-0">
          <p className="text-sm leading-relaxed text-text-secondary">
            {description}
          </p>
        </CardContent>
      ) : null}
    </Card>
  )
}
