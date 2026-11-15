from unittest.mock import Mock
from app.services.report_editor import EvidenceDigest, simplify_report
from app.services.report_export import ReportExportRequest

def test_empty_evidence_is_not_a_failed_export(monkeypatch):
    provider = Mock()
    provider.generate.return_value = EvidenceDigest(summary='No relevant evidence was found.', supporting_quotes=[])
    monkeypatch.setattr('app.services.report_editor.get_llm_provider', lambda: provider)
    report = ReportExportRequest(format='pdf', title='Test', blocks=[
        {'kind':'pagebreak'}, {'kind':'heading','text':'Claim 01'},
        {'kind':'quote','text':'Claim text'}, {'kind':'subheading','text':'Reference 1: Paper'},
        {'kind':'body','text':'Confidence: 62%'}, {'kind':'quote','text':'An unrelated passage in the reference.'},
        {'kind':'body','text':'URL: https://example.org/paper'}])
    output = simplify_report(report)
    text = ' '.join(b.text for b in output.blocks)
    assert 'No directly relevant passage' in text
    assert 'AI analysis' in text
    assert 'not a finding that the claim is incorrect' in text
    assert 'Confidence: 62%' in text
    assert 'URL: https://example.org/paper' in text
    assert 'An unrelated passage' not in text
