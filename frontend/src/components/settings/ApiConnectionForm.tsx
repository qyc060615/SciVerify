import { useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { StatusMark } from './StatusMark'
import { saveApiConnection, testApiConnection, type ApiConnection, type ApiSettings, type CheckResult } from '@/services/settingsService'

const providerLabels: Record<string, string> = { none: 'Disabled', openai: 'OpenAI', 'openai-compatible': 'OpenAI compatible (DeepSeek / Alibaba / custom)', compatible: 'Compatible (legacy alias)', groq: 'Groq', 'groq-compatible': 'Groq compatible' }
const labels: Record<string, string> = { self: 'Separate connection', llm: 'Reuse LLM connection', paperqa: 'Reuse PaperQA2 connection' }
export function ApiConnectionForm({ service, revision, token, onSaved }: {
  service: ApiConnection; revision: number; token: string; onSaved: (settings: ApiSettings) => void
}) {
  const [values, setValues] = useState({ ...service.values })
  const [key, setKey] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [clearKey, setClearKey] = useState(false)
  const [paid, setPaid] = useState(false)
  const [busy, setBusy] = useState<'save' | 'test' | null>(null)
  const [feedback, setFeedback] = useState('')
  const [error, setError] = useState('')
  const [test, setTest] = useState<CheckResult | null>(null)
  const shared = values.connection_source && values.connection_source !== 'self'
  const dirty = key.length > 0 || clearKey || Object.keys(values).some(name => values[name] !== service.values[name])
  function change(name: string, value: string) {
    setValues(old => ({ ...old, [name]: value })); setFeedback(''); setError(''); setTest(null)
    if (name === 'connection_source') { setKey(''); setClearKey(false); setShowKey(false) }
  }
  function cancel() {
    setValues({ ...service.values }); setKey(''); setClearKey(false); setShowKey(false); setFeedback(''); setError(''); setTest(null)
  }
  async function action(mode: 'save' | 'test') {
    setBusy(mode); setError(''); setFeedback(''); setTest(null)
    const draft = { values, api_key: key || undefined, clear_api_key: clearKey }
    try {
      if (mode === 'save') {
        const next = await saveApiConnection(service.id, draft, revision, token)
        onSaved(next); setValues({ ...(next.services.find(item => item.id === service.id)?.values ?? values) }); setKey(''); setShowKey(false); setClearKey(false)
        setFeedback('Saved. Restart the backend after current jobs finish to apply changes.')
      } else setTest(await testApiConnection(service.id, draft, paid, token))
    } catch (error) { setError(error instanceof Error ? error.message : 'The request failed. Your draft has been kept.') }
    finally { setBusy(null) }
  }
  return <details className="rounded-xl border border-border bg-surface">
    <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-4 py-4 text-sm marker:text-text-muted">
      <span className="mr-auto font-medium text-text-primary">{service.label}</span>
      <span className="max-w-full truncate text-xs text-text-muted">{service.values.provider || service.values.model || service.values.base_url}</span>
      {dirty ? <Badge variant="warning">Unsaved</Badge> : service.pending_restart ? <Badge variant="warning">Restart required</Badge> : <Badge variant="muted">{service.supports_key ? service.has_key ? 'Key configured' : 'No key configured' : 'No key needed'}</Badge>}
    </summary>
    <div className="space-y-4 border-t border-border px-4 py-4">
      <p className="text-sm text-text-secondary">{service.purpose}</p>
      {service.active_model && <p className="break-all text-xs text-text-muted">Active model: {service.active_model}</p>}
      <fieldset disabled={busy !== null} className="min-w-0 space-y-4 disabled:opacity-70">
        {service.share_options.length > 0 && <Select label="Provider connection" id={service.id + '-connection'} value={values.connection_source}
          onChange={e => change('connection_source', e.target.value)} options={['self', ...service.share_options].map(value => ({ value, label: labels[value] }))} />}
        {shared && <p className="text-xs text-text-muted">Base URL and API key follow the selected saved connection after restart. Model ID stays independent.</p>}
        <div className="grid min-w-0 gap-4 sm:grid-cols-2">
          {service.fields.filter(field => !(shared && field.name === 'base_url')).map(field => field.kind === 'select'
            ? <Select key={field.name} id={service.id + '-' + field.name} label={field.label} value={values[field.name]} onChange={e => change(field.name, e.target.value)} options={field.options.map(value => ({ value, label: providerLabels[value] ?? value }))} />
            : <Input key={field.name} id={service.id + '-' + field.name} label={field.label} type={field.kind === 'number' ? 'number' : 'text'} value={values[field.name]} autoComplete="off" spellCheck={false}
                onChange={e => change(field.name, e.target.value)} hint={field.name === 'model' ? 'Enter the exact provider Model ID. This is not a live model list.' : undefined} />)}
        </div>
        {service.supports_key && !shared && <div className="space-y-2">
          <div className="flex items-end gap-2"><Input id={service.id + '-api-key'} label="API Key" type={showKey ? 'text' : 'password'} value={key} autoComplete="off" spellCheck={false}
            placeholder={service.has_own_key ? 'Saved key — leave blank to keep' : 'Enter a new API key'} disabled={clearKey} onChange={e => { setKey(e.target.value); setTest(null); setFeedback('') }} />
            <Button size="sm" variant="ghost" disabled={!key || clearKey} aria-label={showKey ? 'Hide new API key' : 'Show new API key'} onClick={() => setShowKey(!showKey)}>{showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}</Button></div>
          {service.has_own_key && <Button variant="ghost" size="sm" onClick={() => { setClearKey(!clearKey); setKey(''); setTest(null); setFeedback('') }}>{clearKey ? 'Undo key removal' : 'Remove saved key on Save'}</Button>}
          {clearKey && <p className="text-xs text-warning">Saving will clear this connection’s key after restart. The original .env file is unchanged.</p>}
        </div>}
        {service.paid_test && <label className="flex items-start gap-2 text-xs text-text-secondary"><input type="checkbox" className="mt-0.5 shrink-0" checked={paid} onChange={e => setPaid(e.target.checked)} />I allow one small model request for this test. Provider charges may apply.</label>}
        <div className="flex flex-wrap gap-2">
          <Button size="sm" loading={busy === 'save'} disabled={!dirty} onClick={() => void action('save')}>Save</Button>
          <Button size="sm" variant="outline" disabled={!dirty} onClick={cancel}>Cancel</Button>
          <Button size="sm" variant="ghost" loading={busy === 'test'} disabled={service.paid_test && !paid} onClick={() => void action('test')}>Test connection</Button>
        </div>
      </fieldset>
      {feedback && <p role="status" className="text-sm text-success">{feedback}</p>}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      {test && <div role="status" className="flex items-start gap-2 text-sm text-text-secondary"><StatusMark state={test.state} /><div><p>{test.message}</p><p className="mt-1 text-xs text-text-muted">{test.scope} Tests use this draft with saved shared connections; they do not activate or save it.</p></div></div>}
    </div>
  </details>
}
