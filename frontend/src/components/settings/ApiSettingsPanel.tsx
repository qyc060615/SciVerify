import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Spinner } from '@/components/ui/Spinner'
import { ApiConnectionForm } from './ApiConnectionForm'
import { getApiSettings, type ApiSettings } from '@/services/settingsService'

export function ApiSettingsPanel() {
  const [settings, setSettings] = useState<ApiSettings | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    getApiSettings(controller.signal).then(setSettings).catch(error => {
      if (!controller.signal.aborted) setError(error instanceof Error ? error.message : 'Could not load API configuration.')
    })
    return () => controller.abort()
  }, [attempt])
  return <div className="space-y-4">
    <p className="text-sm text-text-secondary">Configure the LLM, PaperQA2, and embedding connections. Saved keys stay on the backend and are never returned to this page. Blank key fields keep the saved key.</p>
    <p className="text-xs text-text-muted">All saved changes apply after a backend restart. Finish running jobs before restarting. Model roles are fixed by the existing pipeline.</p>
    {error && <Panel><p role="alert" className="text-sm text-danger">{error}</p><Button className="mt-3" size="sm" variant="outline" onClick={() => { setError(''); setAttempt(attempt + 1) }}>Retry</Button></Panel>}
    {!settings && !error && <p className="flex items-center gap-2 text-sm text-text-muted"><Spinner size="sm" />Loading API configuration…</p>}
    {settings?.restart_required && <p role="status" className="rounded-lg border border-warning/30 p-3 text-sm text-warning">Saved configuration differs from this process. Restart the backend to apply it.</p>}
    {settings && <div className="space-y-3">{settings.services.filter(service => ['llm', 'paperqa', 'embedding'].includes(service.id)).map(service => <ApiConnectionForm key={service.id} service={service} revision={settings.revision} token={settings.management_token ?? ''}
      onSaved={next => setSettings(previous => ({ ...next, management_token: previous?.management_token }))} />)}</div>}
  </div>
}
