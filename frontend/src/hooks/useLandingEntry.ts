import { useAuth } from '@/hooks/useAuth'
import { ROUTES } from '@/constants'

export function useLandingEntry() {
  const { isLocalDemo } = useAuth()
  return {
    isLocalDemo,
    startPath: isLocalDemo ? ROUTES.APP_HOME : ROUTES.REGISTER,
  }
}
