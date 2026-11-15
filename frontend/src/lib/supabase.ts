import { createClient, type SupabaseClient } from '@supabase/supabase-js'
import { env } from '@/lib/env'
import { isLocalDemoMode } from '@/lib/demo-mode'

let client: SupabaseClient | null = null

export function isSupabaseConfigured(): boolean {
  return Boolean(env.supabaseUrl.trim() && env.supabaseAnonKey.trim())
}

export function getSupabaseClient(): SupabaseClient {
  if (isLocalDemoMode()) {
    throw new Error('Supabase is unavailable in Local Demo mode.')
  }

  if (!isSupabaseConfigured()) {
    throw new Error(
      'Supabase is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in frontend/.env',
    )
  }

  client ??= createClient(env.supabaseUrl, env.supabaseAnonKey)
  return client
}

export function resetSupabaseClient(): void {
  client = null
}
