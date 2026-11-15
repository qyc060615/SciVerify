import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LOCAL_HISTORY_KEY, readLocalHistory } from '@/services/localHistory'
import * as history from '@/services/historyService'
import { useVerificationStore } from '@/stores/verificationStore'
import { report } from './fixtures/report'

const supabase = vi.hoisted(() => ({ get: vi.fn(), configured: vi.fn(() => true) }))
vi.mock('@/lib/supabase', () => ({ getSupabaseClient: supabase.get, isSupabaseConfigured: supabase.configured }))

beforeEach(() => {
  vi.stubEnv('DEV', true)
  vi.stubEnv('VITE_LOCAL_DEMO_MODE', 'true')
  localStorage.clear()
  useVerificationStore.getState().clearRecords()
  supabase.get.mockReset().mockImplementation(() => { throw new Error('Demo must not access Supabase') })
  supabase.configured.mockClear()
})
afterEach(() => {
  expect(supabase.get).not.toHaveBeenCalled()
  expect(supabase.configured).not.toHaveBeenCalled()
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
})

function storeRaw(records: unknown[], version = 1) {
  localStorage.setItem(LOCAL_HISTORY_KEY, JSON.stringify({ version, records }))
}

describe('local history through the existing service/store interfaces', () => {
  it('saves complete reports, sorts newest first, upserts the same ID and deletes persistently', async () => {
    const newer = { ...report, id: 'report-two', createdAt: '2026-01-03T00:00:00.000Z' }
    await history.saveVerificationHistory('local-demo-user', report)
    await history.saveVerificationHistory('local-demo-user', newer)
    const updated = { ...report, summary: 'Updated summary' }
    await history.saveVerificationHistory('local-demo-user', updated)
    expect(await history.listVerificationHistory('local-demo-user')).toEqual([newer, updated])
    expect(JSON.parse(localStorage.getItem(LOCAL_HISTORY_KEY)!)).toEqual({ version: 1, records: [newer, updated] })
    await useVerificationStore.getState().loadRecords('local-demo-user')
    await useVerificationStore.getState().deleteRecord('local-demo-user', report.id)
    expect(useVerificationStore.getState().records).toEqual([newer])
    expect(readLocalHistory().records).toEqual([newer])
  })

  it('restores the full report after memory is cleared, without transforming scientific fields', async () => {
    expect(await useVerificationStore.getState().addRecord('local-demo-user', report)).toEqual({ saved: true })
    useVerificationStore.getState().clearRecords()
    await useVerificationStore.getState().loadRecords('local-demo-user')
    expect(useVerificationStore.getState().getRecord(report.id)).toEqual(report)
    expect(useVerificationStore.getState().hydrated).toBe(true)
  })

  it.each(['{broken', JSON.stringify({ version: 99, records: [report] }), JSON.stringify({ version: 1, records: {} }), 'null'])('handles an unreadable envelope: %s', async (raw) => {
    localStorage.setItem(LOCAL_HISTORY_KEY, raw)
    await useVerificationStore.getState().loadRecords('local-demo-user')
    const state = useVerificationStore.getState()
    expect(state.records).toEqual([])
    expect(state.warning).toMatch(/could not be read/)
    expect(state.error).toBeNull()
    expect(state.hydrated).toBe(true)
    expect(localStorage.getItem(LOCAL_HISTORY_KEY)).toBe(raw)
  })

  it.each([
    { verdict: 'UNKNOWN' }, { verdict: 'supports' }, { verdict: null },
    { id: '' }, { claim: ' ' }, { citation: null }, { confidence: '80' },
    { confidence: 101 }, { confidence: -1 }, { createdAt: 'not-a-date' },
    { evidence: {} }, { evidence: [{ excerpt: {} }] }, { prosecutor: [] },
    { defenderDetail: { analysis: 'Invalid nested report' } },
    { claimTraceability: { segments: 'bad', overallCoverage: 80 } },
  ])('skips an invalid record while retaining the valid report: %j', async (invalidFields) => {
    storeRaw([report, { ...report, id: 'invalid-report', ...invalidFields }])
    const warn = vi.fn()
    expect(await history.listVerificationHistory('local-demo-user', warn)).toEqual([report])
    expect(warn).toHaveBeenCalledWith('Some local history records could not be loaded.')
    expect(readLocalHistory().records.some((r) => r.verdict === 'INSUFFICIENT')).toBe(false)
  })

  it('does not accept arrays/null as a report object', () => {
    storeRaw([null, [], report])
    expect(readLocalHistory()).toEqual({ records: [report], warning: 'Some local history records could not be loaded.' })
  })

  it('does not overwrite an unreadable envelope or pretend a deletion succeeded', async () => {
    const original = JSON.stringify({ version: 99, records: [report] })
    localStorage.setItem(LOCAL_HISTORY_KEY, original)
    expect(await useVerificationStore.getState().addRecord('local-demo-user', report)).toEqual({ saved: false })
    await expect(useVerificationStore.getState().deleteRecord('local-demo-user', report.id)).rejects.toThrow('Unsupported local history')
    expect(useVerificationStore.getState().getRecord(report.id)).toEqual(report)
    expect(localStorage.getItem(LOCAL_HISTORY_KEY)).toBe(original)
  })

  it('getItem SecurityError becomes a nonblocking warning', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('Disabled', 'SecurityError') })
    await useVerificationStore.getState().loadRecords('local-demo-user')
    expect(useVerificationStore.getState().warning).toMatch(/unavailable/)
    expect(useVerificationStore.getState().error).toBeNull()
    expect(useVerificationStore.getState().hydrated).toBe(true)
  })

  it.each(['QuotaExceededError', 'SecurityError'])('save failure retains the report in memory: %s', async (name) => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('Unavailable', name) })
    expect(await useVerificationStore.getState().addRecord('local-demo-user', report)).toEqual({ saved: false })
    expect(useVerificationStore.getState().getRecord(report.id)).toEqual(report)
  })

  it('failed storage reads must not turn a save into false success', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Storage disabled') })
    expect(await useVerificationStore.getState().addRecord('local-demo-user', report)).toEqual({ saved: false })
    expect(useVerificationStore.getState().getRecord(report.id)).toEqual(report)
  })

  it('stringify failure retains the current report', async () => {
    vi.spyOn(JSON, 'stringify').mockImplementation(() => { throw new Error('Cannot serialize') })
    expect(await useVerificationStore.getState().addRecord('local-demo-user', report)).toEqual({ saved: false })
    expect(useVerificationStore.getState().getRecord(report.id)).toEqual(report)
  })

  it('failed persistent deletion rejects and retains the memory and stored record', async () => {
    await useVerificationStore.getState().addRecord('local-demo-user', report)
    const original = localStorage.getItem(LOCAL_HISTORY_KEY)
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Delete write failed') })
    await expect(useVerificationStore.getState().deleteRecord('local-demo-user', report.id)).rejects.toThrow('Delete write failed')
    expect(useVerificationStore.getState().getRecord(report.id)).toEqual(report)
    expect(localStorage.getItem(LOCAL_HISTORY_KEY)).toBe(original)
  })
})
