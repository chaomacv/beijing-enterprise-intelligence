"""Apply a model-selected field plan without regenerating source values."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor,as_completed
import json
from pathlib import Path
import time

from .common import dump,file_hash,ontology,stable_id
from .extract import review_result,validate_results
from .readers import read_records
from .resolve import normalize,valid_code
from . import subject_guards
from .subject_guards import ORG_MARKERS,recognizable_organization

EMPTY={'','-','--','—','/','null','none','nan','暂无','不详','无'}
TRACE_FIELDS=['file_id','root_file_id','scope_id','sheet','row','source_quality','source_kind','ocr_min_confidence']


def empty(value):return value is None or str(value).strip().casefold() in EMPTY


def reference(field,row,card=None):
    if not field:return None
    value=(card or {}).get('filename') if field=='__filename__' else row['cells'].get(field)
    if empty(value):return None
    return {'field':field,'value':str(value)}


def condition(item,row):
    value=row['cells'].get(item['field']);op=item['op']
    if op=='nonempty':return not empty(value)
    if op=='empty':return empty(value)
    normalized=normalize(str(value or ''));values=[normalize(v) for v in item['values']]
    return any(v in normalized for v in values if v) if op=='contains_any' else normalized in values


def apply_plan(row,card,plan):
    rid=row['record_id'];mode=plan['mode']
    if mode=='row_llm':return None,'requires_record_semantics',[]
    if mode=='review':return review_result(rid),'unresolved_file_mapping',[]
    if mode=='exclude':return {'record_id':rid,'status':'NO_EVENT','entities':[],'events':[]},'plan_excluded',[]
    entities=[];slots={};kinds=[]
    for index,mapping in enumerate(plan['entities']):
        name=reference(mapping['name_field'],row)
        if name is None:continue
        if name['value'].strip() in set(card['columns'])|set(ontology()['name_fields']):
            return {'record_id':rid,'status':'NO_EVENT','entities':[],'events':[]},'structural_header_record',[]
        if mapping['kind']=='person':return review_result(rid),'personal_subject_not_enterprise_fact',[]
        if mapping['name_field'].strip() in {'项目名称','工程名称','单体工程','单体工程名称'}:
            return review_result(rid),'project_field_cannot_directly_identify_organization',[]
        if mapping['name_field'].strip()=='案件名称':return review_result(rid),'case_title_cannot_directly_identify_organization',[]
        if not recognizable_organization(name['value']):return review_result(rid),'subject_name_not_recognizable_requires_review',[]
        code=reference(mapping['code_field'],row)
        if mapping['kind']=='unknown' and not (code and valid_code(code['value'])) and not any(k in name['value'] for k in ORG_MARKERS):
            return review_result(rid),'subject_kind_uncertain',[]
        slots[index]=len(entities);kinds.append(mapping['kind'])
        entities.append({'role':mapping['role'],'name':name,'credit_code':code,'address':reference(mapping['address_field'],row)})
    if not entities:return review_result(rid),'missing_subject_value',[]
    if mode=='entity_only':return {'record_id':rid,'status':'NO_EVENT','entities':entities,'events':[]},'entity_basic_information',kinds
    events=[];negative=False
    for mapping in plan['events']:
        if mapping['event_type']=='administrative_penalty':
            explicit_negative=any(str(value).strip() in ('合格','检查合格','未发现问题','未发现违法行为','无处罚','不予处罚','未予处罚')
                for field,value in row['cells'].items() if any(k in field for k in ('结果','结论','状态','事件内容')))
            if explicit_negative:negative=True;continue
        if not all(condition(c,row) for c in mapping['when']):continue
        if any(condition(c,row) for c in mapping['unless']):negative=True;continue
        if mapping['subject_index'] not in slots:return review_result(rid),'missing_event_subject',[]
        target=slots[mapping['subject_index']]
        if kinds[target]=='person':return review_result(rid),'personal_event_not_enterprise_fact',[]
        if mapping['event_type']=='administrative_penalty':
            for field,value in row['cells'].items():
                if not any(k in field for k in ('结果','结论','状态')) or len(value)>120:continue
                value=value.strip()
                if value in ('合格','检查合格','未发现问题','未发现违法行为','无处罚','不予处罚','未予处罚') or value.startswith(('未发现违法','未发现问题','不予处罚')):
                    negative=True;break
            else:value=None
            if value is not None and negative:continue
        evidence=[r for field in mapping['evidence_fields'] if (r:=reference(field,row,card))]
        if not evidence:return review_result(rid),'missing_fact_evidence',[]
        status=mapping['default_status']
        if any(v in card['filename'] for v in ('拟认定','拟支持','拟推荐','拟奖励','拟通过')):status='proposed'
        for rule in mapping['status_rules']:
            value=row['cells'].get(rule['field'],'')
            if len(value)<=200 and len(rule['contains'])>=2 and rule['contains'] in value:status=rule['status']
        events.append({'subject_index':target,'event_type':mapping['event_type'],'status':status,
            'date':reference(mapping['date_field'],row),'amount':reference(mapping['amount_field'],row),
            'document_no':reference(mapping['document_field'],row),'evidence':evidence})
    if not events and not negative:return review_result(rid),'no_planned_fact_condition_satisfied',[]
    result={'record_id':rid,'status':'EXTRACTED' if events else 'NO_EVENT','entities':entities,'events':events}
    validate_results({'results':[result]},[row],card)
    return result,'explicit_negative_result' if negative and not events else 'validated_field_mapping',kinds


def write_line(stream,value):
    offset=stream.tell();stream.write((json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8'));return offset


def derived(result,trace,kinds):
    mentions=[];events=[]
    for index,entity in enumerate(result['entities']):
        name=entity['name']['value'];code=entity['credit_code']['value'] if entity['credit_code'] else None
        address=entity['address']['value'] if entity['address'] else None
        mentions.append({'mention_id':stable_id(result['record_id'],index),'record_id':result['record_id'],
            'entity_index':index,'role':entity['role'],'kind':kinds[index] if index<len(kinds) else 'unknown',
            'name':name,'raw_code':code,'valid_code':valid_code(code),'address':address,
            'normalized_name':normalize(name),'normalized_address':normalize(address),**trace})
    for index,event in enumerate(result['events']):
        events.append({'fact_id':stable_id(result['record_id'],index),'record_id':result['record_id'],
            'subject_mention_id':stable_id(result['record_id'],event['subject_index']),**event,**trace})
    return mentions,events


def materialize_file(args):
    profile,root=args;root=Path(root);fid=profile['file_id']
    rawdir=root/'05_records'/fid;outdir=root/'06_validation'/fid
    rawdir.mkdir(parents=True,exist_ok=True);outdir.mkdir(parents=True,exist_ok=True)
    cards={c['scope_id']:c for c in profile['cards']};plans={};signatures={}
    for scope,card in cards.items():
        saved=root/'04_plans/scopes'/(scope+'.json')
        if saved.exists():
            data=json.loads(saved.read_text(encoding='utf-8'));plans[scope]=data['plan'];signatures[scope]=data['signature']
        else:
            decision=root/'03_screen/scopes'/(scope+'.json')
            excluded=decision.exists() and json.loads(decision.read_text(encoding='utf-8'))['decision']['decision']=='DROP'
            plans[scope]={'mode':'exclude' if excluded else 'review',
                'reason':'screen_excluded' if excluded else 'missing_field_plan','entities':[],'events':[]}
    key=stable_id('materializer-v3-subject-guard',file_hash(__file__),file_hash(subject_guards.__file__),fid,plans,signatures)
    prior=outdir/'mapping_summary.json'
    if prior.exists():
        value=json.loads(prior.read_text(encoding='utf-8'))
        if value.get('key')==key:return value
    modes={p['mode'] for p in plans.values()}
    if not modes or modes=={'exclude'}:
        value={'file_id':fid,'key':key,'status':'EXCLUDED','expected_records':profile['records'],'raw_records':0,'mapped_records':0,'pending_llm':0,'excluded_records':profile['records']}
        dump(prior,value);return value
    if file_hash(profile['path'])!=profile['sha256']:raise ValueError('Input changed since profiling')
    outputs={'raw':rawdir/'rows.jsonl','chunks':rawdir/'chunks.jsonl','draft':outdir/'mapped_results.jsonl',
        'mentions':outdir/'mapped_mentions.jsonl','events':outdir/'mapped_events.jsonl','pending':outdir/'pending_llm.jsonl'}
    streams={k:p.with_name(p.name+'.part').open('wb') for k,p in outputs.items()}
    statuses=Counter();seen=Counter();contexts={};chunk=[];excluded=0;pending=0;raw_count=0
    start=time.monotonic()
    try:
        for sheet,ordinal,cells,context in read_records(Path(profile['path']),profile['kind']):
            scope=stable_id(fid,sheet);seen[scope]+=1
            if scope not in cards:raise ValueError('Unexpected worksheet scope')
            plan=plans[scope]
            if plan['mode']=='exclude':excluded+=1;continue
            rid=stable_id(fid,sheet,ordinal);card=cards[scope]
            base={k:context[k] for k in ('original_header','header_record','preamble','source_kind') if k in context}
            context_id=stable_id(base);contexts[context_id]=base
            per_record={k:v for k,v in context.items() if k not in base}
            row={'record_id':rid,'sheet':sheet,'row':ordinal,'cells':cells,'context':context}
            trace={'file_id':fid,'root_file_id':profile.get('root_file_id') or fid,'scope_id':scope,'sheet':sheet,'row':ordinal}
            trace.update(source_quality='OCR_UNVERIFIED' if cells.get('__text_source__')=='rapidocr_cpu' else 'NATIVE_EXTRACTED',
                source_kind=cells.get('__text_source__') or profile.get('source',{}).get('source_kind') or context.get('source_kind') or profile['kind'],
                ocr_min_confidence=float(cells['__ocr_min_confidence__']) if cells.get('__text_source__')=='rapidocr_cpu' else None)
            offset=write_line(streams['raw'],{**trace,'record_id':rid,'cells':cells,'context_id':context_id,'context':per_record})
            raw_count+=1;chunk.append(rid)
            try:result,reason,kinds=apply_plan(row,card,plan)
            except Exception as error:result,reason,kinds=review_result(rid),type(error).__name__+': '+str(error)[:160],[]
            if result is None:
                pending+=1;write_line(streams['pending'],{**trace,'record_id':rid,'raw_offset':offset,'reason':reason})
            else:
                statuses[result['status']]+=1
                write_line(streams['draft'],{**trace,**result,'method':'llm_field_plan','plan_signature':signatures.get(scope),'reason':reason})
                mentions,events=derived(result,trace,kinds)
                for value in mentions:write_line(streams['mentions'],value)
                for value in events:write_line(streams['events'],value)
            if len(chunk)==1000:
                write_line(streams['chunks'],{'chunk':raw_count//1000,'records':len(chunk),'first_record_id':chunk[0],'last_record_id':chunk[-1]});chunk=[]
        if sum(seen.values())!=profile['records']:raise ValueError('Record count differs from profile')
        if chunk:write_line(streams['chunks'],{'chunk':raw_count//1000+1,'records':len(chunk),'first_record_id':chunk[0],'last_record_id':chunk[-1]})
        for stream in streams.values():stream.close()
        for output_path in outputs.values():output_path.with_name(output_path.name+'.part').replace(output_path)
        dump(rawdir/'contexts.json',contexts)
        value={'file_id':fid,'key':key,'status':'MAPPED','expected_records':profile['records'],'raw_records':raw_count,
            'mapped_records':sum(statuses.values()),'record_statuses':dict(statuses),'pending_llm':pending,
            'excluded_records':excluded,'seconds':round(time.monotonic()-start,2)}
        dump(prior,value);return value
    finally:
        for stream in streams.values():stream.close()


def materialize(profiles,root,workers=6):
    root=Path(root);tasks=[(p,str(root)) for p in profiles if p['cards']]
    results=[];start=time.monotonic()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(materialize_file,task):task[0] for task in tasks}
        for future in as_completed(futures):
            profile=futures[future]
            try:result=future.result()
            except Exception as error:
                result={'file_id':profile['file_id'],'status':'REVIEW','expected_records':profile['records'],
                    'error':type(error).__name__+': '+str(error)[:200]}
                dump(root/'06_validation'/profile['file_id']/'mapping_failure.json',result)
            results.append(result)
            if len(results)%20==0 or len(results)==len(tasks):
                value={'stage':'05_06_materialize','completed_files':len(results),'total_files':len(tasks),
                    'raw_records':sum(v.get('raw_records',0) for v in results),
                    'pending_llm':sum(v.get('pending_llm',0) for v in results),'seconds':round(time.monotonic()-start,1)}
                dump(root/'06_validation/progress.json',value);print(json.dumps(value),flush=True)
    summary={'complete':True,'files':len(results),'file_statuses':dict(Counter(v['status'] for v in results)),
        'raw_records':sum(v.get('raw_records',0) for v in results),'mapped_records':sum(v.get('mapped_records',0) for v in results),
        'pending_llm':sum(v.get('pending_llm',0) for v in results),'excluded_records':sum(v.get('excluded_records',0) for v in results),
        'seconds':round(time.monotonic()-start,2)}
    dump(root/'06_validation/mapping_files.json',results);dump(root/'06_validation/mapping_summary.json',summary)
    return results
