import type { VerdictKey } from '@/constants/verdicts'
import type {
  DashboardStats,
  VerificationFormInput,
  VerificationResult,
  VerificationStage,
} from '@/types/verification'

const daysAgo = (days: number) =>
  new Date(Date.now() - days * 86_400_000).toISOString()

export const VERIFICATION_STAGES: VerificationStage[] = [
  {
    id: 'finding-paper',
    title: 'Finding paper',
    group: 'pipeline',
    activeMessage: 'Resolving DOI and locating the cited paper...',
  },
  {
    id: 'retrieving-full-text',
    title: 'Retrieving full text',
    group: 'pipeline',
    activeMessage: 'Downloading and validating the full-text source...',
  },
  {
    id: 'extracting-evidence',
    title: 'Extracting evidence',
    group: 'pipeline',
    activeMessage: 'Parsing, chunking, and ranking relevant evidence...',
  },
  {
    id: 'prosecutor',
    title: 'Prosecutor analysis',
    group: 'agent',
    agent: 'prosecutor',
    activeMessage: 'Searching for contradictions and limitations...',
  },
  {
    id: 'defender',
    title: 'Defender analysis',
    group: 'agent',
    agent: 'defender',
    activeMessage: 'Finding supporting evidence...',
  },
  {
    id: 'adjudicator',
    title: 'Adjudication',
    group: 'agent',
    agent: 'adjudicator',
    activeMessage: 'Weighing arguments against evidence...',
  },
  {
    id: 'validating-result',
    title: 'Validating result',
    group: 'pipeline',
    activeMessage: 'Checking verdict consistency and calibrating confidence...',
  },
]

/** @deprecated Use VERIFICATION_STAGES instead */
export const VERIFICATION_LOADING_STEPS = VERIFICATION_STAGES.map(
  (stage) => stage.title,
)

