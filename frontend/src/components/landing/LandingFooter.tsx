import { Link } from 'react-router-dom'
import { ShieldCheck } from 'lucide-react'
import { ROUTES } from '@/constants'

type FooterLink =
  | { label: string; href: string; to?: never }
  | { label: string; to: string; href?: never }

const footerLinks: FooterLink[] = [
  { label: 'How it works', href: '#how-it-works' },
  { label: 'Agents', href: '#agents' },
  { label: 'Verdicts', href: '#verdicts' },
  { label: 'Sign in', to: ROUTES.LOGIN },
  { label: 'UI preview', to: `/${ROUTES.UI_PREVIEW}` },
]

export function LandingFooter() {
  return (
    <footer className="border-t border-border bg-surface/40 px-4 py-12 sm:px-6">
      <div className="mx-auto flex max-w-6xl flex-col gap-8 md:flex-row md:items-start md:justify-between">
        <div>
          <Link
            to={ROUTES.HOME}
            className="inline-flex items-center gap-2 text-text-primary"
          >
            <ShieldCheck className="h-5 w-5 text-primary" />
            <span className="font-semibold">SciVerify</span>
          </Link>
          <p className="mt-3 max-w-sm text-sm text-text-secondary">
            Multi-agent scientific citation verification for research teams
            who need evidence-backed answers.
          </p>
        </div>

        <nav className="grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-3">
          {footerLinks.map((link) =>
            link.to ? (
              <Link
                key={link.label}
                to={link.to}
                className="text-sm text-text-secondary transition-colors hover:text-text-primary"
              >
                {link.label}
              </Link>
            ) : (
              <a
                key={link.label}
                href={link.href}
                className="text-sm text-text-secondary transition-colors hover:text-text-primary"
              >
                {link.label}
              </a>
            ),
          )}
        </nav>
      </div>

      <div className="mx-auto mt-10 max-w-6xl border-t border-border pt-6 text-xs text-text-muted">
        © {new Date().getFullYear()} SciVerify. Built for research integrity.
      </div>
    </footer>
  )
}
