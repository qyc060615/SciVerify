import type { AuthError } from '@supabase/supabase-js'

const AUTH_ERROR_MESSAGES: Record<string, string> = {
  invalid_credentials: 'Incorrect email or password.',
  email_not_confirmed: 'Please confirm your email before signing in.',
  user_already_registered: 'An account with this email already exists.',
  weak_password: 'Password is too weak. Use at least 8 characters.',
  over_request_rate_limit: 'Too many attempts. Please wait and try again.',
  same_password: 'Choose a different password from your current one.',
  session_expired: 'Your reset link has expired. Request a new one.',
}

export function mapAuthError(error: unknown, fallback: string): string {
  if (!error || typeof error !== 'object') {
    return fallback
  }

  const authError = error as AuthError
  const code = authError.code ?? authError.name
  const message = authError.message?.toLowerCase() ?? ''

  if (code && AUTH_ERROR_MESSAGES[code]) {
    return AUTH_ERROR_MESSAGES[code]
  }

  if (message.includes('invalid login credentials')) {
    return AUTH_ERROR_MESSAGES.invalid_credentials
  }

  if (message.includes('email not confirmed')) {
    return AUTH_ERROR_MESSAGES.email_not_confirmed
  }

  if (message.includes('user already registered')) {
    return AUTH_ERROR_MESSAGES.user_already_registered
  }

  if (message.includes('password')) {
    return AUTH_ERROR_MESSAGES.weak_password
  }

  if (message.includes('rate limit')) {
    return AUTH_ERROR_MESSAGES.over_request_rate_limit
  }

  if (message.includes('session') && message.includes('expired')) {
    return AUTH_ERROR_MESSAGES.session_expired
  }

  return fallback
}
