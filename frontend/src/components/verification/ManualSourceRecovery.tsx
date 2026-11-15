import { useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { uploadManualSource } from '@/services/verificationService'
import type { BackendVerificationResponse } from '@/types/backend-verification'

export function ManualSourceRecovery({ response, onAccepted, onCancel }: {
  response: BackendVerificationResponse
  onAccepted: () => Promise<void>
  onCancel: () => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const limit = response.source_recovery?.max_size_bytes ?? 20 * 1024 * 1024

  async function upload() {
    if (!file || busy) return
    setError(null)
    if (!file.size || file.size > limit) {
      setError('Select a non-empty PDF within the upload size limit.')
      return
    }
    setBusy(true)
    try {
      await uploadManualSource(response.paper.doi, file)
      await onAccepted()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'The PDF could not be uploaded. Try again.')
    } finally {
      setBusy(false)
    }
  }

  return <Panel padding="lg" className="space-y-4">
    <h2 className="text-lg font-semibold">Upload the cited PDF to continue</h2>
    <p>The cited paper could not be retrieved automatically.</p>
    <p className="text-sm text-text-secondary">{response.paper.title ?? response.paper.doi}</p>
    <p className="text-sm">DOI: {response.paper.doi}</p>
    <p className="text-sm text-text-secondary">
      Your claim and context are preserved. The PDF must match this paper.
      Maximum size: {Math.floor(limit / 1024 / 1024)} MB.
    </p>
    <label className="block text-sm">
      Cited PDF
      <input type="file" accept="application/pdf,.pdf" disabled={busy}
        className="mt-2 block w-full"
        onChange={(event) => { setFile(event.target.files?.[0] ?? null); setError(null) }} />
    </label>
    {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
    <div className="flex gap-2">
      <Button disabled={!file || busy} onClick={upload}>
        {busy ? 'Validating PDF...' : 'Upload and retry verification'}
      </Button>
      <Button variant="outline" disabled={busy} onClick={onCancel}>New verification</Button>
    </div>
  </Panel>
}
