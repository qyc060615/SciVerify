# Unified Source Retrieval — pre-implementation audit

Baseline: develop / cb9a39173d90dad80c561eeba5219990a1672c64.
Tracked working tree clean. Existing audits, source bytes and both live Jobs are preserved.

| Module | DOI dependency / URL blocker | Minimal change | Compatibility risk |
| --- | --- | --- | --- |
| Reference / M3B fingerprint | Reference already carries URL and resolution candidates | Keep original Reference and extraction unchanged; derive a locator | Do not add default fields to fingerprinted Reference |
| SourceDocument | DOI already optional; adapters assume paper.doi for identity | Derive identity from typed locator + raw content hash; preserve DOI identity algorithm | Existing evidence IDs must remain stable |
| PaperMetadata / PaperSource | paper.doi required; provenance only URL/hash | Optional DOI, explicit locator and acquisition provenance | Existing DOI response keys/values remain usable |
| AcceptedSourceArtifact / LocalSourceStore | normalize_doi and root/doi index | Add URL index and versioned metadata; retain version-1 DOI read/write | Avoid migration or rewriting existing cache |
| SourceBinding | DOI required, no locator/version relationship | Optional DOI plus typed locator/provenance, omit absent additions in serialization | Old JSON round-trip and snapshot checksum must stay exact |
| M4 acquisition | No DOI immediately becomes DOI_MISSING | Dispatch DOI to existing retrieve_paper; URL to qualified acquisition | Preserve injected DOI retrievers and old error semantics |
| JobSnapshot | Binding checked via normalize_doi(reference.doi) | Compare typed locators; unchanged task-key/fingerprint algorithm | Old snapshots and completed results must load unchanged |
| Resume / worker pins | Uses DOI as cache/expected-version key | Same locator key in resume and core; preserve raw hash/version checks | A locator update must not silently replace pinned content |
| Manual recovery | DOI resolver and DOI upload form | Keep DOI recovery; URL recovery initially uses qualified automatic acquisition + explicit hash confirmation | Do not accept arbitrary uploaded URL PDFs without identity validation |
| PaperQA2 | Receives SourceDocument and canonical EvidenceChunk; cache uses complete source/chunks | No retriever rewrite; propagate provenance through existing metadata | Cache must distinguish locator/content identity and uncertainty |
| UI | Reports no DOI / URL unsupported | Display locator, source/version relationship, actual URL/hash and warnings | Old Jobs remain renderable; no UI architecture redesign |

## Minimal implementation plan

1. Add a typed DOI/URL locator, keeping DOI values distinct from URL acquisition locations and SHA-256 versions.
2. Reuse DOI retrieval, parsers, chunker and content-addressed artifacts; extend only their missing URL/provenance boundaries.
3. Use a public-address-pinned HTTP transport, bounded redirects, streamed size limits, content checks and strict document/identity qualification for external URL acquisition.
4. Preserve old snapshot serialization and DOI source identifiers; extend binding and resume comparisons without changing task/event orchestration.
5. Check retitled preprints with author/model/subject metadata AND accepted full-text evidence; retain probable-same-work and historical-version warnings rather than asserting exact identity.
6. Add integration/HTTP contracts and full backend/frontend checks, then real source-only acceptance. No paid scientific calls or new live verification Job.

## Initial live diagnosis (before changes)

- Ref 7: normal PMC HTML downloads successfully and parses, but has substantive unstructured article paragraphs/figures rather than IMRAD headings. Existing qualifier rejects it. PMC PDF routes return non-PDF content; Europe PMC HTML is HTTP 403. No challenge bypass attempted.
- Ref 12: baseline recheck now retrieves and qualifies PMC7289658 HTML (57 chunks). Previous live failure is not reproducible on this request; do not claim a matching-policy fix is needed for this particular HTML.
- Ref 11: no usable full-text candidate from existing discovery; investigate discovery metadata and legal repositories before changing qualification.

Raw baseline observations are in backend/data/researchguard/evaluations/unified-source-20261018/. This audit is created before business-code changes.
