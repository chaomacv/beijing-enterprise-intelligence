"""Versioned, conservative refinement of legacy qualification observations.

Run after aggregation. The source database and model checkpoints stay read-only.
Source-topic rules separate the object of a record; they do not certify validity.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

VERSION = 'qualification-refinement-v1'
LABELS = {
    'business_permit': '企业经营许可',
    'enterprise_qualification': '企业行业资质',
    'personnel_qualification': '人员执业资格',
    'product_registration': '产品注册备案',
    'equipment_inspection': '设备检验登记',
    'qualification_application': '申请办理',
    'regulatory_inspection': '监督检查',
    'industry_assessment': '行业考核与年检',
    'project_approval': '项目审批与验收',
    'qualification_review': '待分类复核',
}
# Specific procedural and object rules precede generic business-permit rules.
# Ambiguous administrative permissions deliberately remain unclassified.
RULES = [
    ('application', 'qualification_application',
     r'资质申请|申请情况|许可申请|许可受理|申请受理|审批办理|办理进度|申报情况|申报信息|办事指南|审批事项|办理事项|许可事项|审批服务'),
    ('inspection', 'regulatory_inspection',
     r'监督检查|日常检查|执法检查|行政检查|领域检查|抽查检查|监督抽查|抽检|双随机|监督管理检查'),
    ('personnel', 'personnel_qualification',
     r'建造师|建筑师|监理工程师|勘察设计工程师|注册工程师|注册人员|执业人员|从业人员|执业药师|医师注册|护士注册|人员.*(资格|资质|考核|证书)|安全生产考核|三类人员|主要负责人.*考核|特种作业人员'),
    ('equipment', 'equipment_inspection',
     r'特种设备.*(检验|登记|注册)|设备监督检验|设备定期检验|电梯.*(检验|登记)|锅炉.*(检验|登记)|压力容器.*(检验|登记)|压力管道.*登记|脚手架使用登记'),
    ('product', 'product_registration',
     r'药品批准|药品注册|药品备案|化妆品.*(基本信息|注册|备案|批准)|医疗器械.*(产品|注册证|产品备案)|产品.*(注册|备案|批准)|保健食品.*(注册|备案)|特殊食品.*(注册|备案)'),
    ('assessment', 'industry_assessment',
     r'信誉考核|信用评价|信用等级|企业信用|社会组织年检|年度检查|年检信息|年检结果|年审信息|质量考核|等级评定|标准化.*(达标|考评)'),
    ('project', 'project_approval',
     r'施工许可|建设.*许可|规划许可|规划验收|工程.*验收|竣工验收|建设项目.*(审批|备案)|投资项目.*(核准|备案)'),
    ('enterprise', 'enterprise_qualification',
     r'企业资质|企业.*资质|机构资质|单位资质|工程.*资质|建筑业.*资质|劳务.*资质|检测.*资质|检验.*资质|资质证书|资质审批结果|监测机构能力认定'),
    ('business', 'business_permit',
     r'经营许可|生产许可|食品.*许可|餐饮.*许可|食品.*备案|食品经营单位证件|食杂店备案|医疗器械经营备案|医疗器械经营企业证件|排污许可|排水.*许可|取水许可|卫生许可|道路运输经营|出版物.*许可|印刷.*许可|文化.*许可|经营性互联网文化单位审批|娱乐场所.*许可|安全生产许可证|药品经营|药品生产|药品零售企业.*许可|旅行社.*许可|劳务派遣.*许可|人力资源.*许可|民办.*办学许可|特种设备.*单位许可|节目制作经营单位设立许可'),
]


def classify_scope(filename, sheet=''):
    """Classify source context, never arbitrary business-cell text."""
    title = str(filename or '') + ' ' + str(sheet or '')
    if re.search(r'培训|考试通知|申报通知|政策解读|办事指南', title):
        return 'qualification_review', 'non_award_context'
    for rule, category, pattern in RULES:
        if re.search(pattern, title):
            return category, rule
    return 'qualification_review', 'ambiguous_source_topic'


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def refine(database, output):
    """Create independent corrected tables and receipts; no inferred licence count."""
    import duckdb
    database, output = Path(database).resolve(), Path(output).resolve()
    if not database.is_file():
        raise ValueError('A completed aggregation database is required')
    if output.exists():
        raise ValueError('Use a new output directory; prior deliveries are immutable')
    output.mkdir(parents=True)
    recipe = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    source_stat = database.stat()
    db = duckdb.connect(str(output / 'classification.duckdb'))
    try:
        db.execute("SET threads=2")
        db.execute("SET memory_limit='3GB'")
        db.execute('SET temp_directory=' + literal(output / 'temp'))
        db.execute('ATTACH ' + literal(database) + ' AS original (READ_ONLY)')
        scopes = db.execute('SELECT scope_id,filename,sheet FROM original.source_scopes').fetchall()
        db.execute('CREATE TABLE scope_rules(scope_id VARCHAR PRIMARY KEY, refined_type VARCHAR, rule_id VARCHAR)')
        if scopes:
            db.executemany('INSERT INTO scope_rules VALUES (?,?,?)',
                           [(sid, *classify_scope(name, sheet)) for sid, name, sheet in scopes])
        # Retain every original source pointer. No source disappears in reclassification.
        db.execute('''CREATE TABLE classified_event_sources AS
            SELECT e.event_id,e.fact_id,e.record_id,e.file_id,e.scope_id,e.entity_id,
                e.event_type AS original_type,e.status AS original_status,
                CASE WHEN e.event_type='qualification'
                  THEN coalesce(r.refined_type,'qualification_review') ELSE e.event_type END AS event_type,
                CASE WHEN e.event_type='qualification'
                  THEN coalesce(r.rule_id,'missing_scope') ELSE 'unchanged_non_qualification' END AS rule_id
            FROM original.event_sources e LEFT JOIN scope_rules r USING(scope_id)''')
        db.execute('''CREATE TABLE source_consensus AS
            SELECT event_id,count(DISTINCT event_type) AS category_count,min(event_type) AS only_type
            FROM classified_event_sources GROUP BY event_id''')
        # Only named reference fields provide issuance evidence. In particular,
        # "有效期" is not a certificate number and an inspecting authority is not a result.
        db.execute('''CREATE TABLE classified_events AS
          WITH base AS (
            SELECT e.event_id,e.entity_id,e.record_id,e.file_id,e.scope_id,
              e.event_type AS original_type,e.status AS original_status,
              CASE WHEN e.event_type<>'qualification' THEN e.event_type
                WHEN c.category_count=1 THEN c.only_type ELSE 'qualification_review' END AS event_type,
              CASE WHEN e.event_type<>'qualification' THEN 'unchanged_non_qualification'
                WHEN c.category_count>1 THEN 'conflicting_source_categories'
                ELSE coalesce(r.rule_id,'missing_scope') END AS classification_reason,
              json_extract_string(e.document_no,'$.field') AS doc_field,
              json_extract_string(e.document_no,'$.value') AS doc_value,
              json_extract_string(e.date,'$.field') AS date_field,
              json_extract_string(e.date,'$.value') AS date_value,
              from_json(e.evidence,'[{"field":"VARCHAR","value":"VARCHAR"}]') AS refs
            FROM original.events e JOIN source_consensus c USING(event_id)
              LEFT JOIN scope_rules r USING(scope_id)),
          proof AS (
            SELECT *,
              coalesce(regexp_matches(doc_field,'证书.*(编号|号码)|证件.*编号|许可证.*(编号|号码|号)|许可.*文号|批准文号|备案.*(号|编号)|注册.*(号|编号)'),false)
                AND coalesce(length(trim(doc_value))>=3 AND lower(trim(doc_value)) NOT IN ('null','none','nan','暂无','不详'),false)
                AND NOT coalesce(regexp_matches(doc_field,'有效|期限|日期'),false) AS has_certificate_reference,
              coalesce(regexp_matches(date_field,'发证|核发|批准|许可决定|审批|注册|备案|验收'),false)
                AND coalesce(length(trim(date_value))>=6,false) AS has_issuance_date,
              coalesce(len(list_filter(refs,x -> regexp_matches(x.field,'(检查|检验|考核|年检|信誉).*(结论|结果|等级)|^(结论|结果)$')
                AND length(trim(x.value)) BETWEEN 1 AND 60 AND lower(trim(x.value)) NOT IN ('null','none','nan','暂无','不详')))>0,false) AS has_result_reference
            FROM base)
          SELECT event_id,entity_id,record_id,file_id,scope_id,original_type,original_status,event_type,
            CASE WHEN original_type<>'qualification' THEN original_status
              WHEN event_type IN ('qualification_review','qualification_application') THEN 'unknown'
              WHEN original_status<>'confirmed' THEN original_status
              WHEN event_type IN ('business_permit','enterprise_qualification','personnel_qualification','product_registration','project_approval')
                AND (has_certificate_reference OR has_issuance_date) THEN 'confirmed'
              WHEN event_type IN ('equipment_inspection','regulatory_inspection','industry_assessment')
                AND has_result_reference THEN 'confirmed'
              ELSE 'unknown' END AS status,
            classification_reason,
            event_type='qualification_review' AS classification_requires_review,
            CASE WHEN original_type<>'qualification' THEN 'unchanged'
              WHEN event_type='qualification_application' THEN 'application_is_not_award'
              WHEN event_type='qualification_review' THEN 'classification_unresolved'
              WHEN original_status='confirmed' AND NOT
                (CASE WHEN event_type IN ('business_permit','enterprise_qualification','personnel_qualification','product_registration','project_approval')
                  THEN has_certificate_reference OR has_issuance_date ELSE has_result_reference END)
                THEN 'insufficient_structured_stage_evidence'
              ELSE 'original_stage_retained_no_promotion' END AS stage_reason,
            CASE WHEN event_type='personnel_qualification' THEN 'associated_personnel_not_enterprise_owned'
              WHEN event_type='equipment_inspection' THEN 'associated_equipment_not_enterprise_qualification'
              WHEN event_type='product_registration' THEN 'associated_product_not_enterprise_qualification'
              WHEN event_type='project_approval' THEN 'associated_project_not_enterprise_qualification'
              ELSE 'source_subject_association_only' END AS subject_relation,
            'not_verified' AS current_validity
          FROM proof''')
        # Corrected tags have their own table; legacy profiles.tags remain a traceable baseline.
        db.execute('''CREATE TABLE classified_profile_tags AS
            SELECT entity_id,event_type,status,count(*) AS observed_events
            FROM classified_events GROUP BY 1,2,3''')
        def rows(query):
            result = db.execute(query)
            names = [x[0] for x in result.description]
            return [dict(zip(names, row)) for row in result.fetchall()]
        before = db.execute('SELECT count(*) FROM original.events').fetchone()[0]
        after, unique = db.execute('SELECT count(*),count(DISTINCT event_id) FROM classified_events').fetchone()
        sources = db.execute('SELECT count(*) FROM original.event_sources').fetchone()[0]
        assert before == after == unique
        assert sources == db.execute('SELECT count(*) FROM classified_event_sources').fetchone()[0]
        legacy = db.execute("SELECT count(*) FROM original.events WHERE event_type='qualification'").fetchone()[0]
        assert legacy == db.execute("SELECT count(*) FROM classified_events WHERE original_type='qualification'").fetchone()[0]
        categories = rows('''SELECT event_type,status,count(*) AS observed_events,
            count(DISTINCT entity_id) AS associated_profiles FROM classified_events GROUP BY 1,2 ORDER BY 1,2''')
        category_profiles = rows('''SELECT event_type,count(DISTINCT entity_id) AS associated_profiles
            FROM classified_events GROUP BY 1 ORDER BY 1''')
        changes = rows('''SELECT original_status,status,stage_reason,count(*) AS observed_events
            FROM classified_events WHERE original_type='qualification' GROUP BY 1,2,3 ORDER BY 1,2,3''')
        for table in ['scope_rules','classified_events','classified_event_sources','classified_profile_tags']:
            path = output / (table + '.parquet')
            db.execute('COPY '+table+' TO '+literal(path)+" (FORMAT PARQUET,COMPRESSION ZSTD)")
            assert db.execute('SELECT count(*) FROM '+table).fetchone()[0] == db.execute('SELECT count(*) FROM read_parquet(?)',[str(path)]).fetchone()[0]
        # Public receipt is deliberately allowlisted: no source names, IDs, rows or paths.
        public = {'version': VERSION, 'created_at': datetime.now(timezone.utc).isoformat(),
                  'basis': 'source_topic_rules_and_structured_stage_evidence_not_manual_row_validation',
                  'semantic_accuracy_evaluated': False, 'total_events': after,
                  'legacy_qualification_events': legacy, 'unique_licences': None,
                  'unique_registered_enterprises': None, 'category_status': categories,
                  'category_profiles': category_profiles, 'stage_changes': changes}
        (output/'public_summary.json').write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        private = {**public, 'source_database':str(database),'recipe_sha256':recipe,
                   'source_stat_before': {'bytes':source_stat.st_size,'mtime_ns':source_stat.st_mtime_ns},
                   'output_source_links':sources,'checks':{'event_ids_conserved':True,'source_links_conserved':True,
                   'parquet_counts_verified':True,'current_validity_inferred':False}}
        final_stat = database.stat()
        assert (source_stat.st_size,source_stat.st_mtime_ns)==(final_stat.st_size,final_stat.st_mtime_ns)
        (output/'audit.json').write_text(json.dumps(private,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        db.execute('CHECKPOINT')
        return public
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    result=refine(args.database,args.output)
    print(json.dumps({'version':result['version'],'events':result['total_events'],
                      'legacy_qualification_events':result['legacy_qualification_events']},ensure_ascii=False))


if __name__=='__main__':
    main()
