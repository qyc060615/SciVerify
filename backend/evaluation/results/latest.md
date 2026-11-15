SciVerify Evaluation
====================

Cases: 30
Verdict Accuracy: 100.0%

Per-Verdict Accuracy:
- CONTRADICTS: 100.0%
- FABRICATED: 100.0%
- INSUFFICIENT: 100.0%
- OVERSTATED: 100.0%
- SUPPORTS: 100.0%

Evidence:
- Average evidence count: 0.9
- Average relevance: 0.61
- Average claim overlap: 0.55
- Duplicate rate: 0.0%
- Evidence coverage rate: 56.7%

Traceability:
- Completeness: 96.7%
- Coverage: 48.9%
- Link rate: 41.7%
- Supported segments: 22.9%
- Partial segments: 17.1%
- Unsupported segments: 42.9%
- Contradicted segments: 17.1%

Validation:
- Override rate: 0.0%
- Warning rate: 10.0%

Agent Agreement:
- Agreement: 85.7%

Confidence:
- Correct verdict avg: 0.70
- Incorrect verdict avg: n/a
- Average confidence error: 0.30
- Confidence risk rate: 3.3%

Robustness:
- Unsupported-claim detection: 100.0%

Failure analysis:
- Weak Evidence: 6
- Poor Traceability: 13
- Overconfident: 1
- Agent Disagreement: 4

Worst-performing cases:
- safety_contradicts_003: expected=CONTRADICTS, actual=CONTRADICTS, confidence=0.84, evidence_coverage=100.0%, traceability_coverage=81.0%, failures=[AGENT_DISAGREEMENT]
- conclusion_reversal_003: expected=CONTRADICTS, actual=CONTRADICTS, confidence=0.83, evidence_coverage=100.0%, traceability_coverage=80.0%, failures=[AGENT_DISAGREEMENT]
- legacy_no_traceability_001: expected=SUPPORTS, actual=SUPPORTS, confidence=0.82, evidence_coverage=0.0%, traceability_coverage=n/a, failures=[OVERCONFIDENT]
- mortality_contradicts_001: expected=CONTRADICTS, actual=CONTRADICTS, confidence=0.81, evidence_coverage=100.0%, traceability_coverage=79.0%, failures=[AGENT_DISAGREEMENT]
- accuracy_overstated_001: expected=OVERSTATED, actual=OVERSTATED, confidence=0.78, evidence_coverage=100.0%, traceability_coverage=62.0%, failures=[AGENT_DISAGREEMENT]
- multi_assertion_one_supported_003: expected=OVERSTATED, actual=OVERSTATED, confidence=0.77, evidence_coverage=50.0%, traceability_coverage=38.0%, failures=[POOR_TRACEABILITY]
- universal_overstated_001: expected=OVERSTATED, actual=OVERSTATED, confidence=0.76, evidence_coverage=50.0%, traceability_coverage=35.0%, failures=[POOR_TRACEABILITY]
- always_eliminates_003: expected=OVERSTATED, actual=OVERSTATED, confidence=0.74, evidence_coverage=50.0%, traceability_coverage=35.0%, failures=[POOR_TRACEABILITY]
- fabricated_claim_001: expected=FABRICATED, actual=FABRICATED, confidence=0.72, evidence_coverage=0.0%, traceability_coverage=5.0%, failures=[POOR_TRACEABILITY]
- not_in_paper_003: expected=FABRICATED, actual=FABRICATED, confidence=0.70, evidence_coverage=0.0%, traceability_coverage=4.0%, failures=[POOR_TRACEABILITY]

Regression:
PASS

Confusion matrix:
- SUPPORTS -> SUPPORTS: 7
- OVERSTATED -> OVERSTATED: 7
- CONTRADICTS -> CONTRADICTS: 6
- INSUFFICIENT -> INSUFFICIENT: 6
- FABRICATED -> FABRICATED: 4