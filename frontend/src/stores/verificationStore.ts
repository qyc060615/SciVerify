import { create } from 'zustand'
import * as historyService from '@/services/historyService'
import type { VerificationResult } from '@/types/verification'

interface VerificationStoreState {
  records: VerificationResult[]
  loading: boolean
  hydrated: boolean
  error: string | null
  warning: string | null
  loadRecords: (userId: string) => Promise<void>
  addRecord: (
    userId: string,
    record: VerificationResult,
  ) => Promise<{ saved: boolean }>
  deleteRecord: (userId: string, recordId: string) => Promise<void>
  getRecord: (id: string) => VerificationResult | undefined
  clearRecords: () => void
}

export const useVerificationStore = create<VerificationStoreState>((set, get) => ({
  records: [],
  loading: false,
  hydrated: false,
  error: null,
  warning: null,

  loadRecords: async (userId) => {
    set({ loading: true, error: null, warning: null })
    try {
      let warning: string | null = null
      const records = await historyService.listVerificationHistory(userId, (message) => { warning = message })
      set({ records, loading: false, hydrated: true, error: null, warning })
    } catch {
      set({
        loading: false,
        hydrated: true,
        error: 'Unable to load verification history. Please try again later.',
      })
    }
  },

  addRecord: async (userId, record) => {
    set((state) => ({
      records: [
        record,
        ...state.records.filter((existing) => existing.id !== record.id),
      ],
    }))

    try {
      await historyService.saveVerificationHistory(userId, record)
      return { saved: true }
    } catch {
      return { saved: false }
    }
  },

  deleteRecord: async (userId, recordId) => {
    await historyService.deleteVerificationHistory(userId, recordId)
    set((state) => ({
      records: state.records.filter((record) => record.id !== recordId),
    }))
  },

  getRecord: (id) => get().records.find((record) => record.id === id),

  clearRecords: () =>
    set({
      records: [],
      loading: false,
      hydrated: false,
      error: null,
      warning: null,
    }),
}))
