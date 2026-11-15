import { createContext, useContext, useState, type ReactNode } from 'react'
import { cn } from '@/lib/cn'

interface TabsContextValue {
  value: string
  setValue: (value: string) => void
}

const TabsContext = createContext<TabsContextValue | null>(null)

function useTabsContext() {
  const context = useContext(TabsContext)
  if (!context) {
    throw new Error('Tabs components must be used within Tabs')
  }
  return context
}

export interface TabsProps {
  defaultValue: string
  children: ReactNode
  className?: string
}

export function Tabs({ defaultValue, children, className }: TabsProps) {
  const [value, setValue] = useState(defaultValue)

  return (
    <TabsContext.Provider value={{ value, setValue }}>
      <div className={cn('flex flex-col gap-4', className)}>{children}</div>
    </TabsContext.Provider>
  )
}

export interface TabItem {
  value: string
  label: string
  disabled?: boolean
}

export interface TabsListProps {
  items: TabItem[]
  className?: string
}

export function TabsList({ items, className }: TabsListProps) {
  const { value, setValue } = useTabsContext()

  return (
    <div
      role="tablist"
      className={cn(
        'inline-flex w-full flex-wrap gap-1 rounded-lg border border-border bg-surface p-1 sm:w-auto',
        className,
      )}
    >
      {items.map((item) => {
        const isActive = value === item.value

        return (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={isActive}
            disabled={item.disabled}
            onClick={() => setValue(item.value)}
            className={cn(
              'rounded-md px-3 py-2 text-sm font-medium transition-colors disabled:opacity-50',
              isActive
                ? 'bg-surface-elevated text-text-primary shadow-sm'
                : 'text-text-secondary hover:text-text-primary',
            )}
          >
            {item.label}
          </button>
        )
      })}
    </div>
  )
}

export interface TabsPanelProps {
  value: string
  children: ReactNode
  className?: string
}

export function TabsPanel({ value, children, className }: TabsPanelProps) {
  const { value: activeValue } = useTabsContext()

  if (activeValue !== value) return null

  return (
    <div role="tabpanel" className={cn('rounded-xl', className)}>
      {children}
    </div>
  )
}
