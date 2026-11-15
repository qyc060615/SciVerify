"""Offline production matching, bounded providers and legacy wire compatibility."""
import asyncio
import json
from pathlib import Path

import httpx
import pytest

from app.researchguard.domain import Reference
from app.services.reference_resolver import (
    ResolutionInputError, discover_url, is_public_http_url, resolve_reference, resolve_references,
)
from app.services.citation_context import fingerprint
from app.services.manuscript_verification import validate_combined_input
from app.services.verification_job_models import JobSnapshot
from app.tests.test_manuscript_verification import inputs

TITLE = "Safety and immunogenicity of two RNA-based vaccine candidates"


def reference(**updates):
    return Reference(id="r1", manuscript_id="m1", raw_text="Author. " + TITLE,
        title=TITLE, authors=("A Smith", "B Jones"), year=2020, journal="Example Journal").model_copy(update=updates)


def work(doi="10.1234/correct", **updates):
    return {"DOI": doi, "title": [TITLE], "author": [{"given": "Alice", "family": "Smith"}, {"given": "Bob", "family": "Jones"}],
        "published-print": {"date-parts": [[2020]]}, "container-title": ["Example Journal"], "type": "journal-article", **updates}


def alex(doi="https://doi.org/10.1234/correct", **updates):
    return {"doi": doi, "display_name": TITLE, "authorships": [{"author": {"display_name": "Alice Smith"}}, {"author": {"display_name": "Bob Jones"}}],
        "publication_year": 2020, "type": "article", "primary_location": {"source": {"display_name": "Example Journal"}}, **updates}


async def resolve(ref=None, crossref=None, openalex=None):
    calls = []
    def handler(request):
        calls.append(request)
        cross = "crossref" in request.url.host
        value = crossref if cross else openalex
        if isinstance(value, Exception):
            raise value
        if isinstance(value, httpx.Response):
            return value
        return httpx.Response(200, json={"message": {"items": value or []}} if cross else {"results": value or []})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await resolve_reference(ref or reference(), client=client), calls


@pytest.mark.anyio
async def test_preserves_original_doi_without_search():
    result, calls = await resolve(reference(doi="DOI: 10.1234/Original"))
    assert result.original_doi == "DOI: 10.1234/Original" and result.resolved_doi == "10.1234/original"
    assert result.provider == "original" and not calls and result.match_confidence is None


@pytest.mark.anyio
async def test_correct_crossref_match_does_not_take_first_hit():
    result, calls = await resolve(crossref=[work("10.1234/wrong", title=["Other vaccine study"]), work()])
    assert result.status == "resolved" and result.resolved_doi == "10.1234/correct" and len(calls) == 1
    assert result.candidates[0].rejection_reason == "TITLE_MISMATCH"
    assert calls[0].url.params["rows"] == "10"


@pytest.mark.anyio
async def test_falls_back_to_openalex_after_no_crossref_result():
    result, calls = await resolve(openalex=[alex()])
    assert result.status == "resolved" and result.provider == "openalex" and len(calls) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("updates,reason", [
    ({"title": ["Safety of vaccine candidates against COVID-19"]}, "TITLE_MISMATCH"),
    ({"author": [{"family": "Other"}]}, "AUTHOR_CONFLICT"),
    ({"published-print": {"date-parts": [[2015]]}}, "YEAR_CONFLICT"),
    ({"title": [TITLE.replace("two", "three")]}, "TITLE_MISMATCH"),
    ({"type": "dataset"}, "PUBLICATION_TYPE_CONFLICT"),
])
async def test_rejects_related_but_different_publication(updates, reason):
    result, _ = await resolve(crossref=[work(**updates)])
    assert result.status == "not_found" and result.resolved_doi is None
    assert result.candidates[0].rejection_reason == reason


@pytest.mark.anyio
async def test_title_identifier_conflict_even_when_similarity_is_high():
    suffix = " in humans under randomized trials for BNT162b"
    ref = reference(title=TITLE + suffix + "2")
    result, _ = await resolve(ref, crossref=[work(title=[TITLE + suffix + "1"])])
    assert result.resolved_doi is None and result.candidates[0].rejection_reason == "TITLE_IDENTIFIER_CONFLICT"


