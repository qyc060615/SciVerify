import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

export interface AppHeaderProps {
  title: string
  description?: string
  eyebrow?: string
  status?: {
    label: string
    ready?: boolean
  }
  actions?: ReactNode
  className?: string
}

export function AppHeader({
  title,
  description,
  eyebrow,
  status,
  actions,
  className,
}: AppHeaderProps) {
  return (
    <header
      className={cn(
        'flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-center sm:justify-between sm:gap-6',
        className,
      )}
    >
      <div className="min-w-0 flex-1">
        {eyebrow ? (
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-widest text-primary">
            {eyebrow}
          </p>
        ) : null}
        <h1 className="text-2xl font-semibold tracking-tight text-text-primary sm:text-[1.75rem]">
          {title}
        </h1>
        {description ? (
          <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-text-secondary">
            {description}
          </p>
        ) : null}
        {status ? (
          <p className="mt-2 inline-flex items-center gap-2 text-xs font-medium text-text-secondary">
            <span
              className={cn(
                'h-2 w-2 rounded-full',
                status.ready === false ? 'bg-warning' : 'bg-success',
              )}
              aria-hidden
            />
            {status.label}
          </p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex w-full shrink-0 flex-wrap items-center gap-2 sm:w-auto sm:justify-end">
          {actions}
        </div>
      ) : null}
    </header>
  )
}
