import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { ShieldCheck } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { ROUTES } from '@/constants'
import { Spinner } from '@/components/ui/Spinner'

export function ProtectedRoute() {
  const { initializing, isAuthenticated } = useAuth()
  const location = useLocation()

  if (initializing) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4">
        <Spinner size="lg" className="text-primary" />
        <p className="text-sm text-text-secondary">Loading your session...</p>
      </div>
    )
  }

  if (!isAuthenticated) {
    const redirect = encodeURIComponent(location.pathname)
    return (
      <Navigate
        to={`${ROUTES.LOGIN}?redirect=${redirect}`}
        replace
        state={{ from: location }}
      />
    )
  }

  return <Outlet />
}

export function GuestRoute() {
  const { initializing, isAuthenticated, isLocalDemo } = useAuth()
  const location = useLocation()
  const redirect =
    (location.state as { from?: { pathname: string } } | null)?.from
      ?.pathname ??
    new URLSearchParams(location.search).get('redirect') ??
    ROUTES.APP_HOME

  if (initializing) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4">
        <Spinner size="lg" className="text-primary" />
        <p className="text-sm text-text-secondary">Loading...</p>
      </div>
    )
  }

  if (isAuthenticated) {
    return <Navigate to={isLocalDemo ? ROUTES.APP_HOME : redirect} replace />
  }

  return <Outlet />
}

export function AuthLoadingScreen() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background">
      <ShieldCheck className="h-8 w-8 text-primary" />
      <Spinner size="lg" className="text-primary" />
      <p className="text-sm text-text-secondary">Authenticating...</p>
    </div>
  )
}
