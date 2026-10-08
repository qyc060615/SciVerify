import { useEffect, type ReactNode } from 'react'
import * as authService from '@/services/authService'
import * as profileService from '@/services/profileService'
import { isSupabaseConfigured } from '@/lib/supabase'
import { useAuthStore } from '@/stores/authStore'
import { isLocalDemoMode } from '@/lib/demo-mode'
import { localDemoUser, localDemoProfile } from '@/lib/demo-identity'

async function loadProfile(userId: string) {
  try {
    return await profileService.getProfile(userId)
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const {
    setAuth,
    setProfile,
    setInitializing,
    setRecoverySession,
    reset,
  } = useAuthStore()

  useEffect(() => {
    let mounted = true

    const finishInitializing = () => {
      if (mounted) {
        setInitializing(false)
      }
    }

    if (isLocalDemoMode()) {
      setAuth(localDemoUser, null)
      setProfile(localDemoProfile)
      setRecoverySession(false)
      finishInitializing()
      return () => {
        mounted = false
      }
    }

    if (!isSupabaseConfigured()) {
      finishInitializing()
      return () => {
        mounted = false
      }
    }

    const initialize = async () => {
      try {
        const session = await authService.getSession()
        if (!mounted) return

        setAuth(session?.user ?? null, session)

        if (session?.user) {
          const profile = await loadProfile(session.user.id)
          if (mounted) setProfile(profile)
        }
      } catch {
        if (mounted) {
          reset()
        }
      } finally {
        finishInitializing()
      }
    }

    void initialize()

    let subscription: { unsubscribe: () => void } | undefined

    try {
      const { data } = authService.onAuthStateChange(async (event, session) => {
        if (!mounted) return

        if (event === 'PASSWORD_RECOVERY') {
          setRecoverySession(true)
        }

        if (event === 'SIGNED_OUT') {
          reset()
          setInitializing(false)
          return
        }

        setAuth(session?.user ?? null, session)

        if (session?.user) {
          const profile = await loadProfile(session.user.id)
          if (mounted) setProfile(profile)
        } else {
          setProfile(null)
        }

        if (
          event === 'USER_UPDATED' &&
          !useAuthStore.getState().isRecoverySession
        ) {
          setRecoverySession(false)
        }
      })

      subscription = data.subscription
    } catch {
      finishInitializing()
    }

    return () => {
      mounted = false
      subscription?.unsubscribe()
    }
  }, [reset, setAuth, setInitializing, setProfile, setRecoverySession])

  return children
}
