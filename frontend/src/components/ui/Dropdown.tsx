import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { cn } from '@/lib/cn'

interface DropdownContextValue {
  open: boolean
  setOpen: (open: boolean) => void
}

const DropdownContext = createContext<DropdownContextValue | null>(null)

function useDropdownContext() {
  const context = useContext(DropdownContext)
  if (!context) {
    throw new Error('Dropdown components must be used within Dropdown')
  }
  return context
}

export interface DropdownProps {
  children: ReactNode
  className?: string
}

export function Dropdown({ children, className }: DropdownProps) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return

    const handleClickOutside = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false)
      }
    }

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }

    document.addEventListener('mousedown', handleClickOutside)
    window.addEventListener('keydown', handleEscape)

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      window.removeEventListener('keydown', handleEscape)
    }
  }, [open])

  return (
    <DropdownContext.Provider value={{ open, setOpen }}>
      <div ref={containerRef} className={cn('relative inline-flex', className)}>
        {children}
      </div>
    </DropdownContext.Provider>
  )
}

export interface DropdownTriggerProps {
  children: ReactNode
  className?: string
}

export function DropdownTrigger({ children, className }: DropdownTriggerProps) {
  const { open, setOpen } = useDropdownContext()

  return (
    <button
      type="button"
      aria-expanded={open}
      aria-haspopup="menu"
      onClick={() => setOpen(!open)}
      className={className}
    >
      {children}
    </button>
  )
}

export interface DropdownItem {
  label: string
  onSelect?: () => void
  disabled?: boolean
  destructive?: boolean
}

export interface DropdownMenuProps {
  items: DropdownItem[]
  className?: string
}

export function DropdownMenu({ items, className }: DropdownMenuProps) {
  const { open, setOpen } = useDropdownContext()

  if (!open) return null

  return (
    <div
      role="menu"
      className={cn(
        'absolute top-[calc(100%+0.5rem)] right-0 z-50 min-w-44 overflow-hidden rounded-lg border border-border bg-surface-elevated p-1 shadow-lg',
        className,
      )}
    >
      {items.map((item) => (
        <button
          key={item.label}
          type="button"
          role="menuitem"
          disabled={item.disabled}
          onClick={() => {
            item.onSelect?.()
            setOpen(false)
          }}
          className={cn(
            'flex w-full items-center rounded-md px-3 py-2 text-left text-sm transition-colors disabled:opacity-50',
            item.destructive
              ? 'text-danger hover:bg-danger/10'
              : 'text-text-primary hover:bg-surface-hover',
          )}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}
