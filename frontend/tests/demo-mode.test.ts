import { afterEach, describe, expect, it, vi } from 'vitest'
import { isLocalDemoMode } from '@/lib/demo-mode'

afterEach(() => vi.unstubAllEnvs())

describe('development-only Local Demo switch', () => {
  it.each([
    [true, 'true', true], [true, undefined, false], [true, 'false', false],
    [true, 'True', false], [true, ' true ', false], [false, 'true', false],
    [false, 'false', false], [false, undefined, false],
  ])('DEV=%s, flag=%s => %s', (dev, flag, expected) => {
    vi.stubEnv('DEV', dev)
    vi.stubEnv('VITE_LOCAL_DEMO_MODE', flag)
    expect(isLocalDemoMode()).toBe(expected)
  })

  it('Demo readiness needs an API URL, while normal readiness still needs Supabase', async () => {
    vi.stubEnv('DEV', true)
    vi.stubEnv('VITE_LOCAL_DEMO_MODE', 'true')
    vi.stubEnv('VITE_API_BASE_URL', 'http://127.0.0.1:8000')
    vi.stubEnv('VITE_SUPABASE_URL', '')
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', '')
    vi.resetModules()
    const { isEnvConfigured } = await import('@/lib/env')
    expect(isEnvConfigured()).toBe(true)
    vi.stubEnv('VITE_LOCAL_DEMO_MODE', 'false')
    expect(isEnvConfigured()).toBe(false)
    vi.stubEnv('VITE_LOCAL_DEMO_MODE', 'true')
    vi.stubEnv('VITE_API_BASE_URL', '')
    vi.resetModules()
    expect((await import('@/lib/env')).isEnvConfigured()).toBe(false)
  })
})
