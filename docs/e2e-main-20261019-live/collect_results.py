"""Read-only inspection of this real job, usage records and saved source bytes."""
import sys,json,hashlib,re
from pathlib import Path
from collections import Counter,defaultdict
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'backend'))
from app.services.verification_job_store import LocalJobStore
from app.services.verification_job_models import JobSnapshot
from app.services.source_store import LocalSourceStore
from app.services.source_locator import reference_locator
from app.services.document_parser import parse_document
from app.services.evidence_chunker import chunk_sections
from app.researchguard.adapters.sciverify import accepted_source_to_domain


def save(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')

def lines(name):
    p=OUT/name
    return [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()] if p.exists() else []

job_id=json.loads((OUT/'job-created.json').read_text(encoding='utf8'))['job_id']
store=LocalJobStore(ROOT/'backend/data/researchguard/jobs')
snapshot=store.load(job_id)
assert JobSnapshot.model_validate_json(snapshot.model_dump_json())==snapshot
refs={r.id:(i+1,r) for i,r in enumerate(snapshot.parsed.references)}
claims={c.id:(i+1,c) for i,c in enumerate(snapshot.extraction.claims)}
contexts={c.id:c for c in snapshot.extraction.contexts}
inputs=lines('model-inputs.jsonl')
outputs=lines('model-outputs.jsonl')
# Request IDs restart with the audit server; timestamp + ID is the unique key.
by_input={(r['at'],r['id']):r for r in inputs}
usage=[]
for r in outputs:
    inp=by_input[(r['at'],r['id'])]
    messages=inp.get('messages') or []
    system=next((m['content'] for m in messages if m['role']=='system'),'')
    role=('embedding' if r['kind']=='embedding' else
          'prosecutor' if 'You are the Prosecutor agent' in system else
          'defender' if 'You are the Defender agent' in system else
          'adjudicator' if 'You are the Adjudicator agent' in system else
          'extraction' if system.startswith('You receive a located, reliable citation sentence') else
          'paperqa_summary' if system.startswith('Provide a summary of the relevant information') else 'other_chat')
    usage.append({**r,'role':role,'embedding_input_count':inp.get('embedding_input_count') if role=='embedding' else None})
usage_summary={}
for role in sorted({r['role'] for r in usage}):
    records=[r for r in usage if r['role']==role]
    report={'http_requests':len(records),'models':dict(Counter(r['model'] for r in records)),
            'statuses':dict(Counter(str(r['status_code']) for r in records)),
            'usage_unreported':sum(not isinstance(r.get('usage'),dict) for r in records),
            'reported_token_totals':{},'reported_costs':[r['reported_cost'] for r in records if r.get('reported_cost') not in {None,'UNREPORTED'}]}
    for k in ['prompt_tokens','completion_tokens','total_tokens','input_tokens','output_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens']:
        values=[r['usage'][k] for r in records if isinstance(r.get('usage'),dict) and isinstance(r['usage'].get(k),(int,float))]
        if values:report['reported_token_totals'][k]=sum(values)
    report['estimated_cost']='UNREPORTED: provider cost absent; no verified model rate applied'
    usage_summary[role]=report
save('model-usage-detail.json',usage)
save('model-usage-summary.json',{'started_requests':len(inputs),'finished_responses':len(outputs),'roles':usage_summary,
    'recorded_before_successful_resume':sum(r['at']<'2026-10-19T07:07:00' for r in inputs),
    'cost_note':'Includes extraction, the first interrupted pair and the accepted resume. No discarded usage omitted.'})

sources=LocalSourceStore()
source_rows=[]
source_chunks={}
(OUT/'source-text').mkdir(exist_ok=True)
for rid,(number,ref) in refs.items():
    tasks=[t for t in snapshot.tasks if t.reference_id==rid]
    row={'number':number,'reference':ref.model_dump(mode='json'),'scheduled_pairs':len(tasks),
         'outcomes':[{'state':t.state.value,'reason':t.reason_code} for t in tasks]}
    binding=next((t.source_binding for t in tasks if t.source_binding and t.source_binding.source_version),None)
    row['binding']=binding.model_dump(mode='json') if binding else None
    if not tasks:
        row['retrieval_status']='NOT_SCHEDULED: no resolved-attribution pair'
    elif binding:
        locator=reference_locator(ref)
        artifact=sources.get_locator(locator)
        assert artifact is not None and 'sha256:'+artifact.raw_content_sha256==binding.source_version
        sections=parse_document(artifact.content,artifact.format)
        chunks=chunk_sections(sections,artifact.paper.paper_id,artifact.source_url)
        source,domain_chunks=accepted_source_to_domain(artifact.response(cache_hit=True,sections=sections,chunks=chunks))
        assert source.id==binding.source_document_id
        source_chunks[rid]={c.id:c for c in domain_chunks}
        selected=[c for t in tasks if t.pair_outcome for c in t.pair_outcome.verification.evidence_chunks]
        for c in selected:
            original=source_chunks[rid][c.id]
            assert original.text==c.text and original.source_document_id==c.source_document_id
        row.update(retrieval_status='FULL_TEXT_ACCEPTED',source_document_audit_reconstruction=source.model_dump(mode='json'),
                   raw_content_sha256=artifact.raw_content_sha256,format=artifact.format,total_available_chunks=len(chunks),
                   selected_chunks_match_saved_artifact=True,paper=artifact.paper.model_dump(mode='json'),
                   source_url=artifact.source_url,provider=artifact.provider,
                   source_identity_statuses=sorted({c.metadata.get('source_identity_status','unknown') for c in selected}),
                   cache_hit_values=sorted({c.metadata.get('source_cache_hit') for c in selected if 'source_cache_hit' in c.metadata}))
        (OUT/'source-text'/f'ref-{number}.txt').write_text('\n\n'.join(s.section_name+'\n'+s.text for s in sections),encoding='utf8')
    else:
        row['retrieval_status']='NO_ACCEPTED_SOURCE_IN_JOB'
    source_rows.append(row)
save('source-audit.json',source_rows)

pairs=[]
context_checks=[]
resumed_at = max((e.timestamp for e in snapshot.events if e.event_type == 'job_resumed'), default='')
for t in snapshot.tasks:
    cn,claim=claims[t.claim_id]
    rn,ref=refs[t.reference_id]
    outcome=t.pair_outcome
    row={'claim_number':cn,'reference_number':rn,'claim':claim.model_dump(mode='json'),
         'reference':ref.model_dump(mode='json'),'state':t.state.value,'reason':t.reason_code,'attempt':t.attempt,
         'pair_outcome':outcome.model_dump(mode='json') if outcome else None}
    if outcome and outcome.verification.evidence_chunks:
        chunks=outcome.verification.evidence_chunks
        row['total_available_chunks']=len(source_chunks.get(t.reference_id,{}))
        row['retrieved_chunk_count']=len(chunks)
        checks={}
        for role in ['Prosecutor','Defender','Adjudicator']:
            matches=[]
            for request in inputs:
                if request['at'] > snapshot.updated_at or (resumed_at and request['at'] < resumed_at):
                    continue  # Keep formal Job input checks separate from discarded/targeted calls.
                user='\n'.join(m['content'] for m in request.get('messages') or [] if m['role']=='user')
                if ('Role: '+role+'\n') in user and claim.text in user and chunks[0].id in user:
                    ctx=re.search(r'Manuscript context[^\n]*:\n({[^\n]*})',user)
                    context=json.loads(ctx.group(1)) if ctx else None
                    matches.append({'at':request['at'],'request_id':request['id'],'context':context,
                        'citation_context_matches':bool(context and context['citation_context']==contexts[claim.context_id].text),
                        'manuscript_title_matches_parsed':bool(context and context['manuscript_title']==snapshot.parsed.manuscript.title),
                        'original_paragraph_present':bool(context and context.get('original_paragraph')),
                        'all_selected_evidence_ids_present':all(c.id in user for c in chunks)})
            checks[role]=matches
        row['actual_agent_input_checks']=checks
        context_checks.append({'claim_number':cn,'reference_number':rn,'roles_found':list(k for k,v in checks.items() if v),
             'context_and_evidence_pass':all(v and all(m['citation_context_matches'] and m['manuscript_title_matches_parsed'] and m['all_selected_evidence_ids_present'] for m in v) for v in checks.values())})
    pairs.append(row)
save('pair-audit.json',pairs)
save('agent-context-audit.json',context_checks)
before=json.loads((OUT/'integrity-before.json').read_text(encoding='utf8'))
changed=[]
for p,digest in before.items():
    path=Path(p)
    if not path.is_absolute():path=ROOT/path
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:changed.append(p)
old_jobs=[]
for old_id in ['job_355c3d27d93e47ecaa4126378989f61b','job_3dbc1247f5f34c20b65a81831455e40f']:
    old=store.load(old_id)
    old_jobs.append({'job_id':old_id,'state':old.state.value,'revision':old.revision,'json_roundtrip':JobSnapshot.model_validate_json(old.model_dump_json())==old})
completed=[t for t in snapshot.tasks if t.state.value=='completed']
scientific=[t for t in completed if t.pair_outcome.verification.evidence_chunks and t.pair_outcome.verification.traceability.metadata.get('legacy_provenance',{}).get('adjudicator')]
planned_refs={t.reference_id for t in snapshot.tasks}
available_refs={t.reference_id for t in snapshot.tasks if t.source_binding and t.source_binding.source_version}
metrics={'job_id':job_id,'state':snapshot.state.value,'revision':snapshot.revision,'created_at':snapshot.created_at,'updated_at':snapshot.updated_at,
    'total_pairs':len(snapshot.tasks),'completed_pairs':len(completed),'scientific_agent_completed_pairs':len(scientific),
    'task_states':dict(Counter(t.state.value for t in snapshot.tasks)),'reason_codes':dict(Counter(t.reason_code for t in snapshot.tasks)),
    'verdicts':dict(Counter(t.pair_outcome.verification.verdict.value for t in completed)),
    'pair_completion_rate':{'numerator':len(completed),'denominator':len(snapshot.tasks)},
    'source_coverage_among_planned_references':{'numerator':len(available_refs),'denominator':len(planned_refs)},
    'source_coverage_among_all_references':{'numerator':len(available_refs),'denominator':len(refs)},
    'claim_attribution_coverage':{'numerator':sum(c.attribution_status.value=='resolved' for _,c in claims.values()),'denominator':len(claims)},
    'scientific_verification_coverage':{'numerator':len(scientific),'denominator':len(snapshot.tasks)},
    'attribution_blocked':len(snapshot.attribution_blocked),'current_job_roundtrip':True,'old_job_compatibility':old_jobs,
    'protected_preexisting_files_checked':len(before),'protected_preexisting_files_changed':changed,
    'agent_context_checks_all_pass':all(c['context_and_evidence_pass'] for c in context_checks)}
save('acceptance-metrics.json',metrics)
print(json.dumps(metrics,ensure_ascii=True,indent=2))
assert not changed,'Preexisting user data changed'
