import { forwardRef, type InputHTMLAttributes } from 'react'
import { Check } from 'lucide-react'
import { cn } from '@/lib/cn'

export interface CheckboxProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: string
  description?: string
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, label, description, id, ...props }, ref) => {
    const checkboxId = id ?? label?.toLowerCase().replace(/\s+/g, '-')

    return (
      <label
        htmlFor={checkboxId}
        className={cn(
          'group flex cursor-pointer items-start gap-3',
          props.disabled && 'cursor-not-allowed opacity-60',
          className,
        )}
      >
        <span className="relative mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center">
          <input
            ref={ref}
            id={checkboxId}
            type="checkbox"
            className="peer sr-only"
            {...props}
          />
          <span className="flex h-4 w-4 items-center justify-center rounded border border-border bg-surface transition-colors peer-focus-visible:ring-2 peer-focus-visible:ring-primary/40 peer-checked:border-primary peer-checked:bg-primary [&_svg]:opacity-0 peer-checked:[&_svg]:opacity-100">
            <Check className="h-3 w-3 text-white" />
          </span>
        </span>
        {(label || description) && (
          <span className="flex flex-col gap-0.5">
            {label ? (
              <span className="text-sm font-medium text-text-primary">
                {label}
              </span>
            ) : null}
            {description ? (
              <span className="text-xs text-text-muted">{description}</span>
            ) : null}
          </span>
        )}
      </label>
    )
  },
)

Checkbox.displayName = 'Checkbox'