@pytest.mark.anyio
async def test_multiple_identities_are_ambiguous_and_not_applied():
    result, _ = await resolve(crossref=[work(), work("10.1234/another")])
    assert result.status == "ambiguous" and result.resolved_doi is None


@pytest.mark.anyio
async def test_provider_hits_are_deduplicated_by_doi():
    result, _ = await resolve(crossref=[work(), work()])
    assert result.status == "resolved"


@pytest.mark.anyio
async def test_preprint_is_never_silently_replaced_by_article():
    result, _ = await resolve(reference(raw_text=TITLE + ". preprint.", journal=None, year=None), crossref=[work()], openalex=[alex()])
    assert result.status == "ambiguous" and result.match_reason == "VERSION_UNCERTAIN"
    assert result.resolved_doi is None


@pytest.mark.anyio
async def test_explicit_preprint_type_can_match_original_version():
    result, _ = await resolve(reference(raw_text=TITLE + ". preprint.", journal=None, year=None),
        crossref=[work(type="posted-content", subtype="preprint", relation={"is-preprint-of": [{"id": "10.1234/article"}]})])
    assert result.status == "resolved" and result.candidates[0].relations == ("is-preprint-of",)
    assert "PREPRINT_TYPE_MATCH" in result.candidates[0].evidence


@pytest.mark.anyio
async def test_preprint_versions_remain_ambiguous():
    result, _ = await resolve(reference(raw_text="preprint", journal=None, year=None),
        crossref=[work(type="posted-content", subtype="preprint"), work("10.1234/v2", type="posted-content", subtype="preprint")])
    assert result.status == "ambiguous"


@pytest.mark.anyio
async def test_unicode_case_and_typesetting_hyphens():
    result, _ = await resolve(reference(title=TITLE.replace("RNA-based", "RNAbased").upper(), authors=("A Smíth", "B Jones")), crossref=[work()])
    assert result.status == "resolved"


@pytest.mark.anyio
@pytest.mark.parametrize("authors,year,expected", [((),2020,"resolved"), ((),None,"not_found"), (("A Smith","B Jones"),None,"resolved"), (("A Smith",),None,"not_found")])
async def test_missing_metadata_requires_extra_corroboration(authors, year, expected):
    result, _ = await resolve(reference(authors=authors, year=year), crossref=[work()])
    assert result.status == expected


@pytest.mark.anyio
async def test_online_first_year_and_small_corroborated_offset():
    result, _ = await resolve(crossref=[work(**{"published-print": {"date-parts": [[2021]]}, "published-online": {"date-parts": [[2020]]}})])
    assert result.status == "resolved" and "YEAR_MATCH" in result.candidates[0].evidence
    result, _ = await resolve(crossref=[work(**{"published-print": {"date-parts": [[2019]]}})])
    assert result.status == "resolved" and "YEAR_OFFSET_1_VERSION_CHECK" in result.candidates[0].evidence


@pytest.mark.anyio
async def test_created_year_is_not_a_publication_date():
    item = work(); item.pop("published-print"); item["created"] = {"date-parts": [[2020]]}
    result, _ = await resolve(reference(authors=()), crossref=[item])
    assert result.resolved_doi is None


@pytest.mark.anyio
@pytest.mark.parametrize("doi", ["bad", "", None, "https://www.cdc.gov/test"])
async def test_search_candidates_must_have_real_doi(doi):
    result, _ = await resolve(crossref=[work(doi)])
    assert result.status == "not_found" and not result.candidates


@pytest.mark.anyio
async def test_invalid_original_doi_is_preserved_not_replaced():
    result, calls = await resolve(reference(doi="bad"), crossref=[work()])
    assert result.original_doi == "bad" and result.resolved_doi is None and not calls


@pytest.mark.anyio
@pytest.mark.parametrize("failure,code", [
    (httpx.ReadTimeout("secret"), "CROSSREF_TIMEOUT"),
    (httpx.Response(429), "CROSSREF_RATE_LIMIT"),
    (httpx.Response(200, content=b"not-json"), "CROSSREF_INVALID_JSON"),
    (httpx.Response(200, json=[]), "CROSSREF_INVALID_RESPONSE"),
    (httpx.Response(302, headers={"location":"http://127.0.0.1/private"}), "CROSSREF_HTTP_ERROR"),
])
async def test_provider_failures_are_isolated_and_fallback_can_succeed(failure, code):
    result, calls = await resolve(crossref=failure, openalex=[alex()])
    assert result.status == "resolved" and code in result.diagnostics and len(calls) == 2
    assert "secret" not in result.model_dump_json()


