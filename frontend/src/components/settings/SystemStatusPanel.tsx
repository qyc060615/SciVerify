import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Spinner } from '@/components/ui/Spinner'
import { StatusMark } from './StatusMark'
import { getApiSettings, getSystemStatus, refreshSystemStatus, type ServiceStatus } from '@/services/settingsService'

export function SystemStatusPanel() {
  const [rows, setRows] = useState<ServiceStatus[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    getSystemStatus(controller.signal).then(setRows).catch(() => { if (!controller.signal.aborted) setError('Could not reach the local settings service.') })
    return () => controller.abort()
  }, [])
  async function refresh() {
    setBusy(true); setError('')
    try {
      const settings = await getApiSettings()
      setRows(await refreshSystemStatus(settings.management_token ?? ''))
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Could not refresh service status.')
      setRows(old => old.map(row => ({ ...row, state: 'unknown', message: 'Could not refresh this status.', scope: 'No current check result.' })))
    }
    finally { setBusy(false) }
  }
  return <div className="space-y-4">
    <div className="flex items-start justify-between gap-3"><p className="text-sm text-text-secondary">Active backend configuration. Refresh checks service APIs; model tests run only when you request them in API.</p><Button size="sm" variant="outline" loading={busy} onClick={() => void refresh()}>Refresh</Button></div>
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    <Panel padding="none" className="divide-y divide-border">
      {!rows.length && !error && <p className="flex items-center gap-2 p-4 text-sm text-text-muted"><Spinner size="sm" />Reading status…</p>}
      {rows.map(row => <div key={row.id} className="flex min-w-0 items-center justify-between gap-4 px-4 py-3">
        <div className="min-w-0"><span className="text-sm text-text-primary">{row.label}</span>{row.state === 'failed' && <p className="mt-1 break-words text-xs text-text-muted">{row.message}</p>}</div>
        <StatusMark state={row.state} title={row.message + ' ' + row.scope} />
      </div>)}
    </Panel>
  </div>
}
