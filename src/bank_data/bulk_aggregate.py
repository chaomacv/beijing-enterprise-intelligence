"""Disk-backed identity resolution and fact exports; no all-pairs comparison."""
from collections import Counter
import csv
import json
from pathlib import Path
import time

from .common import dump,ontology


MENTION_COLUMNS={'mention_id':'VARCHAR','record_id':'VARCHAR','entity_index':'BIGINT','role':'VARCHAR','kind':'VARCHAR',
    'name':'VARCHAR','raw_code':'VARCHAR','valid_code':'VARCHAR','address':'VARCHAR','normalized_name':'VARCHAR',
    'normalized_address':'VARCHAR','file_id':'VARCHAR','root_file_id':'VARCHAR','scope_id':'VARCHAR','sheet':'VARCHAR','row':'BIGINT'}
FACT_COLUMNS={'fact_id':'VARCHAR','record_id':'VARCHAR','subject_mention_id':'VARCHAR','event_type':'VARCHAR','status':'VARCHAR',
    'date':'JSON','amount':'JSON','document_no':'JSON','evidence':'JSON','file_id':'VARCHAR','root_file_id':'VARCHAR',
    'scope_id':'VARCHAR','sheet':'VARCHAR','row':'BIGINT'}
RESULT_COLUMNS={'record_id':'VARCHAR','file_id':'VARCHAR','root_file_id':'VARCHAR','scope_id':'VARCHAR','sheet':'VARCHAR',
    'row':'BIGINT','status':'VARCHAR','method':'VARCHAR','reason':'JSON','model_provenance':'JSON',
    'strategy_signature':'VARCHAR','representative_record_id':'VARCHAR','content_key':'VARCHAR'}
for columns in [MENTION_COLUMNS,FACT_COLUMNS,RESULT_COLUMNS]:
    columns.update(source_quality='VARCHAR',source_kind='VARCHAR',ocr_min_confidence='DOUBLE')


def literal(value):return "'"+str(value).replace("'","''")+"'"


def import_lines(db,name,files,columns):
    if files:
        db.execute('CREATE OR REPLACE TABLE '+name+' AS SELECT * FROM read_json(?,format=\'newline_delimited\',columns='+
            '{'+','.join(literal(k)+':'+literal(v) for k,v in columns.items())+'},maximum_object_size=67108864)',[files])
    else:db.execute('CREATE OR REPLACE TABLE '+name+'('+','.join('"'+k+'" '+v for k,v in columns.items())+')')


def export(db,query,path,kind):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.part')
    options="FORMAT PARQUET,COMPRESSION ZSTD" if kind=='parquet' else 'FORMAT JSON,ARRAY false'
    db.execute('COPY ('+query+') TO '+literal(temp)+' ('+options+')');temp.replace(path)


