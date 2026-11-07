"""Bounded-memory local-model extraction for records that need row semantics."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import queue
import shutil
import threading
import time

from .bulk_client import BatchClient
from .bulk_rows import derived,write_line,TRACE_FIELDS
from .common import dump,ontology,resource,stable_id,file_hash
from .extract import review_result,source_bound_schema,validate_results


def load_row(root,task):
    directory=Path(root)/'05_records'/task['file_id']
    with (directory/'rows.jsonl').open('rb') as stream:
        stream.seek(task['raw_offset']);raw=json.loads(stream.readline())
    contexts=json.loads((directory/'contexts.json').read_text(encoding='utf-8'))
    return {'record_id':raw['record_id'],'sheet':raw['sheet'],'row':raw['row'],'cells':raw['cells'],
            'context':{**contexts[raw['context_id']],**raw['context']}}


def extract_request(client,records,card,feedback=None):
    payload={'context':{k:card[k] for k in ['filename','sheet','columns','source']},
             'event_types':ontology()['events'],'records':records}
    if feedback:payload['validation_feedback']=feedback
    return client.request(resource('extract.md'),payload,source_bound_schema(records),2048)


def merge_fragments(parent,fragments):
    if any(result['status']=='REVIEW' for result in fragments):return review_result(parent['record_id'])
    entities=[];entity_lookup={};events=[];event_keys=set()
    for result in fragments:
        slots={}
        for i,entity in enumerate(result['entities']):
            key=stable_id(entity)
            if key not in entity_lookup:entity_lookup[key]=len(entities);entities.append(entity)
            slots[i]=entity_lookup[key]
        for event in result['events']:
            event={**event,'subject_index':slots[event['subject_index']]};key=stable_id(event)
            if key not in event_keys:events.append(event);event_keys.add(key)
    return {'record_id':parent['record_id'],'status':'EXTRACTED' if events else 'NO_EVENT','entities':entities,'events':events}


def infer(client,records,card,depth=0,feedback=None):
    try:
        request=extract_request(client,records,card,feedback)
        response=client.call([request])[0];data=client.content(response)
        results=validate_results(data,records,card);by_id={r['record_id']:r for r in results}
        return [by_id[r['record_id']] for r in records],[]
    except Exception as error:
        # Infrastructure failures must not be disguised as a record-level decision.
        if not isinstance(error,(ValueError,TypeError,KeyError)):raise
        message=type(error).__name__+': '+str(error)[:180]
        if len(records)>1:
            mid=len(records)//2
            a,x=infer(client,records[:mid],card,depth+1);b,y=infer(client,records[mid:],card,depth+1)
            return a+b,x+y
        row=records[0];text=row['cells'].get('__text__')
        if text and len(text)>400 and depth<5:
            middle=len(text)//2;parts=[(0,min(len(text),middle+80)),(max(0,middle-80),len(text))]
            children=[];traces=[]
            for start,end in parts:
                fragment={**row,'record_id':stable_id(row['record_id'],start,end),
                    'cells':{**row['cells'],'__text__':text[start:end]}}
                results,errors=infer(client,[fragment],card,depth+1)
                children.extend(results);traces.extend(errors)
            result=merge_fragments(row,children)
            validate_results({'results':[result]},[row],card)
            return [result],traces+[{'record_id':row['record_id'],'reason':'adaptive_text_split','fragments':parts}]
        if feedback is None and depth<4:
            return infer(client,records,card,depth+1,'上次输出未通过来源校验：'+message+'。逐条复制原始ID，字段和引用值必须来自本行，不要改写日期或名称。')
        return [review_result(row['record_id'])],[{'record_id':row['record_id'],'reason':message}]


def resolve_pending(profiles,root,endpoints,model,tokenizer_dir,client_class=BatchClient):
    root=Path(root);directory=root/'06_validation';mapping=json.loads((directory/'mapping_files.json').read_text(encoding='utf-8'))
    scope_cards={c['scope_id']:c for p in profiles for c in p['cards']}
    strategy=client_class.cache_signature() if hasattr(client_class,'cache_signature') else 'canonical-source-refs-v2'
    signature=stable_id('corpus-record-llm-v3',file_hash(__file__),model,resource('extract.md'),ontology(),2048,0,strategy)
    tasks=queue.Queue(maxsize=256);lock=threading.Lock();completed=0;total=sum(v.get('pending_llm',0) for v in mapping);start=time.monotonic()
    error_flag=threading.Event()
    def enqueue(value):
        while not error_flag.is_set():
            try:tasks.put(value,timeout=1);return True
            except queue.Full:continue
        return False
    def target(task):return directory/task['file_id']/'llm_results'/(task['record_id']+'.json')
    def producer():
        nonlocal completed
        try:
            for value in mapping:
                path=directory/value['file_id']/'pending_llm.jsonl'
                if value.get('status')!='MAPPED' or not path.exists():continue
                group=[];scope=None
                with path.open(encoding='utf-8') as f:
                    for line in f:
                        if error_flag.is_set():return
                        task=json.loads(line);destination=target(task)
                        if destination.exists():
                            saved=json.loads(destination.read_text(encoding='utf-8'))
                            if saved.get('signature')==signature:
                                with lock:completed+=1
                                continue
                        if group and (scope!=task['scope_id'] or len(group)==4):
                            if not enqueue(group):return
                            group=[]
                        scope=task['scope_id'];group.append(task)
                if group and not enqueue(group):return
        except Exception:
            error_flag.set();raise
        finally:
            if error_flag.is_set():
                while True:
                    try:tasks.get_nowait()
                    except queue.Empty:break
            for _ in endpoints:
                if not enqueue(None):
                    try:tasks.put_nowait(None)
                    except queue.Full:pass
    def save(task,result,errors,client):
        nonlocal completed
        if result['record_id']!=task['record_id']:raise ValueError('Record assignment mismatch')
        value={'signature':signature,'task':task,'result':result,'errors':errors,'method':getattr(client_class,'method','local_llm_record'),
            'strategy_signature':strategy,'model_provenance':getattr(client,'record_provenance',{}).pop(task['record_id'],None)}
        dump(target(task),value)
        with lock:
            completed+=1
            if completed%20==0 or completed==total:
                progress={'stage':'06_record_llm','completed_records':completed,'total_records':total,'seconds':round(time.monotonic()-start,1)}
                dump(directory/'llm_progress.json',progress);print(json.dumps(progress),flush=True)
    def worker(endpoint):
        client=client_class(endpoint,model,tokenizer_dir,root/'model_cache')
        try:
            while True:
                group=tasks.get()
                if group is None:return
                groups=[group]
                for _ in range(3):
                    try:extra=tasks.get_nowait()
                    except queue.Empty:break
                    if extra is None:tasks.put(None);break
                    groups.append(extra)
                pending=[];requests=[]
                for group in groups:
                    records=[load_row(root,task) for task in group];card=scope_cards[group[0]['scope_id']]
                    try:request=extract_request(client,records,card)
                    except ValueError:
                        results,errors=infer(client,records,card)
                        for task,result in zip(group,results):save(task,result,errors,client)
                        continue
                    requests.append(request);pending.append((group,records,card))
                if not requests:continue
                responses=client.call(requests)
                for (group,records,card),response in zip(pending,responses):
                    try:
                        checked=validate_results(client.content(response),records,card);by_id={r['record_id']:r for r in checked}
                        results=[by_id[r['record_id']] for r in records];errors=[]
                    except (ValueError,TypeError,KeyError):results,errors=infer(client,records,card)
                    for task,result in zip(group,results):save(task,result,errors,client)
        except Exception:error_flag.set();raise
    with ThreadPoolExecutor(max_workers=len(endpoints)+1) as pool:
        produce=pool.submit(producer);workers=[pool.submit(worker,endpoint) for endpoint in endpoints]
        for f in workers:f.result()
        produce.result()
    summary={'complete':True,'signature':signature,'strategy_signature':strategy,'method':getattr(client_class,'method','local_llm_record'),
        'records':total,'completed_records':completed,'seconds':round(time.monotonic()-start,2)}
    dump(directory/'llm_summary.json',summary);return summary


def finalize_validation(profiles,root):
    root=Path(root);stage=root/'06_validation';mapping=json.loads((stage/'mapping_files.json').read_text(encoding='utf-8'))
    model_summary=stage/'llm_summary.json'
    expected_signature=json.loads(model_summary.read_text(encoding='utf-8'))['signature'] if model_summary.exists() else None
    totals=Counter();summaries=[]
    for value in mapping:
        if value['status']!='MAPPED':summaries.append(value);continue
        fid=value['file_id'];path=stage/fid;seen=set();statuses=Counter();methods=Counter()
        streams={name:(path/(name+'.jsonl.part')).open('wb') for name in ['record_results','mentions','events']}
        try:
            with (path/'mapped_results.jsonl').open('rb') as f:
                for line in f:
                    data=json.loads(line);rid=data['record_id']
                    if rid in seen:raise ValueError('Duplicate mapped record')
                    seen.add(rid);statuses[data['status']]+=1;methods[data['method']]+=1;streams['record_results'].write(line)
            for origin,dest in [('mapped_mentions','mentions'),('mapped_events','events')]:
                with (path/(origin+'.jsonl')).open('rb') as f:shutil.copyfileobj(f,streams[dest])
            pending=path/'pending_llm.jsonl'
            with pending.open(encoding='utf-8') as f:
                for line in f:
                    task=json.loads(line);saved=json.loads((path/'llm_results'/(task['record_id']+'.json')).read_text(encoding='utf-8'))
                    if expected_signature and saved.get('signature')!=expected_signature:raise ValueError('Model checkpoint belongs to another extraction strategy')
                    result=saved['result'];rid=result['record_id']
                    if rid!=task['record_id'] or rid in seen:raise ValueError('Missing/duplicate model record')
                    method=saved.get('method','local_llm_record')
                    seen.add(rid);statuses[result['status']]+=1;methods[method]+=1
                    trace={k:task.get(k) for k in TRACE_FIELDS}
                    provenance={key:saved[key] for key in ['model_provenance','strategy_signature','representative_record_id','content_key'] if key in saved}
                    write_line(streams['record_results'],{**trace,**result,'method':method,'reason':saved['errors'],**provenance})
                    mentions,events=derived(result,trace,(saved.get('model_provenance') or {}).get('entity_kinds',[]))
                    for item in mentions:write_line(streams['mentions'],item)
                    for item in events:write_line(streams['events'],item)
            if len(seen)!=value['raw_records']:raise ValueError('Record coverage mismatch')
            with (root/'05_records'/fid/'rows.jsonl').open('rb') as f:
                for line in f:
                    rid=json.loads(line)['record_id']
                    if rid not in seen:raise ValueError('Raw record missing a disposition')
            for stream in streams.values():stream.close()
            for name in streams:(path/(name+'.jsonl.part')).replace(path/(name+'.jsonl'))
            report={**value,'status':'COMPLETE','final_records':len(seen),'record_statuses':dict(statuses),'methods':dict(methods),
                    'record_id_coverage_complete':True}
            dump(path/'summary.json',report);summaries.append(report);totals.update(statuses)
        finally:
            for stream in streams.values():stream.close()
    summary={'complete':True,'file_results':dict(Counter(v['status'] for v in summaries)),
        'record_statuses':dict(totals),'records':sum(totals.values()),'semantic_accuracy_evaluated':False}
    dump(stage/'files.json',summaries);dump(stage/'summary.json',summary);return summary
