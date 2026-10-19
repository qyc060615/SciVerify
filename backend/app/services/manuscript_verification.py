"""Sequential, invocation-local whole-paper orchestration. No job runtime."""
import hashlib
import json

from anyio import to_thread

from app.researchguard.domain import (
    AttributionStatus, ClaimExtractionResult, ExtractionStatus, ParsedManuscript,
    ProcessingStatus, VerificationResult, VerificationTraceability,
)
from app.researchguard.manuscript_verification import (
    AttributionBlockedClaim, CoreCoverage, ManuscriptCoreResult, PairOutcome, SourceBinding,
)
from app.researchguard.adapters.sciverify import (
    accepted_source_to_domain, evidence_to_legacy, map_sciverify_verdict, standalone_claim_to_domain,
)
from app.researchguard.adapters.paperqa2 import PaperQA2RetrievalError
from app.schemas.evidence import EvidencePaperSummary, EvidenceRetrievalResponse, EvidenceRetrievalStatus
from app.schemas.paper import PaperRetrievalStatus, RetrievePaperResponse
from app.schemas.verification import VerificationResponse, VerificationStatus, Verdict as LegacyVerdict
from app.services.citation_context import fingerprint, validate_input
from app.services.claim_attribution import validate_result
from app.services.paper_retriever import retrieve_paper, PaperNotFoundError, PaperProviderError
from app.services.verification_service import verify_prepared_evidence
from app.services.source_store import SourceDurabilityError
from app.utils.claim_preprocessor import preprocess_claim
from app.utils.doi import InvalidDOIError, normalize_doi
from app.researchguard.source_locator import SourceLocator
from app.services.source_locator import reference_locator
from app.services.source_acquisition import retrieve_reference_source

MAX_CLAIMS = 256
MAX_PAIRS = 1024
MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_PAIR_PAYLOAD_BYTES = 256 * 1024


def validate_combined_input(parsed, extraction):
    """Revalidate copied models and the exact M3B input projection before I/O."""
    parsed = validate_input(parsed)
    extraction = ClaimExtractionResult.model_validate(extraction.model_dump())
    if extraction.manuscript_id != parsed.manuscript.id:
        raise ValueError("Extraction manuscript identity mismatch")
    if extraction.metadata.input_fingerprint != "sha256:" + fingerprint(parsed):
        raise ValueError("Extraction input fingerprint mismatch")
    if len(extraction.claims) > MAX_CLAIMS:
        raise ValueError("Core claim limit exceeded")
    if sum(len(c.reference_ids) for c in extraction.claims) > MAX_PAIRS:
        raise ValueError("Core pair limit exceeded")
    payload = [parsed.model_dump(mode="json"), extraction.model_dump(mode="json")]
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError("Core input size limit exceeded")
    references = {r.id for r in parsed.references}
    for claim in extraction.claims:
        if len(set(claim.reference_ids)) != len(claim.reference_ids) or not set(claim.reference_ids) <= references:
            raise ValueError("Claim contains foreign or duplicate references")
        if preprocess_claim(claim.text).original != claim.text:
            raise ValueError("Core must preserve original claim text")
    # Validate full context bounds as well as the existing grounding/link checks.
    paragraphs = {p.id: p for p in parsed.paragraphs}
    for context in extraction.contexts:
        paragraph = paragraphs.get(context.paragraph_id)
        if paragraph is None or context.span.end > len(paragraph.text):
            raise ValueError("Extraction context outside manuscript paragraph")
    try:
        validate_result(parsed, extraction)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Invalid combined extraction graph") from exc
    return parsed, extraction


def _default_retriever(chunks):
    from app.researchguard.adapters.paperqa2 import PaperQA2Config, PaperQA2EvidenceRetriever
    return PaperQA2EvidenceRetriever(chunks, PaperQA2Config.from_environment())


def plan_manuscript_pairs(parsed, extraction):
    """Deterministic original-identity plan; callers validate combined input first."""
    references = {r.id: r for r in parsed.references}
    callouts = {c.id: c for c in parsed.citation_callouts}
    plan, blocked = [], []
    for claim in extraction.claims:
        if claim.attribution_status != AttributionStatus.RESOLVED:
            blocked.append(AttributionBlockedClaim(claim_id=claim.id,
                reason_code="ATTRIBUTION_" + claim.attribution_status.value.upper()))
            continue
        for rid in claim.reference_ids:
            calls = tuple(cid for cid in claim.citation_callout_ids if rid in callouts[cid].reference_ids)
            plan.append((claim, references[rid], calls))
    return tuple(plan), tuple(blocked)


