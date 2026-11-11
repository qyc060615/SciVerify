"""Bounded, positive-only decomposition of explicit named citation structures.

Parents retain their original ID/status. Only individual claims get source pairs;
decomposition is an attribution relation, never a scientific support verdict.
"""
import hashlib
import json
import re

from app.researchguard.domain import AttributionStatus, CitationResolutionStatus, TextSpan, ManuscriptDiagnostic

_NAME = r'[A-Za-z][A-Za-z0-9_./-]{0,79}'


def _normal(text):
    return re.sub(r'\s+', ' ', text).strip().rstrip('.').casefold()


def _named_pair(parsed, context, prefix):
    """Read names next to their own callouts; never map a group by list order."""
    calls = {c.id: c for c in parsed.citation_callouts}
    local = [calls[cid] for cid in context.citation_callout_ids]
    if (context.scope_kind != 'sentence' or len(local) != 2
            or any(c.resolution_status != CitationResolutionStatus.RESOLVED
                   or len(c.reference_ids) != 1 for c in local)
            or local[0].reference_ids == local[1].reference_ids):
        return None
    text = next(p.text for p in parsed.paragraphs if p.id == context.paragraph_id)
    a, b = local
    head = text[context.focal_span.start:a.span.start]
    first = re.fullmatch(prefix + rf'(?P<name>{_NAME})\s*', head, re.I)
    second = re.fullmatch(rf'\s+and\s+(?P<name>{_NAME})\s*', text[a.span.end:b.span.start], re.I)
    if not first or not second or first['name'].casefold() == second['name'].casefold():
        return None
    return text, ((first['name'], a), (second['name'], b)), text[b.span.end:context.focal_span.end]


def recover_context(parsed, context, claims):
    """Keep all old claims; add explicit individual claims or link existing ones."""
    result, notes = list(claims), []
    reporting = _named_pair(parsed, context, r'\s*(?:For (?:instance|example),\s*)?in\s+')
    for index, parent in enumerate(claims):
        if parent.attribution_status != AttributionStatus.AMBIGUOUS:
            continue
        children = []
        if reporting:
            _, owners, tail = reporting
            match = re.fullmatch(r'\s*,\s*it is (?:stated|reported) that they (?P<predicate>[^.!?;\n]+)\.?\s*', tail, re.I)
            if (match and not re.search(r'\b(?:while|whereas|but|respectively)\b', match['predicate'], re.I)
                    and _normal(parent.text) == _normal(f'{owners[0][0]} and {owners[1][0]} {match["predicate"]}')):
                for name, call in owners:
                    text = f'{name} {match["predicate"].strip().rstrip(".")}.'
                    span = TextSpan(start=context.focal_span.start, end=context.focal_span.end)
                    key = json.dumps(['named-reporting-v1', parent.id, text, call.id])
                    child = parent.model_copy(update=dict(id='claim:' + hashlib.sha256(key.encode()).hexdigest(),
                        text=text, citation_callout_ids=(call.id,), reference_ids=call.reference_ids,
                        source_spans=(span,), attribution_status=AttributionStatus.RESOLVED, decomposed_into=()))
                    children.append(child.id)
                    if child.id not in {c.id for c in result}:
                        result.append(child)
                    else:
                        # Rebuild canonical children during graph validation too;
                        # a forged payload cannot keep the ID and change numbers.
                        result[next(i for i, c in enumerate(result) if c.id == child.id)] = child
        if not children:
            generic = re.fullmatch(r'Several (?P<noun>[a-z -]+) have been developed to (?P<purpose>[^.!?;]+)\.?', parent.text, re.I)
            if generic:
                noun = generic['noun'].strip()
                singular = next((noun[:-len(plural)] + single for plural, single in
                    [('libraries', 'library'), ('tools', 'tool'), ('frameworks', 'framework')]
                    if noun.casefold().endswith(plural)), None)
                if singular:
                    prefix = r'\s*To ' + re.escape(generic['purpose'].rstrip('.')) + r',\s*several ' + re.escape(noun) + r' have been developed such as\s+'
                    pair = _named_pair(parsed, context, prefix)
                    if pair and re.fullmatch(r'\s*(?:\(now as [A-Za-z][A-Za-z0-9_./ -]*\))?\.?\s*', pair[2]):
                        for name, call in pair[1]:
                            expected = _normal(f'{name} is a {singular} developed to {generic["purpose"]}')
                            matches = [c for c in claims if c.attribution_status == AttributionStatus.RESOLVED
                                and not c.decomposed_into and c.citation_callout_ids == (call.id,)
                                and c.reference_ids == call.reference_ids and _normal(c.text) == expected]
                            if len(matches) != 1:
                                children = []
                                break
                            children.append(matches[0].id)
        if children:
            result[index] = parent.model_copy(update={'decomposed_into': tuple(children)})
            notes.append(ManuscriptDiagnostic(code='NAMED_CITATION_DECOMPOSED', entity_id=parent.id,
                severity='info', safe_message='Original statement retained; see its individual claims. This is not a support verdict.'))
    return tuple(result), tuple(notes)


def validate_decompositions(parsed, result):
    """Clients cannot hide arbitrary gaps by supplying made-up child links."""
    for context in result.contexts:
        claims = tuple(c for c in result.claims if c.context_id == context.id)
        linked = [c for c in claims if c.decomposed_into]
        if not linked:
            continue
        actual = {c.id: c for c in claims}
        # Rebuild without trusting supplied links, including nonmatching parents.
        bare = tuple(c.model_copy(update={'decomposed_into': ()}) for c in claims)
        rebuilt, _ = recover_context(parsed, context, bare)
        rebuilt = {c.id: c for c in rebuilt}
        for parent in linked:
            if (len(set(parent.decomposed_into)) != len(parent.decomposed_into)
                    or parent.decomposed_into != rebuilt[parent.id].decomposed_into):
                raise ValueError('Invalid claim decomposition')
            for cid in parent.decomposed_into:
                if cid not in actual or actual[cid] != rebuilt.get(cid):
                    raise ValueError('Invalid decomposition member')
