import { Outlet } from 'react-router-dom'
import { useState } from 'react'
import { Toaster } from 'sonner'
import {
  AppMobileMenuButton,
  AppMobileNav,
  AppSidebar,
} from '@/components/app/AppSidebar'
import { HistoryHydrator } from '@/components/verification/HistoryHydrator'
import { useVerificationStore } from '@/stores/verificationStore'

export default function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const historyWarning = useVerificationStore((state) => state.warning)

  return (
    <div className="min-h-screen bg-background text-text-primary">
      <HistoryHydrator />
      <div className="flex min-h-screen">
        <aside className="hidden w-64 shrink-0 border-r border-border bg-surface/95 lg:block">
          <AppSidebar />
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center border-b border-border px-4 py-3 lg:hidden">
            <AppMobileMenuButton onClick={() => setMobileOpen(true)} />
            <span className="ml-3 text-sm font-medium text-text-primary">
              SciVerify Workspace
            </span>
          </div>

          <main className="mx-auto w-full max-w-6xl flex-1 overflow-x-hidden px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
            {historyWarning ? (
              <p role="status" className="mb-4 rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-text-secondary">
                {historyWarning}
              </p>
            ) : null}
            <Outlet />
          </main>
        </div>
      </div>

      <AppMobileNav open={mobileOpen} onClose={() => setMobileOpen(false)} />
      <Toaster richColors theme="dark" />
    </div>
  )
}
