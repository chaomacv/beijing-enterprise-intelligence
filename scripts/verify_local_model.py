"""Synthetic regression probe; this is not a real-data quality benchmark."""
import argparse
from collections import Counter
import json
from pathlib import Path

from bank_data.cli import demo_input
from bank_data.common import dump
from bank_data.extract import RuleBaseline
from bank_data.workflow import workflow


def assess(root):
    decisions=json.loads((root/'file_decisions.json').read_text(encoding='utf-8'))
    records=json.loads((root/'facts/record_results.json').read_text(encoding='utf-8'))
    events=[event for row in records for event in row['events']]
    checks={
        'file_dispositions':Counter(row['status'] for row in decisions)=={'KEEP':2,'DROP':1},
        'all_four_selected_records':len(records)==4,
        'one_passed_inspection_without_event':sum(row['status']=='NO_EVENT' for row in records)==1,
        'no_unresolved_selected_records':all(row['status']!='REVIEW' for row in records),
        'exact_event_types_and_stages':Counter((e['event_type'],e['status']) for e in events)=={
            ('administrative_penalty','confirmed'):1,('innovation','confirmed'):1,('innovation','proposed'):1},
    }
    return {'kind':'synthetic_regression_not_accuracy_benchmark','checks':checks,'passed':all(checks.values())}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--backend',choices=['local','rules'],default='local')
    parser.add_argument('--endpoint',default='http://127.0.0.1:8000/v1')
    parser.add_argument('--model')
    parser.add_argument('--tokenizer-dir',type=Path)
    args=parser.parse_args()
    if args.backend=='local' and (not args.model or not args.tokenizer_dir):
        parser.error('Local inference requires --model and --tokenizer-dir')
    root=args.work_dir.resolve()
    source=root.parent/(root.name+'_synthetic_input')
    demo_input(source)
    def factory(store):
        if args.backend=='rules':return RuleBaseline()
        from bank_data.llm import LocalQwen
        return LocalQwen(store,args.endpoint,args.model,args.tokenizer_dir)
    summary=workflow(source,root,factory)
    report={**assess(root),'backend':summary['backend'],'model':args.model if args.backend=='local' else None}
    dump(root/'regression_report.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
