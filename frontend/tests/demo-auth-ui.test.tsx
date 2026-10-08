import { StrictMode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, MemoryRouter, RouterProvider } from 'react-router-dom'
import { createClient } from '@supabase/supabase-js'
import { AuthProvider } from '@/components/auth/AuthProvider'
import { useAuth } from '@/hooks/useAuth'
import { useAuthStore } from '@/stores/authStore'
import { useVerificationStore } from '@/stores/verificationStore'
import { localDemoUser, localDemoProfile } from '@/lib/demo-identity'
import { getSupabaseClient, isSupabaseConfigured } from '@/lib/supabase'
import * as authService from '@/services/authService'
import * as profileService from '@/services/profileService'
import { apiClient } from '@/services/api'
import { GuestRoute, ProtectedRoute } from '@/routes/ProtectedRoute'
import AppLayout from '@/layouts/AppLayout'
import LoginPage from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'
import ForgotPasswordPage from '@/pages/ForgotPasswordPage'
import ResetPasswordPage from '@/pages/ResetPasswordPage'
import VerifyPage from '@/pages/VerifyPage'
import HistoryPage from '@/pages/HistoryPage'
import SettingsPage from '@/pages/SettingsPage'
import { AppSidebar } from '@/components/app/AppSidebar'
import { LandingHero } from '@/components/landing/LandingHero'
import { LandingCTA } from '@/components/landing/LandingCTA'
import { LandingNavbar } from '@/components/landing/LandingNavbar'
import { LOCAL_HISTORY_KEY } from '@/services/localHistory'
import { toast } from 'sonner'
import { report } from './fixtures/report'

// Nonempty Supabase env remains present throughout every Demo test.
vi.mock('@/lib/env', () => ({ env: {
  supabaseUrl: 'https://offline-fixture.supabase.co', supabaseAnonKey: 'offline-public-key',
  apiBaseUrl: 'http://127.0.0.1:8000',
} }))
vi.mock('@supabase/supabase-js', () => ({ createClient: vi.fn(() => { throw new Error('Supabase initialization is forbidden in Demo') }) }))

let currentRouter: ReturnType<typeof createMemoryRouter> | undefined
beforeEach(() => {
  vi.stubEnv('DEV', true)
  vi.stubEnv('VITE_LOCAL_DEMO_MODE', 'true')
  useAuthStore.getState().reset()
  useAuthStore.getState().setInitializing(true)
  useVerificationStore.getState().clearRecords()
  localStorage.clear()
  vi.stubGlobal('IntersectionObserver', class {
    observe() {} disconnect() {} unobserve() {}
  })
  vi.mocked(createClient).mockClear()
})
afterEach(() => {
  cleanup()
  currentRouter?.dispose()
  currentRouter = undefined
  expect(createClient).not.toHaveBeenCalled()
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
})

function AuthStateProbe() {
  const { user, session, isAuthenticated, isLocalDemo, initializing } = useAuth()
  return <p>{JSON.stringify({ id: user?.id, session, isAuthenticated, isLocalDemo, initializing })}</p>
}

function mountRoute(path: string) {
  currentRouter = createMemoryRouter([
    { element: <GuestRoute />, children: [
      { path: '/login', element: <LoginPage /> },
      { path: '/register', element: <RegisterPage /> },
    ] },
    { path: '/forgot-password', element: <ForgotPasswordPage /> },
    { path: '/reset-password', element: <ResetPasswordPage /> },
    { element: <ProtectedRoute />, children: [{ element: <AppLayout />, children: [
      { path: '/app/home', element: <h1>Workspace ready</h1> },
      { path: '/app/verify', element: <VerifyPage /> },
      { path: '/app/verify/:verificationId', element: <VerifyPage /> },
      { path: '/app/history', element: <HistoryPage /> },
      { path: '/app/settings', element: <SettingsPage /> },
    ] }] },
  ], { initialEntries: [path] })
  const rendered = render(<StrictMode><AuthProvider><RouterProvider router={currentRouter} /></AuthProvider></StrictMode>)
  return { ...rendered, router: currentRouter }
}

