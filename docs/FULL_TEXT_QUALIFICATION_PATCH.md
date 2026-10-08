# Full-Text Qualification Patch

Baseline: `936d0fdf95aebbdac46f7f79dada55847ce70c9b` (`develop`).

## Problem and scope

Previously, both remote retrieval and source-cache reuse treated any parseable
chunks as sufficient proof of full text. Repository records with an abstract
therefore entered the evidence pipeline and cache without the paper body.

This patch changes only source qualification and bounded direct-link retrieval.
PaperQA2, its index cache, manual PDF identity checks, agents, verifier, API
contracts, frontend, and Local Demo Mode are unchanged.

## Acceptance rules

`backend/app/services/full_text_qualifier.py` supplies the same qualification
helper to the remote and cache paths. PDF acceptance continues to rely on the
existing PDF transport validity, parsing, and chunking checks; no PDF classifier
was added.

HTML qualification removes abstract containers, navigation, metadata, forms,
scripts, and other page chrome from its inspection copy. It looks for canonical
body sections (Introduction/Background, Methods, Results, Discussion, Conclusion)
and counts paragraph prose within them. Abstract subsections are excluded;
ordinary subsections retain their canonical parent. References do not count.

Acceptance requires at least two substantive body-section categories, each with
at least 100 characters of paragraph prose, and at least 400 characters overall.
Only paragraphs of at least 40 characters contribute. It also requires an
article/body container, explicit full-text HTML metadata, or at least three body
categories. Thus neither length, an article wrapper, metadata, nor a nonempty
chunk is independently sufficient. Existing paywall/interstitial checks remain
in force. Known PMC/Europe PMC HTML is evaluated by these content rules, rather
than accepted merely because of its hostname.

## Landing-page follow-up

Rejected HTML may expose `citation_pdf_url`, `citation_fulltext_html_url`,
`link[type=application/pdf]`, PDF path suffixes, PDF-labelled anchors, or explicit
View/Read/Open full-text links. Supplementary and bibliographic/navigation links
are excluded. Relative URLs resolve against the final downloaded document URL,
including redirects. Malformed URLs, non-HTTP(S) schemes, credentials, localhost,
and literal private/local IP targets are rejected.

At most three direct links per original page are returned, with PDF first.
At most six follow-ups and 24 candidate retrieval attempts are allowed per DOI
request. HTTP redirects retain the existing HTTP client's redirect policy.
Fragments are removed for deduplication; original and final URLs participate in
the visited set. A queued duplicate is promoted instead of fetched twice.
Follow-ups are depth one and cannot expose further follow-ups. Every download
uses the existing transport service, including size, timeout, access-control,
interstitial, and content validity checks. Even an otherwise unparseable download
page can expose a valid direct PDF link.

## Cache and failure behavior

Cached HTML must pass the same qualification before chunk reuse and
`source_cache_hit`. Rejected cache content logs
`source_cache_rejected ... reason=not_full_text` and falls through to ordinary
discovery. Rejected remote HTML never reaches chunk acceptance or cache writes.
A subsequently accepted document updates the DOI pointer to its actual bytes,
format, hash, and final URL. Old rejected bytes are not garbage-collected by this
patch; if discovery fails, the old artifact remains stored but is rejected again
on the next request.

All candidates failing still produces `FULL_TEXT_UNAVAILABLE`; the unchanged
upper pipeline maps that to `source_required`, with no semantic verdict.
New events are `full_text_candidate_rejected ... reason=landing_or_abstract`,
`full_text_followup_discovered ... format=pdf|html`, and `source_cache_rejected`.
They contain no source body, prompt, API key, or provider response body.

## Files and offline validation

- `backend/app/services/full_text_qualifier.py`: qualification and direct links.
- `backend/app/services/paper_retriever.py`: both acceptance paths and bounded queue.
- `backend/app/tests/full_text_fixtures.py`: synthetic full-body and landing HTML.
- `backend/app/tests/test_full_text_qualification.py`: 30 deterministic regressions
  with real transport/parser/chunker/store and an HTTP MockTransport.
- Existing `test_paper_retriever.py`, `test_pmc_runtime_retrieval.py`, and
  `test_source_lifecycle.py`: replace underspecified successful HTML fixtures with
  structured scholarly HTML while retaining their original test purposes.

Coverage includes parseable abstract rejection, PDF metadata/anchors/MIME links,
redirect-relative resolution, next-candidate fallback, legitimate scholarly
HTML including PMC/Europe PMC, old-cache rejection and replacement, valid PDF
and HTML reuse, URL deduplication/promotion, one-hop cycles, budgets, malformed
links, transport size/timeouts, and paywall/interstitial rejection. Existing M2
tests continue to cover manual recovery, source-required versus semantic
insufficiency, and PaperQA index reuse.

Final validation: `cd backend` then `python -m pytest -q`: **646 passed**, with
one existing Starlette TestClient deprecation warning. Tests use synthetic local
fixtures and the suite's public-network guard.

No real server was started, no browser was used, no real provider/public API or
DOI E2E was called, and real `.env` files were not modified. No push was performed.

## Limits and next validation

HTML qualification is a conservative structural heuristic, not proof that every
section of a paper is present. Short papers, non-English/nonstandard headings,
unstructured body markup, or unusual DOM layouts may be rejected and require
manual PDF recovery. A misleading page imitating multiple scholarly body sections
could still pass. No publisher-specific scraper, JavaScript rendering, recursive
crawling, or new PDF identity/completeness classifier is included. Synthetic
PMC/Europe PMC regressions do not establish live access availability.

A future explicitly authorized real Single-Claim E2E must confirm that the
previous repository landing now yields the actual paper PDF and that the report
uses that source. This offline patch alone does not certify a real verdict.

Recommended commit message: `fix: reject landing pages as full-text sources`.
