import argparse
import csv
import json
import os
from pathlib import Path

from .extract import RuleBaseline
from .prepare import prepare
from .store import Store


def demo_input(root):
    root.mkdir(parents=True, exist_ok=True)
    header = ['企业名称', '统一社会信用代码', '注册地址', '事件内容', '状态', '日期', '处罚决定文书号']
    rows = {
        '合成示例_行政处罚.csv': [
            ['合成示例甲科技有限公司', '', '北京市测试区示例路1号', '行政处罚：罚款', '已处罚', '2026-01-01', 'SYNTHETIC-P-001'],
            ['合成示例乙科技有限公司', '', '北京市测试区示例路2号', '检查合格', '合格', '2026-01-02', '']],
        '合成示例_高新技术认定.csv': [
            ['合成示例甲科技有限公司', '', '北京市测试区示例路1号', '高新技术企业认定', '已认定', '2026-02-01', ''],
            ['合成示例乙科技有限公司', '', '北京市测试区示例路2号', '高新技术企业拟认定', '拟认定', '2026-02-02', '']],
    }
    for name, data in rows.items():
        with (root / name).open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f); writer.writerow(header); writer.writerows(data)
    with (root / '合成示例_树木统计.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f); writer.writerow(['序号', '公园', '树木数量']); writer.writerow(['1', '虚构公园', '10'])


def main():
    p = argparse.ArgumentParser(description='北京公开文件后处理；真实数据与模型权重放在仓库外。')
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'run'):
        s = sub.add_parser(name)
        s.add_argument('--input', type=Path, required=True)
        s.add_argument('--work-dir', type=Path, required=True)
        if name == 'run':
            s.add_argument('--backend', choices=('local', 'rules'), default='local')
            s.add_argument('--endpoint', default=os.environ.get('BANK_LLM_ENDPOINT', 'http://127.0.0.1:8000/v1'))
            s.add_argument('--model', default=os.environ.get('BANK_LLM_MODEL', 'Qwen/Qwen3-8B'))
            s.add_argument('--tokenizer-dir', type=Path)
    demo = sub.add_parser('demo')
    demo.add_argument('--work-dir', type=Path, required=True)
    args = p.parse_args()
    from .pipeline import run
    store = Store(args.work_dir)
    try:
        if args.command == 'demo':
            # Synthetic inputs are stored beside, not inside, the processing output.
            source = args.work_dir.resolve().parent / (args.work_dir.name + '_synthetic_input')
            demo_input(source)
            prepared = prepare(store, source)
            result = run(store, RuleBaseline())
            result['input_kind'] = 'synthetic_demo_not_real_bank_data'
        else:
            prepared = prepare(store, args.input)
            if args.command == 'prepare': result = prepared
            else:
                if args.backend == 'rules': backend = RuleBaseline()
                else:
                    from .llm import LocalQwen
                    backend = LocalQwen(store, args.endpoint, args.model, args.tokenizer_dir)
                result = run(store, backend)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        store.close()
    return 0
