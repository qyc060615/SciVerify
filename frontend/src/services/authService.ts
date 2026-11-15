import type { Session, User } from '@supabase/supabase-js'
import { getSupabaseClient, isSupabaseConfigured } from '@/lib/supabase'
import { mapAuthError } from '@/lib/auth-errors'
import type { SignUpResult } from '@/types/auth'
import { isLocalDemoMode } from '@/lib/demo-mode'
import { localDemoUser } from '@/lib/demo-identity'

function requireSupabase() {
  if (isLocalDemoMode()) {
    throw new Error('Account management is unavailable in Local Demo mode.')
  }

  if (!isSupabaseConfigured()) {
    throw new Error(
      'Supabase is not configured. Add VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY to frontend/.env',
    )
  }

  return getSupabaseClient()
}

export async function getSession(): Promise<Session | null> {
  if (isLocalDemoMode()) return null
  if (!isSupabaseConfigured()) {
    return null
  }

  const { data, error } = await requireSupabase().auth.getSession()
  if (error) throw new Error(mapAuthError(error, 'Unable to load session.'))
  return data.session
}

export async function getUser(): Promise<User | null> {
  if (isLocalDemoMode()) return localDemoUser
  if (!isSupabaseConfigured()) {
    return null
  }

  const { data, error } = await requireSupabase().auth.getUser()
  if (error) throw new Error(mapAuthError(error, 'Unable to load user.'))
  return data.user
}

export async function signIn(
  email: string,
  password: string,
): Promise<{ user: User; session: Session }> {
  const { data, error } = await requireSupabase().auth.signInWithPassword({
    email,
    password,
  })

  if (error) {
    throw new Error(mapAuthError(error, 'Unable to sign in. Please try again.'))
  }

  if (!data.user || !data.session) {
    throw new Error('Unable to sign in. Please try again.')
  }

  return { user: data.user, session: data.session }
}

export async function signUp(
  email: string,
  password: string,
  fullName: string,
): Promise<SignUpResult> {
  const { data, error } = await requireSupabase().auth.signUp({
    email,
    password,
    options: {
      data: {
        full_name: fullName,
      },
    },
  })

  if (error) {
    throw new Error(
      mapAuthError(error, 'Unable to create account. Please try again.'),
    )
  }

  const needsEmailConfirmation = Boolean(data.user && !data.session)

  return {
    user: data.user,
    session: data.session,
    needsEmailConfirmation,
  }
}

export async function signOut(): Promise<void> {
  if (isLocalDemoMode()) return
  if (!isSupabaseConfigured()) {
    return
  }

  const { error } = await requireSupabase().auth.signOut()
  if (error) {
    throw new Error(mapAuthError(error, 'Unable to sign out. Please try again.'))
  }
}

export async function sendPasswordReset(email: string): Promise<void> {
  const redirectTo = `${window.location.origin}/reset-password`

  const { error } = await requireSupabase().auth.resetPasswordForEmail(email, {
    redirectTo,
  })

  if (error) {
    throw new Error(
      mapAuthError(error, 'Unable to send reset email. Please try again.'),
    )
  }
}

export async function updatePassword(password: string): Promise<void> {
  const { error } = await requireSupabase().auth.updateUser({ password })

  if (error) {
    throw new Error(
      mapAuthError(error, 'Unable to update password. Please try again.'),
    )
  }
}

export function onAuthStateChange(
  callback: Parameters<
    ReturnType<typeof getSupabaseClient>['auth']['onAuthStateChange']
  >[0],
) {
  return requireSupabase().auth.onAuthStateChange(callback)
}
