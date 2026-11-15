// Vite replaces DEV with false in production, regardless of local env files.
export function isLocalDemoMode(): boolean {
  return import.meta.env.DEV && import.meta.env.VITE_LOCAL_DEMO_MODE === 'true'
}
