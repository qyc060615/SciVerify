import type { VerdictKey } from '@/constants/verdicts'

export type SourceType = 'doi' | 'url' | 'citation' | 'reference'

export type CitationStatus = 'verified' | 'fabricated' | 'unverified'

export type EvidenceStrength = 'HIGH' | 'MEDIUM' | 'LOW'

export interface AgentDetail {
  analysis: string
  stance?: string
  confidence?: number
  keyPoints: string[]
  supportingEvidence: string[]
  contradictingEvidence: string[]
}

export interface AdjudicatorDetail extends AgentDetail {
  verdict?: VerdictKey
  reasoning?: string
  suggestedCorrection?: string | null
}

export interface AgentAnalysis {
  role: string
  summary: string
  finding: string
  status: 'completed' | 'running' | 'idle'
}

export interface EvidenceItem {
  id: string
  title: string
  authors?: string
  source: string
  year?: number
  excerpt: string
  whyItMatters?: string
  relevance: number
  claimOverlap?: number
  numericOverlap?: number
  strength?: EvidenceStrength
  evidenceType: string
  identifier?: string
  sourceUrl?: string
  page?: number | null
  chunkIndex?: number
  verdict?: VerdictKey
}

export interface EvidenceFactor {
  text: string
  supported: boolean
}

export interface SuggestedCorrection {
  originalClaim: string
  problem: string
  suggestedWording: string
}

export type ClaimSegmentStatus =
  | 'SUPPORTED'
  | 'PARTIALLY_SUPPORTED'
  | 'UNSUPPORTED'
  | 'CONTRADICTED'

export interface ClaimSegment {
  id: string
  text: string
  status: ClaimSegmentStatus
  coverageScore: number
  evidenceIds: string[]
}

export interface ClaimTraceability {
  segments: ClaimSegment[]
  overallCoverage: number
  warnings?: string[]
}

export interface VerificationResult {
  id: string
  claim: string
  citation: string
  sourceType: SourceType
  context?: string
  citationStatus: CitationStatus
  verdict: VerdictKey
  confidence: number
  summary: string
  reasoning: string
  paperTitle?: string
  paperDoi?: string
  agentAgreement?: boolean | null
  validationWarnings?: string[]
  evidenceFactors: EvidenceFactor[]
  prosecutor: AgentAnalysis
  defender: AgentAnalysis
  adjudicator: AgentAnalysis
  prosecutorDetail?: AgentDetail
  defenderDetail?: AgentDetail
  adjudicatorDetail?: AdjudicatorDetail
  evidence: EvidenceItem[]
  suggestedCorrection?: SuggestedCorrection | null
  claimTraceability?: ClaimTraceability
  createdAt: string
}

export type VerificationRecord = VerificationResult

export interface VerificationFormInput {
  claim: string
  citation: string
  sourceType: SourceType
  context?: string
}

export interface DashboardStats {
  total: number
  supports: number
  overstated: number
  contradicts: number
  insufficient: number
  fabricated: number
}

export interface VerificationProgressUpdate {
  stageId: string
  stageIndex: number
  message?: string
}

export type VerificationStageGroup = 'pipeline' | 'agent'

export interface VerificationStage {
  id: string
  title: string
  group: VerificationStageGroup
  agent?: 'prosecutor' | 'defender' | 'adjudicator'
  activeMessage?: string
}
