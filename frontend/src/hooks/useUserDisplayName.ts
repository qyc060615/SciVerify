import { useAuth } from '@/hooks/useAuth'

export function useUserDisplayName(): string {
  const { user, profile } = useAuth()

  if (profile?.full_name) return profile.full_name

  const metadataName = user?.user_metadata?.full_name
  if (typeof metadataName === 'string' && metadataName.trim()) {
    return metadataName
  }

  return user?.email?.split('@')[0] ?? 'Researcher'
}
