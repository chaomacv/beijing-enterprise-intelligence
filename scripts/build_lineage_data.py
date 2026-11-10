"""Build the public, count-conserving lineage story from completed aggregate exports."""
import argparse
import hashlib
import json
from pathlib import Path


def build(assets):
    def read(name):
        return json.loads((assets / name).read_text(encoding='utf-8'))
    final, run, gallery = [read(name) for name in ['final-results.json', 'run-summary.json', 'gallery-data.json']]
    if not run['validation']['final_audit_passed'] or not gallery['final_pipeline_complete']:
        raise ValueError('Completed batch required')
    c = {'known': final['input']['known_logical_records'],
         'excluded': final['preparation']['excluded_records'],
         'retained': final['preparation']['retained_records'],
         'mapped': final['preparation']['field_mapped_records'],
         'semantic': final['preparation']['pending_semantic_source_records'],
         'representatives': final['semantic_work']['representative_records'],
         'reused': final['semantic_work']['exact_duplicate_source_records']}
    outcomes = {row['status']: row['records'] for row in final['record_statuses']}
    equations = [{'total': 'known', 'parts': ['excluded', 'retained']},
                 {'total': 'retained', 'parts': ['mapped', 'semantic']},
                 {'total': 'semantic', 'parts': ['representatives', 'reused']}]
    for row in equations:
        assert c[row['total']] == sum(c[key] for key in row['parts'])
    assert sum(outcomes.values()) == c['retained'] == final['counts']['record_ledger']
    assert c['representatives'] == gallery['progress']['total']
    n = lambda key: f'{c[key]:,}'
    stages = [
        {'title': '固定输入', 'input': '5,200 份已接收原始附件',
         'output': '固定附件、来源及哈希台账；原件继续保留。',
         'flow': ['5,200 份附件进入本批；上游 22 个下载失败项另记，不计入成功输入。'],
         'files': ['01_inputs/input_ledger.json', '01_inputs/snapshot_integrity.json']},
        {'title': '解析与抽样', 'input': '5,200 份原附件及其容器成员',
         'output': '11,701 个逻辑文件 → 13,281 个作用域 → 43,653,625 条已知逻辑记录。',
         'flow': ['展开压缩包、读取表格和转换文档，保留来源关系。',
                  '43,653,625 按逻辑文件计数，尚未做相关性分流；65 个不可可靠读取的逻辑文件另列复核。'],
         'files': ['02_profiles/文件总表.csv', '02_profiles/all_profiles_native.json']},
        {'title': '文件筛选', 'input': '文件名、表头及分层样本组成的文件卡片',
         'output': '逐作用域保留、排除或复核判断，传入字段方案。',
         'flow': ['模型先判断文件主题，不能把抽样行数当作完整文件记录数。',
                  '排除记录在03–05合并对账，不把总排除量虚分到单个筛选步骤。'],
         'files': ['03_screen/筛选总表.csv', '03_screen/scopes/']},
        {'title': '字段方案', 'input': '相关或需继续规划的作用域与样本',
         'output': '9,551 份方案：映射 1,347／主体信息 408／逐行语义 382／排除 6,939／复核 475。',
         'flow': ['模型理解字段和条件，确定哪些记录可由程序执行、哪些需要逐条语义处理。',
                  '方案数是作用域级计量，不与记录条数直接相减。'],
         'files': ['04_plans/字段方案总表.csv', '04_plans/config.json']},
        {'title': '完整读取与分流', 'input': f"{n('known')} 条已知逻辑记录及03–04决策",
         'output': f"排除 {n('excluded')}；保留 {n('retained')} = 字段方案 {n('mapped')} + 复杂语义来源 {n('semantic')}。",
         'flow': [f"{n('known')} = {n('excluded')} + {n('retained')}",
                  f"{n('retained')} = {n('mapped')} + {n('semantic')}",
                  '保留记录保存完整原值、上下文和稳定编号；排除有独立台账。'],
         'files': ['05_records/<file_id>/rows.jsonl', '05_records/<file_id>/contexts.json']},
        {'title': '抽取、复用与回填', 'input': f"字段方案 {n('mapped')} 条；复杂语义来源 {n('semantic')} 条",
         'output': f"复杂来源按完整内容分成 {n('representatives')} 个代表，复用 {n('reused')} 条来源；推理后回填到 {n('semantic')} 条。两通道合并为 {n('retained')} 条台账。",
         'flow': [f"{n('semantic')} = {n('representatives')} + {n('reused')}",
                  '仅同文件、同表、完整字段和语境一致才复用；逐条核对来源后回填。',
                  f"{n('representatives')} 是语义通道工作量，不是最终仅剩的记录数。",
                  f"合并后：EXTRACTED {outcomes['EXTRACTED']:,}／NO_EVENT {outcomes['NO_EVENT']:,}／REVIEW {outcomes['REVIEW']:,}。"],
         'files': ['06_validation/内容去重总表.csv', '06_validation/content_indices/', '06_validation/<file_id>/record_results.jsonl']},
        {'title': '身份关联', 'input': '8,800,229 条主体提及及其来源证据',
         'output': '5,202,714 个主体画像，包含 4,364,721 个临时身份。',
         'flow': ['代码校验、名称与非空地址用于保守关联；冲突和近名保留复核。',
                  '一条记录可以含多个提及；画像数不是逻辑记录数，也不等于独立登记企业数。'],
         'files': ['07_entities/results.duckdb', '07_entities/entity_mentions.parquet']},
        {'title': '结果导出', 'input': '逐条台账、主体关联与事件候选',
         'output': '15,861,277 条台账／5,202,714 个画像／5,968,620 条事件观察／6,331,400 条事件来源。',
         'flow': ['画像、事件与来源使用不同计量单位，不能相加或画成记录持续缩减。',
                  '分类修正保留原事件ID与来源，修正后的分类标签另存。'],
         'files': ['08_results/record_ledger.parquet', '08_results/profiles.parquet', '08_results/events.parquet', '08_results/event_sources.parquet']},
        {'title': '复核与覆盖对账', 'input': f"5,200 份原附件、{n('known')} 条已知逻辑记录及导出结果",
         'output': f"{n('retained')} 条处理台账 + {n('excluded')} 条显式排除 = {n('known')} 条已知记录全部有去向。",
         'flow': ['导出回读与数量守恒通过；文件失败、结构问题及语义待复核分别保留。',
                  f"REVIEW {outcomes['REVIEW']:,} 条包含在处理台账中，不从分母再次扣除。"],
         'files': ['audit.json', '09_review/record_review.parquet', '交付汇总/全量汇总.json']},
    ]
    points = [
        ('parsed', '解析总量', 'known', '条已知逻辑记录', 1, [stages[1]['output'], '原始附件与逻辑文件的统计口径不同，保留原附件关系。']),
        ('retained', '保留', 'retained', '条保留记录', 4, [f"显式排除 {n('excluded')} 条，保留 {n('retained')} 条。", stages[4]['flow'][0]]),
        ('semantic', '语义来源', 'semantic', '条复杂来源记录', 4, [f"{n('mapped')} 条走字段方案；{n('semantic')} 条进入逐条语义通道。", stages[4]['flow'][1]]),
        ('representatives', '内容代表', 'representatives', '个内容代表', 5, [f"精确分组：{n('representatives')} 个代表 + {n('reused')} 条重复来源。", stages[5]['flow'][1]]),
        ('restored', '来源回填', 'semantic', '条复杂来源记录', 5, ['代表推理完成后，逐来源核对并回填，恢复原始来源粒度。', f"{n('representatives')} 个推理结果服务于 {n('semantic')} 条来源，不删除重复记录。"]),
        ('ledger', '合并台账', 'retained', '条处理台账记录', 7, [f"字段方案 {n('mapped')} + 回填语义来源 {n('semantic')} = {n('retained')}。", '提取、无事件和待复核三类都保留独立去向。']),
        ('accounted', '覆盖对账', 'known', '条已对账的已知记录', 8, [stages[8]['output'], '最终数量回到全批覆盖口径；处理台账与排除台账分别保留。']),
    ]
    result = {'schema_version': 1, 'kind': 'completed_batch_lineage',
              'source_commit': final['source_commit'], 'completed_at': final['completed_at'],
              'hash_basis': 'utf8_lf_newlines',
              'source_sha256': {name: hashlib.sha256((assets / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                                for name in ['final-results.json', 'run-summary.json', 'gallery-data.json']},
              'counts': c, 'outcomes': outcomes, 'equations': equations,
              'flow_axis': 'processing_stage_order_not_elapsed_time',
              'flow_points': [{'id': ident, 'name': name, 'count': c[key], 'count_key': key,
                               'unit': unit, 'step': step, 'details': details}
                              for ident, name, key, unit, step, details in points],
              'stages': stages, 'progress': gallery['progress'],
              'timing_note': '阶段图按处理顺序排列，不虚构阶段完成时刻。时间图只使用真实观测；末点为最终验收时已全部完成，并非精确推理结束时刻。'}
    (assets / 'data-lineage.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Exported seven lineage points, nine stages and actual progress observations.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets-dir', type=Path, default=Path('showcase/assets'))
    build(parser.parse_args().assets_dir)
