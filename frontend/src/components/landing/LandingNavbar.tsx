import { Link } from 'react-router-dom'
import { Menu, ShieldCheck, X } from 'lucide-react'
import { useState } from 'react'
import { cn } from '@/lib/cn'
import { ROUTES } from '@/constants'
import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/Button'

const navLinks = [
  { label: 'How it works', href: '#how-it-works' },
  { label: 'Agents', href: '#agents' },
  { label: 'Verdicts', href: '#verdicts' },
  { label: 'Trust', href: '#trust' },
]

export function LandingNavbar() {
  const [open, setOpen] = useState(false)
  const { isAuthenticated, initializing, isLocalDemo } = useAuth()

  return (
    <header className="sticky top-0 z-50 border-b border-border/60 bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <Link
          to={ROUTES.HOME}
          className="flex items-center gap-2.5 text-text-primary transition-colors hover:text-primary"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-surface-elevated">
            <ShieldCheck className="h-4 w-4 text-primary" />
          </span>
          <span className="text-base font-semibold tracking-tight">SciVerify</span>
        </Link>

        <nav className="hidden items-center gap-8 md:flex">
          {navLinks.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="text-sm text-text-secondary transition-colors hover:text-text-primary"
            >
              {link.label}
            </a>
          ))}
        </nav>

        <div className="hidden items-center gap-3 md:flex">
          {isLocalDemo || (!initializing && isAuthenticated) ? (
            <Link to={ROUTES.APP_HOME}>
              <Button size="sm">{isLocalDemo ? 'Enter Local Demo' : 'Workspace'}</Button>
            </Link>
          ) : (
            <>
              <Link to={ROUTES.LOGIN}>
                <Button variant="ghost" size="sm">
                  Sign in
                </Button>
              </Link>
              <Link to={ROUTES.REGISTER}>
                <Button size="sm">Get started</Button>
              </Link>
            </>
          )}
        </div>

        <button
          type="button"
          className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-border text-text-secondary md:hidden"
          aria-label={open ? 'Close menu' : 'Open menu'}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      <div
        className={cn(
          'border-t border-border/60 bg-background md:hidden',
          open ? 'block' : 'hidden',
        )}
      >
        <nav className="mx-auto flex max-w-6xl flex-col gap-1 px-4 py-4">
          {navLinks.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="rounded-lg px-3 py-2.5 text-sm text-text-secondary transition-colors hover:bg-surface-elevated hover:text-text-primary"
              onClick={() => setOpen(false)}
            >
              {link.label}
            </a>
          ))}
          <div className="mt-3 flex flex-col gap-2 border-t border-border pt-4">
            {isLocalDemo || (!initializing && isAuthenticated) ? (
              <Link to={ROUTES.APP_HOME} onClick={() => setOpen(false)}>
                <Button className="w-full">{isLocalDemo ? 'Enter Local Demo' : 'Workspace'}</Button>
              </Link>
            ) : (
              <>
                <Link to={ROUTES.LOGIN} onClick={() => setOpen(false)}>
                  <Button variant="outline" className="w-full">
                    Sign in
                  </Button>
                </Link>
                <Link to={ROUTES.REGISTER} onClick={() => setOpen(false)}>
                  <Button className="w-full">Get started</Button>
                </Link>
              </>
            )}
          </div>
        </nav>
      </div>
    </header>
  )
}
