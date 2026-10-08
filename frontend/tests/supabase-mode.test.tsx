import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { createClient } from '@supabase/supabase-js'
import { AuthProvider } from '@/components/auth/AuthProvider'
import { useAuth } from '@/hooks/useAuth'
import { useAuthStore } from '@/stores/authStore'
import { resetSupabaseClient } from '@/lib/supabase'
import { env } from '@/lib/env'
import { localDemoUser, localDemoProfile } from '@/lib/demo-identity'
import * as auth from '@/services/authService'
import * as profile from '@/services/profileService'
import * as history from '@/services/historyService'
import { GuestRoute, ProtectedRoute } from '@/routes/ProtectedRoute'
import LoginPage from '@/pages/LoginPage'
import { report } from './fixtures/report'

const sdk = vi.hoisted(() => ({
  getSession: vi.fn(), getUser: vi.fn(), signInWithPassword: vi.fn(), signUp: vi.fn(),
  signOut: vi.fn(), resetPasswordForEmail: vi.fn(), updateUser: vi.fn(),
  onAuthStateChange: vi.fn(), unsubscribe: vi.fn(), from: vi.fn(),
}))
vi.mock('@/lib/env', () => ({ env: {
  supabaseUrl: 'https://offline-fixture.supabase.co', supabaseAnonKey: 'offline-public-key', apiBaseUrl: 'http://127.0.0.1:8000',
} }))
vi.mock('@supabase/supabase-js', () => ({ createClient: vi.fn(() => ({ auth: sdk, from: sdk.from })) }))

const remoteUser = { ...localDemoUser, id: 'remote-user', aud: 'authenticated' }
const remoteProfile = { ...localDemoProfile, id: 'remote-profile', user_id: remoteUser.id, full_name: 'Cloud user' }
// Offline normal-mode SDK fixture only; Demo never creates a session.
const session = { user: remoteUser, access_token: 'offline-test-token', refresh_token: 'offline-test-refresh', token_type: 'bearer', expires_in: 3600 }
let router: ReturnType<typeof createMemoryRouter> | undefined

beforeEach(() => {
  vi.stubEnv('DEV', true)
  vi.stubEnv('VITE_LOCAL_DEMO_MODE', 'false')
  vi.clearAllMocks()
  resetSupabaseClient()
  useAuthStore.getState().reset()
  useAuthStore.getState().setInitializing(true)
  sdk.getSession.mockResolvedValue({ data: { session }, error: null })
  sdk.getUser.mockResolvedValue({ data: { user: remoteUser }, error: null })
  sdk.signInWithPassword.mockResolvedValue({ data: { user: remoteUser, session }, error: null })
  sdk.signUp.mockResolvedValue({ data: { user: remoteUser, session }, error: null })
  sdk.signOut.mockResolvedValue({ error: null })
  sdk.resetPasswordForEmail.mockResolvedValue({ error: null })
  sdk.updateUser.mockResolvedValue({ error: null })
  sdk.onAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: sdk.unsubscribe } } })
})
afterEach(() => { cleanup(); router?.dispose(); router = undefined; vi.unstubAllEnvs() })

function remoteTable(data: unknown) {
  const response = { data, error: null }
  const table = {
    select: vi.fn(), eq: vi.fn(), order: vi.fn().mockResolvedValue(response),
    upsert: vi.fn().mockResolvedValue(response), delete: vi.fn(), update: vi.fn(),
    maybeSingle: vi.fn().mockResolvedValue(response), single: vi.fn().mockResolvedValue(response),
    then: (resolve: (value: unknown) => unknown) => Promise.resolve(response).then(resolve),
  }
  for (const method of [table.select, table.eq, table.delete, table.update]) method.mockReturnValue(table)
  return table
}

function AuthProbe() {
  const { isAuthenticated, isLocalDemo, session: currentSession } = useAuth()
  return <p>{JSON.stringify({ isAuthenticated, isLocalDemo, hasSession: Boolean(currentSession) })}</p>
}

it('normal AuthProvider still loads a cloud session/profile and subscribes/unsubscribes', async () => {
  const table = remoteTable(remoteProfile)
  sdk.from.mockReturnValue(table)
  const mounted = render(<AuthProvider><AuthProbe /></AuthProvider>)
  await waitFor(() => expect(useAuthStore.getState().initializing).toBe(false))
  expect(useAuthStore.getState().user).toEqual(remoteUser)
  expect(useAuthStore.getState().profile).toEqual(remoteProfile)
  expect(screen.getByText(/"isAuthenticated":true/).textContent).toContain('"isLocalDemo":false')
  expect(sdk.getSession).toHaveBeenCalledOnce()
  expect(sdk.from).toHaveBeenCalledWith('profiles')
  expect(sdk.onAuthStateChange).toHaveBeenCalledOnce()
  mounted.unmount()
  expect(sdk.unsubscribe).toHaveBeenCalledOnce()
})