def aggregate(root,profiles):
    import duckdb
    root=Path(root);stage=root/'07_entities';result=root/'08_results';review=root/'09_review'
    for path in [stage,result,review,stage/'temp']:path.mkdir(parents=True,exist_ok=True)
    start=time.monotonic();db=duckdb.connect(str(stage/'results.duckdb'))
    db.execute("SET memory_limit='32GB'");db.execute('SET threads=8');db.execute('SET temp_directory='+literal(stage/'temp'))
    def checkpoint(name,**extra):
        value={'stage':'07_08_aggregate','operation':name,'seconds':round(time.monotonic()-start,1),**extra}
        dump(stage/'progress.json',value);print(json.dumps(value),flush=True)
    try:
        checkpoint('import_validated_partitions')
        scope_rows=[(c['scope_id'],p['file_id'],p['filename'],c['sheet'],c['quality_flags'],c['row_count']) for p in profiles for c in p['cards']]
        db.execute('CREATE OR REPLACE TABLE source_scopes(scope_id VARCHAR PRIMARY KEY,file_id VARCHAR,filename VARCHAR,sheet VARCHAR,quality_flags VARCHAR[],known_rows BIGINT)')
        if scope_rows:db.executemany('INSERT INTO source_scopes VALUES (?,?,?,?,?,?)',scope_rows)
        completed=json.loads((root/'06_validation/files.json').read_text(encoding='utf-8'))
        dirs=[root/'06_validation'/p['file_id'] for p in completed if p['status']=='COMPLETE']
        import_lines(db,'mentions',[str(p/'mentions.jsonl') for p in dirs],MENTION_COLUMNS)
        import_lines(db,'facts',[str(p/'events.jsonl') for p in dirs],FACT_COLUMNS)
        import_lines(db,'raw_record_ledger',[str(p/'record_results.jsonl') for p in dirs],RESULT_COLUMNS)
        if db.execute('SELECT count(*) FROM raw_record_ledger r LEFT JOIN source_scopes q USING(scope_id) WHERE q.scope_id IS NULL').fetchone()[0]:
            raise ValueError('A record references an unknown source scope')
        db.execute('CREATE OR REPLACE TABLE record_ledger AS SELECT r.*,q.quality_flags FROM raw_record_ledger r JOIN source_scopes q USING(scope_id)')
        nrecords,unique=db.execute('SELECT count(*),count(DISTINCT record_id) FROM record_ledger').fetchone()
        if nrecords!=unique:raise ValueError('Duplicate global record IDs')
        nmentions,unique=db.execute('SELECT count(*),count(DISTINCT mention_id) FROM mentions').fetchone()
        if nmentions!=unique:raise ValueError('Duplicate global mention IDs')
        checkpoint('resolve_strong_and_weak_identities',records=nrecords,mentions=nmentions)
        db.execute('''CREATE OR REPLACE TABLE name_address_codes AS
            SELECT normalized_name,normalized_address,count(DISTINCT valid_code) AS n_codes,min(valid_code) AS only_code
            FROM mentions WHERE valid_code IS NOT NULL GROUP BY 1,2''')
        db.execute('''CREATE OR REPLACE TABLE entity_mentions AS
            SELECT m.*,q.quality_flags,
            'E_' || substr(sha256(CASE
              WHEN m.valid_code IS NOT NULL THEN 'code:' || m.valid_code
              WHEN m.normalized_address<>'' AND coalesce(k.n_codes,0)=1 THEN 'code:' || k.only_code
              WHEN m.normalized_address<>'' AND coalesce(k.n_codes,0)=0
                THEN 'name_address:' || m.normalized_name || chr(31) || m.normalized_address
              ELSE 'provisional:' || m.mention_id END),1,24) AS entity_id,
            CASE WHEN m.valid_code IS NOT NULL THEN 'checksum_valid_code'
              WHEN m.normalized_address<>'' AND coalesce(k.n_codes,0)=1 THEN 'exact_name_address_to_unique_code'
              WHEN m.normalized_address<>'' AND coalesce(k.n_codes,0)=0 THEN 'exact_name_and_address'
              WHEN coalesce(k.n_codes,0)>1 THEN 'conflicting_codes_require_review'
              ELSE 'insufficient_identity_fields' END AS match_reason
            FROM mentions m LEFT JOIN name_address_codes k USING(normalized_name,normalized_address)
              LEFT JOIN source_scopes q ON m.scope_id=q.scope_id''')
        db.execute('''CREATE OR REPLACE TABLE entities AS
            WITH base AS (SELECT entity_id,min(valid_code) AS valid_code,count(*) AS source_mentions
              FROM entity_mentions GROUP BY entity_id),
            names AS (SELECT entity_id,list(name ORDER BY name) AS names FROM
              (SELECT DISTINCT entity_id,name FROM entity_mentions) GROUP BY entity_id),
            addresses AS (SELECT entity_id,list(address ORDER BY address) AS addresses FROM
              (SELECT DISTINCT entity_id,address FROM entity_mentions WHERE address IS NOT NULL AND address<>'') GROUP BY entity_id),
            roles AS (SELECT entity_id,list(role ORDER BY role) AS roles FROM
              (SELECT DISTINCT entity_id,role FROM entity_mentions) GROUP BY entity_id),
            kinds AS (SELECT entity_id,list(kind ORDER BY kind) AS kinds FROM
              (SELECT DISTINCT entity_id,kind FROM entity_mentions) GROUP BY entity_id),
            quality AS (SELECT entity_id,list(source_quality ORDER BY source_quality) AS observed_source_quality FROM
              (SELECT DISTINCT entity_id,source_quality FROM entity_mentions) GROUP BY entity_id),
            structure AS (SELECT entity_id,list(flag ORDER BY flag) AS observed_quality_flags FROM
              (SELECT DISTINCT m.entity_id,u.flag FROM entity_mentions m CROSS JOIN unnest(m.quality_flags) AS u(flag)) GROUP BY entity_id)
            SELECT base.*,names.names,addresses.addresses,roles.roles,kinds.kinds,quality.observed_source_quality,
              coalesce(structure.observed_quality_flags,[]::VARCHAR[]) AS observed_quality_flags,
              CASE WHEN valid_code IS NOT NULL THEN 'code_checksum_only_not_registry_verified' ELSE 'provisional' END AS identity_status
            FROM base LEFT JOIN names USING(entity_id) LEFT JOIN addresses USING(entity_id)
              LEFT JOIN roles USING(entity_id) LEFT JOIN kinds USING(entity_id) LEFT JOIN quality USING(entity_id)
              LEFT JOIN structure USING(entity_id)''')
        checkpoint('resolve_event_sources')
        db.execute('''CREATE OR REPLACE TABLE event_sources AS
            SELECT f.*,m.entity_id,m.quality_flags,
              'F_' || substr(sha256(CASE WHEN json_extract_string(f.document_no,'$.value') IS NOT NULL
                THEN m.entity_id || chr(31) || f.event_type || chr(31) || f.status || chr(31) ||
                  json_extract_string(f.document_no,'$.value') || chr(31) || coalesce(cast(f.date AS VARCHAR),'') || chr(31) ||
                  coalesce(cast(f.amount AS VARCHAR),'') || chr(31) || coalesce(cast(f.evidence AS VARCHAR),'')
                ELSE f.fact_id END),1,24) AS event_id
            FROM facts f JOIN entity_mentions m ON f.subject_mention_id=m.mention_id''')
        nfacts=db.execute('SELECT count(*) FROM facts').fetchone()[0]
        if db.execute('SELECT count(*) FROM event_sources').fetchone()[0]!=nfacts:raise ValueError('A fact lost its source subject')
        db.execute('''CREATE OR REPLACE TABLE events AS
            WITH representative AS (SELECT * EXCLUDE(rank) FROM
              (SELECT *,row_number() OVER(PARTITION BY event_id ORDER BY fact_id) AS rank FROM event_sources) WHERE rank=1),
            flags AS (SELECT event_id,list(flag ORDER BY flag) AS quality_flags FROM
              (SELECT DISTINCT e.event_id,u.flag FROM event_sources e CROSS JOIN unnest(e.quality_flags) AS u(flag)) GROUP BY event_id)
            SELECT r.* EXCLUDE(quality_flags),coalesce(f.quality_flags,[]::VARCHAR[]) AS quality_flags
            FROM representative r LEFT JOIN flags f USING(event_id)''')
        tags=[{'event_type':k,'label':v['tag']} for k,v in ontology()['events'].items()]
        db.execute('CREATE OR REPLACE TABLE tag_labels(event_type VARCHAR,label VARCHAR)')
        db.executemany('INSERT INTO tag_labels VALUES (?,?)',[(v['event_type'],v['label']) for v in tags])
        db.execute('''CREATE OR REPLACE TABLE profiles AS
            WITH counts AS (SELECT entity_id,event_type,status,count(*) AS event_count FROM events GROUP BY 1,2,3),
            tags AS (SELECT entity_id,list(struct_pack(event_type:=c.event_type,event_status:=c.status,
                label:=CASE c.status WHEN 'proposed' THEN '拟议：' WHEN 'revoked' THEN '已撤销：'
                    WHEN 'removed' THEN '已移出：' WHEN 'unknown' THEN '阶段未明：' ELSE '' END || l.label,
                observed_event_count:=c.event_count)) AS tags FROM counts c JOIN tag_labels l USING(event_type) GROUP BY entity_id)
            SELECT e.*,t.tags,cast(NULL AS DOUBLE) AS credit_score,'observed_sources_only' AS coverage
            FROM entities e LEFT JOIN tags t USING(entity_id)''')
        checkpoint('generate_conservative_match_candidates')
        db.execute('''CREATE OR REPLACE TABLE name_ambiguities AS
            SELECT normalized_name,count(DISTINCT entity_id) AS entity_count,
              CASE WHEN count(DISTINCT entity_id)<=100 THEN list(DISTINCT entity_id) ELSE NULL END AS candidate_entities,
              count(DISTINCT entity_id)>100 AS candidate_overflow
            FROM entity_mentions GROUP BY normalized_name HAVING count(DISTINCT entity_id)>1''')
        db.execute('''CREATE OR REPLACE TABLE name_neighbors AS
            WITH aliases AS (SELECT DISTINCT entity_id,normalized_name FROM entity_mentions WHERE length(normalized_name)>=4),
            neighbors AS (SELECT *,lag(entity_id) OVER w AS other_entity_id,lag(normalized_name) OVER w AS other_name
              FROM aliases WINDOW w AS(PARTITION BY substr(normalized_name,1,4) ORDER BY normalized_name,entity_id))
            SELECT DISTINCT entity_id,other_entity_id,normalized_name,other_name,
                jaro_winkler_similarity(normalized_name,other_name) AS name_similarity,
                'REVIEW_ONLY_NOT_EQUIVALENCE' AS decision
            FROM neighbors WHERE other_entity_id IS NOT NULL AND entity_id<>other_entity_id
              AND normalized_name<>other_name AND jaro_winkler_similarity(normalized_name,other_name)>=0.88''')
        checkpoint('export_results')
        for name in ['entities','entity_mentions','name_address_codes','name_ambiguities','name_neighbors']:
            export(db,'SELECT * FROM '+name,stage/(name+'.parquet'),'parquet')
        for name in ['profiles','events','event_sources','record_ledger']:
            export(db,'SELECT * FROM '+name,result/(name+'.parquet'),'parquet')
            if name!='record_ledger':export(db,'SELECT * FROM '+name,result/(name+'.jsonl'),'json')
        export(db,"SELECT * FROM record_ledger WHERE status='REVIEW'",review/'record_review.parquet','parquet')
        export(db,"SELECT * FROM record_ledger WHERE status='REVIEW'",review/'record_review.jsonl','json')
        db.execute('''CREATE OR REPLACE TABLE structural_review_scopes AS SELECT q.*,c.processed_records
            FROM source_scopes q JOIN (SELECT scope_id,count(*) AS processed_records FROM record_ledger GROUP BY scope_id) c USING(scope_id)
            WHERE array_length(q.quality_flags)>0''')
        export(db,'SELECT * FROM source_scopes',stage/'source_scopes.parquet','parquet')
        export(db,'SELECT * FROM structural_review_scopes',review/'structural_review_scopes.parquet','parquet')
        export(db,'SELECT * FROM structural_review_scopes',review/'structural_review_scopes.jsonl','json')
        with (review/'表头及结构复核清单.csv').open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['scope_id','file_id','文件名','工作表','结构标记','已知记录数','已处理记录数'])
            for row in db.execute('SELECT * FROM structural_review_scopes ORDER BY file_id,sheet').fetchall():
                writer.writerow([*row[:4],json.dumps(row[4],ensure_ascii=False),*row[5:]])
        dump(review/'file_review.json',[{k:p.get(k) for k in ['file_id','root_file_id','relative_path','filename','kind','error','native_error','source']}
            for p in profiles if p['status']=='REVIEW'])
        dump(result/'file_index.json',[{k:p.get(k) for k in ['file_id','root_file_id','relative_path','path','filename','kind','sha256','status','records','source']}
            for p in profiles])
        counts={name:db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ['record_ledger','entities','entity_mentions','events','event_sources','name_ambiguities','name_neighbors']}
        statuses=dict(db.execute('SELECT status,count(*) FROM record_ledger GROUP BY status').fetchall())
        summary={'complete':True,'counts':counts,'record_statuses':statuses,
            'event_categories':dict(db.execute('SELECT event_type,count(*) FROM events GROUP BY event_type').fetchall()),
            'file_statuses':dict(Counter(p['status'] for p in profiles)),'semantic_accuracy_evaluated':False,
            'fuzzy_candidates_do_not_merge':True,
            'input_scope_quality_flags':dict(Counter(flag for p in profiles for c in p['cards'] for flag in c['quality_flags'])),
            'processed_scopes_requiring_structural_review':db.execute('SELECT count(*) FROM structural_review_scopes').fetchone()[0],
            'record_coverage_basis':'按解析器识别的逻辑记录对账；表头候选保存在上下文，不等于全部物理行已经人工核验。',
            'seconds':round(time.monotonic()-start,2)}
        dump(result/'summary.json',summary);db.execute('CHECKPOINT');return summary
    finally:db.close()