describe('Demo authentication and account UI', () => {
  it('initializes a stable local identity/session=null without auth/profile/subscription calls', async () => {
    const session = vi.spyOn(authService, 'getSession')
    const subscription = vi.spyOn(authService, 'onAuthStateChange')
    const profile = vi.spyOn(profileService, 'getProfile')
    expect(isSupabaseConfigured()).toBe(true)
    render(<StrictMode><AuthProvider><AuthStateProbe /></AuthProvider></StrictMode>)
    await waitFor(() => expect(useAuthStore.getState().initializing).toBe(false))
    expect(useAuthStore.getState().user).toEqual(localDemoUser)
    expect(useAuthStore.getState().profile).toEqual(localDemoProfile)
    expect(useAuthStore.getState().session).toBeNull()
    expect(screen.getByText(/"isAuthenticated":true/).textContent).toContain('"isLocalDemo":true')
    expect(session).not.toHaveBeenCalled()
    expect(subscription).not.toHaveBeenCalled()
    expect(profile).not.toHaveBeenCalled()
  })

  it('service-level guards stop every cloud account action before client creation', async () => {
    expect(await authService.getSession()).toBeNull()
    expect(await authService.getUser()).toEqual(localDemoUser)
    expect(await profileService.getProfile(localDemoUser.id)).toEqual(localDemoProfile)
    await authService.signOut()
    await expect(authService.signIn('test@example.invalid', 'password')).rejects.toThrow('Local Demo')
    await expect(authService.signUp('test@example.invalid', 'password', 'Test')).rejects.toThrow('Local Demo')
    await expect(authService.sendPasswordReset('test@example.invalid')).rejects.toThrow('Local Demo')
    await expect(authService.updatePassword('password')).rejects.toThrow('Local Demo')
    await expect(profileService.updateProfile(localDemoUser.id, { full_name: 'Other' })).rejects.toThrow('read-only')
    expect(() => authService.onAuthStateChange(() => {})).toThrow('Local Demo')
    expect(() => getSupabaseClient()).toThrow('Local Demo')
  })

  it('ProtectedRoute admits the Demo user with a null session', async () => {
    const { router } = mountRoute('/app/home')
    await screen.findByRole('heading', { name: 'Workspace ready' })
    expect(router.state.location.pathname).toBe('/app/home')
    expect(useAuthStore.getState().session).toBeNull()
  })

  it.each(['/login', '/register', '/login?redirect=/login', '/register?redirect=/register', '/forgot-password', '/reset-password'])('redirects %s to workspace without account calls or loops', async (path) => {
    const reset = vi.spyOn(authService, 'sendPasswordReset')
    const update = vi.spyOn(authService, 'updatePassword')
    const signOut = vi.spyOn(authService, 'signOut')
    const { router } = mountRoute(path)
    await screen.findByRole('heading', { name: 'Workspace ready' })
    expect(router.state.location.pathname).toBe('/app/home')
    expect(reset).not.toHaveBeenCalled()
    expect(update).not.toHaveBeenCalled()
    expect(signOut).not.toHaveBeenCalled()
  })

  it('landing primary links enter Demo without a registration detour', () => {
    render(<MemoryRouter><AuthProvider><LandingNavbar /><LandingHero /><LandingCTA /></AuthProvider></MemoryRouter>)
    expect(screen.getByRole('link', { name: 'Start verifying' }).getAttribute('href')).toBe('/app/home')
    for (const link of screen.getAllByRole('link', { name: 'Enter Local Demo' })) {
      expect(link.getAttribute('href')).toBe('/app/home')
    }
    expect(screen.queryByRole('link', { name: 'Sign in' })).toBeNull()
  })

  it('settings/sidebar expose only the local read-only identity, without logout/password actions', () => {
    render(<MemoryRouter><AuthProvider><SettingsPage /><AppSidebar /></AuthProvider></MemoryRouter>)
    expect(screen.getAllByText('Local Demo').length).toBeGreaterThan(0)
    expect(screen.getByLabelText('Full name')).toHaveProperty('readOnly', true)
    expect(screen.getByLabelText('Email')).toHaveProperty('value', localDemoUser.email)
    expect(screen.queryByRole('button', { name: /logout|password/i })).toBeNull()
    expect(screen.queryByText(/existing Supabase session/)).toBeNull()
  })
})

describe('Demo report persistence through actual routes and components', () => {
  it('refresh-style initialization restores a complete report at its deep link', async () => {
    await useVerificationStore.getState().addRecord(localDemoUser.id, report)
    useVerificationStore.getState().clearRecords()
    const { router } = mountRoute(`/app/verify/${report.id}`)
    await screen.findByRole('heading', { name: 'Verification report' })
    expect(screen.getByText(report.reasoning)).toBeTruthy()
    expect(screen.getByText(report.evidence[0].excerpt)).toBeTruthy()
    expect(screen.getByText(report.context!)).toBeTruthy()
    expect(useVerificationStore.getState().getRecord(report.id)).toEqual(report)
    expect(router.state.location.pathname).toBe(`/app/verify/${report.id}`)
    expect(screen.queryByText('Verification report not found.')).toBeNull()
  })

  it('bad records produce a visible warning without hiding legitimate history', async () => {
    localStorage.setItem(LOCAL_HISTORY_KEY, JSON.stringify({ version: 1, records: [report, { ...report, id: 'bad', verdict: 'UNKNOWN' }] }))
    mountRoute('/app/history')
    await screen.findByText(report.claim)
    expect(screen.getByRole('status').textContent).toBe('Some local history records could not be loaded.')
  })

  it('a completed verification still renders a report and warns when persistent saving fails', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: {
      status: 'success', claim: report.claim, verdict: 'SUPPORTS', confidence: 0.8,
      paper: { paper_id: report.citation, doi: report.citation, title: report.paperTitle },
      summary: report.summary, reasoning: report.reasoning, evidence: [],
    } })
    const warning = vi.spyOn(toast, 'warning')
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('Full', 'QuotaExceededError') })
    mountRoute('/app/verify')
    fireEvent.change(await screen.findByLabelText('Scientific claim'), { target: { value: report.claim } })
    fireEvent.change(screen.getByLabelText('Citation / DOI'), { target: { value: report.citation } })
    fireEvent.click(screen.getByRole('button', { name: 'Verify Citation' }))
    await screen.findByRole('heading', { name: 'Verification report' })
    expect(screen.getByText(report.reasoning)).toBeTruthy()
    expect(useVerificationStore.getState().records).toHaveLength(1)
    expect(post).toHaveBeenCalledOnce()
    expect(warning).toHaveBeenCalledWith('Could not save locally. The report is still available now.')
  })
})
