"""Run the real FastAPI app with observational HTTP accounting; no fake providers."""
from pathlib import Path
import sys, os, json, time, threading, itertools
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'backend'))
os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
import app.config
import httpx
from app.main import app
# Process-local settings only; keep .env and existing service unchanged.
os.environ['RESEARCHGUARD_JOBS_ENABLED'] = '1'
os.environ['RESEARCHGUARD_PAPERQA_CACHE_SIZE'] = '16'
lock = threading.RLock()
serial = itertools.count(1)
model_count = 0
MAX_MODEL_REQUESTS = 800

def emit(name, data):
    with lock:
        with (OUT / name).open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(data, ensure_ascii=False, default=str) + '\n')

def begin(request):
    global model_count
    rec = {'id': next(serial), 'at': datetime.now(timezone.utc).isoformat(),
           'method': request.method, 'host': request.url.host, 'path': request.url.path}
    model_request = request.url.path.rstrip('/').endswith(('/chat/completions', '/embeddings'))
    if model_request:
        with lock:
            model_count += 1
            if model_count > MAX_MODEL_REQUESTS:
                emit('limits.jsonl', {'event': 'model_budget_exceeded', 'limit':MAX_MODEL_REQUESTS})
                raise RuntimeError('E2E bounded model request limit reached')
        try:
            payload = json.loads(request.content)
        except Exception:
            payload = {}
        rec.update(kind='embedding' if request.url.path.rstrip('/').endswith('/embeddings') else 'chat',
                   model=payload.get('model', 'UNREPORTED'), model_request_number=model_count)
        # Keep manuscript/evidence messages and model responses; never headers/keys.
        emit('model-inputs.jsonl', {**rec, 'messages':payload.get('messages'),
             'embedding_input_count': len(payload.get('input', [])) if isinstance(payload.get('input'), list) else 1,
             'temperature':payload.get('temperature'), 'stream':payload.get('stream',False)})
    emit('http-start.jsonl', rec)
    return rec, model_request, time.monotonic()

def finish(rec, is_model, start, response=None, error=None):
    entry={**rec,'elapsed_seconds':round(time.monotonic()-start,3)}
    if error:
        entry['error_type']=type(error).__name__
    else:
        entry['status_code']=response.status_code
    if is_model and response is not None:
        try: body=response.json()
        except Exception: body={}
        entry['usage']=body.get('usage', 'UNREPORTED')
        entry['response_model']=body.get('model', 'UNREPORTED')
        entry['reported_cost']=body.get('cost', body.get('response_cost', 'UNREPORTED'))
        emit('model-outputs.jsonl', {**entry, 'choices':body.get('choices'),
              'embedding_vectors_returned':len(body['data']) if isinstance(body.get('data'),list) else None})
    emit('http-finish.jsonl',entry)

original_sync=httpx.Client.send
original_async=httpx.AsyncClient.send

def sync_send(self,request,*args,**kwargs):
    rec, model, start=begin(request)
    try:
        response=original_sync(self,request,*args,**kwargs)
        if model: response.read()
    except Exception as exc:
        finish(rec,model,start,error=exc)
        raise
    finish(rec,model,start,response)
    return response

async def async_send(self,request,*args,**kwargs):
    rec, model, start=begin(request)
    try:
        response=await original_async(self,request,*args,**kwargs)
        if model: await response.aread()
    except Exception as exc:
        finish(rec,model,start,error=exc)
        raise
    finish(rec,model,start,response)
    return response

httpx.Client.send=sync_send
httpx.AsyncClient.send=async_send

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8001,workers=1,log_level='info',access_log=False)
