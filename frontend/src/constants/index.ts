export { VERDICTS, VERDICT_KEYS, getVerdictConfig } from '@/constants/verdicts'
export type { VerdictKey, VerdictConfig } from '@/constants/verdicts'

export const ROUTES = {
  HOME: '/',
  UI_PREVIEW: 'ui-preview',
  LOGIN: '/login',
  REGISTER: '/register',
  FORGOT_PASSWORD: '/forgot-password',
  RESET_PASSWORD: '/reset-password',
  APP: '/app',
  APP_HOME: '/app/home',
  APP_VERIFY: '/app/verify',
  APP_REPOSITORY: '/app/repository',
  APP_HISTORY: '/app/history',
  APP_SETTINGS: '/app/settings',
  APP_MANUSCRIPTS: '/app/manuscripts',
} as const

export function verificationReportPath(verificationId: string) {
  return `/app/verify/${verificationId}`
}

export function wholePaperJobPath(jobId: string) {
  return `/app/manuscripts/jobs/${encodeURIComponent(jobId)}`
}
