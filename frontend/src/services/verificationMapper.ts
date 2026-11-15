import type { VerdictKey } from '@/constants/verdicts'
import type {
  BackendAgentAnalysis,
  BackendAdjudicatorAnalysis,
  BackendClaimTraceability,
  BackendEvidenceItem,
  BackendPaperSummary,
  BackendVerificationResponse,
} from '@/types/backend-verification'
import type {
  AgentAnalysis,
  AgentDetail,
  AdjudicatorDetail,
  ClaimTraceability,
  EvidenceFactor,
  EvidenceItem,
  EvidenceStrength,
  SuggestedCorrection,
  VerificationFormInput,
  VerificationResult,
} from '@/types/verification'

function emptyAgent(role: string): AgentAnalysis {
  return {
    role,
    summary: 'Analysis unavailable.',
    finding: 'No agent output was returned for this verification.',
    status: 'completed',
  }
}

function emptyAgentDetail(): AgentDetail {
  return {
    analysis: 'Analysis unavailable.',
    keyPoints: [],
    supportingEvidence: [],
    contradictingEvidence: [],
  }
}

function emptyAdjudicatorDetail(): AdjudicatorDetail {
  return {
    ...emptyAgentDetail(),
    reasoning: 'No adjudicator output was returned for this verification.',
  }
}

function toConfidencePercent(value: number | null | undefined): number {
  if (value == null || Number.isNaN(value)) return 0
  if (value <= 1) return Math.round(value * 100)
  return Math.round(value)
}

function toCoveragePercent(value: number | null | undefined): number {
  if (value == null || Number.isNaN(value)) return 0
  if (value <= 1) return Math.round(value * 100)
  return Math.round(value)
}

function mapClaimTraceability(
  traceability: BackendClaimTraceability | null | undefined,
): ClaimTraceability | undefined {
  if (!traceability?.segments?.length) return undefined

  return {
    segments: traceability.segments.map((segment) => ({
      id: segment.id,
      text: segment.text,
      status: segment.status,
      coverageScore: toCoveragePercent(segment.coverage_score),
      evidenceIds: segment.evidence_ids ?? [],
    })),
    overallCoverage: toCoveragePercent(traceability.overall_coverage),
    warnings: traceability.warnings?.filter(Boolean),
  }
}

function mapAgent(
  agent: BackendAgentAnalysis | null | undefined,
  role: string,
): AgentAnalysis {
  if (!agent) return emptyAgent(role)

  const keyPoints = agent.key_points?.filter(Boolean) ?? []
  const finding =
    keyPoints.length > 0
      ? keyPoints.join(' ')
      : agent.stance || 'Analysis completed.'

  return {
    role,
    summary: agent.analysis,
    finding,
    status: 'completed',
  }
}

function mapAgentDetail(
  agent: BackendAgentAnalysis | null | undefined,
): AgentDetail | undefined {
  if (!agent) return undefined

  return {
    analysis: agent.analysis,
    stance: agent.stance,
    confidence: toConfidencePercent(agent.confidence),
    keyPoints: agent.key_points?.filter(Boolean) ?? [],
    supportingEvidence: agent.supporting_evidence ?? [],
    contradictingEvidence: agent.contradicting_evidence ?? [],
  }
}

function mapAdjudicator(
  agent: BackendAdjudicatorAnalysis | null | undefined,
): AgentAnalysis {
  if (!agent) return emptyAgent('Adjudicator')

  return {
    role: 'Adjudicator',
    summary: agent.analysis,
    finding: agent.reasoning,
    status: 'completed',
  }
}

function mapAdjudicatorDetail(
  agent: BackendAdjudicatorAnalysis | null | undefined,
  /**
   * The validator-calibrated confidence from the top-level response.
   * We use this instead of `agent.confidence` (the raw LLM value) so that the
   * adjudicator panel always shows the same confidence as the VerdictHeader,
   * eliminating the mismatch between raw and calibrated values.
   */
  calibratedConfidence: number,
): AdjudicatorDetail | undefined {
  if (!agent) return undefined

  return {
    analysis: agent.analysis,
    stance: undefined,
    confidence: calibratedConfidence,
    keyPoints: [],
    supportingEvidence: agent.supporting_evidence ?? [],
    contradictingEvidence: agent.contradicting_evidence ?? [],
    verdict: agent.verdict,
    reasoning: agent.reasoning,
    // suggestedCorrection intentionally omitted here: the backend validator is
    // the canonical source for suggested_correction (it strips it for
    // SUPPORTS/INSUFFICIENT and validates it for OVERSTATED/CONTRADICTS).
    // We read the top-level response.suggested_correction in mapSuggestedCorrection.
    suggestedCorrection: null,
  }
}

function evidenceStrength(relevance: number): EvidenceStrength {
  if (relevance >= 0.7) return 'HIGH'
  if (relevance >= 0.4) return 'MEDIUM'
  return 'LOW'
}

