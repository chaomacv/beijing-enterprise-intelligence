"""Export public catalog statistics and at most ten source pages per theme.

Reads the fixed official catalog only; never exports attachment rows or login URLs.
"""
import argparse
import hashlib
import html
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

THEMES = ['经济建设', '信用服务', '财税金融', '旅游住宿', '交通服务', '餐饮美食',
          '医疗健康', '文体娱乐', '消费购物', '生活安全', '气象服务', '教育科研',
          '社会保障', '劳动就业', '生活服务', '房屋住宅', '政府机构与社会团体',
          '环境与资源保护', '企业服务', '农业农村']


def public_url(value):
    parts = urlsplit(str(value).strip())
    if parts.scheme not in ('http', 'https') or parts.hostname != 'data.beijing.gov.cn':
        raise ValueError('Expected official public source page')
    if not parts.path.startswith('/zyml/') or parts.query or parts.fragment or parts.username:
        raise ValueError('Source page must not contain authentication or query values')
    return urlunsplit(('https', 'data.beijing.gov.cn', parts.path, '', ''))


def select_samples(rows, limit=10):
    """Evenly spaced, deterministic catalog samples; all rows when <= limit."""
    ordered = sorted(rows, key=lambda row: (row['name'], row['url']))
    if len(ordered) <= limit:
        return ordered
    return [ordered[i * (len(ordered) - 1) // (limit - 1)] for i in range(limit)]


def build(snapshot, run, output, batch_summary):
    import xlrd
    catalog_file = snapshot / 'catalog/datasets.json'
    catalog = json.loads(catalog_file.read_text(encoding='utf-8'))
    export = snapshot / catalog['source_export']
    sheet = xlrd.open_workbook(str(export)).sheet_by_index(0)
    headers = sheet.row_values(0)
    expected = {public_url(row['dataset_url']) for row in catalog['datasets']}
    by_theme = {theme: [] for theme in THEMES}
    seen = set()
    for index in range(1, sheet.nrows):
        row = dict(zip(headers, sheet.row_values(index)))
        url = public_url(row['文章访问路径'])
        if url not in expected or url in seen:
            raise ValueError('Catalog export and downloaded catalog differ')
        seen.add(url)
        theme = str(row['所属主题']).strip()
        by_theme[theme].append({'name': html.unescape(str(row['数据集名称']).strip()),
                                'url': url, 'department': str(row['所属部门']).strip(),
                                'formats': str(row['格式类型']).strip()})
    if seen != expected:
        raise ValueError('Incomplete catalog export')
    final = json.loads((run / '交付汇总/全量汇总.json').read_text(encoding='utf-8'))
    # Counts are cross-checked against the completed public batch contract.
    public_run = json.loads(batch_summary.read_text(encoding='utf-8'))
    if not final['audit']['all_original_files_accounted_for']:
        raise ValueError('Completed input audit required')
    themes = [{'name': theme, 'count': len(by_theme[theme]),
               'samples': select_samples(by_theme[theme])} for theme in THEMES]
    examples = [
        ('鲜羊肉价格.csv', '商品、市场、价格', '低相关', '鲜羊肉价格'),
        ('婚姻登记机关.csv', '机关、地址、电话', '低相关', '婚姻登记机关'),
        ('企业处罚公示.pdf', '企业名称、处罚文号', '高相关', '行政处罚信用公示信息'),
        ('中标企业名单.zip', '中标单位、项目、金额', '高相关', '中标公告'),
        ('科技独角兽企业名单.docx', '企业名称、行业、认定年份', '高相关', '独角兽'),
    ]
    all_rows = [row for rows in by_theme.values() for row in rows]
    result = {'schema_version': 1, 'kind': 'public_catalog_overview',
              'snapshot_date': '2026-11-07', 'catalog_sha256': hashlib.sha256(export.read_bytes()).hexdigest(),
              'dataset_count': len(seen), 'sample_limit': 10,
              'sampling': '名称排序后等距取样；不超过10个全部保留，不代表相关性排名',
              'link_kind': 'official_dataset_download_page_not_authenticated_attachment_url',
              'themes': themes, 'examples': []}
    if public_run['corpus']['catalog_datasets'] != len(seen) or not public_run['final_pipeline_complete']:
        raise ValueError('Public batch summary and catalog do not match')
    result['batch'] = {k: public_run['corpus'][k] for k in ['attachments', 'logical_files', 'known_logical_records', 'upstream_failed_downloads']}
    for filename, fields, relevance, term in examples:
        matches = sorted((row for row in all_rows if term in row['name']), key=lambda row: (row['name'] != term, row['name']))
        if not matches:
            raise ValueError('No real source for example: ' + term)
        result['examples'].append({'filename': filename, 'fields': fields, 'relevance': relevance,
                                   'illustrative': True, 'source': matches[0]})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'datasets': len(seen), 'themes': len(themes),
                      'published_source_links': sum(len(t['samples']) for t in themes)}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot-dir', required=True, type=Path)
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--batch-summary', required=True, type=Path)
    args = parser.parse_args()
    build(args.snapshot_dir, args.run_dir, args.output, args.batch_summary)
