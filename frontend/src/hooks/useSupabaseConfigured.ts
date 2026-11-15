import { isSupabaseConfigured } from '@/lib/supabase'

export function useSupabaseConfigured(): boolean {
  return isSupabaseConfigured()
}
