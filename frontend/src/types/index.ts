export type {
  UserProfile,
  AuthState,
  LoginFormData,
  RegisterFormData,
  ForgotPasswordFormData,
  ResetPasswordFormData,
  SignUpResult,
  UpdateProfileInput,
} from '@/types/auth'

export type { VerdictKey } from '@/constants/verdicts'

export type {
  AgentAnalysis,
  DashboardStats,
  EvidenceItem,
  SourceType,
  SuggestedCorrection,
  VerificationFormInput,
  VerificationRecord,
  VerificationResult,
} from '@/types/verification'

export type AgentStatus = 'idle' | 'running' | 'completed' | 'error'

export type TimelineStepStatus = 'pending' | 'active' | 'completed' | 'error'

export interface ApiError {
  message: string
  status?: number
}
