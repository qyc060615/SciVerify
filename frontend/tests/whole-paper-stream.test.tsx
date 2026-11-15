import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useVerificationJob } from '@/hooks/useVerificationJob'
import { jobFixture, jobId } from './fixtures/job'

const get = vi.hoisted(() => vi.fn())
vi.mock('@/services/verificationJobService', async original => ({ ...await original<object>(), getVerificationJob: get }))
class Stream {
  static all: Stream[] = []
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  listeners: Record<string, ((event: MessageEvent) => void)[]> = {}
  closed = false
  constructor(readonly url: string) { Stream.all.push(this) }
  addEventListener(type: string, callback: (event: MessageEvent) => void) { (this.listeners[type] ??= []).push(callback) }
  close() { this.closed = true }
  event(sequence: number, id = jobId) { for (const callback of this.listeners.job ?? []) callback(new MessageEvent('job', { lastEventId: String(sequence), data: JSON.stringify({ sequence, job_id: id }) })) }
}
beforeEach(() => { vi.useFakeTimers(); get.mockReset(); Stream.all = []; vi.stubGlobal('EventSource', Stream); get.mockResolvedValue(jobFixture()) })
afterEach(() => { cleanup(); vi.useRealTimers() })
async function tick(ms = 1) { await act(async () => { await vi.advanceTimersByTimeAsync(ms) }) }
function hook(id = jobId) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  return { ...renderHook(({ job }) => useVerificationJob(job), { wrapper, initialProps: { job: id } }), client }
}
it('coalesces events, ignores duplicate sequences, and reads authoritative snapshots', async () => {
  const h = hook(); await tick(); const stream = Stream.all[0]
  act(() => { stream.onopen?.() }); await tick(160)
  const before = get.mock.calls.length
  get.mockResolvedValue({ ...jobFixture(), revision: 8, next_sequence: 10 })
  act(() => { stream.event(8); stream.event(8); stream.event(9); stream.event(9) })
  await tick(160)
  expect(get.mock.calls.length - before).toBe(1); expect(h.result.current.data?.revision).toBe(8)
  const count = get.mock.calls.length; act(() => stream.event(9)); await tick(160); expect(get.mock.calls.length).toBe(count)
})
it('falls back to polling, retains confirmed results offline, then reconnects with a cursor', async () => {
  const h = hook(); await tick(); const stream = Stream.all[0]
  act(() => stream.onopen?.()); await tick(160)
  get.mockRejectedValue(new Error('offline'))
  act(() => stream.onerror?.()); await tick(160)
  expect(stream.closed).toBe(true); expect(h.result.current.data?.revision).toBe(6)
  expect(h.result.current.connection).toBe('Polling fallback')
  get.mockResolvedValue({ ...jobFixture(), revision: 7, next_sequence: 9 })
  await tick(3000)
  expect(Stream.all.length).toBeGreaterThan(1); expect(Stream.all[1].url).toContain('after=7')
  expect(h.result.current.data?.revision).toBe(7)
})
it('does not overwrite a newer snapshot with an older GET', async () => {
  const h = hook(); await tick()
  act(() => h.result.current.acceptSnapshot({ ...jobFixture(), revision: 9 }))
  await tick()
  await act(async () => { await h.result.current.refresh() })
  await tick()
  expect(h.result.current.data?.revision).toBe(9)
})
it('isolates old requests on job ID change and closes connections on unmount', async () => {
  const h = hook(); await tick(); const old = Stream.all[0]
  const secondId = 'job_' + 'e'.repeat(32)
  get.mockResolvedValue({ ...jobFixture(), job_id: secondId, revision: 2 })
  h.rerender({ job: secondId }); await tick()
  expect(old.closed).toBe(true); expect(h.result.current.data?.job_id).toBe(secondId)
  act(() => old.event(99)); await tick(160); expect(h.result.current.data?.job_id).toBe(secondId)
  h.unmount(); expect(Stream.all.at(-1)?.closed).toBe(true)
  const calls = get.mock.calls.length; await tick(10000); expect(get.mock.calls.length).toBe(calls)
})
it('does not subscribe or poll after a completed report', async () => {
  get.mockResolvedValue({ ...jobFixture(), status: 'completed' })
  const h = hook(); await tick(); const count = get.mock.calls.length; await tick(9000)
  expect(get.mock.calls.length).toBe(count); expect(h.result.current.connection).toBe('Report loaded')
})
it('refreshes again if an event arrives while an older GET is still in flight', async () => {
  const h = hook(); await tick(); const stream = Stream.all[0]
  let resolve!: (value: ReturnType<typeof jobFixture>) => void
  get.mockImplementationOnce(() => new Promise(r => { resolve = r }))
  act(() => stream.onopen?.()); await tick(160)
  act(() => stream.event(9))
  await act(async () => resolve(jobFixture()))
  get.mockResolvedValue({ ...jobFixture(), revision: 8, next_sequence: 10 })
  await tick(400)
  expect(h.result.current.data?.revision).toBe(8)
})