it('normal account services retain the existing SDK calls', async () => {
  expect(await auth.getSession()).toEqual(session)
  expect(await auth.getUser()).toEqual(remoteUser)
  expect(await auth.signIn('cloud@example.invalid', 'test-password')).toEqual({ user: remoteUser, session })
  await auth.signUp('cloud@example.invalid', 'test-password', 'Cloud user')
  await auth.sendPasswordReset('cloud@example.invalid')
  await auth.updatePassword('new-password')
  await auth.signOut()
  expect(sdk.signInWithPassword).toHaveBeenCalledWith({ email: 'cloud@example.invalid', password: 'test-password' })
  expect(sdk.signUp).toHaveBeenCalledOnce()
  expect(sdk.resetPasswordForEmail).toHaveBeenCalledOnce()
  expect(sdk.updateUser).toHaveBeenCalledWith({ password: 'new-password' })
  expect(sdk.signOut).toHaveBeenCalledOnce()
})

it('normal profile and history retain remote table operations and full report parsing', async () => {
  const profiles = remoteTable(remoteProfile)
  const rows = [{ id: report.id, user_id: remoteUser.id, claim: report.claim, doi: report.citation, verdict: report.verdict, confidence: report.confidence, result_json: report, created_at: report.createdAt }]
  const records = remoteTable(rows)
  sdk.from.mockImplementation((name) => name === 'profiles' ? profiles : records)
  expect(await profile.getProfile(remoteUser.id)).toEqual(remoteProfile)
  await profile.updateProfile(remoteUser.id, { full_name: 'Cloud user' })
  await history.saveVerificationHistory(remoteUser.id, report)
  expect(records.upsert.mock.calls[0][0]).toMatchObject({ user_id: remoteUser.id, result_json: report })
  expect(await history.listVerificationHistory(remoteUser.id)).toEqual([report])
  expect(records.eq).toHaveBeenCalledWith('user_id', remoteUser.id)
  expect(records.order).toHaveBeenCalledWith('created_at', { ascending: false })
  await history.deleteVerificationHistory(remoteUser.id, report.id)
  expect(records.delete).toHaveBeenCalledOnce()
  expect(records.eq).toHaveBeenCalledWith('id', report.id)
})

it('a user without a session remains unauthenticated in normal mode', () => {
  useAuthStore.getState().setAuth(remoteUser, null)
  render(<AuthProbe />)
  expect(screen.getByText(/"isAuthenticated":false/)).toBeTruthy()
})

it('missing Supabase configuration does not silently enable Demo or create a client', async () => {
  const previous = env.supabaseUrl
  // This object is the offline env fixture, not a real environment file.
  Object.assign(env, { supabaseUrl: '' })
  try {
    render(<AuthProvider><AuthProbe /></AuthProvider>)
    await waitFor(() => expect(useAuthStore.getState().initializing).toBe(false))
    expect(useAuthStore.getState().user).toBeNull()
    expect(screen.getByText(/"isAuthenticated":false/).textContent).toContain('"isLocalDemo":false')
    expect(createClient).not.toHaveBeenCalled()
  } finally {
    Object.assign(env, { supabaseUrl: previous })
  }
})

it('normal protected routes still send unauthenticated users to the login form', async () => {
  sdk.getSession.mockResolvedValue({ data: { session: null }, error: null })
  router = createMemoryRouter([
    { element: <ProtectedRoute />, children: [{ path: '/app/home', element: <p>Protected workspace</p> }] },
    { element: <GuestRoute />, children: [{ path: '/login', element: <LoginPage /> }] },
  ], { initialEntries: ['/app/home'] })
  render(<AuthProvider><RouterProvider router={router} /></AuthProvider>)
  await screen.findByRole('heading', { name: 'Sign in' })
  expect(router.state.location.pathname).toBe('/login')
  expect(screen.queryByText('Protected workspace')).toBeNull()
})

it('production ignores a leftover Demo flag and uses the normal cloud initializer', async () => {
  vi.stubEnv('DEV', false)
  vi.stubEnv('VITE_LOCAL_DEMO_MODE', 'true')
  sdk.from.mockReturnValue(remoteTable(remoteProfile))
  render(<AuthProvider><AuthProbe /></AuthProvider>)
  await waitFor(() => expect(useAuthStore.getState().initializing).toBe(false))
  expect(sdk.getSession).toHaveBeenCalledOnce()
  expect(createClient).toHaveBeenCalledOnce()
  expect(useAuthStore.getState().user?.id).toBe(remoteUser.id)
  expect(screen.getByText(/"isLocalDemo":false/)).toBeTruthy()
})
