import { Outlet } from 'react-router-dom'
import { Toaster } from 'sonner'

export default function RootLayout() {
  return (
    <div className="min-h-screen bg-background text-text-primary">
      <main className="container mx-auto px-4 py-8">
        <Outlet />
      </main>
      <Toaster richColors theme="dark" />
    </div>
  )
}
