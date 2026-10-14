import manuscript from './manuscript.json'
import type { Claim, Context, ContextResult, ExtractionMetadata, Paragraph, Reference, Callout } from '@/types/manuscript'
import type { VerificationJob } from '@/types/verification-job'

export const jobId = 'job_' + 'a'.repeat(32)
export function jobFixture(): VerificationJob {
  const extraction = manuscript.job_request.extraction
  return {
    job_id: jobId, status: 'waiting_for_source', revision: 6, input_provenance: 'client_supplied', manuscript_id: extraction.manuscript_id, manuscript_title: 'Local manuscript review',
    paragraphs: manuscript.parse_response.parsed.paragraphs as Paragraph[], references: manuscript.parse_response.parsed.references as Reference[], citation_callouts: manuscript.parse_response.parsed.citation_callouts as Callout[],
    claims: extraction.claims as Claim[], contexts: extraction.contexts as Context[], context_results: extraction.context_results as ContextResult[], extraction_metadata: extraction.metadata as ExtractionMetadata,
    extraction_diagnostics: [], attribution_blocked: [], next_sequence: 8, runtime_error_code: null,
    coverage: { total_claims: 1, total_references: 3, total_pairs: 2, completed_pairs: 1, blocked_source_pairs: 1, failed_pairs: 0, pending_pairs: 0, running_pairs: 0, ambiguous_claims: 0, unresolved_claims: 0, failed_extraction_contexts: 0, skipped_extraction_contexts: 0, coverage_complete: false },
    tasks: extraction.claims[0].reference_ids.map((rid, i) => ({
      task_key: 'task_' + i, claim_id: extraction.claims[0].id, reference_id: rid, state: i === 0 ? 'completed' : 'blocked_source', reason_code: i === 0 ? 'VERIFIED' : 'SOURCE_REQUIRED_FULL_TEXT_UNAVAILABLE', attempt: 1,
      source_binding: i === 0 ? { reference_id: rid, doi: '10.1234/local', source_document_id: 'source:local', source_version: 'sha256:' + 'b'.repeat(64) } : null,
      source_version: i === 0 ? 'sha256:' + 'b'.repeat(64) : null, expected_raw_hash: i === 0 ? 'b'.repeat(64) : null, last_error_code: null, resume_available: i !== 0,
      pair_outcome: i === 0 ? { reference_id: rid, citation_callout_ids: extraction.claims[0].citation_callout_ids, reason_code: 'VERIFIED', binding: { reference_id: rid, doi: '10.1234/local', source_document_id: 'source:local', source_version: 'sha256:' + 'b'.repeat(64) }, legacy_verdict: 'CONTRADICTS', verification: {
        claim_id: extraction.claims[0].id, processing_status: 'completed', verdict: 'CONTRADICTED', confidence: .8, explanation: 'The cited findings contradict this claim.',
        evidence_chunks: [{ id: 'evidence:local', source_document_id: 'source:local', section: 'Results', page: null, source_url: 'https://example.org/paper', text: 'The controlled study did not find the claimed improvement.', retrieval_score: 8, metadata: { source_identity_status: 'uncertain', parsed_content_fingerprint: 'c'.repeat(64) } }], traceability: { evidence_ids: ['evidence:local'], method: 'paperqa2+prepared_verifier', warnings: [], metadata: {} },
      } } : null,
    })),
  }
}
