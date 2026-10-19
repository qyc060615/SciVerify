"""Proposal intent only; existing attribution/ownership policy stays unchanged."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.researchguard.adapters.claim_llm import ClaimLLMError, PROMPT_VERSION
from app.researchguard.domain import AtomicClaim, AttributionStatus, ClaimExtractionResult, ParsedManuscript
from app.schemas.claim_extraction import ClaimProposal
from app.services.citation_context import build_contexts
from app.services.claim_attribution import validate_proposal, ProposalRejected
from app.tests.test_claim_extractor import FakeProvider, adapter, run
from app.tests.test_citation_context import manuscript, request_payload


def candidate(intent="cited", labels=("12",), text="A factual proposition", quote=None):
    return {"text":text,"evidence_quote":quote or text,"attribution_intent":intent,"citation_labels":list(labels)}


@pytest.mark.parametrize("intent,labels", [("cited",("12",)),("none",()),("uncertain",())])
def test_valid_intent_label_combinations(intent, labels):
    result=ClaimProposal.model_validate(candidate(intent,labels))
    assert result.attribution_intent == intent and result.citation_labels == labels


@pytest.mark.parametrize("intent,labels", [("cited",()),("none",("12",)),("uncertain",("12",)),("maybe",())])
def test_invalid_intent_label_combinations(intent, labels):
    with pytest.raises(ValidationError):
        ClaimProposal.model_validate(candidate(intent,labels))


@pytest.mark.parametrize("missing", ["text","evidence_quote","attribution_intent","citation_labels"])
def test_all_fields_required_without_legacy_inference(missing):
    data=candidate(); data.pop(missing)
    with pytest.raises(ValidationError):
        ClaimProposal.model_validate(data)


@pytest.mark.parametrize("extra", ["subject","predicate","qualifier","shared_subject","reasoning","confidence","verdict","reference_ids","callout_ids","offsets","DOI"])
def test_no_extra_authority_fields(extra):
    with pytest.raises(ValidationError):
        ClaimProposal.model_validate({**candidate(),extra:"untrusted"})


@pytest.mark.parametrize("label", ["c1","99","r3","callout:0"])
def test_cited_invented_or_synthetic_labels_still_rejected(label):
    parsed=manuscript(); context=build_contexts(parsed)[0].context
    with pytest.raises(ProposalRejected) as exc:
        validate_proposal(parsed,context,ClaimProposal.model_validate(candidate(labels=(label,),text="A improves accuracy")))
    assert exc.value.code == "UNKNOWN_CITATION_CALLOUT"


def test_none_is_grounded_excluded_and_not_passed_to_attribution(monkeypatch):
    forbidden=Mock(side_effect=AssertionError("none must not derive references"))
    monkeypatch.setattr("app.services.claim_extractor.validate_proposal",forbidden)
    provider=FakeProvider(lambda _: {"claims":[candidate("none",(),"A improves accuracy")]})
    result=run(manuscript(),provider=provider)
    assert result.status == "completed" and not result.claims
    context=result.context_results[0]
    assert context.status == "completed" and not context.rejected_proposals and not context.accepted_claim_ids
    assert [(d.code,d.severity) for d in context.diagnostics] == [("NO_EXTERNAL_ATTRIBUTION","info")]
    assert "Proposition 1" in context.diagnostics[0].safe_message
    assert "AMBIGUOUS_CITATION_SCOPE" not in result.model_dump_json()
    forbidden.assert_not_called()


def test_uncertain_uses_existing_ambiguous_path_without_reference_links():
    result=run(manuscript(),provider=FakeProvider(lambda _: {"claims":[candidate("uncertain",(),"A improves accuracy")]}))
    assert result.status == "partial" and len(result.claims) == 1
    claim=result.claims[0]
    assert claim.attribution_status == "ambiguous" and not claim.reference_ids and not claim.citation_callout_ids
    assert {d.code for d in result.diagnostics} == {"AMBIGUOUS_CITATION_SCOPE"}


@pytest.mark.parametrize("quote,reason", [("Other text","QUOTE_NOT_FOUND"),("[3]","CITATION_MARKER_AS_SOURCE")])
def test_none_does_not_bypass_focal_grounding(quote,reason):
    result=run(manuscript(),provider=FakeProvider(lambda _: {"claims":[candidate("none",(),"Own fact",quote)]}))
    assert result.status == "failed" and not result.claims
    assert result.context_results[0].rejected_proposals[0].reason_code == reason


def test_none_repeated_and_neighbor_quotes_still_rejected():
    repeated=manuscript("A improves accuracy and A improves accuracy [3].")
    result=run(repeated,provider=FakeProvider(lambda _: {"claims":[candidate("none",(),"A improves accuracy")]}))
    assert result.context_results[0].rejected_proposals[0].reason_code == "QUOTE_AMBIGUOUS"
    first="Background information."
    parsed=manuscript(first+" A improves accuracy [3].",[(0,len(first)),(len(first)+1,len(first)+25)])
    result=run(parsed,provider=FakeProvider(lambda _: {"claims":[candidate("none",(),"Own fact",first)]}))
    assert result.context_results[0].rejected_proposals[0].reason_code == "QUOTE_NOT_FOUND"


def test_mixed_intents_keep_only_cited_and_uncertain_without_false_failure():
    data=[candidate("none",(),"A improves accuracy"),candidate("cited",("3",),"A improves accuracy"),candidate("uncertain",(),"A improves accuracy")]
    result=run(manuscript(),provider=FakeProvider(lambda _: {"claims":data}))
    assert [c.attribution_status.value for c in result.claims] == ["resolved","ambiguous"]
    assert result.claims[0].reference_ids == ("r3",) and not result.claims[1].reference_ids
    assert result.status == "partial" and len(result.context_results[0].accepted_claim_ids) == 2


def test_none_with_invalid_grounding_is_not_misreported_as_empty_success():
    data=[candidate("none",(),"A improves accuracy"),candidate("none",(),"Own fact","not in focal")]
    result=run(manuscript(),provider=FakeProvider(lambda _: {"claims":data}))
    assert result.status == "failed" and not result.claims
    assert result.context_results[0].rejected_proposals[0].proposal_index == 1


@pytest.mark.parametrize("intent,labels", [("cited",()),("none",("3",)),("uncertain",("3",)),("maybe",())])
def test_adapter_rejects_inconsistent_typed_response_without_repair(intent,labels):
    with pytest.raises(ClaimLLMError) as exc:
        adapter(FakeProvider(lambda _: {"claims":[candidate(intent,labels,"A improves accuracy")]}))
    assert exc.value.code == "EXTRACTION_INVALID_RESPONSE"


def test_adapter_revalidates_copied_models_and_requires_intent():
    from app.schemas.claim_extraction import ExtractionProposal
    valid=ExtractionProposal.model_validate({"claims":[candidate("cited",("3",),"A improves accuracy")]})
    class Forged(FakeProvider):
        def generate(self,*args,**kwargs):
            return valid.model_copy(update={"claims":(valid.claims[0].model_copy(update={"attribution_intent":"none"}),)})
    with pytest.raises(ClaimLLMError) as exc:
        adapter(Forged())
    assert exc.value.code == "EXTRACTION_INVALID_RESPONSE"
    data=candidate("cited",("3",),"A improves accuracy"); data.pop("attribution_intent")
    with pytest.raises(ClaimLLMError):
        adapter(FakeProvider(lambda _: {"claims":[data]}))


def test_prompt_and_schema_explain_attribution_not_just_fact_verifiability():
    provider=FakeProvider(); adapter(provider)
    system=provider.systems[0]; schema=provider.prompts[0]["output_schema"]["$defs"]["ClaimProposal"]
    assert set(schema["required"]) == {"text","evidence_quote","attribution_intent","citation_labels"}
    assert schema["properties"]["attribution_intent"]["enum"] == ["cited","none","uncertain"]
    assert schema["additionalProperties"] is False
    for phrase in ["citation-backed facts", "manuscript-own facts", "Being in a citation sentence does not imply",
                   'Use attribution_intent="none"', 'Use attribution_intent="uncertain"',
                   "Do not use uncertain merely because", "Do not use none when you are unsure",
                   "Neighbors are read-only", "Use visible citation labels", "Do not invent labels",
                   "uncertainty and reporting framing", "preliminary evidence", "chain-of-thought",
                   '"attribution_intent": "none", "citation_labels": []',
                   '"attribution_intent": "cited", "citation_labels": ["12"]']:
        assert phrase in system
    assert "rate/incidence of severe fatigue" in system and "do not turn preliminary evidence into proof" in system
    assert PROMPT_VERSION == "focal-atomic-semantic-ownership-v7"


def test_fatigue_intents_are_routed_without_downstream_domain_changes():
    own="Severe fatigue was observed in approximately 4% of BNT162b2 recipients"
    comparison="which is higher than that observed in recipients of some vaccines recommended for older adults"
    parsed=manuscript(own+", "+comparison+" [12].")
    data=[candidate("none",(),own+".",own),candidate("cited",("12",),"The rate of severe fatigue in BNT162b2 recipients was higher than that in recipients of some vaccines recommended for older adults.",comparison)]
    result=run(parsed,provider=FakeProvider(lambda _: {"claims":data}))
    assert result.status == "completed" and len(result.claims) == 1
    assert result.claims[0].reference_ids == ("r12",) and "rate of severe fatigue" in result.claims[0].text
    assert [d.code for d in result.diagnostics] == ["NO_EXTERNAL_ATTRIBUTION"]
    assert "attribution_intent" not in AtomicClaim.model_fields
    assert set(AttributionStatus) == {AttributionStatus.RESOLVED,AttributionStatus.AMBIGUOUS,AttributionStatus.UNRESOLVED}


def test_extraction_http_contract_does_not_require_new_client_fields():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.routes.manuscripts import get_extraction_provider_factory
    provider=FakeProvider(lambda _: {"claims":[candidate("none",(),"A improves accuracy")]})
    app.dependency_overrides[get_extraction_provider_factory]=lambda:lambda:provider
    try:
        with TestClient(app) as client:
            response=client.post("/api/manuscripts/extract-claims",json=request_payload(manuscript()))
        assert response.status_code == 200 and response.json()["status"] == "completed" and response.json()["claims"] == []
        assert response.json()["diagnostics"][0]["code"] == "NO_EXTERNAL_ATTRIBUTION"
        assert "attribution_intent" not in response.json()
    finally:
        app.dependency_overrides.pop(get_extraction_provider_factory,None)


def test_frozen_pre_fix_whole_paper_payload_remains_compatible():
    from app.services.manuscript_verification import validate_combined_input
    path=Path(__file__).resolve().parents[3]/"frontend/tests/fixtures/manuscript.json"
    saved=json.loads(path.read_text(encoding="utf-8"))["job_request"]
    validate_combined_input(ParsedManuscript.model_validate(saved["parsed"]),ClaimExtractionResult.model_validate(saved["extraction"]))
