# Reference source discovery, identity and manual recovery

Stage 2 checks persistent sources before bounded network acquisition. Metadata ambiguity,
provider failure, missing fields and publication-version differences retain candidates
rather than preventing download. Candidate DOI/URL records and download outcomes remain
visible, including rejected and unattempted candidates.

## Identity states

- CONFIRMED: usable persisted full text plus direct document evidence, such as a matching
  title/title-area layout, title corroborated by authors, the explicitly cited arXiv ID,
  or an already verified DOI association. Year differences, missing authors and host
  allowlist membership do not independently downgrade this work identity.
- POSSIBLE: usable full text with insufficient direct association evidence. This does
  not mean the file is missing or corrupt.
- CONFLICT: a known primary source is demonstrably another work. Rejected secondary
  candidates remain individually visible without automatically condemning the primary
  reference.
- UNAVAILABLE: bounded acquisition did not obtain usable full text.
- CANDIDATE_FOUND is an operational local-check state before acquisition; it does not
  claim full text exists.

Confirmation concerns the cited work, not exact historical version bytes. Version and
identity warnings remain in provenance and evidence. Existing scientific verdicts,
claim attribution and verification algorithms are unchanged.

## Manual PDF upload

Stage 2 provides matching/correct-PDF upload actions for possible or conflicting sources.
References without an established DOI/URL require explicit selection of a discovered
target; no candidate is preselected. The existing multipart endpoint
POST /api/sources/manual-reference additionally accepts an optional serialized locator.
The backend checks candidate membership and PDF identity. The client validates the
reference, selected-target receipt and SHA-256, then confirms the saved file through a
fresh local source check before updating availability.

A known primary cached identity conflict waits for explicit upload; it does not trigger
automatic recovery downloads. R10-specific recovery automation is not included. Normal
initial candidate discovery, legal-source fallback and missing/corrupt-file handling
retain their existing bounded behavior. Upload does not automatically resume a job,
rerun completed pairs or override a scientific CONTRADICTED verdict.

## Validation

Latest source-focused regression: 130 backend tests passed. Current frontend validation:
198 tests passed, TypeScript/Vite build and ESLint passed. A real R10 cache check with
HTTP sending forbidden returned CONFLICT / needs_attention with zero network requests.
Real cached title pages were rechecked: 29 corresponding full texts meet the broadened
confirmation standard; the unrelated R10 thesis is rejected. Detailed local transcripts,
source-cache files and historical test artifacts are intentionally not part of this commit.
