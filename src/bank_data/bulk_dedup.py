"""Infer exact same-scope content once, retaining every original source record."""
from concurrent.futures import ProcessPoolExecutor,ThreadPoolExecutor,as_completed
from functools import lru_cache
import json
from multiprocessing import get_context
from pathlib import Path
import time

from .common import dump,file_hash,stable_id
from .extract import validate_results
from .bulk_semantics import load_row,resolve_pending as resolve_unique

VERSION='exact-content-same-scope-context-v1'
RELATIVE=('同上','同前','上述','前述','上行','下行','上一条','下一条','上条','该企业','该公司','该单位')


def link_directory(path,target):
    path=Path(path);target=Path(target).resolve();path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink():
        if path.resolve()!=target:raise ValueError('Unexpected execution-view link')
    elif path.exists():raise ValueError('Execution-view path is not a link')
    else:path.symlink_to(target,target_is_directory=True)


def semantic_key(task,cells,context,card_key):
    key=stable_id(VERSION,task['scope_id'],card_key,cells,context,task.get('source_quality'),task.get('source_kind'),task.get('ocr_min_confidence'))
    # Relative statements can depend on neighboring rows, so keep them separate.
    if any(marker in str(value) for value in cells.values() for marker in RELATIVE):
        key=stable_id(key,task['record_id'])
    return key


def prepare_view(profiles,root):
    root=Path(root);stage=root/'06_validation';view=stage/'unique_inference';view.mkdir(parents=True,exist_ok=True)
    (root/'model_cache').mkdir(exist_ok=True);link_directory(view/'model_cache',root/'model_cache')
    mapping=json.loads((stage/'mapping_files.json').read_text(encoding='utf-8'))
    cards={c['scope_id']:c for p in profiles for c in p['cards']}
    card_keys={key:stable_id({k:card[k] for k in ['filename','sheet','columns','source']}) for key,card in cards.items()}
    selected=[];manifests=[];started=time.monotonic()
    for item in mapping:
        if item.get('status')!='MAPPED' or not item.get('pending_llm'):continue
        fid=item['file_id'];rawdir=root/'05_records'/fid;pending=stage/fid/'pending_llm.jsonl'
        link_directory(view/'05_records'/fid,rawdir)
        resultdir=stage/fid/'llm_results';resultdir.mkdir(exist_ok=True)
        link_directory(view/'06_validation'/fid/'llm_results',resultdir)
        directory=stage/'content_indices'/fid;directory.mkdir(parents=True,exist_ok=True)
        manifest=directory/'manifest.json';index=directory/'records.jsonl';groups_path=directory/'groups.jsonl'
        unique=view/'06_validation'/fid/'pending_llm.jsonl'
        contexts=json.loads((rawdir/'contexts.json').read_text(encoding='utf-8'))
        fingerprint=stable_id(VERSION,file_hash(__file__),file_hash(pending),file_hash(rawdir/'rows.jsonl'),
            contexts,sorted((key,card_keys[key]) for key in {c['scope_id'] for p in profiles if p['file_id']==fid for c in p['cards']}))
        cached=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else None
        if cached and cached.get('fingerprint')==fingerprint and index.exists() and groups_path.exists() and unique.exists():info=cached
        else:
            groups={};count=0
            with pending.open(encoding='utf-8') as tasks,(rawdir/'rows.jsonl').open('rb') as rawstream,\
                 index.with_suffix('.part').open('w',encoding='utf-8') as indices,unique.with_suffix('.part').open('w',encoding='utf-8') as representatives:
                for line in tasks:
                    task=json.loads(line);rawstream.seek(task['raw_offset']);raw=json.loads(rawstream.readline())
                    if raw['record_id']!=task['record_id'] or raw['scope_id']!=task['scope_id'] or raw['row']!=task['row'] or raw['sheet']!=task['sheet']:
                        raise ValueError('Pending task does not identify its original raw record')
                    context={**contexts[raw['context_id']],**raw['context']}
                    key=semantic_key(task,raw['cells'],context,card_keys[task['scope_id']]);group=groups.get(key)
                    if group is None:
                        group={'content_key':key,'file_id':fid,'scope_id':task['scope_id'],'representative_record_id':task['record_id'],
                            'source_records':0,'first_row':task['row'],'last_row':task['row']};groups[key]=group
                        representatives.write(json.dumps(task,ensure_ascii=False)+'\n')
                    group['source_records']+=1;group['last_row']=task['row'];count+=1
                    indices.write(json.dumps({'task':task,'content_key':key,'representative_record_id':group['representative_record_id']},ensure_ascii=False)+'\n')
            index.with_suffix('.part').replace(index);unique.with_suffix('.part').replace(unique)
            with groups_path.with_suffix('.part').open('w',encoding='utf-8') as stream:
                for group in groups.values():stream.write(json.dumps(group,ensure_ascii=False)+'\n')
            groups_path.with_suffix('.part').replace(groups_path)
            if count!=item['pending_llm']:raise ValueError('Content index does not cover every pending source record')
            info={'fingerprint':fingerprint,'file_id':fid,'source_records':count,'unique_records':len(groups),
                'duplicate_records':count-len(groups),'duplicate_groups':sum(g['source_records']>1 for g in groups.values()),
                'index':str(index),'groups':str(groups_path)}
            dump(manifest,info)
        manifests.append(info);selected.append({**item,'pending_llm':info['unique_records']})
        if len(manifests)%10==0:dump(stage/'dedup_progress.json',{'phase':'index','files':len(manifests),'seconds':round(time.monotonic()-started,1)})
    dump(view/'06_validation/mapping_files.json',selected)
    summary={'method':VERSION,'files':len(manifests),'source_records':sum(m['source_records'] for m in manifests),
        'unique_model_records':sum(m['unique_records'] for m in manifests),'exact_duplicate_records':sum(m['duplicate_records'] for m in manifests),
        'duplicate_groups':sum(m['duplicate_groups'] for m in manifests),'index_seconds':round(time.monotonic()-started,2),
        'source_records_removed':False,'same_scope_cells_and_context_required':True,'relative_statements_kept_separate':True,
        'view':str(view),'model_progress':str(view/'06_validation/llm_progress.json')}
    dump(stage/'dedup_summary.json',summary);dump(stage/'dedup_files.json',manifests)
    from .bulk_report import write_csv
    write_csv(stage/'内容去重总表.csv',['file_id','原始待抽取记录','不同内容记录','重复内容记录','重复组'],
        ([m['file_id'],m['source_records'],m['unique_records'],m['duplicate_records'],m['duplicate_groups']] for m in manifests))
    return view,manifests,summary


