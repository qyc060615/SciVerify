import { cn } from '@/lib/cn'

const sizes = {
  sm: 'h-8 w-8 text-xs',
  md: 'h-10 w-10 text-sm',
  lg: 'h-12 w-12 text-base',
} as const

export type AvatarSize = keyof typeof sizes

export interface AvatarProps {
  src?: string
  alt?: string
  name?: string
  size?: AvatarSize
  className?: string
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}

export function Avatar({
  src,
  alt,
  name,
  size = 'md',
  className,
}: AvatarProps) {
  const initials = name ? getInitials(name) : '?'

  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full border border-border bg-surface-elevated font-medium text-text-secondary',
        sizes[size],
        className,
      )}
    >
      {src ? (
        <img src={src} alt={alt ?? name ?? 'Avatar'} className="h-full w-full object-cover" />
      ) : (
        initials
      )}
    </span>
  )
}
