import { Navigate, Outlet } from 'react-router-dom'
import { isLocalDemoMode } from '@/lib/demo-mode'
import { ROUTES } from '@/constants'

export function WholePaperRoute() {
  return isLocalDemoMode() ? <Outlet /> : <Navigate to={ROUTES.APP_VERIFY} replace />
}