async def verify_manuscript_core(
    parsed: ParsedManuscript, extraction: ClaimExtractionResult, *,
    source_retriever=retrieve_paper, evidence_retriever_factory=None,
    prepared_verifier=verify_prepared_evidence, llm=None, top_k=5,
    selected_pairs=None, on_pair_started=None, on_pair_finished=None,
    expected_raw_hashes=None, expected_source_versions=None, source_durability_check=None,
) -> ManuscriptCoreResult:
    """Inject a sync source callable, retriever factory, and async verifier.

    Factories receive canonical prepared chunks; their retrieve method uses the
    existing PaperQA2 signature. All memoized successes/failures expire on return.
    """
    parsed, extraction = validate_combined_input(parsed, extraction)
    if type(top_k) is not int or not 1 <= top_k <= 20:
        raise ValueError("Core top_k must be between 1 and 20")
    factory = evidence_retriever_factory or _default_retriever
    plan, blocked = plan_manuscript_pairs(parsed, extraction)
    if selected_pairs is not None:
        selected_pairs = tuple(selected_pairs)
        legal = {(c.id, r.id) for c, r, _ in plan}
        if len(set(selected_pairs)) != len(selected_pairs) or not set(selected_pairs) <= legal:
            raise ValueError("Core selection contains duplicate or unknown pairs")
        plan = tuple(item for item in plan if (item[0].id, item[1].id) in set(selected_pairs))
    expected_raw_hashes = expected_raw_hashes or {}
    expected_source_versions = expected_source_versions or {}

    prepared, sources, outcomes, provenance = {}, {}, [], {}
    original_claim_ids = {c.id for c in extraction.claims}
    for claim, reference, calls in plan:
        # Runtime/storage exceptions propagate, outside semantic failure isolation.
        if on_pair_started is not None:
            await on_pair_started(claim.id, reference.id)
        binding, selected = None, ()
        status, reason = ProcessingStatus.FAILED, "SOURCE_PREPARATION_FAILURE"
        legacy_verdict, result = None, None
        try:
            try:
                locator = reference_locator(reference)
            except ValueError:
                status, reason = ProcessingStatus.CITATION_UNRESOLVED, 'DOI_INVALID' if reference.doi else 'SOURCE_URL_INVALID'
                raise _PairBlocked() from None
            if locator is None:
                status, reason = ProcessingStatus.CITATION_UNRESOLVED, 'DOI_MISSING'
                raise _PairBlocked()
            doi = locator.value if locator.kind == 'doi' else None
            key = locator.key
            # A provisional version requires its own content review even when an
            # exact DOI reference happened to prepare that same source earlier.
            memo = (key, reference.id if not reference.doi and locator.kind == 'doi' else None)
            binding = SourceBinding(reference_id=reference.id, doi=doi,
                                    locator=locator if not reference.doi else None)
            if memo not in prepared:
                # Store only normalized domain data, not mutable provider responses.
                try:
                    if reference.doi and source_retriever is not retrieve_paper:
                        response = await to_thread.run_sync(source_retriever, doi)
                    else:
                        from functools import partial
                        response = await to_thread.run_sync(partial(retrieve_reference_source, reference,
                            doi_retriever=source_retriever if source_retriever is not retrieve_paper else None))
                    response = RetrievePaperResponse.model_validate(response.model_dump())
                    actual_locator = response.source.locator or SourceLocator(kind='doi', value=response.paper.doi)
                    provenance[memo] = response.source.provenance
                    if response.source.provenance:
                        binding = binding.model_copy(update={'provenance': response.source.provenance})
                    if actual_locator != locator or (locator.kind == 'url' and response.paper.doi is not None):
                        prepared[memo] = (ProcessingStatus.SOURCE_MISMATCH, "SOURCE_DOI_MISMATCH" if doi else 'SOURCE_LOCATOR_MISMATCH')
                    elif key in expected_raw_hashes and response.source.raw_content_sha256 != expected_raw_hashes[key]:
                        prepared[memo] = (ProcessingStatus.SOURCE_MISMATCH, "SOURCE_VERSION_CONFLICT")
                    elif response.detail in {'SOURCE_IDENTITY_CONFLICT', 'SOURCE_IDENTITY_UNCERTAIN', 'SOURCE_VERSION_UNCONFIRMED'}:
                        prepared[memo] = (ProcessingStatus.SOURCE_MISMATCH if response.detail == 'SOURCE_IDENTITY_CONFLICT'
                                          else ProcessingStatus.SOURCE_UNAVAILABLE, response.detail)
                    elif response.status != PaperRetrievalStatus.SUCCESS:
                        required = response.status in {PaperRetrievalStatus.METADATA_ONLY,
                            PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE, PaperRetrievalStatus.PARSING_FAILURE}
                        failure_status = ProcessingStatus.FAILED if response.status == PaperRetrievalStatus.PROVIDER_ERROR else ProcessingStatus.SOURCE_UNAVAILABLE
                        prepared[memo] = (failure_status, "SOURCE_REQUIRED_" + response.status.value.upper()
                            if required else "SOURCE_" + response.status.value.upper())
                    else:
                        if source_durability_check is not None:
                            await to_thread.run_sync(source_durability_check, response)
                        source, chunks = accepted_source_to_domain(response)
                        if key in expected_source_versions and source.content_hash != expected_source_versions[key]:
                            prepared[memo] = (ProcessingStatus.SOURCE_MISMATCH, "SOURCE_VERSION_CONFLICT")
                        elif len(source.model_dump_json().encode("utf-8")) > MAX_PAIR_PAYLOAD_BYTES:
                            prepared[memo] = (ProcessingStatus.FAILED, "SOURCE_METADATA_SIZE_LIMIT")
                        else:
                            prepared[memo] = (source, tuple(chunks))
                except SourceDurabilityError as exc:
                    prepared[memo] = (ProcessingStatus.FAILED, exc.code)
                except PaperNotFoundError:
                    prepared[memo] = (ProcessingStatus.SOURCE_UNAVAILABLE, "SOURCE_NOT_FOUND")
                except PaperProviderError:
                    prepared[memo] = (ProcessingStatus.FAILED, "SOURCE_PROVIDER_ERROR")
                except Exception:
                    prepared[memo] = (ProcessingStatus.FAILED, "SOURCE_PREPARATION_FAILURE")
            source, chunks = prepared[memo]
            if isinstance(source, ProcessingStatus):
                status, reason = source, chunks
                raise _PairBlocked()
            sources[source.id] = source
            prov = provenance.get(memo)
            if prov:
                prov = prov.model_copy(update={'original_citation': reference.raw_text})
            binding = binding.model_copy(update={"source_document_id": source.id, "source_version": source.content_hash,
                                                 'provenance': prov})
            reason = "EVIDENCE_RETRIEVAL_FAILURE"
            processed = preprocess_claim(claim.text)
            projection = standalone_claim_to_domain(processed, source)
            # Query-only namespace cannot impersonate an original extraction ID.
            query_id = "m4-query:" + hashlib.sha256(json.dumps([claim.id, reference.id, source.id]).encode()).hexdigest()
            while query_id in original_claim_ids:
                query_id = "query:" + query_id
            projection = projection.model_copy(update={"id": query_id})
            # Injectable retrievers cannot mutate the provenance used for checks.
            retriever = factory(tuple(c.model_copy(deep=True) for c in chunks))
            retrieved = await retriever.retrieve(projection, source.model_copy(deep=True), top_k)
            reason = "EVIDENCE_SOURCE_MISMATCH"
            originals = {c.id: c for c in chunks}
            if len(retrieved) > top_k or len({c.id for c in retrieved}) != len(retrieved):
                raise _PairBlocked()
            for chunk in retrieved:
                original = originals.get(chunk.id)
                # Scores and query-summary metadata may vary; source fields may not.
                if original is None or chunk.model_dump(exclude={"retrieval_score", "metadata"}) != original.model_dump(exclude={"retrieval_score", "metadata"}):
                    status = ProcessingStatus.SOURCE_MISMATCH
                    raise _PairBlocked()
                if any(chunk.metadata.get(k) != v for k, v in original.metadata.items()):
                    status = ProcessingStatus.SOURCE_MISMATCH
                    raise _PairBlocked()
            selected = tuple(retrieved)
            if len(json.dumps([c.model_dump(mode="json") for c in selected], ensure_ascii=False).encode("utf-8")) > MAX_PAIR_PAYLOAD_BYTES:
                selected = ()
                reason = "EVIDENCE_SIZE_LIMIT"
                raise _PairBlocked()
            reason = "EVIDENCE_BRIDGE_FAILURE"
            evidence = evidence_to_legacy(list(selected), processed)
            query_status = EvidenceRetrievalStatus.SUCCESS if evidence else EvidenceRetrievalStatus.NO_RELEVANT_EVIDENCE
            bridge = EvidenceRetrievalResponse(status=query_status, claim=claim.text,
                paper=EvidencePaperSummary(paper_id=source.id, doi=doi, title=source.title),
                evidence=evidence, total_chunks_considered=len(chunks))
            reason = "VERIFIER_EXECUTION_FAILURE"
            kwargs = {"llm": llm} if llm is not None else {}
            # Optional context belongs to the built-in semantic verifier, not to
            # the historical/custom prepared-verifier two-argument contract.
            if prepared_verifier is verify_prepared_evidence:
                context = next(c for c in extraction.contexts if c.id == claim.context_id)
                kwargs["verification_context"] = json.dumps({
                    "manuscript_title": parsed.manuscript.title,
                    "citation_context": context.text,
                    "cited_source_title": source.title,
                    "cited_source_year": source.year,
                }, ensure_ascii=False)
            # Keep an untouched bridge to detect verifier mutation/foreign output.
            legacy = await prepared_verifier(claim.text, bridge.model_copy(deep=True), **kwargs)
            legacy = VerificationResponse.model_validate(legacy.model_dump())
            if len(legacy.model_dump_json().encode("utf-8")) > MAX_PAIR_PAYLOAD_BYTES:
                reason = "VERIFIER_SIZE_LIMIT"
                raise _PairBlocked()
            if legacy.status not in {VerificationStatus.SUCCESS, VerificationStatus.INSUFFICIENT_EVIDENCE}:
                reason = "VERIFIER_" + legacy.status.value.upper()
                raise _PairBlocked()
            if (legacy.claim != claim.text or legacy.paper != bridge.paper or legacy.evidence != bridge.evidence
                    or legacy.verdict is None
                    or (not evidence and (legacy.status != VerificationStatus.INSUFFICIENT_EVIDENCE or legacy.verdict != LegacyVerdict.INSUFFICIENT))
                    or (evidence and legacy.status != VerificationStatus.SUCCESS)):
                reason = "VERIFIER_CONTRACT_MISMATCH"
                raise _PairBlocked()
            result = VerificationResult(claim_id=claim.id, processing_status=ProcessingStatus.COMPLETED,
                verdict=map_sciverify_verdict(legacy.verdict, processing_status=ProcessingStatus.COMPLETED),
                confidence=legacy.confidence, evidence_chunks=selected,
                explanation=legacy.reasoning or legacy.summary,
                traceability=VerificationTraceability(evidence_ids=tuple(c.id for c in selected),
                    method="paperqa2+prepared_verifier", warnings=tuple(legacy.validation_warnings or ()) + (prov.warnings if prov else ()),
                    metadata={"legacy_provenance": legacy.model_dump(mode="json", exclude={
                        "claim", "paper", "evidence", "confidence", "reasoning", "summary"})}))
            legacy_verdict = legacy.verdict
            status = ProcessingStatus.COMPLETED
            reason = "VERIFIED" if evidence else "NO_RELEVANT_EVIDENCE"
        except _PairBlocked:
            pass
        except PaperQA2RetrievalError:
            status, reason = ProcessingStatus.FAILED, "PAPERQA2_ADAPTER_FAILURE"
        except Exception:
            # Includes embedding/provider/bridge exceptions; never invent a verdict.
            status = ProcessingStatus.FAILED
        if result is None:
            result = VerificationResult(claim_id=claim.id, processing_status=status, evidence_chunks=selected)
        outcomes.append(PairOutcome(reference_id=reference.id, citation_callout_ids=calls,
            reason_code=reason, binding=binding, verification=result, legacy_verdict=legacy_verdict))
        if on_pair_finished is not None:
            await on_pair_finished(outcomes[-1].model_copy(deep=True))

    completed = sum(p.processing_status == ProcessingStatus.COMPLETED for p in outcomes)
    failed = sum(p.processing_status == ProcessingStatus.FAILED for p in outcomes)
    coverage = CoreCoverage(claims=len(extraction.claims), references=len(parsed.references), pairs=len(outcomes),
        completed=completed, failed=failed, blocked=len(outcomes) - completed - failed,
        unresolved_claims=sum(c.attribution_status == AttributionStatus.UNRESOLVED for c in extraction.claims),
        ambiguous_claims=sum(c.attribution_status == AttributionStatus.AMBIGUOUS for c in extraction.claims),
        failed_contexts=sum(c.status == ExtractionStatus.FAILED for c in extraction.context_results),
        skipped_contexts=sum(c.status == ExtractionStatus.SKIPPED for c in extraction.context_results),
        coverage_complete=bool(outcomes) and not blocked and completed == len(outcomes)
            and extraction.status == ExtractionStatus.COMPLETED)
    return ManuscriptCoreResult(parsed=parsed, extraction=extraction, sources=tuple(sources.values()),
        pairs=tuple(outcomes), attribution_blocked=tuple(blocked), coverage=coverage)


class _PairBlocked(Exception):
    """Internal control flow for a classified, isolated pair outcome."""
