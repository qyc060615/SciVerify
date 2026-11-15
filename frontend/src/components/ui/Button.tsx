import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'
import { Spinner } from '@/components/ui/Spinner'

const variants = {
  primary:
    'bg-primary text-white hover:bg-primary-hover shadow-sm disabled:opacity-50',
  secondary:
    'bg-surface-elevated text-text-primary hover:bg-surface-hover border border-border',
  outline:
    'border border-border bg-transparent text-text-primary hover:bg-surface-elevated',
  ghost: 'bg-transparent text-text-secondary hover:bg-surface-elevated hover:text-text-primary',
  danger:
    'bg-danger/10 text-danger border border-danger/20 hover:bg-danger/20',
} as const

const sizes = {
  sm: 'h-8 px-3 text-xs gap-1.5 rounded-md',
  md: 'h-10 px-4 text-sm gap-2 rounded-lg',
  lg: 'h-11 px-5 text-base gap-2 rounded-lg',
} as const

export type ButtonVariant = keyof typeof variants
export type ButtonSize = keyof typeof sizes

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant = 'primary',
      size = 'md',
      loading = false,
      disabled,
      children,
      ...props
    },
    ref,
  ) => (
    <button
      ref={ref}
      className={cn(
        'inline-flex items-center justify-center font-medium transition-colors disabled:pointer-events-none',
        variants[variant],
        sizes[size],
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <Spinner size="sm" className="text-current" /> : null}
      {children}
    </button>
  ),
)

Button.displayName = 'Button'
