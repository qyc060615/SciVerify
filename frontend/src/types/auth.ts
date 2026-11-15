import type { Session, User } from '@supabase/supabase-js'

export interface UserProfile {
  id: string
  user_id: string
  full_name: string | null
  avatar_url: string | null
  created_at: string
  updated_at: string
}

export interface AuthState {
  user: User | null
  session: Session | null
  profile: UserProfile | null
  initializing: boolean
  isRecoverySession: boolean
}

export interface LoginFormData {
  email: string
  password: string
}

export interface RegisterFormData {
  fullName: string
  email: string
  password: string
  confirmPassword: string
}

export interface ForgotPasswordFormData {
  email: string
}

export interface ResetPasswordFormData {
  password: string
  confirmPassword: string
}

export interface SignUpResult {
  user: User | null
  session: Session | null
  needsEmailConfirmation: boolean
}

export interface UpdateProfileInput {
  full_name?: string
  avatar_url?: string | null
}
