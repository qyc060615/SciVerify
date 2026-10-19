"""One real C8 replay after a confirmed fix; no new Job, retrieval or embedding."""
from pathlib import Path
import sys,json,hashlib,asyncio
sys.stdout.reconfigure(encoding='utf-8')
# Observes genuine provider HTTP traffic using the same audit ledger.
import audit_server
from app.services.verification_job_store import LocalJobStore
from app.services.source_store import LocalSourceStore
from app.researchguard.adapters.sciverify import evidence_to_legacy
from app.schemas.evidence import EvidenceRetrievalResponse,EvidencePaperSummary
from app.services.verification_service import verify_prepared_evidence
from app.services.llm.provider import get_llm_provider
from app.utils.claim_preprocessor import preprocess_claim
OUT=Path(__file__).parent
ROOT=OUT.parents[1]
job_id=json.loads((OUT/'job-created.json').read_text(encoding='utf8'))['job_id']
job_path=ROOT/'backend/data/researchguard/jobs'/(job_id+'.json')
if (OUT/'targeted-c8-live-started.json').exists():raise RuntimeError('One targeted replay already initiated; do not duplicate it.')
snapshot=LocalJobStore().load(job_id)
claim=snapshot.extraction.claims[7]
task=next(t for t in snapshot.tasks if t.claim_id==claim.id)
reference=next(r for r in snapshot.parsed.references if r.id==task.reference_id)
context=next(c for c in snapshot.extraction.contexts if c.id==claim.context_id)
paragraph=next(p for p in snapshot.parsed.paragraphs if p.id==claim.paragraph_id)
artifact=LocalSourceStore().get(reference.doi)
assert artifact is not None
original_hash=hashlib.sha256(job_path.read_bytes()).hexdigest()
evidence=evidence_to_legacy(list(task.pair_outcome.verification.evidence_chunks),preprocess_claim(claim.text))
bridge=EvidenceRetrievalResponse(status='success',claim=claim.text,
    paper=EvidencePaperSummary(paper_id=task.source_binding.source_document_id,doi=reference.doi,title=artifact.paper.title),
    evidence=evidence,total_chunks_considered=0)
verification_context=json.dumps({'manuscript_title':snapshot.parsed.manuscript.title,
    'citation_context':context.text,'original_paragraph':paragraph.text,
    'cited_source_title':artifact.paper.title,'cited_source_year':artifact.paper.year},ensure_ascii=False)
(OUT/'targeted-c8-live-started.json').write_text(json.dumps({'job_id':job_id,'claim_id':claim.id,'reference_id':reference.id,
    'mode':'One real three-agent replay; reuse original selected evidence without retrieval or embedding',
    'job_sha256_before':original_hash,'verification_context':json.loads(verification_context)},ensure_ascii=False,indent=2),encoding='utf8')
provider=get_llm_provider()
provider.max_rate_limit_retries=1
result=asyncio.run(verify_prepared_evidence(claim.text,bridge,llm=provider,verification_context=verification_context))
assert hashlib.sha256(job_path.read_bytes()).hexdigest()==original_hash,'Formal Job changed during targeted replay'
(OUT/'targeted-c8-live-result.json').write_text(json.dumps({'mode':'REAL LLM, same original evidence, no new Job',
    'original_job_verdict':task.pair_outcome.verification.verdict.value,'original_job_confidence':task.pair_outcome.verification.confidence,
    'job_unchanged':True,'result':result.model_dump(mode='json')},ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'status':result.status.value,'verdict':result.verdict.value if result.verdict else None,'confidence':result.confidence,
    'reasoning':result.reasoning,'job_unchanged':True},ensure_ascii=False),flush=True)
