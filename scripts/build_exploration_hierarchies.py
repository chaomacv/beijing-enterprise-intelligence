"""Build additive, public-only sunburst trees from a completed private run.

Run on the private server. No cell values, enterprise identities, source paths or
internal IDs are exported. Logical files receive display-only sequential labels.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


LABELS = {
    'administrative_penalty': '行政处罚', 'business_abnormal': '经营异常',
    'business_permit': '企业经营许可', 'enterprise_qualification': '企业行业资质',
    'equipment_inspection': '设备检验登记', 'personnel_qualification': '人员执业资格',
    'qualification_review': '待分类复核', 'industry_assessment': '行业考核与年检',
    'product_registration': '产品注册备案', 'qualification_application': '申请办理',
    'project_approval': '项目审批与验收', 'regulatory_inspection': '监督检查',
    'innovation': '科技认定', 'environment': '环保监管或绿色认定',
    'operating_status': '经营状态', 'procurement': '政府采购或中标',
    'subsidy': '政策支持', 'tax_credit': '税务或纳税信用',
}
STAGES = {'confirmed': '已记录阶段', 'proposed': '拟议阶段', 'unknown': '阶段未明',
          'removed': '已移出', 'revoked': '已撤销'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def normalized_url(value):
    return str(value or '').replace('http://', 'https://').rstrip('/')


def tree_from_counts(name, counts):
    """Every source unit belongs to exactly one leaf; internal totals reconcile."""
    branches = {}
    for names, count in sorted(counts.items()):
        if not isinstance(count, int) or count <= 0:
            raise ValueError('Invalid leaf count')
        current = branches
        for part in names[:-1]:
            current = current.setdefault(part, {})
        if names[-1] in current:
            raise ValueError('Duplicate or mixed-depth path')
        current[names[-1]] = count
    serial = 0

    def node(label, content):
        nonlocal serial
        serial += 1
        result = {'id': 'n' + str(serial), 'name': label}
        if isinstance(content, int):
            result['value'] = content
        else:
            result['children'] = [node(k, v) for k, v in content.items()]
            result['children'].sort(key=lambda n: (-n['value'], n['name']))
            result['value'] = sum(n['value'] for n in result['children'])
        return result
    return node(name, branches)


def record_labels(category, stages, status):
    if not category:
        return ('待复核记录', '保留复核') if status == 'REVIEW' else ('未提取目标事件', '未提取目标事件')
    kinds = category.split('|')
    category_label = LABELS.get(kinds[0], '未识别事件类别') if len(kinds) == 1 else '多事件类别记录'
    detail = '、'.join(STAGES.get(s, s) for s in stages.split('|'))
    if len(kinds) > 1:
        detail = '＋'.join(LABELS.get(k, '未识别事件类别') for k in kinds) + ' · ' + detail
    return category_label, detail


def build(run, snapshot, output):
    import duckdb
    import xlrd
    final = read(run / '交付汇总/全量汇总.json')
    if not final['audit']['all_original_files_accounted_for'] or not final['exports_round_trip_validated']:
        raise ValueError('Completed-run audits are required')
    inputs = read(run / '01_inputs/input_ledger.json')
    profiles = read(run / '02_profiles/all_profiles_native.json')
    catalog = read(snapshot / 'catalog/datasets.json')
    sheet = xlrd.open_workbook(str(snapshot / catalog['source_export'])).sheet_by_index(0)
    headers = sheet.row_values(0)
    metadata = {}
    for i in range(1, sheet.nrows):
        row = dict(zip(headers, sheet.row_values(i)))
        metadata[normalized_url(row['文章访问路径'])] = {
            'department': str(row['所属部门']).strip() or '官网部门未标注',
            'dataset': str(row['数据集名称']).strip() or '官网数据集未标注',
            'theme': str(row['所属主题']).strip() or '官网主题未标注',
        }
    original_counts, logical_counts = Counter(), Counter()
    roots = {}
    missing_metadata = 0
    for item in inputs:
        meta = metadata.get(normalized_url(item['source'].get('dataset_url')))
        if meta is None:
            missing_metadata += 1
            meta = {'department': '官网部门未匹配', 'dataset': '官网数据集未匹配', 'theme': '官网主题未匹配'}
        roots[item['file_id']] = meta
        original_counts[(str(item.get('kind') or '未知格式').upper(), meta['department'], meta['dataset'])] += 1
    for i, p in enumerate(sorted(profiles, key=lambda x: x['file_id']), 1):
        source = p.get('source') or {}
        kind = source.get('source_kind')
        method = {'native_document_or_ocr_text': '正文提取／OCR', 'xml_xpath_fields': 'XML 表格展开',
                  'gdal_filegdb_attributes': '地理库属性提取'}.get(kind)
        if not method:
            method = '原始附件' if p['file_id'] == (p.get('root_file_id') or p['file_id']) else '压缩包展开／派生文件'
        logical_counts[(str(p.get('kind') or '未知类型').upper(), method, f'逻辑文件 {i:05d}')] = 1
    records_per_root = Counter()
    for p in profiles:
        records_per_root[p.get('root_file_id') or p['file_id']] += int(p.get('records') or 0)
    if set(records_per_root) - set(roots):
        raise ValueError('Unknown source root')
    db = duckdb.connect(str(run / '07_entities/results.duckdb'), read_only=True)
    try:
        db.execute("SET memory_limit='8GB'")
        db.execute('SET threads=2')
        db.execute('SET preserve_insertion_order=false')
        classification_path = str(run / '10_classification_v1/classification.duckdb').replace("'", "''")
        db.execute("ATTACH '" + classification_path + "' AS refined (READ_ONLY)")
        db.execute('CREATE TEMP TABLE root_themes(root_file_id VARCHAR, theme VARCHAR)')
        db.executemany('INSERT INTO root_themes VALUES (?, ?)', [(k, v['theme']) for k, v in roots.items()])
        # Group by source record, not event: a multi-event record is counted once.
        # Use all source links, including sources of conservatively merged events.
        db.execute('''CREATE TEMP TABLE per_record_events AS
          SELECT s.record_id,
            string_agg(DISTINCT e.event_type, '|' ORDER BY e.event_type) AS category,
            string_agg(DISTINCT e.status, '|' ORDER BY e.status) AS stages
          FROM refined.classified_event_sources s
          JOIN refined.classified_events e USING(event_id) GROUP BY s.record_id''')
        grouped = db.execute('''SELECT t.theme, e.category, e.stages, r.status, count(*)
          FROM record_ledger r JOIN root_themes t USING(root_file_id)
          LEFT JOIN per_record_events e USING(record_id) GROUP BY 1,2,3,4''').fetchall()
        retained = dict(db.execute('SELECT root_file_id, count(*) FROM record_ledger GROUP BY 1').fetchall())
    finally:
        db.close()
    record_counts = Counter()
    for theme, category, stages, status, count in grouped:
        label, detail = record_labels(category, stages, status)
        record_counts[(theme, label, detail)] += count
    excluded = 0
    for root_id, total in records_per_root.items():
        count = total - retained.get(root_id, 0)
        if count < 0:
            raise ValueError('Record ledger exceeds profiled input')
        if count:
            record_counts[(roots[root_id]['theme'], '已筛选排除', '筛选或字段方案明确排除')] += count
            excluded += count
    expected = [final['downloaded_attachments'], final['native']['logical_files'], final['audit']['known_logical_records']]
    counts_list = [original_counts, logical_counts, record_counts]
    if [sum(x.values()) for x in counts_list] != expected or excluded != final['preparation']['excluded_records']:
        raise ValueError('Hierarchy counts do not match final audit')
    definitions = [
        ('attachments', '原始附件', '份', ['文件格式', '来源部门', '数据集'],
         '按实际识别格式、官网“所属部门”和数据集归组；数量为已接收附件个数。'),
        ('logical', '逻辑文件', '个', ['文件类型', '生成方式', '具体文件'],
         '包含原始附件、展开成员与转换结果；末层为一一对应的匿名文件编号，不公开原文件名或路径。'),
        ('records', '业务记录', '条', ['业务主题', '事件类别', '细分类别'],
         '主题来自官网目录；每条逻辑记录只计一次。细分为真实事件阶段或处理去向，多类别记录单列；包含排除和待复核记录，不等于已确认企业事实。'),
    ]
    output.mkdir(parents=True, exist_ok=True)
    modes = []
    for (key, label, unit, levels, note), counts in zip(definitions, counts_list):
        tree = tree_from_counts(label, counts)
        document = {'schema_version': 2, 'kind': 'verified_exploration_hierarchy', 'mode': key,
                    'unit': unit, 'levels': levels, 'note': note, 'tree': tree}
        encoded = (json.dumps(document, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
        name = 'sunburst-' + key + '.json'
        (output / name).write_bytes(encoded)
        modes.append({'id': key, 'label': label, 'unit': unit, 'levels': levels, 'total': tree['value'],
                      'file': name, 'sha256': hashlib.sha256(encoded).hexdigest(), 'note': note})
    result = {'schema_version': 2, 'kind': 'verified_exploration_manifest', 'default_mode': 'attachments',
              'snapshot_at': final['created_at'], 'source_commit': final['source_commit'],
              'semantic_accuracy_evaluated': False, 'modes': modes,
              'checks': {'all_mode_totals_reconciled': True, 'records_counted_once': True,
                         'excluded_records': excluded, 'unmatched_catalog_attachments': missing_metadata},
              'record_detail_basis': 'official_catalog_theme_then_exclusive_event_category_then_stage_or_processing_outcome',
              'source': 'completed_private_run_20261107'}
    (output / 'event-hierarchy.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'totals': expected, 'unmatched_metadata': missing_metadata, 'files': [m['file'] for m in modes]}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--snapshot-dir', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    build(args.run_dir, args.snapshot_dir, args.output_dir)
