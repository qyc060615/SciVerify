"""Explicit named owners only; no guessed collective support or fabricated verdicts."""
import pytest

from app.services.claim_attribution import validate_result
from app.services.claim_decomposition import recover_context
from app.services.citation_context import build_contexts
from app.services.manuscript_verification import plan_manuscript_pairs
from app.tests.test_citation_context import manuscript
from app.tests.test_claim_attribution import check, proposal
from app.tests.test_claim_extractor import FakeProvider, run


REPORT = 'For instance, in Alpha [3] and Beta [4], it is stated that they used 8 GPUs.'
CLAIM = 'Alpha and Beta used 8 GPUs.'
QUOTE = 'they used 8 GPUs'
COLLECTIVE = 'To ease metric use, several hands-on libraries have been developed such as alpha [3] and beta [4].'
GENERAL = 'Several hands-on libraries have been developed to ease metric use.'


def response(text=CLAIM, quote=QUOTE):
    return {'claims': [dict(text=text, evidence_quote=quote,
        attribution_intent='cited', citation_labels=['3', '4'])]}


def test_reporting_keeps_parent_and_separates_owners_and_numbers():
    parsed = manuscript(REPORT)
    old = check(parsed, proposal(CLAIM, QUOTE, ('3', '4')))
    result = run(parsed, provider=FakeProvider(lambda _: response()))
    parent, a, b = result.claims
    assert parent.id == old.id and parent.text == old.text
    assert parent.attribution_status == 'ambiguous' and parent.decomposed_into == (a.id, b.id)
    assert [a.text, b.text] == ['Alpha used 8 GPUs.', 'Beta used 8 GPUs.']
    assert a.reference_ids == ('r3',) and b.reference_ids == ('r4',)
    assert result.status == 'completed'
    plan, blocked = plan_manuscript_pairs(parsed, result)
    assert not blocked and [c.id for c, _, _ in plan] == [a.id, b.id]
    assert all(len(c.source_spans) == 1 for c in (a, b))
    assert result == run(parsed, provider=FakeProvider(lambda _: response()))


@pytest.mark.parametrize('text,claim', [
    (REPORT, 'Alpha and Gamma used 8 GPUs.'),
    (REPORT, 'Alpha and Beta used 80 GPUs.'),
    (REPORT.replace('it is stated that they', 'we'), CLAIM),
    (REPORT.replace('used 8 GPUs', 'used 8 GPUs but we used 4'), CLAIM),
    (REPORT.replace(' and Beta [4]', ', while Beta [4]'), CLAIM),
    (REPORT.replace('Beta [4]', 'Beta [3]'), CLAIM),
])
def test_reporting_does_not_recover_wrong_owner_number_or_competing_clause(text, claim):
    parsed = manuscript(text)
    context = build_contexts(parsed)[0].context
    # Structural replay does not need to trust a model-selected citation group.
    old = check(manuscript(REPORT), proposal(claim, QUOTE, ('3', '4')))
    recovered, _ = recover_context(parsed, context, (old,))
    assert recovered == (old,)


def collective_response(modify=None):
    claims = [dict(text=GENERAL, evidence_quote='To ease metric use, several hands-on libraries have been developed',
        attribution_intent='uncertain', citation_labels=[])]
    for name, label in [('alpha', '3'), ('beta', '4')]:
        claims.append(dict(text=f'{name} is a hands-on library developed to ease metric use.',
            evidence_quote=COLLECTIVE, attribution_intent='cited', citation_labels=[label]))
    if modify:
        modify(claims)
    return {'claims': claims}


def test_collective_links_existing_members_without_extra_pairs_or_verdict():
    parsed = manuscript(COLLECTIVE)
    provider = FakeProvider(lambda _: collective_response())
    result = run(parsed, provider=provider)
    parent, a, b = result.claims
    assert parent.decomposed_into == (a.id, b.id)
    assert parent.attribution_status == 'ambiguous' and not parent.reference_ids
    assert a == check(parsed, proposal(a.text, COLLECTIVE, ('3',)))
    assert b == check(parsed, proposal(b.text, COLLECTIVE, ('4',)))
    plan, blocked = plan_manuscript_pairs(parsed, result)
    assert not blocked and len(plan) == 2 and result.status == 'completed'
    assert len(provider.prompts) == 1


@pytest.mark.parametrize('change', ['missing', 'wrong_purpose', 'wrong_reference', 'uncertain_member'])
def test_collective_requires_both_exact_resolved_members(change):
    def modify(claims):
        if change == 'missing': claims.pop()
        if change == 'wrong_purpose': claims[2]['text'] = 'beta is a hands-on library developed to predict disease.'
        if change == 'wrong_reference': claims[2]['citation_labels'] = ['3']
        if change == 'uncertain_member': claims[2].update(attribution_intent='uncertain', citation_labels=[])
    result = run(manuscript(COLLECTIVE), provider=FakeProvider(lambda _: collective_response(modify)))
    assert not result.claims[0].decomposed_into and result.status == 'partial'


@pytest.mark.parametrize('case', ['fallback', 'unresolved'])
def test_named_recovery_never_crosses_untrusted_or_unresolved_context(case):
    original = manuscript(REPORT)
    parent = check(original, proposal(CLAIM, QUOTE, ('3', '4')))
    parsed = manuscript(REPORT, statuses={1: 'unresolved'}) if case == 'unresolved' else original
    context = build_contexts(parsed)[0].context
    if case == 'fallback':
        context = context.model_copy(update={'scope_kind': 'paragraph_fallback'})
    recovered, _ = recover_context(parsed, context, (parent,))
    assert recovered == (parent,)


