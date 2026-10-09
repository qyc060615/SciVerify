"""Async M3B application boundary; extraction only, context failures isolated."""
import asyncio
import logging
from functools import partial

from anyio import to_thread

from app.researchguard.adapters.claim_llm import ClaimLLMAdapter, ClaimLLMError, PROMPT_VERSION
from app.researchguard.domain import (
    AttributionStatus, ClaimExtractionMetadata, ClaimExtractionResult, ContextExtractionResult,
    ExtractionStatus, RejectedClaimProposalSummary,
)
from app.services.citation_context import CONTEXT_POLICY_VERSION, build_contexts, diagnostic, fingerprint, validate_input
from app.services.claim_attribution import ATTRIBUTION_POLICY_VERSION, ProposalRejected, validate_proposal, validate_result

MAX_CONCURRENT_CONTEXTS = 2
logger = logging.getLogger(__name__)


async def extract_claims(parsed, *, provider=None, provider_factory=None):
    parsed = validate_input(parsed)
    plans = build_contexts(parsed)
    paragraphs = {p.id: p for p in parsed.paragraphs}
    calls = {c.id: c for c in parsed.citation_callouts}
    provider_error = None
    if any(not plan.skip_code for plan in plans) and provider is None:
        try:
            if provider_factory is None:
                from app.services.llm.provider import get_llm_provider
                provider_factory = get_llm_provider
            provider = provider_factory()
        except Exception:
            provider_error = ClaimLLMError("EXTRACTION_PROVIDER_UNAVAILABLE")
    model = getattr(provider, "model", None)
    model = model if isinstance(model, str) and len(model) <= 200 else None
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CONTEXTS)

    async def run(plan):
        context = plan.context
        if plan.skip_code:
            return (), ContextExtractionResult(context_id=context.id, status=ExtractionStatus.SKIPPED,
                                                diagnostics=plan.diagnostics)
        try:
            if provider_error:
                raise provider_error
            async with semaphore:
                proposal = await to_thread.run_sync(partial(ClaimLLMAdapter(provider).propose,
                    context, paragraphs[context.paragraph_id], [calls[cid] for cid in context.citation_callout_ids]))
        except ClaimLLMError as exc:
            return (), ContextExtractionResult(context_id=context.id, status=ExtractionStatus.FAILED,
                diagnostics=plan.diagnostics + (diagnostic(exc.code, context.id),))
        accepted, rejected, notes = [], [], list(plan.diagnostics)
        for i, proposed in enumerate(proposal.claims):
            try:
                checked = validate_proposal(parsed, context, proposed)
                if checked.claim.id not in {c.id for c in accepted}:
                    accepted.append(checked.claim)
                notes.extend(checked.diagnostics)
            except ProposalRejected as exc:
                rejected.append(RejectedClaimProposalSummary(proposal_index=i, reason_code=exc.code))
                notes.append(diagnostic(exc.code, context.id))
        if proposal.claims and not accepted:
            status = ExtractionStatus.FAILED
            notes.append(diagnostic("EXTRACTION_VALIDATION_FAILED", context.id))
        elif rejected or any(c.attribution_status != AttributionStatus.RESOLVED for c in accepted):
            status = ExtractionStatus.PARTIAL
        else:
            status = ExtractionStatus.COMPLETED
        return tuple(accepted), ContextExtractionResult(context_id=context.id, status=status,
            accepted_claim_ids=tuple(c.id for c in accepted), diagnostics=tuple(notes), rejected_proposals=tuple(rejected))

    # gather preserves input order, independently of worker completion order.
    outputs = await asyncio.gather(*(run(plan) for plan in plans))
    context_results = tuple(output[1] for output in outputs)
    states = [r.status for r in context_results]
    if not states or all(s == ExtractionStatus.SKIPPED for s in states):
        status = ExtractionStatus.SKIPPED
    elif all(s in {ExtractionStatus.FAILED, ExtractionStatus.SKIPPED} for s in states):
        status = ExtractionStatus.FAILED
    elif all(s == ExtractionStatus.COMPLETED for s in states):
        status = ExtractionStatus.COMPLETED
    else:
        status = ExtractionStatus.PARTIAL
    notes = tuple(d for r in context_results for d in r.diagnostics)
    if not plans:
        notes += (diagnostic("NO_CITATION_CONTEXTS", parsed.manuscript.id, "info"),)
    result = ClaimExtractionResult(manuscript_id=parsed.manuscript.id, status=status,
        contexts=tuple(p.context for p in plans), claims=tuple(c for output in outputs for c in output[0]),
        context_results=context_results, diagnostics=notes,
        metadata=ClaimExtractionMetadata(model=model, prompt_version=PROMPT_VERSION,
            context_policy_version=CONTEXT_POLICY_VERSION, attribution_policy_version=ATTRIBUTION_POLICY_VERSION,
            input_fingerprint="sha256:" + fingerprint(parsed)))
    validate_result(parsed, result)
    logger.info("claim_extraction_completed contexts=%d claims=%d status=%s", len(plans), len(result.claims), status.value)
    return result


def failure_http_status(result):
    if result.status != ExtractionStatus.FAILED:
        return 200
    codes = {d.code for d in result.diagnostics}
    if "EXTRACTION_TIMEOUT" in codes:
        return 504
    if codes & {"EXTRACTION_PROVIDER_UNAVAILABLE", "EXTRACTION_RATE_LIMITED", "EXTRACTION_PROVIDER_ERROR"}:
        return 503
    return 502
