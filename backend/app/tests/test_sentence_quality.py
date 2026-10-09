"""Bounded text-quality isolation; real failure literals are test data only."""
import asyncio

import pytest

from app.researchguard.adapters.grobid_tei import parse_tei
from app.services.citation_context import build_contexts
from app.services.claim_attribution import ProposalRejected, validate_proposal
from app.services.claim_extractor import extract_claims
from app.schemas.claim_extraction import ClaimProposal, SourceQuote
from app.tests.test_claim_extractor import FakeProvider
from app.tests.test_grobid_tei import MANUSCRIPT, bibliography, tei


def parsed_body(body):
    return parse_tei(tei('<div><head>Results</head>' + body + '</div>',
                        bibliography(('b1', 'Study one'), ('b2', 'Study two'))), MANUSCRIPT)


def assert_offsets(parsed):
    paragraphs = {p.id: p for p in parsed.paragraphs}
    for call in parsed.citation_callouts:
        assert paragraphs[call.paragraph_id].text[call.span.start:call.span.end] == call.text
    for p in parsed.paragraphs:
        assert all(0 <= s.start < s.end <= len(p.text) for s in p.sentence_spans)
        assert all(a.end <= b.start for a, b in zip(p.sentence_spans, p.sentence_spans[1:]))
    for plan in build_contexts(parsed):
        c = plan.context
        assert c.text == paragraphs[c.paragraph_id].text[c.span.start:c.span.end]
        assert all(c.focal_span.start <= call.span.start < call.span.end <= c.focal_span.end
                   for call in parsed.citation_callouts if call.id in c.citation_callout_ids)


@pytest.mark.parametrize('prefix', [
    'n engl j med nejm.org 2 T h e ne w e ngl a nd jou r na l o f m e dicine C oronavirus ',
    'a research review sample.org 9 R e v i e w A bnormal ',
])
def test_gr1_generic_contamination_is_skipped_without_provider(prefix):
    parsed = parsed_body('<p><s>' + prefix + 'affected many people '
        '<ref type="bibr" target="#b1">1</ref> during 2020. '
        '<ref type="bibr" target="#b2">2</ref> Older adults face higher risks.</s></p>')
    plan = build_contexts(parsed)[0]
    assert plan.skip_code == 'SKIPPED_UNRELIABLE_TEXT'
    def forbidden():
        pytest.fail('Contaminated focal must not initialize a provider')
    result = asyncio.run(extract_claims(parsed, provider_factory=forbidden))
    assert result.status == 'skipped' and not result.claims
    assert {d.code for d in result.diagnostics} == {'SKIPPED_UNRELIABLE_TEXT'}
    assert_offsets(parsed)


@pytest.mark.parametrize('stem,tail', [('incuba', 'tion'), ('assess', 'ment')])
def test_gr2_nonadjacent_continuation_is_isolated_not_joined(stem, tail):
    parsed = parsed_body(f'<p><s>A response followed the estimated {stem}-</s></p>'
        '<p><s>Table values and unrelated layout material.</s></p>'
        '<p><s>Copyright 2020. All rights reserved.</s></p>'
        f'<p><s>{tail} period of 5 days, <ref type="bibr" target="#b1">10</ref> '
        'indicating an early protective effect.</s>'
        '<s>A improves accuracy <ref type="bibr" target="#b2">11</ref>.</s></p>')
    before = tuple(p.text for p in parsed.paragraphs)
    plans = build_contexts(parsed)
    assert [p.skip_code for p in plans] == ['SKIPPED_INCOMPLETE_TEXT', None]
    assert 'LAYOUT_METADATA_INSUFFICIENT' in {d.code for d in plans[0].diagnostics}
    provider = FakeProvider(lambda payload: {'claims': []})
    result = asyncio.run(extract_claims(parsed, provider=provider))
    assert len(provider.prompts) == 1
    assert provider.prompts[0]['focal_text'].startswith('A improves accuracy')
    assert result.context_results[0].status == 'skipped'
    assert tuple(p.text for p in parsed.paragraphs) == before
    assert_offsets(parsed)