export const MOCK_VERIFICATION_HISTORY: VerificationResult[] = [
  {
    id: 'mock-001',
    claim:
      'The method improves accuracy by 40% on real-world software development tasks.',
    citation: '10.1000/demo.2024.001 — Demo Clinical Outcomes Study',
    sourceType: 'doi',
    citationStatus: 'verified',
    verdict: 'OVERSTATED',
    confidence: 76,
    summary:
      'The paper supports the general direction of the claim, but the cited statement exaggerates the reported effect.',
    reasoning:
      'The cited evidence supports the direction of the claim but does not support the reported magnitude.',
    evidenceFactors: [
      { text: 'Direction of effect supported', supported: true },
      { text: 'Study population matches', supported: true },
      { text: 'Claimed effect size is higher than reported', supported: false },
    ],
    prosecutor: {
      role: 'Prosecutor',
      summary: 'Challenge the claim',
      finding:
        'The source reports a 23% improvement, not the 40% stated in the claim.',
      status: 'completed',
    },
    defender: {
      role: 'Defender',
      summary: 'Build the strongest supporting case',
      finding:
        'The cited study does demonstrate a statistically significant improvement under the tested conditions.',
      status: 'completed',
    },
    adjudicator: {
      role: 'Adjudicator',
      summary: 'Make the final evidence-backed decision',
      finding:
        'The direction of the effect is supported, but the magnitude is overstated.',
      status: 'completed',
    },
    evidence: [
      {
        id: 'ev-001',
        title: 'Demo Clinical Outcomes Study',
        authors: 'Chen et al.',
        source: 'Demo Journal of Applied Research',
        year: 2024,
        excerpt:
          'The intervention group showed a statistically significant reduction in the primary biomarker compared with placebo controls.',
        whyItMatters:
          'Confirms a positive effect but reports a smaller magnitude than the claim states.',
        relevance: 94,
        strength: 'HIGH',
        evidenceType: 'Primary outcome',
        identifier: '10.1000/demo.2024.001',
        verdict: 'SUPPORTS',
      },
    ],
    suggestedCorrection: {
      originalClaim:
        'The method improves accuracy by 40% on real-world software development tasks.',
      problem: 'The cited paper reports a 23% improvement.',
      suggestedWording:
        'The method improved accuracy by 23% under the reported experimental conditions.',
    },
    createdAt: daysAgo(1),
  },
  {
    id: 'mock-002',
    claim:
      'Meta-analysis confirms the therapy improves long-term survival across all subgroups.',
    citation: 'https://example.org/demo/meta-analysis-review',
    sourceType: 'url',
    citationStatus: 'verified',
    verdict: 'CONTRADICTS',
    confidence: 82,
    summary:
      'The cited review does not support survival improvements across all subgroups as stated.',
    reasoning:
      'Subgroup analyses in the cited review show null or inconsistent survival effects in several cohorts.',
    evidenceFactors: [
      { text: 'Overall pooled trend reported', supported: true },
      { text: 'Universal subgroup benefit claimed', supported: false },
      { text: 'Several subgroup analyses show null effects', supported: false },
    ],
    prosecutor: {
      role: 'Prosecutor',
      summary: 'Challenge the claim',
      finding:
        'Multiple subgroups in the cited review do not show significant survival benefit.',
      status: 'completed',
    },
    defender: {
      role: 'Defender',
      summary: 'Build the strongest supporting case',
      finding:
        'Pooled estimates show a modest survival trend in the overall population.',
      status: 'completed',
    },
    adjudicator: {
      role: 'Adjudicator',
      summary: 'Make the final evidence-backed decision',
      finding:
        'The universal subgroup claim is not supported by the cited evidence.',
      status: 'completed',
    },
    evidence: [
      {
        id: 'ev-002',
        title: 'Demo Meta-Analysis Review',
        authors: 'Williams et al.',
        source: 'Demo Evidence Synthesis Reports',
        year: 2023,
        excerpt:
          'Pooled hazard ratios varied substantially across predefined subgroups, with several confidence intervals crossing unity.',
        whyItMatters:
          'Directly contradicts the claim that all subgroups benefited.',
        relevance: 88,
        strength: 'HIGH',
        evidenceType: 'Meta-analysis',
        sourceUrl: 'https://example.org/demo/meta-analysis-review',
        verdict: 'CONTRADICTS',
      },
    ],
    suggestedCorrection: {
      originalClaim:
        'Meta-analysis confirms the therapy improves long-term survival across all subgroups.',
      problem:
        'The cited meta-analysis reports mixed survival effects across subgroups.',
      suggestedWording:
        'The cited meta-analysis reports mixed survival effects across subgroups, with pooled estimates that should be interpreted cautiously.',
    },
    createdAt: daysAgo(3),
  },
  {
    id: 'mock-003',
    claim:
      'The compound demonstrates complete tumor regression in preclinical models.',
    citation: 'Smith et al., Demo Oncology Letters, 2022',
    sourceType: 'citation',
    citationStatus: 'verified',
    verdict: 'SUPPORTS',
    confidence: 91,
    summary:
      'The cited preclinical study reports complete regression in a defined model subset.',
    reasoning:
      'The claim aligns with reported complete regression outcomes in the referenced model conditions.',
    evidenceFactors: [
      { text: 'Complete regression documented in source', supported: true },
      { text: 'Model conditions match claim scope', supported: true },
      { text: 'Effect observed in all model types', supported: false },
    ],
    prosecutor: {
      role: 'Prosecutor',
      summary: 'Challenge the claim',
      finding:
        'Complete regression was observed only in a specific model configuration.',
      status: 'completed',
    },
    defender: {
      role: 'Defender',
      summary: 'Build the strongest supporting case',
      finding:
        'The study explicitly documents complete regression under the tested preclinical conditions.',
      status: 'completed',
    },
    adjudicator: {
      role: 'Adjudicator',
      summary: 'Make the final evidence-backed decision',
      finding:
        'The claim is supported when scoped to the conditions described in the source.',
      status: 'completed',
    },
    evidence: [
      {
        id: 'ev-003',
        title: 'Preclinical Tumor Regression Study (Demo)',
        authors: 'Smith et al.',
        source: 'Demo Oncology Letters',
        year: 2022,
        excerpt:
          'Complete tumor regression was observed in the treated cohort under the specified xenograft conditions.',
        whyItMatters:
          'Provides direct support for regression outcomes under defined preclinical conditions.',
        relevance: 92,
        strength: 'HIGH',
        evidenceType: 'Preclinical',
        verdict: 'SUPPORTS',
      },
    ],
    suggestedCorrection: {
      originalClaim:
        'The compound demonstrates complete tumor regression in preclinical models.',
      problem:
        'The claim is broadly stated but the source specifies particular model conditions.',
      suggestedWording:
        'The compound demonstrated complete tumor regression in the specific preclinical model conditions described in the cited study.',
    },
    createdAt: daysAgo(5),
  },
  {
    id: 'mock-004',
    claim:
      'The dataset proves universal efficacy with no observed adverse events.',
    citation: 'Demo unpublished manuscript reference text',
    sourceType: 'reference',
    citationStatus: 'unverified',
    verdict: 'INSUFFICIENT',
    confidence: 58,
    summary:
      'Insufficient reliable evidence is available to evaluate universal efficacy or safety claims.',
    reasoning:
      'The provided reference lacks peer-reviewed outcomes data required for this evaluation.',
    evidenceFactors: [
      { text: 'Peer-reviewed outcomes available', supported: false },
      { text: 'Safety data independently verified', supported: false },
      { text: 'Reference may contain preliminary observations', supported: true },
    ],
    prosecutor: {
      role: 'Prosecutor',
      summary: 'Challenge the claim',
      finding:
        'No verified outcomes data supports universal efficacy or zero adverse events.',
      status: 'completed',
    },
    defender: {
      role: 'Defender',
      summary: 'Build the strongest supporting case',
      finding:
        'The reference may contain preliminary observations, but they are not independently verified.',
      status: 'completed',
    },
    adjudicator: {
      role: 'Adjudicator',
      summary: 'Make the final evidence-backed decision',
      finding:
        'Available material is insufficient for a definitive verdict on efficacy or safety.',
      status: 'completed',
    },
    evidence: [],
    suggestedCorrection: {
      originalClaim:
        'The dataset proves universal efficacy with no observed adverse events.',
      problem:
        'No peer-reviewed evidence supports universal efficacy or zero adverse events.',
      suggestedWording:
        'Further peer-reviewed evidence is required before efficacy or safety claims can be stated.',
    },
    createdAt: daysAgo(8),
  },
  {
    id: 'mock-005',
    claim:
      'AI improves software development productivity by 50% across enterprise teams.',
    citation: '10.1000/demo.2023.045',
    sourceType: 'doi',
    citationStatus: 'verified',
    verdict: 'OVERSTATED',
    confidence: 74,
    summary:
      'The cited trial supports improvement, but the 50% figure exceeds what the source reports.',
    reasoning:
      'Reported gains are positive but materially lower than the stated percentage.',
    evidenceFactors: [
      { text: 'Productivity improvement direction supported', supported: true },
      { text: 'Enterprise team context partially matches', supported: true },
      { text: 'Claimed 50% gain exceeds reported results', supported: false },
    ],
    prosecutor: {
      role: 'Prosecutor',
      summary: 'Challenge the claim',
      finding: 'Reported productivity gains are closer to 11–14% in the source.',
      status: 'completed',
    },
    defender: {
      role: 'Defender',
      summary: 'Build the strongest supporting case',
      finding:
        'The trial reports statistically significant productivity improvements on benchmark tasks.',
      status: 'completed',
    },
    adjudicator: {
      role: 'Adjudicator',
      summary: 'Make the final evidence-backed decision',
      finding:
        'Improvement is supported, but the exact 50% figure is not substantiated.',
      status: 'completed',
    },
    evidence: [
      {
        id: 'ev-005',
        title: 'Demo Benchmark Trial',
        authors: 'Patel et al.',
        source: 'Demo Methods Journal',
        year: 2023,
        excerpt:
          'The proposed method improved benchmark accuracy by approximately 12% relative to the baseline system.',
        whyItMatters:
          'Supports a positive effect but with a substantially lower magnitude than claimed.',
        relevance: 90,
        strength: 'HIGH',
        evidenceType: 'Trial outcome',
        identifier: '10.1000/demo.2023.045',
        verdict: 'OVERSTATED',
      },
    ],
    suggestedCorrection: {
      originalClaim:
        'AI improves software development productivity by 50% across enterprise teams.',
      problem:
        'The cited trial reports productivity gains closer to 11–14%, not 50%.',
      suggestedWording:
        'The cited trial reports a statistically significant productivity improvement, though the magnitude is lower than 50%.',
    },
    createdAt: daysAgo(12),
  },
  {
    id: 'mock-006',
    claim:
      'A randomized controlled trial demonstrates 95% cure rates using compound XR-900.',
    citation: '10.9999/nonexistent.2025.000 — Unknown Journal of Fabricated Science',
    sourceType: 'doi',
    citationStatus: 'fabricated',
    verdict: 'FABRICATED',
    confidence: 98,
    summary:
      'The cited source could not be verified and appears to be fabricated or non-existent.',
    reasoning:
      'No matching publication was found for the provided DOI or journal reference.',
    evidenceFactors: [
      { text: 'DOI resolves to a known publication', supported: false },
      { text: 'Journal and venue are verifiable', supported: false },
      { text: 'Claim references non-existent trial data', supported: false },
    ],
    prosecutor: {
      role: 'Prosecutor',
      summary: 'Challenge the claim',
      finding:
        'The DOI and journal reference do not match any verified publication in demo databases.',
      status: 'completed',
    },
    defender: {
      role: 'Defender',
      summary: 'Build the strongest supporting case',
      finding:
        'No credible source material was found to support the cited trial outcomes.',
      status: 'completed',
    },
    adjudicator: {
      role: 'Adjudicator',
      summary: 'Make the final evidence-backed decision',
      finding:
        'Citation authenticity check failed — the reference appears fabricated.',
      status: 'completed',
    },
    evidence: [],
    suggestedCorrection: {
      originalClaim:
        'A randomized controlled trial demonstrates 95% cure rates using compound XR-900.',
      problem:
        'The cited DOI and journal could not be verified as a real publication.',
      suggestedWording:
        'Remove or replace this citation with a verified peer-reviewed source before stating trial outcomes.',
    },
    createdAt: daysAgo(10),
  },
]

