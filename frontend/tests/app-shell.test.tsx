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

it.each(['/app/manuscripts', '/app/repository', '/app/history', '/app/settings', '/app/manuscripts/jobs/job_test'].flatMap(route => [1, 50].map(lines => ({ route, lines }))))('keeps full-width scrolling separate from centered content on $route with $lines lines', ({ route, lines }) => {
  render(<MemoryRouter initialEntries={[route]}><Routes><Route element={<AppLayout />}><Route path="*" element={<div>{Array.from({ length: lines }, (_, index) => <p key={index}>Content {index}</p>)}</div>} /></Route></Routes></MemoryRouter>)
  const main = screen.getByRole('main')
  expect(main.className).toContain('overflow-y-auto')
  expect(main.className).toContain('min-h-0')
  expect(main.className).toContain('w-full')
  expect(main.className).toContain('min-w-0')
  expect(main.className).not.toContain('max-w-')
  expect(main.className).not.toContain('mx-auto')
  const content = main.firstElementChild as HTMLElement
  expect(content.className).toContain('mx-auto')
  expect(content.className).toContain('max-w-6xl')
  expect(content.className).toContain('px-4 py-6 sm:px-6 lg:px-8 lg:py-8')
  expect(content.querySelector('[class*="overflow-y-auto"]')).toBeNull()
  expect(screen.getByText('Content ' + (lines - 1)).closest('main')).toBe(main)
  const shell = main.parentElement!.parentElement!.parentElement!
  expect(shell.className).toContain('h-dvh')
  expect(shell.className).toContain('overflow-hidden')
  const sidebar = shell.querySelector('aside')!
  expect(sidebar.className).toContain('border-r')
  expect(sidebar.className).toContain('lg:block')
  expect(sidebar.querySelector('[class*="overflow-y-auto"]')).toBeTruthy()
  expect(sidebar.textContent).toContain('ResearchGuard')
  expect(sidebar.textContent).toContain('Local Demo')
  expect(main.contains(sidebar)).toBe(false)
})