def test_gr3_gr4_normal_sentences_and_grouped_ownership_survive():
    parsed = parsed_body('<p><s>Recent data show increasing rates among younger adults.</s>'
        '<s><ref type="bibr" target="#b1">3</ref> The favorable safety profile '
        '<ref type="bibr" target="#b1">4,</ref><ref type="bibr" target="#b2">8</ref> '
        'was confirmed in phase 2/3.</s></p>')
    plans = build_contexts(parsed)
    assert [p.skip_code for p in plans] == [None, None]
    assert [tuple(c.text for c in parsed.citation_callouts if c.id in p.context.citation_callout_ids)
            for p in plans] == [('3',), ('4,', '8')]
    assert plans[0].context.scope_kind == 'trailing_marker'
    assert_offsets(parsed)


def test_gr5_correct_neighbor_remains_read_only():
    parsed = parsed_body('<p><s>A improves accuracy <ref type="bibr" target="#b1">1</ref>.</s>'
                         '<s>Older adults face higher risks.</s></p>')
    plan = build_contexts(parsed)[0]
    assert plan.skip_code is None and 'Older adults' in plan.context.text
    p = parsed.paragraphs[0]
    assert 'Older adults' not in p.text[plan.context.focal_span.start:plan.context.focal_span.end]
    q = ClaimProposal(text='Older adults face higher risks',
        source_quotes=(SourceQuote(quote='Older adults face higher risks'),),
        citation_callout_ids=plan.context.citation_callout_ids)
    with pytest.raises(ProposalRejected) as e:
        validate_proposal(parsed, plan.context, q)
    assert e.value.code == 'QUOTE_NOT_FOUND'


def test_gr6_multiple_prose_sentences_in_one_s_are_not_trusted():
    parsed = parsed_body('<p><s>A improves accuracy <ref type="bibr" target="#b1">1</ref>. '
                         'Older adults face higher risks.</s></p>')
    assert build_contexts(parsed)[0].skip_code == 'SKIPPED_UNRELIABLE_TEXT'


def test_gr7_sentence_separator_is_emitted_before_offsets():
    parsed = parsed_body('<p><s>A improves accuracy <ref type="bibr" target="#b1">1</ref>.</s>'
                         '<s>β cells respond <ref type="bibr" target="#b2">2</ref>.</s></p>')
    assert parsed.paragraphs[0].text == 'A improves accuracy 1. β cells respond 2.'
    assert parsed.paragraphs[0].sentence_spans[1].start == len('A improves accuracy 1. ')
    assert_offsets(parsed)


@pytest.mark.parametrize('opening', [
    '30% of participants', 'SARS-CoV-2', 'BNT162b2', 'p53', 'miR-21', 'akt',
    '(A)', '“A”', 'Smith et al.', 'Dr. Smith', 'U.S. studies', 'Fig. 2',
])
@pytest.mark.parametrize('marker', ['[1]', '1'])
def test_normal_scientific_openings_are_preserved(opening, marker):
    parsed = parsed_body('<p><s>A prior phrase ends in an uninterpreted regula-</s></p>'
        f'<p><s>{opening} showed an improved response '
        f'<ref type="bibr" target="#b1">{marker}</ref>.</s></p>')
    assert build_contexts(parsed)[0].skip_code is None
    assert_offsets(parsed)


def test_decimal_and_reporting_abbreviations_are_not_sentence_boundaries():
    parsed = parsed_body('<p><s>Smith et al. observed 98.6% efficacy '
                         '<ref type="bibr" target="#b1">1</ref>.</s></p>')
    assert build_contexts(parsed)[0].skip_code is None


def test_broken_ending_and_generic_boilerplate_are_isolated():
    for text in ['A response followed the estimated regula-',
                 'Downloaded from example.org at Research University.',
                 'Copyright © 2020 Example Publisher.']:
        parsed = parsed_body('<p><s>' + text + '<ref type="bibr" target="#b1">1</ref></s></p>')
        assert build_contexts(parsed)[0].skip_code in {'SKIPPED_INCOMPLETE_TEXT', 'SKIPPED_UNRELIABLE_TEXT'}
