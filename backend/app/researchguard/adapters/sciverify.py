"""Explicit, opt-in legacy verdict translation; existing routes do not use it."""
from app.schemas.verification import Verdict as SciVerifyVerdict

from ..domain import ProcessingStatus, Verdict


_VERDICTS = {
    SciVerifyVerdict.SUPPORTS: Verdict.SUPPORTED,
    SciVerifyVerdict.OVERSTATED: Verdict.OVERSTATED,
    SciVerifyVerdict.CONTRADICTS: Verdict.CONTRADICTED,
    SciVerifyVerdict.INSUFFICIENT: Verdict.INSUFFICIENT,
    # Lack of support is not positive evidence of contradiction. Lossy mapping;
    # future application adapters should retain the raw verdict in trace metadata.
    SciVerifyVerdict.FABRICATED: Verdict.INSUFFICIENT,
}


def map_sciverify_verdict(
    verdict: SciVerifyVerdict | None, *, processing_status: ProcessingStatus
) -> Verdict | None:
    """Map only a completed semantic assessment.

    The caller must classify processing using retrieval diagnostics, not the
    legacy verdict alone. SciVerify insufficient_evidence combines unavailable
    sources and empty evidence; it cannot safely determine completion by itself.
    There is no legacy top-level equivalent of PARTIALLY_SUPPORTED.
    """
    status = ProcessingStatus(processing_status)
    if status != ProcessingStatus.COMPLETED:
        return None
    if verdict is None:
        raise ValueError("Completed assessment requires a SciVerify verdict")
    return _VERDICTS[SciVerifyVerdict(verdict)]
