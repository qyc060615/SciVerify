import { useCallback, useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getVerificationJob, jobStreamUrl } from '@/services/verificationJobService'
import { ApiResponseError } from '@/services/api'
import type { VerificationJob } from '@/types/verification-job'

export function useVerificationJob(jobId: string) {
  const client = useQueryClient()
  const key = ['whole-paper-job', jobId]
  const queryFn = useCallback(async ({ signal }: { signal?: AbortSignal }) => {
    const snapshot = await getVerificationJob(jobId, signal)
    if (snapshot.job_id !== jobId) throw new Error('The backend returned a different job.')
    const cached = client.getQueryData<VerificationJob>(['whole-paper-job', jobId])
    return cached && cached.revision > snapshot.revision ? cached : snapshot
  }, [client, jobId])
  const query = useQuery({ queryKey: key, queryFn, retry: false, staleTime: 0, refetchOnMount: 'always', enabled: /^job_[0-9a-f]{32}$/.test(jobId) })
  const [transport, setTransport] = useState({ jobId: '', mode: 'Connecting' })
  useEffect(() => {
    if (!/^job_[0-9a-f]{32}$/.test(jobId)) return
    const queryKey = ['whole-paper-job', jobId]
    let alive = true, source: EventSource | null = null, live = false, cursor = 0
    let debounce: ReturnType<typeof setTimeout> | undefined
    const snapshot = () => client.getQueryData<VerificationJob>(queryKey)
    const settled = () => ['completed', 'failed'].includes(snapshot()?.status ?? '')
    const unavailable = () => {
      const error = client.getQueryState(queryKey)?.error
      return error instanceof ApiResponseError && [400, 403, 404, 422].includes(error.status ?? 0)
    }
    function revalidate() {
      if (!alive) return
      void client.fetchQuery({ queryKey, queryFn, staleTime: 0 }).then(data => {
        if (!alive) return
        if (data.next_sequence - 1 < cursor) scheduleRefresh()
        cursor = Math.max(cursor, data.next_sequence - 1)
        if (settled()) { source?.close(); source = null; live = false }
      }).catch(() => { /* TanStack retains the last confirmed snapshot and error. */ })
    }
    function scheduleRefresh() {
      if (!debounce) debounce = setTimeout(() => { debounce = undefined; revalidate() }, 150)
    }
    function connect() {
      if (!alive || source || settled() || unavailable()) return
      if (typeof EventSource === 'undefined') { setTransport({ jobId, mode: 'Polling fallback' }); return }
      try { source = new EventSource(jobStreamUrl(jobId, cursor)) } catch { setTransport({ jobId, mode: 'Polling fallback' }); return }
      source.onopen = () => { if (alive) { live = true; setTransport({ jobId, mode: 'Live updates' }); scheduleRefresh() } }
      source.addEventListener('job', raw => {
        if (!alive) return
        const message = raw as MessageEvent
        const sequence = Number(message.lastEventId)
        if (!Number.isSafeInteger(sequence) || sequence <= cursor) return
        try {
          const event = JSON.parse(message.data) as { job_id: string; sequence: number }
          if (event.job_id !== jobId || event.sequence !== sequence) return
        } catch { return }
        cursor = sequence
        scheduleRefresh()
      })
      const fallback = () => {
        source?.close(); source = null; live = false
        if (alive) { setTransport({ jobId, mode: 'Polling fallback' }); scheduleRefresh() }
      }
      source.onerror = fallback
      source.addEventListener('stream_error', fallback)
    }
    // Automatic reconnect uses our durable cursor, rather than creating a job.
    const first = setTimeout(connect, 0)
    const polling = setInterval(() => {
      if (!alive || settled() || unavailable()) return
      if (!live) { revalidate(); connect() }
    }, 3000)
    const online = () => { if (alive && !settled()) { revalidate(); connect() } }
    window.addEventListener('online', online)
    return () => {
      alive = false; source?.close(); clearTimeout(first); clearInterval(polling)
      if (debounce) clearTimeout(debounce)
      window.removeEventListener('online', online)
    }
  }, [client, jobId, queryFn])
  const refresh = () => client.fetchQuery({ queryKey: key, queryFn, staleTime: 0 })
  const acceptSnapshot = (snapshot: VerificationJob) => {
    if (snapshot.job_id !== jobId) return
    client.setQueryData<VerificationJob>(key, old => old && old.revision > snapshot.revision ? old : snapshot)
  }
  return { ...query, refresh, acceptSnapshot, connection: ['completed', 'failed'].includes(query.data?.status ?? '') ? 'Report loaded' : transport.jobId === jobId ? transport.mode : 'Connecting' }
}