export function computeDashboardStats(
  records: VerificationResult[],
): DashboardStats {
  return {
    total: records.length,
    supports: records.filter((r) => r.verdict === 'SUPPORTS').length,
    overstated: records.filter((r) => r.verdict === 'OVERSTATED').length,
    contradicts: records.filter((r) => r.verdict === 'CONTRADICTS').length,
    insufficient: records.filter((r) => r.verdict === 'INSUFFICIENT').length,
    fabricated: records.filter((r) => r.verdict === 'FABRICATED').length,
  }
}

const TEMPLATE_BY_VERDICT: Record<VerdictKey, VerificationResult> =
  Object.fromEntries(
    MOCK_VERIFICATION_HISTORY.map((record) => [record.verdict, record]),
  ) as Record<VerdictKey, VerificationResult>

function resolveVerdictFromInput(input: VerificationFormInput): VerdictKey {
  const claim = input.claim.toLowerCase()
  const citation = input.citation.toLowerCase()

  if (
    citation.includes('fabricated') ||
    citation.includes('nonexistent') ||
    citation.includes('unknown paper') ||
    citation.includes('fake')
  ) {
    return 'FABRICATED'
  }
  if (claim.includes('contradict') || claim.includes('all subgroups')) {
    return 'CONTRADICTS'
  }
  if (
    claim.includes('insufficient') ||
    claim.includes('universal efficacy') ||
    claim.includes('no adverse')
  ) {
    return 'INSUFFICIENT'
  }
  if (
    claim.includes('complete regression') ||
    claim.includes('fully supports') ||
    (claim.includes('support') && !claim.includes('overstate'))
  ) {
    return 'SUPPORTS'
  }
  if (
    claim.includes('40%') ||
    claim.includes('50%') ||
    claim.includes('20%') ||
    claim.includes('productivity') ||
    claim.includes('accuracy') ||
    claim.includes('overstate') ||
    claim.includes('ai improves')
  ) {
    return 'OVERSTATED'
  }

  return 'OVERSTATED'
}

export function buildMockVerificationResult(
  input: VerificationFormInput,
): VerificationResult {
  const verdict = resolveVerdictFromInput(input)
  const template = TEMPLATE_BY_VERDICT[verdict]

  return {
    ...template,
    id: `mock-${crypto.randomUUID()}`,
    claim: input.claim,
    citation: input.citation,
    sourceType: input.sourceType,
    context: input.context?.trim() || undefined,
    suggestedCorrection: template.suggestedCorrection
      ? {
          ...template.suggestedCorrection,
          originalClaim: input.claim,
        }
      : null,
    createdAt: new Date().toISOString(),
  }
}
