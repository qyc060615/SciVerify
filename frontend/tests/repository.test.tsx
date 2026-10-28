import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import RepositoryPage from '@/pages/RepositoryPage'
import { apiClient } from '@/services/api'
import { AppSidebar, AppMobileNav } from '@/components/app/AppSidebar'

vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: null, signOut: vi.fn(), isLocalDemo: true }) }))
vi.mock('@/hooks/useUserDisplayName', () => ({ useUserDisplayName: () => 'Local researcher' }))
const row = { id: 'real-record', title: 'A saved reference', doi: '10.1234/example', literature_type: 'Reference', format: 'html', source_type: 'Retrieved HTML', availability: 'available', raw_content_sha256: 'a'.repeat(64), source_url: 'https://example.org/paper', related_job_ids: ['job_' + 'a'.repeat(32)] }
function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter><RepositoryPage /></MemoryRouter></QueryClientProvider>)
}
beforeEach(() => { vi.stubEnv('DEV', true); vi.stubEnv('VITE_LOCAL_DEMO_MODE', 'true') })
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllEnvs() })

describe('Repository reads backend inventory', () => {
  it('loads genuine metadata, searches, filters and re-reads on refresh-style remount', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { records: [row], warnings: [] } })
    const view = mount()
    expect(screen.getByText('Loading literature…')).toBeTruthy()
    await screen.findByRole('heading', { name: row.title })
    expect(screen.getByText('Available · Hash verified')).toBeTruthy()
    fireEvent.click(screen.getByText('View literature details'))
    expect(screen.getByRole('link', { name: row.related_job_ids[0] }).getAttribute('href')).toContain('/app/manuscripts/jobs/')
    fireEvent.change(screen.getByLabelText('Search title or DOI'), { target: { value: '10.1234' } })
    expect(screen.getByRole('heading', { name: row.title })).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Literature type'), { target: { value: 'Manuscript' } })
    expect(screen.queryByRole('heading', { name: row.title })).toBeNull()
    view.unmount()
    get.mockResolvedValue({ data: { records: [{ ...row, availability: 'missing' }], warnings: [] } })
    mount()
    await screen.findByText('File missing')
    expect(get).toHaveBeenCalledTimes(2)
    expect(get.mock.calls[0][0]).toBe('/api/repository')
  })
  it('does not invent records for an empty library', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { records: [], warnings: [] } })
    mount()
    await screen.findByText('No stored literature found')
    expect(screen.queryByText(row.title)).toBeNull()
  })
  it('shows errors, partial-inventory warnings and rejects unsafe source links', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { records: [{ ...row, source_url: 'javascript:alert(1)' }], warnings: ['Some source records could not be read and were skipped.'] } })
    mount()
    await screen.findByText(row.title)
    expect(screen.getByText(/Some source records/)).toBeTruthy()
    expect(screen.queryByRole('link', { name: /javascript/ })).toBeNull()
  })
  it('shows API failure rather than an empty success state', async () => {
    vi.spyOn(apiClient, 'get').mockRejectedValue(new Error('offline'))
    mount()
    await screen.findByRole('alert')
    expect(screen.queryByText('No stored literature found')).toBeNull()
  })
})

describe('Workspace navigation', () => {
  it.each([false, true])('has the same navigation on mobile=%s and matches nested routes', mobile => {
    const close = vi.fn()
    render(<MemoryRouter initialEntries={['/app/manuscripts/jobs/job_abc']}>
      {mobile ? <AppMobileNav open onClose={close} /> : <AppSidebar />}
    </MemoryRouter>)
    const links = screen.getAllByRole('link')
    expect(links.map(link => link.textContent).filter(text => ['Whole-paper Verification', 'Repository', 'History', 'Settings'].includes(text ?? ''))).toEqual(['Whole-paper Verification', 'Repository', 'History', 'Settings'])
    expect(screen.queryByRole('link', { name: 'Dashboard' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'New Verification' })).toBeNull()
    expect(screen.getByRole('link', { name: 'Whole-paper Verification' }).getAttribute('aria-current')).toBe('page')
    expect(screen.getByRole('link', { name: /SciVerify/ }).getAttribute('href')).toBe('/app/manuscripts')
    fireEvent.click(screen.getByRole('link', { name: 'Repository' }))
    if (mobile) expect(close).toHaveBeenCalledOnce()
    expect(screen.getByRole('link', { name: 'Repository' }).getAttribute('aria-current')).toBe('page')
  })
  it('preserves the non-demo home destination and local-only feature gates', () => {
    vi.stubEnv('VITE_LOCAL_DEMO_MODE', 'false')
    render(<MemoryRouter><AppSidebar /></MemoryRouter>)
    expect(screen.getByRole('link', { name: /SciVerify/ }).getAttribute('href')).toBe('/app/home')
    expect(screen.queryByRole('link', { name: 'Repository' })).toBeNull()
    expect(screen.getByRole('link', { name: 'History' }).getAttribute('href')).toBe('/app/history')
  })
})
