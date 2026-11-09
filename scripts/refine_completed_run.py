"""Append classification to a completed full run, optionally waiting for its audit.

This is a one-shot downstream stage, not a model restart or a recurring job.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from bank_data.event_taxonomy import refine


def run(root, output, wait=False):
    root, output = Path(root).resolve(), Path(output).resolve()
    status_path = root / 'classification_job.json'
    def status(state, **extra):
        value={'status':state,'updated_at':datetime.now(timezone.utc).isoformat(),
               'output':str(output),**extra}
        temp=status_path.with_suffix('.tmp')
        temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        temp.replace(status_path)
    try:
        while True:
            original=json.loads((root/'run_status.json').read_text(encoding='utf-8'))
            state=original['status']
            if state in ('COMPLETED','COMPLETED_WITH_REVIEW'):
                audit=json.loads((root/'audit.json').read_text(encoding='utf-8'))
                if not (audit['all_readable_records_accounted_for'] and audit['all_original_files_accounted_for']):
                    raise ValueError('Original run did not pass coverage accounting')
                break
            if state=='FAILED' or not wait:
                raise ValueError('Original full run is not complete: '+state)
            status('WAITING_FOR_ORIGINAL_AUDIT',original_stage=original['current_stage'])
            time.sleep(30)
        status('RUNNING')
        receipt=refine(root/'07_entities/results.duckdb',output)
        status('COMPLETE',version=receipt['version'],events=receipt['total_events'])
        return receipt
    except Exception as error:
        status('FAILED',error=type(error).__name__,detail=str(error)[:240])
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--wait',action='store_true')
    args=parser.parse_args()
    run(args.work_dir,args.output,args.wait)
