"""Real HTTP E2E driver. Stage files prevent duplicate paid extraction/job creation."""
import sys, json, hashlib, time, asyncio
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'backend'))
import httpx
BASE='http://127.0.0.1:8001'

def save(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')

def read(name):return json.loads((OUT/name).read_text(encoding='utf-8'))

def once(name,fn):
    if (OUT/name).exists():
        print('EXISTING '+name+'; no repeated request')
        return read(name)
    result=fn()
    save(name,result)
    return result

def request(path,payload=None,files=None,timeout=1800):
    started=time.monotonic()
    with httpx.Client(timeout=timeout,trust_env=False) as client:
        response=client.post(BASE+path,json=payload,files=files) if payload is not None or files else client.get(BASE+path)
    try:body=response.json()
    except Exception:body={'non_json':True}
    print(json.dumps({'path':path,'status':response.status_code,'elapsed_seconds':round(time.monotonic()-started,2)},ensure_ascii=False),flush=True)
    if response.status_code>=400:
        save('http-error-'+str(int(time.time()))+'.json',body)
        if not (isinstance(body,dict) and body.get('status') in {'failed','partial','skipped'} and 'contexts' in body):
            raise RuntimeError('HTTP stage failed: '+str(response.status_code))
    return body

def input_payload(response):
    return {k:response[k] for k in ['schema_version','scope','offset_unit','parsed']}

stage=sys.argv[1]
if stage=='preflight':
    from pypdf import PdfReader
    pdf=ROOT.parent/'main.pdf'
    content=pdf.read_bytes()
    pages=PdfReader(pdf)
    texts=[p.extract_text() or '' for p in pages.pages]
    title='Selecting appropriate endpoints for assessing treatment effects in comparative clinical studies for COVID-19'
    normalized=' '.join(' '.join(texts).split())
    assert title in normalized and '10.1016/j.cct.2020.106145' in normalized, 'PDF_CONTENT_MISMATCH'
    (OUT/'manuscript-text.txt').write_text('\n\n'.join(f'PAGE {i+1}\n'+t for i,t in enumerate(texts)),encoding='utf-8')
    save('pdf-validation.json',{'path':str(pdf),'size':len(content),'sha256':hashlib.sha256(content).hexdigest(),'pages':len(pages.pages),'title':title,'doi':'10.1016/j.cct.2020.106145','first_page':'Elsevier license cover','article_starts_page':2,'verified':True})
    protected={}
    for p in (ROOT/'backend/data').rglob('*'):
        if p.is_file():protected[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    for p in [ROOT/'backend/.env',ROOT/'.env',pdf]:
        if p.is_file():protected[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    save('integrity-before.json',protected)
    import app.config as c
    from importlib.metadata import version
    save('environment.json',{'python':sys.version,'python_executable':sys.executable,'paperqa2':version('paper-qa'),'fastapi':version('fastapi'),
         'grobid':request('/health'),'models':{'verifier':c.LLM_MODEL,'paperqa2':__import__('os').getenv('PAPERQA2_MODEL'),'embedding':__import__('os').getenv('PAPERQA2_EMBEDDING_MODEL')},
         'audit_backend_port':8001,'original_backend_port':8000,'request_budget':800,'paperqa_cache_size':16,'no_mock_providers':True})
    print(json.dumps(read('pdf-validation.json'),ensure_ascii=False),flush=True)
elif stage=='parse':
    pdf=ROOT.parent/'main.pdf'
    data=once('parse-response.json',lambda:request('/api/manuscripts/parse',files={'file':('main.pdf',pdf.read_bytes(),'application/pdf')},timeout=300))
    print(json.dumps({'parse_status':data['status'],'title':data['parsed']['manuscript']['title'],'paragraphs':len(data['parsed']['paragraphs']),'references':len(data['parsed']['references']),'callouts':len(data['parsed']['citation_callouts']),'diagnostics':data['diagnostics']},ensure_ascii=False),flush=True)
elif stage=='resolve':
    data=once('resolved-response.json',lambda:request('/api/manuscripts/resolve-references',input_payload(read('parse-response.json')),timeout=240))
    print(json.dumps([{'number':i+1,'title':r.get('title'),'doi':r.get('doi'),'resolution':r.get('resolution')} for i,r in enumerate(data['parsed']['references'])],ensure_ascii=False),flush=True)
elif stage=='extract':
    from app.schemas.claim_extraction import ClaimExtractionRequest
    from app.services.citation_context import from_request,build_contexts
    parsed=from_request(ClaimExtractionRequest.model_validate(input_payload(read('resolved-response.json'))))
    plans=build_contexts(parsed)
    save('context-plan.json',[{'context':p.context.model_dump(mode='json'),'skip_code':p.skip_code} for p in plans])
    print(json.dumps({'contexts':len(plans),'to_process':sum(not p.skip_code for p in plans),'skipped':sum(bool(p.skip_code) for p in plans)},ensure_ascii=False),flush=True)
    data=once('extraction-response.json',lambda:request('/api/manuscripts/extract-claims',input_payload(read('resolved-response.json'))))
    print(json.dumps({'status':data['status'],'claims':len(data['claims']),'contexts':len(data['contexts']),'states':dict(Counter(x['status'] for x in data['context_results'])),'attributions':dict(Counter(x['attribution_status'] for x in data['claims'])),'pairs':sum(len(c['reference_ids']) for c in data['claims'])},ensure_ascii=False),flush=True)
elif stage=='create':
    from app.schemas.claim_extraction import ClaimExtractionRequest
    from app.services.citation_context import from_request
    from app.researchguard.domain import ClaimExtractionResult
    from app.services.manuscript_verification import validate_combined_input,plan_manuscript_pairs
    parsed=from_request(ClaimExtractionRequest.model_validate(input_payload(read('resolved-response.json'))))
    extraction=ClaimExtractionResult.model_validate(read('extraction-response.json'))
    parsed,extraction=validate_combined_input(parsed,extraction)
    plan,blocked=plan_manuscript_pairs(parsed,extraction)
    assert len(plan)>0 and len(plan)<=100, 'Unexpected request scale; manual audit needed'
    print(json.dumps({'pairs':len(plan),'attribution_blocked':len(blocked),'extraction_status':extraction.status.value},ensure_ascii=False),flush=True)
    data=once('job-created.json',lambda:request('/api/verification/jobs',{'parsed':parsed.model_dump(mode='json'),'extraction':extraction.model_dump(mode='json')}))
    print(json.dumps({'job_id':data['job_id'],'status':data['status'],'revision':data['revision'],'coverage':data['coverage']},ensure_ascii=False),flush=True)
elif stage=='watch':
    created=read('job-created.json')
    deadline=time.monotonic()+5400
    last=None
    while time.monotonic()<deadline:
        data=request('/api/verification/jobs/'+created['job_id'],timeout=60)
        if data['revision']!=last:
            last=data['revision']
            msg={'at':datetime.now(timezone.utc).isoformat(),'job_id':data['job_id'],'status':data['status'],'revision':last,'coverage':data['coverage'],'states':dict(Counter(t['state'] for t in data['tasks'])),'runtime_error':data.get('runtime_error_code')}
            print(json.dumps(msg,ensure_ascii=False),flush=True)
            with (OUT/'job-progress.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(msg)+'\n')
            save('job-latest.json',data)
        if data['status'] not in {'pending','running'}:
            save('job-final.json',data)
            save('job-events.json',request('/api/verification/jobs/'+created['job_id']+'/events'))
            print('TERMINAL '+data['status'],flush=True)
            break
        time.sleep(10)
    else:raise RuntimeError('E2E job monitoring deadline exceeded; inspect before further model work')
else:raise ValueError(stage)
