import * as authService from '@/services/authService'
import { useAuthStore } from '@/stores/authStore'
import { isLocalDemoMode } from '@/lib/demo-mode'
import { LOCAL_DEMO_USER_ID } from '@/lib/demo-identity'

export function useAuth() {
  const isLocalDemo = isLocalDemoMode()
  const {
    user,
    session,
    profile,
    initializing,
    isRecoverySession,
  } = useAuthStore()

  return {
    user,
    session,
    profile,
    initializing,
    isRecoverySession,
    loading: initializing,
    isLocalDemo,
    isAuthenticated: isLocalDemo
      ? user?.id === LOCAL_DEMO_USER_ID
      : Boolean(user && session),
    signIn: authService.signIn,
    signUp: authService.signUp,
    signOut: authService.signOut,
    resetPassword: authService.sendPasswordReset,
    updatePassword: authService.updatePassword,
  }
}
