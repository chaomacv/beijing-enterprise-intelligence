"""Refresh public aggregate snapshots from allowlisted fields of final reports."""
import argparse
import json
from pathlib import Path


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def write(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sync(final_path, classification_path, assets):
    final, classified = read(final_path), read(classification_path)
    run, gallery = read(assets / 'run-summary.json'), read(assets / 'gallery-data.json')
    if not all(final['audit'][k] for k in ['all_original_files_accounted_for', 'all_readable_records_accounted_for']):
        raise ValueError('Final coverage audit required')
    if not final['exports_round_trip_validated'] or classified['total_events'] != final['counts']['events']:
        raise ValueError('Final export/classification reconciliation required')
    run.update(updated_at=final['created_at'], pipeline_status='completed_with_review', final_counts=final['counts'])
    run['validation'].update(final_audit_passed=True, exports_round_trip_validated=True,
                             classification_events_conserved=True)
    gallery['final_pipeline_complete'] = True
    gallery['generated_at'] = final['created_at']
    gallery['subset'].update(snapshot_at=final['created_at'], files=final['downloaded_attachments'],
                              records=final['counts']['record_ledger'], events=final['counts']['events'],
                              profiles=final['counts']['entities'], partial_only=False)
    labels = {r['type']: r['label'] for r in gallery['events']}
    gallery['events'] = [{'type': r['event_type'], 'label': labels[r['event_type']], 'status': r['status'],
                          'count': r['observed_events'], 'associated_profiles': r['associated_profiles']}
                         for r in classified['category_status']]
    gallery['taxonomy'].pop('legacy_qualification_events', None)
    gallery['taxonomy'].pop('refined_types', None)
    gallery['taxonomy'].pop('downgraded_confirmed', None)
    gallery['taxonomy'].update(updated_at=classified['created_at'], total_events=classified['total_events'],
        event_types=sorted({r['event_type'] for r in classified['category_status']}),
        category_count=len({r['event_type'] for r in classified['category_status']}),
        category_profiles=[{'type': r['event_type'], 'count': r['associated_profiles']} for r in classified['category_profiles']])
    gallery['record_statuses'] = [{'status': r['status'], 'count': r['records']} for r in final['record_statuses']]
    gallery['identities'] = [{'status': r['identity_status'], 'count': r['profiles']} for r in final['identity_statuses']]
    gallery['matching'] = [{'reason': r['match_reason'], 'mentions': r['mentions']} for r in final['identity_match_reasons']]
    completed = {'at': final['created_at'], 'completed': run['semantic_work']['representative_records']}
    gallery['progress']['points'] = [p for p in gallery['progress']['points'] if p['at'] < completed['at']] + [completed]
    public = {'schema_version': 1, 'kind': 'completed_run_public_aggregates', 'completed_at': final['created_at'],
              'pipeline_status': 'completed_with_review', 'source_commit': final['source_commit'],
              'model': {'name': final['model'], 'weights': final['weights'], 'deployment': 'local'},
              'input': run['input'], 'counts': final['counts'], 'record_statuses': final['record_statuses'],
              'plans': run['plans'], 'preparation': run['preparation'], 'semantic_work': run['semantic_work'],
              'identity_statuses': final['identity_statuses'], 'events_by_type_and_stage': classified['category_status'],
              'validation': {'file_coverage_passed': True, 'known_record_coverage_passed': True,
                             'exports_round_trip_validated': True, 'semantic_accuracy_evaluated': False},
              'boundaries': {'unreadable_logical_files': final['audit']['unsupported_or_unreadable_files'],
                             'upstream_failed_downloads': final['upstream_failed_download_tasks_not_present'],
                             'profiles_include_provisional_identities': True, 'current_licence_validity_verified': False}}
    classification_public = {key: classified[key] for key in ['version', 'created_at', 'basis',
        'semantic_accuracy_evaluated', 'total_events', 'unique_licences', 'unique_registered_enterprises',
        'category_status', 'category_profiles']}
    classification_public['category_count'] = gallery['taxonomy']['category_count']
    for name, value in [('run-summary.json', run), ('gallery-data.json', gallery), ('final-results.json', public),
                        ('event-classification.json', classification_public)]:
        write(assets / name, value)
    print('Public final aggregates synchronized:', final['counts'])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--final-summary', required=True, type=Path)
    p.add_argument('--classification-summary', required=True, type=Path)
    p.add_argument('--assets-dir', required=True, type=Path)
    a = p.parse_args()
    sync(a.final_summary, a.classification_summary, a.assets_dir)
