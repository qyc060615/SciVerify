import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import AppLayout from '@/layouts/AppLayout'
import { LandingNavbar } from '@/components/landing/LandingNavbar'

vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: null, isLocalDemo: true, isAuthenticated: false, initializing: false, signOut: vi.fn() }) }))
vi.mock('@/hooks/useUserDisplayName', () => ({ useUserDisplayName: () => 'Local researcher' }))
vi.mock('@/lib/demo-mode', () => ({ isLocalDemoMode: () => true }))
vi.mock('@/components/verification/HistoryHydrator', () => ({ HistoryHydrator: () => null }))
vi.mock('@/stores/verificationStore', () => ({ useVerificationStore: (selector: (state: { warning: null }) => unknown) => selector({ warning: null }) }))
afterEach(cleanup)

it('renders the complete landing brand beside the existing shield', () => {
  render(<MemoryRouter><LandingNavbar /></MemoryRouter>)
  const brand = screen.getByRole('link', { name: 'ResearchGuard' })
  expect(brand.querySelector('svg')).toBeTruthy()
  expect(screen.queryByRole('link', { name: 'SciVerify' })).toBeNull()
})

it.each(['/app/manuscripts', '/app/repository', '/app/history', '/app/settings', '/app/manuscripts/jobs/job_test'])('uses the shared viewport shell and independent main scrolling on %s', route => {
  render(<MemoryRouter initialEntries={[route]}><Routes><Route element={<AppLayout />}><Route path="*" element={<div>{Array.from({ length: 50 }, (_, index) => <p key={index}>Long content {index}</p>)}</div>} /></Route></Routes></MemoryRouter>)
  const main = screen.getByRole('main')
  expect(main.className).toContain('overflow-y-auto')
  expect(main.className).toContain('min-h-0')
  const shell = main.parentElement!.parentElement!.parentElement!
  expect(shell.className).toContain('h-dvh')
  expect(shell.className).toContain('overflow-hidden')
  const sidebar = shell.querySelector('aside')!
  expect(sidebar.className).toContain('border-r')
  expect(sidebar.className).toContain('lg:block')
  expect(sidebar.querySelector('[class*="overflow-y-auto"]')).toBeTruthy()
  expect(sidebar.textContent).toContain('ResearchGuard')
  expect(sidebar.textContent).toContain('Local Demo')
  expect(main.textContent).toContain('Long content 49')
})
