import type { User } from '@supabase/supabase-js'
import type { UserProfile } from '@/types/auth'

export const LOCAL_DEMO_USER_ID = 'local-demo-user'
const createdAt = '2026-01-01T00:00:00.000Z'

// A local display identity only: no session, access token or cloud account.
export const localDemoUser: User = {
  id: LOCAL_DEMO_USER_ID,
  email: 'local-demo@researchguard.local',
  app_metadata: {},
  user_metadata: { full_name: 'Local Demo' },
  aud: 'local-demo',
  created_at: createdAt,
}

export const localDemoProfile: UserProfile = {
  id: 'local-demo-profile',
  user_id: LOCAL_DEMO_USER_ID,
  full_name: 'Local Demo',
  avatar_url: null,
  created_at: createdAt,
  updated_at: createdAt,
}
