import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

const variants = {
  default: 'bg-surface-elevated text-text-secondary border-border',
  primary: 'bg-primary-muted text-primary border-primary/20',
  success: 'bg-success/10 text-success border-success/20',
  warning: 'bg-warning/10 text-warning border-warning/20',
  danger: 'bg-danger/10 text-danger border-danger/20',
  muted: 'bg-surface text-text-muted border-border-subtle',
} as const

export type BadgeVariant = keyof typeof variants
export type BadgeSize = 'sm' | 'md'

export interface BadgeProps {
  children: ReactNode
  variant?: BadgeVariant
  size?: BadgeSize
  className?: string
}

export function Badge({
  children,
  variant = 'default',
  size = 'md',
  className,
}: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border font-medium',
        variants[variant],
        size === 'sm' ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-0.5 text-xs',
        className,
      )}
    >
      {children}
    </span>
  )
}
