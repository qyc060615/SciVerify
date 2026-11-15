import { AlertTriangle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { isSupabaseConfigured } from '@/lib/supabase'
import { ROUTES } from '@/constants'
import { Panel } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'

export function SupabaseConfigNotice() {
  if (isSupabaseConfigured()) {
    return null
  }

  return (
    <Panel className="mb-4 space-y-3 border-warning/30 bg-warning/5">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
        <div className="space-y-2">
          <p className="text-sm font-medium text-text-primary">
            Supabase is not configured
          </p>
          <p className="text-sm text-text-secondary">
            Add <code className="text-text-primary">VITE_SUPABASE_URL</code> and{' '}
            <code className="text-text-primary">VITE_SUPABASE_ANON_KEY</code> to{' '}
            <code className="text-text-primary">frontend/.env</code>, then restart
            the dev server.
          </p>
          <p className="text-xs text-text-muted">
            Copy from <code>frontend/.env.example</code>. Never commit real credentials.
          </p>
        </div>
      </div>
      <Link to={ROUTES.HOME}>
        <Button variant="outline" size="sm">
          Back to home
        </Button>
      </Link>
    </Panel>
  )
}
