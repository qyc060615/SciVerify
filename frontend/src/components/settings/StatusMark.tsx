import { Check, Minus, X } from 'lucide-react'
import type { CheckResult } from '@/services/settingsService'

export function StatusMark({ state, title }: { state: CheckResult['state']; title?: string }) {
  const Icon = state === 'ok' ? Check : state === 'failed' ? X : Minus
  return <span role="img" aria-label={state === 'ok' ? 'Passed' : state === 'failed' ? 'Failed' : 'Not checked'} title={title}
    className={state === 'ok' ? 'shrink-0 text-success' : state === 'failed' ? 'shrink-0 text-danger' : 'shrink-0 text-text-muted'}><Icon className="h-4 w-4" aria-hidden="true" /></span>
}
