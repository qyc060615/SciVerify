"""Shared scientific judgment policy; no change to agent response schemas."""

SCIENTIFIC_VERDICT_POLICY = """
Judge the core scientific meaning in normal academic writing, not word-for-word overlap.
SUPPORTS: accept faithful paraphrases, reasonable summaries, synonyms, approximate numbers
and rounding (e.g. 94.8% to approximately 95%), and omissions of noncritical conditions.
OVERSTATED: use only for a material expansion of population, scope, magnitude or causality
that would change a reader's understanding; ordinary simplification is not overstatement.
CONTRADICTS: require an explicit substantive incompatibility for the same study, entity,
outcome and statistical basis. Missing support, incomplete excerpts, a possible objection,
minor wording differences and different experimental conditions are not contradictions.
INSUFFICIENT: use when relevant evidence cannot settle the core claim; do not use merely
because a supported claim is expressed differently. Do not promote absence to support.
FABRICATED: require positive, compelling evidence of invented facts/data/study descriptions;
retrieval failure or lack of a matching statement does not establish fabrication.
Resolve pronouns and temporal expressions using the manuscript context when supplied.
The manuscript is the time reference for its 'previously' or 'earlier study'; the cited
paper can itself be that earlier report. A source's own 'previously' has a different
reference point. Do not require the cited report to describe its own findings as earlier
than itself. For 'subsequent', 'before publication' and 'after publication', identify both
events before comparing. Never invent publication dates; if chronology is essential but
unknown, acknowledge uncertainty. Manuscript context interprets the claim; it is not
independent supporting evidence. Source identity/version warnings concern provenance,
not scientific counterevidence. Use original chunk text, not agent confidence or stance,
to decide. Agreement among agents does not prove correctness.
Before comparing endpoint names, resolve their operational definitions in the original
paragraph and evidence: the clinical state/event, time horizon, population, direction and
mathematical quantity. Different names can describe the same estimand. For example, when
the undesirable state is receiving hospital care, time alive outside that state may be
called event-free time in the manuscript and time in recovery in the source. Equivalent
state definitions and the same area under the same curve support a paraphrase, not a
contradiction based on terminology alone. Never assume equivalence from names: time until
recovery, time spent recovered, and overall survival can be different quantities. If the
supplied definitions do not settle equivalence, acknowledge uncertainty. The paragraph
helps define the claim but does not itself establish a source finding.
For CONTRADICTS or FABRICATED, put at least one verbatim source excerpt in double quotes
in reasoning, cite its chunk in contradicting_evidence, and explain which core assertion
it rules out and why both refer to the same entity, conditions and time frame. A chunk ID
or a quote alone is not proof of conflict. If that relationship cannot be established,
return INSUFFICIENT. Confidence must reflect evidence strength and unresolved ambiguity.
""".strip()
