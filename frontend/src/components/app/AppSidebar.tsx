import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  Settings,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { toast } from 'sonner'
import { useState } from 'react'
import { cn } from '@/lib/cn'
import { ROUTES } from '@/constants'
import { useAuth } from '@/hooks/useAuth'
import { useUserDisplayName } from '@/hooks/useUserDisplayName'
import { Avatar } from '@/components/ui/Avatar'
import { Button } from '@/components/ui/Button'
import { Drawer } from '@/components/ui/Drawer'
import type { LucideIcon } from 'lucide-react'

const workspaceItems = [
  { label: 'Dashboard', to: ROUTES.APP_HOME, icon: LayoutDashboard },
  { label: 'New Verification', to: ROUTES.APP_VERIFY, icon: Sparkles },
  { label: 'History', to: ROUTES.APP_HISTORY, icon: History },
]

const accountItems = [
  { label: 'Settings', to: ROUTES.APP_SETTINGS, icon: Settings },
]

function NavSection({
  title,
  items,
  onNavigate,
}: {
  title: string
  items: Array<{ label: string; to: string; icon: LucideIcon }>
  onNavigate?: () => void
}) {
  const location = useLocation()

  return (
    <div className="space-y-2">
      <p className="px-3 text-[11px] font-semibold uppercase tracking-widest text-text-muted">
        {title}
      </p>
      <div className="flex flex-col gap-0.5">
        {items.map((item) => {
          const active = location.pathname === item.to
          const Icon = item.icon

          return (
            <Link
              key={item.to}
              to={item.to}
              onClick={onNavigate}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                active
                  ? 'border border-primary/20 bg-primary-muted text-primary shadow-sm'
                  : 'border border-transparent text-text-secondary hover:border-border/60 hover:bg-surface-hover hover:text-text-primary',
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {item.label}
            </Link>
          )
        })}
      </div>
    </div>
  )
}

function UserSection({ onNavigate }: { onNavigate?: () => void }) {
  const navigate = useNavigate()
  const { user, signOut, isLocalDemo } = useAuth()
  const displayName = useUserDisplayName()
  const [signingOut, setSigningOut] = useState(false)

  const handleLogout = async () => {
    try {
      setSigningOut(true)
      await signOut()
      toast.success('Signed out successfully.')
      navigate(ROUTES.LOGIN, { replace: true })
      onNavigate?.()
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Unable to sign out.',
      )
    } finally {
      setSigningOut(false)
    }
  }

  return (
    <div className="mt-auto border-t border-border pt-4">
      <div className="mb-3 flex items-center gap-3 rounded-lg border border-border/80 bg-surface-elevated/60 p-3">
        <Avatar name={displayName} size="sm" />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-text-primary">
            {displayName}
          </p>
          <p className="truncate text-xs text-text-muted">{user?.email}</p>
        </div>
      </div>
      {isLocalDemo ? (
        <p className="px-3 text-xs text-text-muted">Local Demo · Browser history</p>
      ) : (
        <Button
          variant="outline"
          size="sm"
          className="w-full justify-start"
          onClick={handleLogout}
          loading={signingOut}
        >
          <LogOut className="h-4 w-4" />
          {signingOut ? 'Signing out...' : 'Logout'}
        </Button>
      )}
    </div>
  )
}

export function AppSidebar({
  mobile = false,
  onNavigate,
}: {
  mobile?: boolean
  onNavigate?: () => void
}) {
  return (
    <div className={cn('flex h-full flex-col', mobile ? 'p-2' : 'p-4')}>
      <Link
        to={ROUTES.APP_HOME}
        onClick={onNavigate}
        className="mb-8 flex items-center gap-2.5 text-text-primary"
      >
        <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-surface-elevated">
          <ShieldCheck className="h-4 w-4 text-primary" />
        </span>
        <div>
          <span className="block font-semibold tracking-tight">SciVerify</span>
          <span className="block text-[11px] text-text-muted">Research workspace</span>
        </div>
      </Link>

      <div className="flex flex-1 flex-col gap-6">
        <NavSection title="Workspace" items={workspaceItems} onNavigate={onNavigate} />
        <NavSection title="Account" items={accountItems} onNavigate={onNavigate} />
      </div>

      <UserSection onNavigate={onNavigate} />
    </div>
  )
}

export function AppMobileNav({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  return (
    <Drawer open={open} onClose={onClose} title="Workspace" side="left">
      <AppSidebar mobile onNavigate={onClose} />
    </Drawer>
  )
}

export function AppMobileMenuButton({ onClick }: { onClick: () => void }) {
  return (
    <Button
      variant="outline"
      size="sm"
      className="lg:hidden"
      onClick={onClick}
      aria-label="Open navigation menu"
    >
      <Menu className="h-4 w-4" />
    </Button>
  )
}