@pytest.mark.parametrize('forgery', ['self', 'missing', 'swapped', 'wrong_member', 'resolved_parent'])
def test_client_cannot_hide_gaps_with_forged_decomposition(forgery):
    parsed = manuscript(REPORT)
    result = run(parsed, provider=FakeProvider(lambda _: response()))
    parent, a, b = result.claims
    if forgery == 'self': parent = parent.model_copy(update={'decomposed_into': (parent.id,)})
    if forgery == 'missing': parent = parent.model_copy(update={'decomposed_into': ('unknown',)})
    if forgery == 'swapped': parent = parent.model_copy(update={'decomposed_into': (b.id, a.id)})
    if forgery == 'wrong_member': a = a.model_copy(update={'text': 'Alpha used 80 GPUs.'})
    if forgery == 'resolved_parent': parent = parent.model_copy(update={'attribution_status': 'resolved'})
    with pytest.raises(ValueError):
        validate_result(parsed, result.model_copy(update={'claims': (parent, a, b)}))


@pytest.mark.parametrize('labels', [('3', '4'), ('3',), ()])
def test_already_split_reporting_recovers_each_named_owner(labels):
    parsed = manuscript(REPORT)
    proposals = [dict(text=f'{name} used 8 GPUs.', evidence_quote=REPORT,
        attribution_intent='cited' if labels else 'uncertain', citation_labels=list(labels))
        for name in ['Alpha', 'Beta']]
    result = run(parsed, provider=FakeProvider(lambda _: {'claims': proposals}))
    assert result.status == 'completed'
    assert len(result.claims) == 2
    for claim, ref in zip(result.claims, ['r3', 'r4']):
        assert claim.attribution_status == 'resolved'
        assert claim.reference_ids == (ref,) and not claim.decomposed_into
    plan, blocked = plan_manuscript_pairs(parsed, result)
    assert not blocked and len(plan) == 2
    validate_result(parsed, result)
    context = result.contexts[0]
    assert recover_context(parsed, context, result.claims)[0] == result.claims


@pytest.mark.parametrize('text,claim', [
    (REPORT, 'Gamma used 8 GPUs.'),
    (REPORT, 'Alpha used 80 GPUs.'),
    (REPORT, 'Alpha did not use 8 GPUs.'),
    (REPORT, 'Alpha used cost-effective GPUs.'),
    (REPORT.replace('it is stated that they', 'we'), 'Alpha used 8 GPUs.'),
    (REPORT.replace('used 8 GPUs', 'used 8 GPUs respectively'), 'Alpha used 8 GPUs respectively.'),
    (REPORT.replace(' and Beta [4]', ', while Beta [4]'), 'Alpha used 8 GPUs.'),
    (REPORT.replace('Beta [4]', 'Beta [3]'), 'Alpha used 8 GPUs.'),
])
def test_already_split_recovery_never_invents_owner_predicate_or_scope(text, claim):
    parsed = manuscript(text)
    context = build_contexts(parsed)[0].context
    original = check(manuscript(REPORT), proposal(claim, REPORT, ('3', '4')))
    assert original.attribution_status == 'ambiguous'
    assert recover_context(parsed, context, (original,))[0] == (original,)


@pytest.mark.parametrize('case', ['fallback', 'unresolved'])
def test_already_split_recovery_requires_trusted_resolved_context(case):
    parsed = manuscript(REPORT, statuses={1: 'unresolved'}) if case == 'unresolved' else manuscript(REPORT)
    context = build_contexts(parsed)[0].context
    if case == 'fallback':
        context = context.model_copy(update={'scope_kind': 'paragraph_fallback'})
    original = check(manuscript(REPORT), proposal('Alpha used 8 GPUs.', REPORT, ('3', '4')))
    assert recover_context(parsed, context, (original,))[0] == (original,)


@pytest.mark.parametrize('name,verb,gerund,rest', [
    ('Orion', 'trained', 'training', 'on 12 nodes'),
    ('Delta', 'applied', 'applying', 'a conditional threshold of 0.8'),
    ('Cedar', 'used', 'using', 'only 3 samples under low pressure'),
])
@pytest.mark.parametrize('frame', [
    '{name} is cited as {gerund} {rest}.',
    '{name} is stated to have {verb} {rest}.',
    'In the {name} paper, it is reported that {name} {verb} {rest}.',
    'It is stated in {name} [3] that {name} {verb} {rest}.',
])
def test_reporting_frames_generalize_without_domain_keywords(name, verb, gerund, rest, frame):
    text = f'In {name} [3] and Vega [4], it is stated that they {verb} {rest}.'
    claim = frame.format(name=name, verb=verb, gerund=gerund, rest=rest)
    result = run(manuscript(text), provider=FakeProvider(lambda _: response(claim, text)))
    assert result.status == 'completed'
    assert result.claims[0].text == claim
    assert result.claims[0].reference_ids == ('r3',)
    assert result.claims[0].attribution_status == 'resolved'


@pytest.mark.parametrize('claim', [
    'Alpha is proven to have used 8 GPUs.',
    'Alpha is cited as using 80 GPUs.',
    'Alpha is cited as not using 8 GPUs.',
    'Gamma is cited as using 8 GPUs.',
    'In the Beta paper, it is stated that Alpha used 8 GPUs.',
    'It is stated in Alpha [4] that Alpha used 8 GPUs.',
    'Alpha is cited as using 8 cost-effective GPUs.',
    'Alpha is cited as using GPUs.',
])
def test_reporting_frames_do_not_erase_substantive_differences(claim):
    result = run(manuscript(REPORT), provider=FakeProvider(lambda _: response(claim, REPORT)))
    assert result.claims[0].attribution_status == 'ambiguous'
    assert not result.claims[0].reference_ids
