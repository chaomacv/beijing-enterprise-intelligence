"""Auditable full-corpus pipeline with explicit intermediate artifacts."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

from .common import dump,stable_id


STEPS=[('01_inputs','原始快照与附件关系','snapshot-manifest.json / archive_members.json'),
       ('02_profiles','格式转换、OCR、文件卡片','all_profiles_native.json / file_cards.jsonl'),
       ('03_screen','本地模型相关性筛选','files.json / scopes/*.json / methods/'),
       ('04_plans','本地模型字段与条件映射','scopes/*.json / prompt.md / config.json'),
       ('05_records','完整记录与分块','*/rows.jsonl / */contexts.json / */chunks.jsonl'),
       ('06_validation','逐行应用、复杂行模型抽取、校验','*/record_results.jsonl / */summary.json'),
       ('07_entities','身份关联与候选','results.duckdb / entity_mentions.parquet / name_neighbors.parquet'),
       ('08_results','事实与画像导出','profiles.parquet / events.parquet / event_sources.parquet / file_index.json'),
       ('09_review','待复核与失败明细','record_review.parquet / file_review.json')]


def report(root,state):
    root=Path(root)
    lines=['# 全量处理：流程与中间结果','',
        '本地 Qwen 负责文件理解、字段方案和复杂记录抽取；程序逐行复制原值、执行条件、校验与匹配。',
        '原始文件保持只读。抽样用于文件判断，不代表模型已理解所有内容；语义准确率尚未独立评测。','',
        '当前状态：**'+state['status']+'**；当前步骤：**'+state['current_stage']+'**。','',
        '| 目录 | 状态 | 步骤 | 主要中间结果 |','| --- | --- | --- | --- |']
    lines.extend('| '+name+' | '+state.get('steps',{}).get(name,{}).get('status','PENDING')+' | '+title+' | '+outputs+' |' for name,title,outputs in STEPS)
    lines+=['','## 每一步的数量与状态','']
    for name in ['02_profiles/native_summary.json','02_profiles/summary.json','03_screen/summary.json',
        '04_plans/summary.json','06_validation/mapping_summary.json','06_validation/dedup_summary.json','06_validation/llm_summary.json',
                 '06_validation/summary.json','08_results/summary.json','audit.json']:
        path=root/name
        if path.exists():
            lines+=['### '+name,'','```json',json.dumps(json.loads(path.read_text(encoding='utf-8')),ensure_ascii=False,indent=2),'```','']
    lines+=['## 如何追溯','',
        '先打开 02_profiles/文件总表.csv、03_screen/筛选总表.csv、04_plans/字段方案总表.csv、05_records/分块与处理总表.csv 和 06_validation/校验总表.csv。它们是适合人工查看的小型索引；全部记录在 JSONL 和 Parquet 中。','',
        '1. 从 08_results/profiles 或 events 的 entity_id / event_id 查找对应 event_sources。',
        '2. event_sources 保存 file_id、scope_id、sheet、row、record_id 与原文引用。',
        '3. 08_results/file_index.json 给出原文件、内容哈希、下载来源及压缩成员关系。',
        '4. 05_records/<file_id>/rows.jsonl 与 contexts.json 保存逐行原值和语境；06_validation 同目录保存结果及方法。',
        '5. 04_plans/scopes/<scope_id>.json 给出字段映射、条件和模型回复，03_screen/scopes 给出筛选依据。',
        '6. OCR 的识别文本、位置和置信度在 01_inputs/ocr_cache；原图和原 PDF 仍保留，OCR 不等于人工核验。','',
        '文件状态含 PROFILED、REVIEW、EMPTY、CONTAINER、CONVERTED、METADATA、COMPONENT。配套元数据和数据库组件不是独立企业记录。',
        '记录状态 EXTRACTED / NO_EVENT / REVIEW 含义不同；排除文件在文件台账中单独计数。未支持、损坏或仍不确定的输入保留复核，不能假装为零条业务内容。',
        '匹配优先校验位有效的信用代码，其次完整名称和非空地址；冲突阻止自动合并，名称近似仅给候选，不生成授信评分。','']
    (root/'流程与结果.md').write_text('\n'.join(lines),encoding='utf-8')


def wait_job(root,pid_name,expected):
    root=Path(root);file=root/pid_name
    if not file.exists():return
    pid=file.read_text().strip();proc=Path('/proc')/pid/'cmdline'
    while proc.exists():
        command=proc.read_bytes().replace(b'\0',b' ').decode(errors='replace')
        if not command or expected not in command:return
        time.sleep(5)


def audit(root,profiles,original_count):
    root=Path(root);validation=json.loads((root/'06_validation/files.json').read_text(encoding='utf-8'))
    expected=sum(p['records'] for p in profiles if p['cards'])
    accounted=sum(v.get('final_records',0)+v.get('excluded_records',0) for v in validation)
    failed_known=sum(v.get('expected_records',0) for v in validation if v['status']=='REVIEW')
    original_ids={p['file_id'] for p in json.loads((root/'01_inputs/input_ledger.json').read_text(encoding='utf-8'))}
    root_ids={p.get('root_file_id') or p['file_id'] for p in profiles}
    value={'original_files':original_count,'root_files_in_final_ledger':len(root_ids),
        'logical_files_including_members_and_derivatives':len(profiles),'known_logical_records':expected,
        'records_with_result_or_explicit_exclusion':accounted,'known_records_in_file_failure':failed_known,
        'all_readable_records_accounted_for':expected==accounted+failed_known,
        'all_original_files_accounted_for':original_ids==root_ids,
        'unsupported_or_unreadable_files':sum(p['status']=='REVIEW' for p in profiles),
        'semantic_accuracy_evaluated':False,'ocr_requires_quality_review':True}
    if not value['all_readable_records_accounted_for'] or not value['all_original_files_accounted_for']:
        raise ValueError('Full-corpus accounting invariant failed')
    dump(root/'audit.json',value);return value


def run(args):
    root=args.work_dir.resolve();root.mkdir(parents=True,exist_ok=True)
    if args.input and (root==args.input.resolve() or root.is_relative_to(args.input.resolve())):
        raise ValueError('Work directory must be outside the input snapshot')
    if os.name!='nt':root.chmod(0o700)
    for name,_,_ in STEPS:(root/name).mkdir(exist_ok=True)
    state={'status':'RUNNING','current_stage':'01_inputs','started_utc':datetime.now(timezone.utc).isoformat(),'steps':{}}
    state_file=root/'run_status.json'
    attempt=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    package=Path(__file__).parent
    snapshot=root/'01_inputs/code_snapshots'/attempt
    snapshot.mkdir(parents=True,exist_ok=True)
    hashes={}
    for path in sorted(package.rglob('*')):
        if path.is_file() and path.suffix in ('.py','.md','.json') and '__pycache__' not in path.parts:
            relative=path.relative_to(package);dest=snapshot/relative;dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,dest);hashes[str(relative)]=hashlib.sha256(path.read_bytes()).hexdigest()
    dump(root/'01_inputs/run_attempts'/(attempt+'.json'),{'attempt':attempt,'code_sha256':hashes,'model':args.model,
        'endpoints':args.endpoints,'tokenizer_dir':str(args.tokenizer_dir),'workers':args.workers,
        'input':str(args.input),'profiles':str(args.profiles),'semantic_accuracy_evaluated':False})
    if state_file.exists():
        prior=json.loads(state_file.read_text(encoding='utf-8'));state['started_utc']=prior.get('started_utc',state['started_utc'])
        state['steps']=prior.get('steps',{})
    def stage(name,status='RUNNING',summary=None):
        previous=state['current_stage']
        if previous!=name and state['steps'].get(previous,{}).get('status')=='RUNNING':
            state['steps'][previous].update(status='COMPLETE',completed_utc=datetime.now(timezone.utc).isoformat())
        state.update(current_stage=name,status=status,updated_utc=datetime.now(timezone.utc).isoformat())
        state['steps'][name]={'status':status,'at_utc':state['updated_utc'],'summary':summary}
        dump(state_file,state);report(root,state);print(json.dumps({'stage':name,'status':status}),flush=True)
    try:
        stage('01_inputs')
        if args.profiles:original=json.loads(args.profiles.read_text(encoding='utf-8'))
        else:
            from .scan import scan
            original,_=scan(args.input,root/'02_profiles/original_scan',workers=args.workers)
            dump(root/'02_profiles/original_profiles.json',original)
        original_count=len(original)
        dump(root/'01_inputs/input_ledger.json',[{k:p.get(k) for k in ['file_id','relative_path','path','sha256','bytes','kind','source']} for p in original])
        stage('02_profiles')
        wait_job(root,'inputs.pid','bank_data.bulk_inputs')
        expanded=root/'02_profiles/all_profiles.json'
        if expanded.exists():profiles=json.loads(expanded.read_text(encoding='utf-8'))
        else:
            from .bulk_inputs import prepare_inputs
            profiles=prepare_inputs(original,root,args.workers)
        wait_job(root,'native.pid','bank_data.bulk_native')
        native=root/'02_profiles/all_profiles_native.json'
        if native.exists():profiles=json.loads(native.read_text(encoding='utf-8'))
        elif not args.skip_native:
            from .bulk_native import enrich
            profiles=enrich(profiles,root,args.workers)
        from .bulk_report import overviews
        overviews(root,profiles)
        stage('03_screen')
        wait_job(root,'screen.pid','bank_data.bulk_screen')
        from .bulk_screen import screen
        screen(profiles,root,args.endpoints,args.model,args.tokenizer_dir)
        overviews(root,profiles)
        stage('04_plans')
        from .bulk_plan import create_plans
        create_plans(profiles,root,args.endpoints,args.model,args.tokenizer_dir)
        overviews(root,profiles)
        stage('05_records')
        from .bulk_rows import materialize
        materialize(profiles,root,args.workers)
        stage('06_validation')
        from .bulk_dedup import resolve_pending
        from .bulk_semantics import finalize_validation
        resolve_pending(profiles,root,args.endpoints,args.model,args.tokenizer_dir,workers=args.workers)
        finalize_validation(profiles,root)
        overviews(root,profiles)
        stage('07_entities')
        from .bulk_aggregate import aggregate
        result=aggregate(root,profiles)
        stage('08_results')
        checks=audit(root,profiles,original_count)
        stage('09_review','COMPLETED_WITH_REVIEW' if checks['unsupported_or_unreadable_files'] or result['record_statuses'].get('REVIEW',0) else 'COMPLETED',result)
        return result
    except Exception as error:
        stage(state['current_stage'],'FAILED',{'error':type(error).__name__,'detail':str(error)[:300]})
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path);p.add_argument('--profiles',type=Path);p.add_argument('--work-dir',type=Path,required=True)
    p.add_argument('--endpoints',nargs='+',required=True);p.add_argument('--model',required=True);p.add_argument('--tokenizer-dir',type=Path,required=True)
    p.add_argument('--workers',type=int,default=6);p.add_argument('--skip-native',action='store_true');args=p.parse_args()
    if not args.input and not args.profiles:p.error('--input or --profiles is required')
    run(args)


if __name__=='__main__':main()
