import type { VerificationResult } from '@/types/verification'

// Fixed offline test data, never used by production code.
export const report: VerificationResult = {
  id: 'report-one', claim: 'The treatment reduced the measured outcome.',
  citation: '10.1234/offline-test', sourceType: 'doi', citationStatus: 'verified',
  verdict: 'SUPPORTS', confidence: 80,
  summary: 'Offline report summary.', reasoning: 'Offline report reasoning.',
  paperTitle: 'Offline fixture paper', paperDoi: '10.1234/offline-test',
  context: 'Original submission context', agentAgreement: true,
  validationWarnings: [], evidenceFactors: [{ text: 'Measured outcome', supported: true }],
  prosecutor: { role: 'Prosecutor', summary: 'Prosecution', finding: 'Scope limitation', status: 'completed' },
  defender: { role: 'Defender', summary: 'Defense', finding: 'Direct support', status: 'completed' },
  adjudicator: { role: 'Adjudicator', summary: 'Adjudication', finding: 'Supported in scope', status: 'completed' },
  defenderDetail: { analysis: 'Full defender analysis', confidence: 80, keyPoints: ['Scope'], supportingEvidence: ['evidence-one'], contradictingEvidence: [] },
  evidence: [{ id: 'evidence-one', title: 'Offline fixture paper', source: 'Results', excerpt: 'Measured outcome decreased.', relevance: 0.8, evidenceType: 'Results', page: 2 }],
  claimTraceability: { segments: [{ id: 'segment-one', text: 'Measured outcome', status: 'SUPPORTED', coverageScore: 80, evidenceIds: ['evidence-one'] }], overallCoverage: 80 },
  createdAt: '2026-01-02T00:00:00.000Z',
}
