"""Export the complete tag-signature census, with no enterprise identifiers.

One node represents every profile with exactly the same observed category set.
Counts include provisional identities and profiles without usable network tags.
"""
import argparse
import json
from pathlib import Path
from build_exploration_hierarchies import LABELS

ORDER = ['business_permit', 'equipment_inspection', 'personnel_qualification', 'qualification_review',
         'industry_assessment', 'enterprise_qualification', 'product_registration',
         'qualification_application', 'project_approval', 'regulatory_inspection']
COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b',
          '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']


def build(run, output):
    import duckdb
    final = json.loads((run / '交付汇总/全量汇总.json').read_text())
    db = duckdb.connect(str(run / '07_entities/results.duckdb'), read_only=True)
    try:
        db.execute("SET memory_limit='8GB'")
        db.execute('SET threads=2')
        db.execute('SET preserve_insertion_order=false')
        path = str(run / '10_classification_v1/classification.duckdb').replace("'", "''")
        db.execute("ATTACH '" + path + "' AS refined (READ_ONLY)")
        # Membership is counted once per entity, independently of event/stage count.
        rows = db.execute('''WITH signatures AS (
          SELECT entity_id, string_agg(DISTINCT event_type, '|' ORDER BY event_type) AS tags
          FROM refined.classified_profile_tags GROUP BY entity_id)
          SELECT coalesce(s.tags,''), count(*),
            count(*) FILTER(WHERE e.identity_status='provisional')
          FROM entities e LEFT JOIN signatures s USING(entity_id)
          GROUP BY 1 ORDER BY 2 DESC, 1''').fetchall()
    finally:
        db.close()
    nodes = [{'id': 'group-' + str(i + 1).zfill(3), 'tags': tags.split('|') if tags else [],
              'profiles': count, 'provisional_profiles': provisional}
             for i, (tags, count, provisional) in enumerate(rows)]
    categories = ORDER + sorted(set(LABELS) - set(ORDER))
    if sum(n['profiles'] for n in nodes) != final['counts']['entities']:
        raise ValueError('Not all profiles are represented')
    if any(set(n['tags']) - set(categories) for n in nodes):
        raise ValueError('Unknown category')
    result = {'schema_version': 2, 'kind': 'complete_real_profile_tag_census',
              'source': 'completed_private_run_20261107_corrected_profile_tags',
              'snapshot_at': final['created_at'], 'profiles': final['counts']['entities'],
              'events': final['counts']['events'], 'sampled': False,
              'representation': 'exact_tag_signature_groups_all_profiles_counted_once',
              'identity_unit': 'associated_profile_including_provisional_not_unique_registered_company',
              'semantic_accuracy_evaluated': False, 'excluded_similarity_tags': ['qualification_review'],
              'similarity': 'binary_jaccard_of_observed_categories_not_business_relationship',
              'categories': [{'id': key, 'label': LABELS[key], 'color': COLORS[i % 10],
                              'profiles': sum(n['profiles'] for n in nodes if key in n['tags'])}
                             for i, key in enumerate(categories)],
              'groups': nodes,
              'checks': {'all_profiles_accounted_for': True, 'no_enterprise_identifiers_exported': True}}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'profiles': result['profiles'], 'groups': len(nodes), 'sampled': False,
                      'without_tags': sum(n['profiles'] for n in nodes if not n['tags'])}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    build(a.run_dir, a.output)
