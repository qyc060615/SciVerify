import { isLocalDemoMode } from '@/lib/demo-mode'

function readEnv(key: keyof ImportMetaEnv): string {
  return import.meta.env[key] ?? ''
}

export const env = {
  supabaseUrl: readEnv('VITE_SUPABASE_URL'),
  supabaseAnonKey: readEnv('VITE_SUPABASE_ANON_KEY'),
  apiBaseUrl: readEnv('VITE_API_BASE_URL'),
} as const

export function isEnvConfigured(): boolean {
  return Boolean(
    env.apiBaseUrl && (isLocalDemoMode() || (env.supabaseUrl && env.supabaseAnonKey)),
  )
}
