import json
from collections import defaultdict

from .common import dump, ontology, stable_id
from .extract import CONTRACT_VERSION, review_result, validate_results, validate_screen
from .resolve import resolve_results
from .llm import ModelUnavailable


def extract_batch(backend, records, card):
    """Bounded retries by recursive splitting. Oversize single records remain visible."""
    try:
        results = backend.extract(records, card)
        return validate_results({'results': results}, records, card), []
    except ModelUnavailable: raise
    except Exception as error:
        if len(records) > 1:
            split = len(records) // 2
            left, a = extract_batch(backend, records[:split], card)
            right, b = extract_batch(backend, records[split:], card)
            return left + right, a + b
        row = records[0]
        return [review_result(row['record_id'])], [{'record_id': row['record_id'],
                'reason': type(error).__name__, 'detail': str(error)[:240]}]


def run(store, backend):
    cards = [(r['id'], json.loads(r['card'])) for r in store.active_scopes()]
    run_key = stable_id(CONTRACT_VERSION, backend.name, ontology(), [card for _, card in cards])
    all_results, record_sources, issues, screening = [], {}, [], []
    expected = set()
    total = store.db.execute('SELECT COUNT(*) FROM records r JOIN active_files a ON r.file_id=a.id').fetchone()[0]
    last_progress = None
    def progress():
        nonlocal last_progress
        if last_progress == len(all_results): return
        last_progress = len(all_results)
        value = {'stage':'extract','completed_records':len(all_results),'total_records':total,
                 'final_exports_ready':False}
        dump(store.root/'progress.json',value)
        print(json.dumps(value),flush=True)
    progress()
    for scope_id, card in cards:
        for row in store.scope_records(scope_id):
            expected.add(row['record_id'])
            record_sources[row['record_id']] = {'file_id': card['file_id'], 'sheet': row['sheet'], 'row': row['row'], 'source': card['source']}
        saved = store.db.execute('SELECT result FROM decisions WHERE scope=? AND backend=?', (scope_id, run_key)).fetchone()
        if saved and json.loads(saved['result'])['decision'] != 'REVIEW':
            decision = json.loads(saved['result'])
        else:
            try: decision = validate_screen(backend.screen(card), card)
            except ModelUnavailable: raise
            except Exception as error:
                decision = {'decision': 'REVIEW', 'event_types': [], 'reason': type(error).__name__, 'evidence_fields': []}
                issues.append({'scope_id': scope_id, 'stage': 'screen', 'reason': type(error).__name__})
            store.db.execute('INSERT OR REPLACE INTO decisions VALUES(?,?,?)', (scope_id, run_key, json.dumps(decision, ensure_ascii=False)))
        screening.append({'scope_id': scope_id, **decision})
        if decision['decision'] != 'KEEP':
            all_results.extend({**review_result(r['record_id']), 'processing_status': 'FILE_EXCLUDED' if decision['decision'] == 'DROP' else 'REVIEW'} for r in store.scope_records(scope_id))
            progress()
            continue
        pending = []
        def process_pending(batch):
            results, errors = extract_batch(backend, batch, card)
            issues.extend(errors)
            for result in results:
                store.db.execute('INSERT OR REPLACE INTO extractions VALUES(?,?,?)', (result['record_id'], run_key, json.dumps(result, ensure_ascii=False)))
            all_results.extend(results)
            store.db.commit()
            progress()
        for row in store.scope_records(scope_id):
            cached = store.db.execute('SELECT result FROM extractions WHERE record_id=? AND backend=?', (row['record_id'], run_key)).fetchone()
            if cached and json.loads(cached['result'])['status'] != 'REVIEW':
                all_results.append(json.loads(cached['result']))
            else:
                pending.append(row)
            if len(pending) >= getattr(backend,'batch_size',12):
                process_pending(pending); pending = []
        if pending: process_pending(pending)
        progress()
    store.db.commit()
    observed = [r['record_id'] for r in all_results]
    if set(observed) != expected or len(observed) != len(set(observed)):
        raise RuntimeError('Coverage invariant failed; refusing to publish a partial profile')
    queued = {issue.get('record_id') for issue in issues}
    for result in all_results:
        if (result['status'] == 'REVIEW' and result.get('processing_status') != 'FILE_EXCLUDED'
                and result['record_id'] not in queued):
            issues.append({'record_id': result['record_id'], 'stage': 'extract',
                           'reason': 'Uncertain source or model decision',
                           'source': record_sources[result['record_id']]})
    resolver, mentions = resolve_results(all_results)
    lookup = {(m['record_id'], m['index']): m['entity_id'] for m in mentions}
    events, relationships = {}, []
    by_entity = defaultdict(list)
    for result in all_results:
        for index, event in enumerate(result['events']):
            entity_id = lookup[(result['record_id'], event['subject_index'])]
            doc = event['document_no']['value'] if event['document_no'] else None
            # Without a strong event number, keep source-specific facts rather than guessing duplicates.
            key = stable_id(entity_id,event['event_type'],doc,event['status'],event['date'],event['amount'],event['evidence']) if doc else stable_id(result['record_id'], index)
            if key not in events:
                events[key] = {'event_id': key, 'entity_id': entity_id, **event, 'sources': []}
                by_entity[entity_id].append(key)
            events[key]['sources'].append({'record_id': result['record_id'], **record_sources[result['record_id']], 'evidence': event['evidence']})
        # Co-occurrence alone is not a business/ownership relationship.
    profiles = []
    for eid, entity in resolver.entities.items():
        tags = []
        for event_id in by_entity[eid]:
            event = events[event_id]
            base = ontology()['events'][event['event_type']]['tag']
            prefix = {'proposed':'拟议：','removed':'已移出：','revoked':'已撤销：','unknown':'阶段未明：'}.get(event['status'],'')
            label = prefix + base
            tags.append({'label': label, 'event_status': event['status'], 'evidence_event_id': event_id})
        profiles.append({**entity, 'tags': tags, 'event_ids': by_entity[eid],
                         'coverage': 'unknown', 'credit_score': None,
                         'note': 'Observed source facts only; no lending decision or absence-of-risk inference.'})
    for name, values in [('screening.json', screening), ('record_results.json', all_results), ('entities.json', list(resolver.entities.values())),
                         ('entity_mentions.json', mentions), ('match_decisions.json', resolver.decisions),
                         ('events.json', list(events.values())), ('profiles.json', profiles), ('review_queue.json', issues),
                         ('source_index.json', record_sources)]:
        dump(store.root / name, values)
    summary = {'backend': backend.name, 'run_key': run_key, 'records': len(expected),
               'status_coverage_complete': True, 'entities': len(profiles), 'events': len(events),
               'review_records': sum(r['status'] == 'REVIEW' and r.get('processing_status') != 'FILE_EXCLUDED' for r in all_results),
               'excluded_records': sum(r.get('processing_status') == 'FILE_EXCLUDED' for r in all_results),
               'semantic_accuracy_evaluated': False, 'rule_baseline': backend.name.startswith('rules')}
    dump(store.root / 'run_summary.json', summary)
    dump(store.root/'progress.json',{'stage':'done','completed_records':len(all_results),
                                    'total_records':total,'final_exports_ready':True})
    return summary