@pytest.mark.anyio
async def test_both_providers_fail_without_false_not_found():
    result, _ = await resolve(crossref=httpx.Response(500), openalex=httpx.Response(429))
    assert result.status == "provider_error" and result.resolved_doi is None


@pytest.mark.anyio
async def test_partial_provider_failure_is_not_definitive_not_found():
    result, _ = await resolve(crossref=httpx.Response(500))
    assert result.status == "provider_error" and result.match_reason == "SEARCH_INCOMPLETE"


@pytest.mark.anyio
@pytest.mark.parametrize("url", ["https://www.who.int/speech", "https://www.cdc.gov/info", "https://www.fda.gov/media/42/download", "https://coronavirus.jhu.edu/map.html"])
async def test_official_web_sources_do_not_search_or_fetch(url):
    result, calls = await resolve(reference(title="Official information", authors=(), journal=None, raw_text=f"Official page ({url})."))
    assert result.status == "non_doi_source" and result.source_url == url and not calls
    assert "DISCOVERED_ONLY" in result.diagnostics


@pytest.mark.anyio
async def test_institution_without_url_remains_discovered_only():
    result, calls = await resolve(reference(authors=(), journal=None, raw_text="World Health Organization. Speech."))
    assert result.status == "non_doi_source" and "URL_MISSING" in result.diagnostics and not calls


@pytest.mark.anyio
async def test_original_reference_url_takes_precedence_over_truncated_tei_target():
    result, calls = await resolve(reference(authors=(), journal=None, url="https://www.who.int/speech",
        raw_text="World Health Organization (https://www . who . int/ speech/ 11 -march -2020)."))
    assert result.source_url == "https://www.who.int/speech/11-march-2020" and not calls
    assert "URL_FIELDS_DISAGREE_RAW_PREFERRED" in result.diagnostics


@pytest.mark.anyio
async def test_merged_trailing_web_reference_does_not_override_article():
    result, _ = await resolve(reference(raw_text=TITLE + ". 13. Food and Drug Administration (https://www.fda.gov/item)."), crossref=[work()])
    assert result.status == "resolved" and "POSSIBLE_MERGED_WEB_REFERENCE" in result.diagnostics


@pytest.mark.parametrize("url", ["http://localhost/x", "http://a.localhost/x", "http://127.0.0.1", "http://127.1", "http://2130706433", "http://169.254.169.254/latest", "http://10.0.0.2", "http://192.168.1.2", "http://[::1]", "http://[::ffff:127.0.0.1]", "file:///tmp/x", "ftp://www.who.int", "https://user:pass@who.int", "https://who.int:8070/x", "https://who.int\\@localhost/x"])
def test_url_discovery_rejects_unsafe_targets(url):
    assert not is_public_http_url(url)


def test_typeset_url_reconstruction_is_limited_to_parentheses():
    assert discover_url("WHO (https://www . who . int/ speeches/ detail/ covid -19).") == "https://www.who.int/speeches/detail/covid-19"


@pytest.mark.anyio
async def test_metadata_insufficient_has_no_network():
    result, calls = await resolve(reference(title=None, raw_text="Missing title", authors=(), journal=None))
    assert result.status == "metadata_insufficient" and not calls


@pytest.mark.anyio
async def test_bounded_candidate_count_response_size_and_api_key_redaction(monkeypatch):
    result, _ = await resolve(crossref=[work("10.1234/wrong", title=["Wrong title"])] * 10 + [work()])
    assert result.resolved_doi is None and len(result.candidates) == 10
    monkeypatch.setenv("OPENALEX_API_KEY", "secret-api-key")
    result, calls = await resolve(crossref=httpx.Response(200, content=b" " * (2 * 1024 * 1024 + 1)), openalex=[alex()])
    assert result.status == "resolved" and "CROSSREF_RESPONSE_TOO_LARGE" in result.diagnostics
    assert calls[-1].headers["Authorization"] == "Bearer secret-api-key"
    assert "secret-api-key" not in result.model_dump_json() and "api_key" not in str(calls[-1].url)


