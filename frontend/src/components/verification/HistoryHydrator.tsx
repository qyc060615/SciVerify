import { useEffect } from 'react'
import { useAuthStore } from '@/stores/authStore'
import { useVerificationStore } from '@/stores/verificationStore'

export function HistoryHydrator() {
  const userId = useAuthStore((state) => state.user?.id)
  const loadRecords = useVerificationStore((state) => state.loadRecords)
  const clearRecords = useVerificationStore((state) => state.clearRecords)

  useEffect(() => {
    if (!userId) {
      clearRecords()
      return
    }

    void loadRecords(userId)
  }, [clearRecords, loadRecords, userId])

  return null
}
