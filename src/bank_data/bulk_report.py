"""Small, human-readable stage indexes; full records remain in JSONL and Parquet."""
import csv
import json
from pathlib import Path


def write_csv(path,columns,rows):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.csv.part')
    with temporary.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(columns)
        for row in rows:
            writer.writerow([json.dumps(v,ensure_ascii=False,separators=(',',':')) if isinstance(v,(dict,list)) else v for v in row])
    temporary.replace(path)


def overviews(root,profiles):
    root=Path(root)
    write_csv(root/'02_profiles/文件总表.csv',
        ['file_id','root_file_id','文件名','格式','解析状态','已知记录数','SHA256','原始路径','解析说明'],
        ([p['file_id'],p.get('root_file_id') or p['file_id'],p['filename'],p.get('kind','unknown'),p['status'],p['records'],
          p['sha256'],p['path'],p.get('native_error') or p.get('error','')] for p in profiles))
    cards=[c for p in profiles for c in p['cards']]
    screen=[];plans=[]
    for card in cards:
        path=root/'03_screen/scopes'/(card['scope_id']+'.json')
        if path.exists():
            value=json.loads(path.read_text(encoding='utf-8'));decision=value['decision']
            screen.append([card['file_id'],card['scope_id'],card['filename'],card['sheet'],card['row_count'],
                decision['decision'],decision['event_types'],decision['evidence_fields'],decision['reason'],value.get('signature')])
        path=root/'04_plans/scopes'/(card['scope_id']+'.json')
        if path.exists():
            value=json.loads(path.read_text(encoding='utf-8'));plan=value['plan']
            plans.append([card['file_id'],card['scope_id'],card['filename'],card['sheet'],card['row_count'],plan['mode'],
                plan['entities'],plan['events'],plan['reason'],value.get('error'),value.get('signature')])
    if screen:write_csv(root/'03_screen/筛选总表.csv',
        ['file_id','scope_id','文件名','工作表','记录数','筛选结果','事件类别','依据字段','原因','方法签名'],screen)
    if plans:write_csv(root/'04_plans/字段方案总表.csv',
        ['file_id','scope_id','文件名','工作表','记录数','处理方式','主体字段','事件与条件','原因','错误','方法签名'],plans)
    for origin,destination in [('mapping_files.json','05_records/分块与处理总表.csv'),('files.json','06_validation/校验总表.csv')]:
        path=root/'06_validation'/origin
        if not path.exists():continue
        values=json.loads(path.read_text(encoding='utf-8'))
        columns=['file_id','status','expected_records','raw_records','mapped_records','pending_llm','excluded_records','final_records',
            'record_statuses','methods','error']
        write_csv(root/destination,columns,([v.get(k) for k in columns] for v in values))
