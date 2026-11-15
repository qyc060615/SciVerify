import type { VerdictKey } from '@/constants/verdicts'
import type { VerificationResult } from '@/types/verification'

export interface VerificationHistoryRow {
  id: string
  user_id: string
  claim: string
  doi: string
  paper_title: string | null
  verdict: VerdictKey
  confidence: number
  summary: string | null
  result_json: VerificationResult
  created_at: string
}

export interface VerificationHistoryInsert {
  id: string
  user_id: string
  claim: string
  doi: string
  paper_title: string | null
  verdict: VerdictKey
  confidence: number
  summary: string | null
  result_json: VerificationResult
  created_at: string
}

export type HistoryDateSort = 'newest' | 'oldest'
