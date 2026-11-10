"""Export allowlisted aggregates for the public notebook gallery; never copy source rows."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from bank_data.event_taxonomy import LABELS, VERSION

FORMATS = {
    'csv': 'CSV', 'xls': 'Excel', 'xlsx': 'Excel', 'jsonl': 'JSONL · 派生',
    'xml': 'XML / RDF', 'rdf': 'XML / RDF', 'jpg': '影像',
    'legacy_word': 'Word', 'docx': 'Word', 'pdf': 'PDF',
    'unsupported_archive': '压缩包', 'rar': '压缩包',
    'txt': '文本 / HTML', 'html': '文本 / HTML', 'htm': '文本 / HTML',
}
STATES = {'PROFILED', 'CONTAINER', 'REVIEW', 'CONVERTED', 'EMPTY', 'COMPONENT'}
EVENTS = {
    'administrative_penalty': '行政处罚', 'business_abnormal': '经营异常',
    'environment': '环保监管', 'innovation': '科技认定',
    'operating_status': '经营状态', 'procurement': '采购中标',
    'qualification': '许可相关候选（旧口径）', 'subsidy': '政策支持', 'tax_credit': '税务信用',
}
BUCKETS = ['未知', '0', '1–10', '11–100', '101–1千', '1千–1万', '1万–10万', '10万–100万', '100万以上']

def bucket(value):
    if value in ('', None, 'None'):
        return 0
    n = int(value)
    assert n >= 0
    if n == 0:
        return 1
    for i, limit in enumerate([10, 100, 1000, 10000, 100000, 1000000], 2):
        if n <= limit:
            return i
    return 8

def build(profile_index, stage_summary, run_summary, progress, classification_summary):
    stage = json.loads(Path(stage_summary).read_text(encoding='utf-8'))
    run = json.loads(Path(run_summary).read_text(encoding='utf-8'))
    points = json.loads(Path(progress).read_text(encoding='utf-8'))
    classified = json.loads(Path(classification_summary).read_text(encoding='utf-8'))
    assert stage['partial_only'] and not stage['final_pipeline_complete']
    formats, bins = Counter(), Counter()
    with Path(profile_index).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        assert {'格式', '解析状态', '已知记录数'} <= set(reader.fieldnames)
        for row in reader:
            kind = FORMATS.get(row['格式'], '地理库组件' if row['解析状态'] == 'COMPONENT' else '其他')
            status = row['解析状态']
            assert status in STATES
            formats[kind, status] += 1
            bins[kind, status, bucket(row['已知记录数'])] += 1
    assert sum(formats.values()) == run['input']['logical_files']
    observed_events = stage['aggregates']['事件类别与阶段']
    assert sum(x['observed_events'] for x in observed_events) == stage['counts']['events']
    assert {x['event_type'] for x in observed_events} <= set(EVENTS)
    assert {x['status'] for x in observed_events} <= {'confirmed', 'proposed', 'unknown', 'removed', 'revoked'}
    assert classified['version'] == VERSION
    assert classified['total_events'] == stage['counts']['events']
    refined = classified['category_status']
    assert sum(x['observed_events'] for x in refined) == classified['total_events']
    assert sum(x['observed_events'] for x in refined if x['event_type'] in LABELS) == sum(x['observed_events'] for x in observed_events if x['event_type']=='qualification')
    assert not any(x['event_type']=='qualification' for x in refined)
    for kind in EVENTS.keys() - {'qualification'}:
        assert {(x['status'],x['observed_events']) for x in observed_events if x['event_type']==kind} == {(x['status'],x['observed_events']) for x in refined if x['event_type']==kind}
    for a, b in zip(points, points[1:]):
        assert a['at'] < b['at'] and a['completed'] <= b['completed']
    assert all(0 <= p['completed'] <= run['semantic_work']['representative_records'] for p in points)
    return {
        'schema_version': 2, 'kind': 'aggregate_notebook_gallery',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_commit': run['source_commit'], 'final_pipeline_complete': False,
        'corpus': {'snapshot_date': run['snapshot_date'], **run['input']},
        'subset': {'snapshot_at': stage['created_at'], 'files': stage['selected_files'],
                   'records': stage['selected_records'], 'events': stage['counts']['events'],
                   'profiles': stage['counts']['entities'], 'partial_only': True,
                   'semantic_accuracy_evaluated': False},
        'formats': [{'format': f, 'status': s, 'files': n} for (f,s),n in sorted(formats.items())],
        'file_space': {'buckets': BUCKETS, 'bins': [
            {'format': f, 'status': s, 'bucket': b, 'files': n} for (f,s,b),n in sorted(bins.items())]},
        'events': [{'type': x['event_type'], 'label': {**EVENTS,**LABELS}[x['event_type']],
                    'status': x['status'], 'count': x['observed_events'],
                    'associated_profiles': x['associated_profiles']} for x in refined],
        'taxonomy': {'version': classified['version'], 'updated_at': classified['created_at'],
                     'basis': classified['basis'], 'total_events': classified['total_events'],
                     'event_types': sorted({x['event_type'] for x in refined}),
                     'category_count': len({x['event_type'] for x in refined}),
                     'unique_licences': None, 'unique_registered_enterprises': None,
                     'category_profiles': [{'type':x['event_type'],'count':x['associated_profiles']} for x in classified['category_profiles']]},
        'record_statuses': [{'status': s, 'count': n} for s,n in sorted(stage['record_statuses'].items())],
        'identities': [{'status': x['identity_status'], 'count': x['profiles']}
                       for x in stage['aggregates']['主体身份状态']],
        'matching': [{'reason': x['match_reason'], 'mentions': x['mentions']}
                     for x in stage['aggregates']['主体身份关联方式']],
        'dedup': {'source_records': run['preparation']['pending_semantic_source_records'],
                  **run['semantic_work']},
        'progress': {'total': run['semantic_work']['representative_records'],
                     'points': [{'at': p['at'], 'completed': p['completed']} for p in points],
                     'series_kind': 'observed_processing_snapshots_not_business_events'},
    }

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['profile-index', 'stage-summary', 'run-summary', 'progress', 'classification-summary', 'output']:
        p.add_argument('--' + name, required=True, type=Path)
    args = p.parse_args()
    result = build(args.profile_index, args.stage_summary, args.run_summary, args.progress, args.classification_summary)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'logical_files': sum(x['files'] for x in result['formats']),
                      'subset_records': result['subset']['records'],
                      'spatial_bins': len(result['file_space']['bins']),
                      'progress_points': len(result['progress']['points'])}))