function mapEvidenceItem(
  item: BackendEvidenceItem,
  paper: BackendPaperSummary,
  verdict?: VerdictKey,
): EvidenceItem {
  return {
    id: item.chunk_id,
    title: `${item.section} · chunk ${item.chunk_index + 1}`,
    source: paper.title ?? paper.doi,
    excerpt: item.text,
    whyItMatters:
      item.claim_numbers?.length || item.evidence_numbers?.length
        ? `Claim numbers: ${item.claim_numbers?.join(', ') || 'none'}. Evidence numbers: ${item.evidence_numbers?.join(', ') || 'none'}.`
        : undefined,
    relevance: Math.round(item.relevance_score * 100),
    claimOverlap: Math.round(item.claim_overlap * 100),
    numericOverlap: Math.round(item.numeric_overlap * 100),
    strength: evidenceStrength(item.relevance_score),
    evidenceType: item.section,
    identifier: paper.doi,
    sourceUrl: item.source_url ?? undefined,
    page: item.page ?? null,
    chunkIndex: item.chunk_index,
    verdict,
  }
}

function buildEvidenceFactors(response: BackendVerificationResponse): EvidenceFactor[] {
  const factors: EvidenceFactor[] = []

  for (const point of response.prosecutor?.key_points ?? []) {
    factors.push({ text: point, supported: false })
  }
  for (const point of response.defender?.key_points ?? []) {
    factors.push({ text: point, supported: true })
  }

  return factors
}

function mapSuggestedCorrection(
  response: BackendVerificationResponse,
  claim: string,
): SuggestedCorrection | null {
  // Use ONLY the top-level response.suggested_correction.
  // The backend validator (verification_validator.py) is the canonical source:
  // it strips suggested_correction for SUPPORTS/INSUFFICIENT verdicts and
  // validates it for OVERSTATED/CONTRADICTS/FABRICATED.  Falling back to
  // response.adjudicator?.suggested_correction would bypass that logic and
  // could display a correction the backend decided to remove.
  const suggested = response.suggested_correction ?? null

  if (!suggested?.trim()) {
    return null
  }

  return {
    originalClaim: claim,
    problem: response.reasoning ?? response.summary ?? 'The claim needs revision.',
    suggestedWording: suggested,
  }
}

function resolveCitationStatus(
  response: BackendVerificationResponse,
): VerificationResult['citationStatus'] {
  if (response.verdict === 'FABRICATED') return 'fabricated'
  if (response.paper?.doi) return 'verified'
  return 'unverified'
}

export function mapBackendVerificationToResult(
  response: BackendVerificationResponse,
  input: VerificationFormInput,
): VerificationResult {
  const verdict = response.verdict ?? 'INSUFFICIENT'
  const confidence = toConfidencePercent(response.confidence)
  const summary =
    response.summary ??
    response.adjudicator?.analysis ??
    'Verification completed.'
  const reasoning =
    response.reasoning ??
    response.adjudicator?.reasoning ??
    response.detail ??
    summary

  return {
    id: crypto.randomUUID(),
    claim: response.claim,
    citation: input.citation,
    sourceType: input.sourceType,
    context: input.context,
    citationStatus: resolveCitationStatus(response),
    verdict,
    confidence,
    summary,
    reasoning,
    paperTitle: response.paper.title ?? undefined,
    paperDoi: response.paper.doi,
    agentAgreement: response.agent_agreement ?? null,
    validationWarnings: response.validation_warnings?.filter(Boolean) ?? [],
    evidenceFactors: buildEvidenceFactors(response),
    prosecutor: mapAgent(response.prosecutor, 'Prosecutor'),
    defender: mapAgent(response.defender, 'Defender'),
    adjudicator: mapAdjudicator(response.adjudicator),
    prosecutorDetail: mapAgentDetail(response.prosecutor),
    defenderDetail: mapAgentDetail(response.defender),
    adjudicatorDetail: mapAdjudicatorDetail(response.adjudicator, confidence),
    evidence: (response.evidence ?? []).map((item) =>
      mapEvidenceItem(item, response.paper, verdict),
    ),
    suggestedCorrection: mapSuggestedCorrection(response, response.claim),
    claimTraceability: mapClaimTraceability(response.claim_traceability),
    createdAt: new Date().toISOString(),
  }
}

export function mapInsufficientEvidenceResult(
  response: BackendVerificationResponse,
  input: VerificationFormInput,
): VerificationResult {
  return {
    id: crypto.randomUUID(),
    claim: response.claim,
    citation: input.citation,
    sourceType: input.sourceType,
    context: input.context,
    citationStatus: response.paper?.doi ? 'verified' : 'unverified',
    verdict: 'INSUFFICIENT',
    confidence: 0,
    summary:
      response.summary ??
      'There was not enough evidence to determine whether the claim is supported.',
    reasoning:
      response.reasoning ??
      response.detail ??
      'Evidence retrieval did not produce usable chunks for verification.',
    paperTitle: response.paper.title ?? undefined,
    paperDoi: response.paper.doi,
    agentAgreement: null,
    validationWarnings: [],
    evidenceFactors: [],
    prosecutor: emptyAgent('Prosecutor'),
    defender: emptyAgent('Defender'),
    adjudicator: emptyAgent('Adjudicator'),
    prosecutorDetail: emptyAgentDetail(),
    defenderDetail: emptyAgentDetail(),
    adjudicatorDetail: emptyAdjudicatorDetail(),
    evidence: (response.evidence ?? []).map((item) =>
      mapEvidenceItem(item, response.paper, 'INSUFFICIENT'),
    ),
    suggestedCorrection: null,
    claimTraceability: mapClaimTraceability(response.claim_traceability),
    createdAt: new Date().toISOString(),
  }
}