@pytest.mark.anyio
async def test_batch_memoization_concurrency_and_ids():
    parsed, _ = inputs()
    r = reference(manuscript_id=parsed.manuscript.id)
    parsed = parsed.model_copy(update={"references": (r, r.model_copy(update={"id":"r2"}))})
    active = peak = count = 0
    async def handler(request):
        nonlocal active, peak, count
        active += 1; peak = max(peak, active); count += 1
        await asyncio.sleep(.01)
        active -= 1
        return httpx.Response(200, json={"message":{"items":[work()]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        enriched = await resolve_references(parsed, client=client)
    assert count == 1 and peak <= 2
    assert [r.id for r in enriched.references] == ["r1","r2"]
    assert [r.resolution.reference_id for r in enriched.references] == ["r1","r2"]
    assert enriched.paragraphs == parsed.paragraphs and enriched.citation_callouts == parsed.citation_callouts


@pytest.mark.anyio
async def test_request_deadline_cancels_network_work(monkeypatch):
    monkeypatch.setattr("app.services.reference_resolver.TOTAL_TIMEOUT", .01)
    parsed, _ = inputs()
    parsed = parsed.model_copy(update={"references": (reference(manuscript_id=parsed.manuscript.id),)})
    async def handler(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json={"message":{"items":[]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        enriched = await resolve_references(parsed, client=client)
    assert enriched.references[0].resolution.match_reason == "REQUEST_DEADLINE"


@pytest.mark.anyio
async def test_reference_count_limit_and_enriched_input_rejection():
    parsed, _ = inputs()
    oversized = parsed.model_copy(update={"references":tuple(reference(id=f"r{i}",manuscript_id=parsed.manuscript.id) for i in range(101))})
    with pytest.raises(ResolutionInputError,match="REFERENCE_LIMIT_EXCEEDED"):
        await resolve_references(oversized)
    result, _ = await resolve(reference(doi="10.1234/local"))
    parsed = parsed.model_copy(update={"references":(reference(manuscript_id=parsed.manuscript.id, resolution=result),)})
    with pytest.raises(ResolutionInputError,match="ALREADY_ENRICHED"):
        await resolve_references(parsed)


def test_pre_change_golden_input_and_fingerprint_are_unchanged():
    from app.researchguard.domain import ClaimExtractionResult, ParsedManuscript
    data = json.loads((Path(__file__).resolve().parents[3] / "frontend/tests/fixtures/manuscript.json").read_text(encoding="utf-8"))
    old = data["job_request"]
    parsed = ParsedManuscript.model_validate(old["parsed"])
    extraction = ClaimExtractionResult.model_validate(old["extraction"])
    assert parsed.model_dump(mode="json") == old["parsed"]
    assert extraction.metadata.input_fingerprint == "sha256:" + fingerprint(parsed)
    validate_combined_input(parsed, extraction)
    assert "url" not in parsed.references[0].model_dump() and "resolution" not in parsed.references[0].model_dump()


def test_old_job_snapshot_roundtrips_without_new_keys():
    from app.tests.test_verification_job_store import snapshot
    old = snapshot().model_dump(mode="json")
    assert JobSnapshot.model_validate(old).model_dump(mode="json") == old


@pytest.mark.parametrize("element", ['<ref target="https://www.who.int/speech"/>','<ptr target="https://www.who.int/speech"/>','<idno type="url">https://www.who.int/speech</idno>'])
def test_tei_retains_explicit_url_without_changing_callouts(element):
    from app.researchguard.adapters.grobid_tei import parse_tei
    from app.tests.test_grobid_tei import tei, MANUSCRIPT
    parsed = parse_tei(tei('<p>研究🧪 &amp; result <ref type="bibr" target="#r">[1]</ref>.</p>',
        '<listBibl><biblStruct xml:id="r"><monogr><title>WHO speech</title></monogr>' + element + '</biblStruct></listBibl>'), MANUSCRIPT)
    assert parsed.references[0].url == "https://www.who.int/speech"
    c=parsed.citation_callouts[0]
    assert parsed.paragraphs[0].text[c.span.start:c.span.end] == "[1]"