def expand_file(args):
    root,info,cards,signature=args;root=Path(root);directory=root/'06_validation'/info['file_id']/'llm_results';count=0;reused=0
    card_keys={key:stable_id({k:card[k] for k in ['filename','sheet','columns','source']}) for key,card in cards.items()}
    @lru_cache(maxsize=1024)
    def representative(rid,key):
        data=json.loads((directory/(rid+'.json')).read_text(encoding='utf-8'))
        if data['signature']!=signature or data['result']['record_id']!=rid:raise ValueError('Invalid representative checkpoint')
        task=data['task'];row=load_row(root,task);card=cards[task['scope_id']]
        if semantic_key(task,row['cells'],row['context'],card_keys[task['scope_id']])!=key:raise ValueError('Representative content changed after indexing')
        validate_results({'results':[data['result']]},[row],card)
        return data
    with Path(info['index']).open(encoding='utf-8') as stream:
        for line in stream:
            index=json.loads(line);task=index['task'];rid=task['record_id'];target=directory/(rid+'.json');row=load_row(root,task);card=cards[task['scope_id']]
            if row['sheet']!=task['sheet'] or row['row']!=task['row'] or semantic_key(task,row['cells'],row['context'],card_keys[task['scope_id']])!=index['content_key']:
                raise ValueError('Source content changed after indexing')
            existing=json.loads(target.read_text(encoding='utf-8')) if target.exists() else None
            if existing and existing.get('signature')==signature:
                validate_results({'results':[existing['result']]},[row],card);count+=1;continue
            source=representative(index['representative_record_id'],index['content_key']);result={**source['result'],'record_id':rid}
            validate_results({'results':[result]},[row],card)
            dump(target,{'signature':signature,'task':task,'result':result,'errors':source.get('errors',[]),
                'method':'local_llm_exact_content_reuse','representative_record_id':index['representative_record_id'],
                'content_key':index['content_key'],'source_cells_and_context_identical':True})
            count+=1;reused+=1
    if count!=info['source_records']:raise ValueError('Incomplete source-record expansion')
    return {'file_id':info['file_id'],'source_records':count,'newly_expanded_records':reused}


def resolve_pending(profiles,root,endpoints,model,tokenizer_dir,workers=6):
    root=Path(root);stage=root/'06_validation';started=time.monotonic()
    view,manifests,summary=prepare_view(profiles,root)
    dump(stage/'dedup_progress.json',{'phase':'local_model','unique_model_records':summary['unique_model_records'],'source_records':summary['source_records'],
        'model_progress':summary['model_progress']})
    with ThreadPoolExecutor(max_workers=1) as monitor:
        future=monitor.submit(resolve_unique,profiles,view,endpoints,model,tokenizer_dir)
        while not future.done():
            progress=view/'06_validation/llm_progress.json'
            if progress.exists():
                value=json.loads(progress.read_text(encoding='utf-8'))
                dump(stage/'llm_progress.json',{'stage':'06_unique_content_llm','completed_unique_records':value['completed_records'],
                    'total_unique_records':value['total_records'],'source_records_total':summary['source_records'],'seconds':value['seconds']})
            time.sleep(5)
        unique=future.result()
    dump(stage/'dedup_progress.json',{'phase':'expand_sources','unique_completed_records':unique['completed_records'],'source_records':summary['source_records']})
    card_lookup={c['scope_id']:c for p in profiles for c in p['cards']};results=[]
    with ProcessPoolExecutor(max_workers=workers,mp_context=get_context('spawn')) as pool:
        futures=[pool.submit(expand_file,(str(root),info,{key:card_lookup[key] for key in {c['scope_id'] for p in profiles if p['file_id']==info['file_id'] for c in p['cards']}},unique['signature'])) for info in manifests]
        for future in as_completed(futures):
            results.append(future.result())
            dump(stage/'dedup_progress.json',{'phase':'expand_sources','files':len(results),'total_files':len(manifests),
                'source_records_expanded':sum(v['source_records'] for v in results),'source_records':summary['source_records']})
    completed=sum(v['source_records'] for v in results)
    if completed!=summary['source_records']:raise ValueError('Not every pending source record received a checked result')
    value={**summary,'complete':True,'signature':unique['signature'],'records':completed,'completed_records':completed,
        'unique_inference':unique,'seconds':round(time.monotonic()-started,2)}
    dump(stage/'llm_summary.json',value);dump(stage/'dedup_progress.json',{'phase':'complete','source_records_expanded':completed})
    return value
