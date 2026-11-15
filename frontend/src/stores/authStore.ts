import type { Session, User } from '@supabase/supabase-js'
import { create } from 'zustand'
import type { UserProfile } from '@/types/auth'

interface AuthStoreState {
  user: User | null
  session: Session | null
  profile: UserProfile | null
  initializing: boolean
  isRecoverySession: boolean
  setAuth: (user: User | null, session: Session | null) => void
  setProfile: (profile: UserProfile | null) => void
  setInitializing: (initializing: boolean) => void
  setRecoverySession: (isRecoverySession: boolean) => void
  reset: () => void
}

export const useAuthStore = create<AuthStoreState>((set) => ({
  user: null,
  session: null,
  profile: null,
  initializing: true,
  isRecoverySession: false,
  setAuth: (user, session) => set({ user, session }),
  setProfile: (profile) => set({ profile }),
  setInitializing: (initializing) => set({ initializing }),
  setRecoverySession: (isRecoverySession) => set({ isRecoverySession }),
  reset: () =>
    set({
      user: null,
      session: null,
      profile: null,
      isRecoverySession: false,
    }),
}))
