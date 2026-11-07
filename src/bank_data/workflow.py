"""Resumable scan -> local-model screen -> selected-record extraction -> export."""
import json
import time
from collections import Counter
from pathlib import Path

from .common import dump, stable_id
from .extract import validate_screen
from .llm import ModelUnavailable
from .pipeline import run
from .prepare import prepare
from .scan import scan
from .store import Store


class ScreenedBackend:
    def __init__(self, backend, decisions):
        self.backend, self.decisions = backend, decisions
        self.name = backend.name + '-screen-' + stable_id(decisions)

    def screen(self, card):
        return self.decisions.get(card['scope_id'], {'decision':'REVIEW','event_types':[],
                                                     'reason':'No completed file decision','evidence_fields':[]})

    def extract(self, records, card): return self.backend.extract(records, card)


def workflow(input_dir, work_dir, backend_factory, through='run', workers=1, retry_review=False):
    root = Path(work_dir).resolve()
    started = time.monotonic()
    profiles, scan_report = scan(input_dir, root, workers=workers, retry_review=retry_review)
    report = {'stage':'scan','input_files':len(profiles),'scan':scan_report,'extraction_complete':False,
              'semantic_accuracy_evaluated':False}
    dump(root/'workflow_summary.json',report)
    if through == 'scan': return report
    store = Store(root/'facts')
    try:
        backend = backend_factory(store)
        cache = root/'screen-cache'; cache.mkdir(exist_ok=True)
        decisions, file_decisions = {}, []
        dump(root/'file_decisions.json',[])
        for index, profile in enumerate(profiles,1):
            outcomes = []
            for card in profile['cards']:
                key = stable_id(backend.name,card)
                saved = cache/(key+'.json')
                try:
                    decision = json.loads(saved.read_text(encoding='utf-8')) if saved.exists() else None
                    if decision is None or (retry_review and decision['decision']=='REVIEW'):
                        decision = backend.screen(card)
                    decision = validate_screen(decision,card)
                except ModelUnavailable: raise
                except Exception as error:
                    decision = {'decision':'REVIEW','event_types':[], 'reason':type(error).__name__, 'evidence_fields':[]}
                dump(saved,decision)
                decisions[card['scope_id']] = decision
                outcomes.append(decision['decision'])
            # Keeping one sheet keeps the whole file; additional sheets retain their decisions.
            overall = 'KEEP' if 'KEEP' in outcomes else ('REVIEW' if 'REVIEW' in outcomes or profile['status']=='REVIEW' else 'DROP')
            if profile['status']=='EMPTY': overall='EMPTY'
            file_decisions.append({'file_id':profile['file_id'],'path':profile['path'],
                'relative_path':profile['relative_path'],'status':overall,'records':profile['records'],
                'profile_status':profile['status'],'error':profile.get('error'),
                'scope_decisions':[{ 'scope_id':c['scope_id'], **decisions[c['scope_id']]} for c in profile['cards']]})
            if index % 10 == 0 or index == len(profiles):
                dump(root/'file_decisions.json',file_decisions)
                print(json.dumps({'stage':'screen','files':index,'total':len(profiles),
                                  'statuses':dict(Counter(p['status'] for p in file_decisions))}),flush=True)
        report.update(stage='screen',backend=backend.name,file_status_counts=dict(Counter(p['status'] for p in file_decisions)),
                      kept_files=sum(p['status']=='KEEP' for p in file_decisions))
        dump(root/'workflow_summary.json',report)
        if through == 'screen': return report
        kept = [p['path'] for p in file_decisions if p['status']=='KEEP']
        preparation = prepare(store,input_dir,selected_paths=kept)
        report.update(stage='prepare',preparation=preparation)
        dump(root/'workflow_summary.json',report)
        if through == 'prepare': return report
        result = run(store,ScreenedBackend(backend,decisions))
        report.update(stage='run',extraction_complete=True,result=result,seconds=round(time.monotonic()-started,2))
        # Complete means every source has a disposition, with unresolved work explicit.
        report['unresolved_files'] = sum(p['status']=='REVIEW' for p in file_decisions) + preparation['status_counts'].get('review',0)
        report['review_records'] = result['review_records']
        report['completed_with_review'] = bool(report['unresolved_files'] or report['review_records'])
        dump(root/'workflow_summary.json',report)
        return report
    finally: store.close()
