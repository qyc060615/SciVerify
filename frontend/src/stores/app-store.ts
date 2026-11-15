import { create } from 'zustand'

interface AppState {
  isInitialized: boolean
  setInitialized: (value: boolean) => void
}

export const useAppStore = create<AppState>((set) => ({
  isInitialized: false,
  setInitialized: (value) => set({ isInitialized: value }),
}))
