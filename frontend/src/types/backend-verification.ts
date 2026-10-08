import type { VerdictKey } from '@/constants/verdicts'

export type BackendVerificationStatus =
  | 'source_required'
  | 'success'
  | 'insufficient_evidence'
  | 'llm_unavailable'
  | 'verification_failed'
  | 'not_found'
  | 'provider_error'

export type BackendVerdict = VerdictKey

export interface VerificationAnalyzeRequest {
  claim: string
  doi: string
}

export interface BackendPaperSummary {
  paper_id: string
  doi: string
  title?: string | null
}

export interface BackendEvidenceItem {
  chunk_id: string
  section: string
  chunk_index: number
  text: string
  relevance_score: number
  claim_overlap: number
  numeric_overlap: number
  claim_numbers?: string[]
  evidence_numbers?: string[]
  source_url?: string | null
  page?: number | null
}

export interface BackendAgentAnalysis {
  agent: 'prosecutor' | 'defender'
  analysis: string
  stance: string
  key_points?: string[]
  supporting_evidence?: string[]
  contradicting_evidence?: string[]
  confidence: number
}

export interface BackendAdjudicatorAnalysis {
  agent: 'adjudicator'
  analysis: string
  verdict: BackendVerdict
  confidence: number
  reasoning: string
  supporting_evidence?: string[]
  contradicting_evidence?: string[]
  suggested_correction?: string | null
}

export type BackendClaimSegmentStatus =
  | 'SUPPORTED'
  | 'PARTIALLY_SUPPORTED'
  | 'UNSUPPORTED'
  | 'CONTRADICTED'

export interface BackendClaimSegment {
  id: string
  text: string
  status: BackendClaimSegmentStatus
  coverage_score: number
  evidence_ids?: string[]
}

export interface BackendClaimTraceability {
  segments: BackendClaimSegment[]
  overall_coverage: number
  warnings?: string[]
}

export interface BackendVerificationResponse {
  source_recovery?: {
    required: true
    reason: 'full_text_unavailable' | 'metadata_only' | 'parsing_failure'
    accepts_manual_pdf: true
    max_size_bytes: number
  } | null
  status: BackendVerificationStatus
  claim: string
  verdict?: BackendVerdict | null
  confidence?: number | null
  summary?: string | null
  reasoning?: string | null
  paper: BackendPaperSummary
  evidence?: BackendEvidenceItem[]
  prosecutor?: BackendAgentAnalysis | null
  defender?: BackendAgentAnalysis | null
  adjudicator?: BackendAdjudicatorAnalysis | null
  suggested_correction?: string | null
  agent_agreement?: boolean | null
  validation_warnings?: string[] | null
  claim_traceability?: BackendClaimTraceability | null
  detail?: string | null
}

export interface VerificationApiErrorBody {
  detail?: string | { code: string; message: string } | Array<{ msg?: string; loc?: string[] }>
}
