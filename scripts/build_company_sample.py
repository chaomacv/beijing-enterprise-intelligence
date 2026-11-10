"""Select 100 real coded corporate profiles; publish aliases and event counts only."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from build_real_network import ORDER, COLORS
from build_exploration_hierarchies import LABELS

SEED = 'enterprise-network-100-v1'


def select(candidates, size=100):
    def key(c):
        return hashlib.sha256((SEED + c['entity_id']).encode()).hexdigest()
    ordered = sorted(candidates, key=key)
    selected, seen, codes = [], set(), set()

    def take(c):
        if c['entity_id'] not in seen and c['valid_code'] not in codes and len(selected) < size:
            selected.append(c)
            seen.add(c['entity_id'])
            codes.add(c['valid_code'])
    # Preserve category coverage before filling each tag-richness stratum in turn.
    frequencies = Counter(t for c in ordered for t in c['counts'] if t != 'qualification_review')
    for tag, _ in sorted(frequencies.items(), key=lambda item: (item[1], item[0])):
        match = next((c for c in ordered if tag in c['counts'] and c['entity_id'] not in seen and c['valid_code'] not in codes), None)
        if match:
            take(match)
    buckets = defaultdict(list)
    for c in ordered:
        tags = sorted(t for t in c['counts'] if t != 'qualification_review')
        buckets[(tags[0], min(len(tags), 3))].append(c)
    for rank in range(max(map(len, buckets.values()), default=0)):
        for bucket in sorted(buckets):
            if rank < len(buckets[bucket]):
                take(buckets[bucket][rank])
    if len(selected) != size:
        raise ValueError('Not enough distinct eligible companies')
    return sorted(selected, key=key)


def build(run, output, private_mapping):
    import duckdb
    final = json.loads((run / '交付汇总/全量汇总.json').read_text())
    db = duckdb.connect(str(run / '07_entities/results.duckdb'), read_only=True)
    try:
        db.execute("SET memory_limit='8GB'")
        db.execute('SET threads=2')
        db.execute('SET preserve_insertion_order=false')
        path = str(run / '10_classification_v1/classification.duckdb').replace("'", "''")
        db.execute("ATTACH '" + path + "' AS refined (READ_ONLY)")
        db.execute('''CREATE TEMP TABLE eligible AS SELECT entity_id,valid_code,names FROM entities
          WHERE valid_code IS NOT NULL AND list_contains(kinds,'business')
          AND (list_contains(roles,'subject') OR list_contains(roles,'supplier') OR list_contains(roles,'buyer'))
          AND NOT list_contains(observed_source_quality,'OCR_UNVERIFIED')
          AND EXISTS(SELECT 1 FROM unnest(names) n(name) WHERE n.name LIKE '%公司%')''')
        db.execute('''CREATE TEMP TABLE company_counts AS
          SELECT t.entity_id,t.event_type,sum(t.observed_events)::BIGINT AS n
          FROM refined.classified_profile_tags t JOIN eligible USING(entity_id)
          WHERE event_type<>'qualification_review' GROUP BY 1,2''')
        eligible_count = db.sql('SELECT count(DISTINCT entity_id) FROM company_counts').fetchone()[0]
        db.execute('''CREATE TEMP TABLE candidate_ids AS WITH richness AS (
          SELECT entity_id,count(*) AS kinds FROM company_counts GROUP BY 1), ranked AS (
          SELECT c.entity_id,row_number() OVER(PARTITION BY c.event_type,least(r.kinds,3)
            ORDER BY sha256(c.entity_id || 'enterprise-network-100-v1')) AS rank
          FROM company_counts c JOIN richness r USING(entity_id))
          SELECT DISTINCT entity_id FROM ranked WHERE rank<=12''')
        rows = db.sql('''SELECT t.entity_id,t.event_type,t.status,t.observed_events,e.valid_code,e.names
          FROM refined.classified_profile_tags t JOIN candidate_ids USING(entity_id)
          JOIN eligible e USING(entity_id) ORDER BY 1,2,3''').fetchall()
    finally:
        db.close()
    candidates = {}
    for entity, tag, status, count, code, names in rows:
        c = candidates.setdefault(entity, {'entity_id': entity, 'valid_code': code, 'names': names,
                                           'counts': Counter(), 'stages': defaultdict(dict)})
        c['counts'][tag] += count
        c['stages'][tag][status] = count
    selected = select(list(candidates.values()))
    companies, mapping = [], []
    categories = ORDER + sorted(set(LABELS) - set(ORDER))
    for i, c in enumerate(selected, 1):
        alias = 'enterprise-' + str(i).zfill(3)
        counts = dict(sorted(c['counts'].items()))
        comparable = {k: n for k, n in counts.items() if k != 'qualification_review'}
        companies.append({'id': alias, 'label': '企业' + str(i).zfill(3),
                          'event_counts': counts, 'stage_counts': dict(c['stages']),
                          'event_count': sum(comparable.values()), 'tag_count': len(comparable),
                          'review_event_count': counts.get('qualification_review', 0)})
        mapping.append({'sample_id': alias, 'entity_id': c['entity_id'], 'valid_code': c['valid_code'], 'names': c['names']})
    result = {'schema_version': 1, 'kind': 'real_enterprise_sample', 'sample_size': 100,
              'snapshot_at': final['created_at'], 'source': 'completed_private_run_corrected_profile_tags',
              'population_profiles': final['counts']['entities'], 'eligible_coded_companies': eligible_count,
              'selection': 'deterministic_category_and_tag_richness_stratified_demonstration_not_random_population_sample',
              'selection_seed': SEED, 'identity_basis': 'company_named_business_profile_checksum_valid_code_not_registry_verified',
              'anonymized': True, 'one_node_per_company': True, 'event_unit': 'source_event_observations_including_uncertain_stages',
              'excluded_similarity_tags': ['qualification_review'],
              'categories': [{'id': tag, 'label': LABELS[tag], 'color': COLORS[i % 10]} for i, tag in enumerate(categories)],
              'companies': companies}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    private_mapping.parent.mkdir(parents=True, exist_ok=True)
    private_mapping.write_text(json.dumps({'selection_seed': SEED, 'companies': mapping}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    private_mapping.chmod(0o600)
    print(json.dumps({'sample_size': len(companies), 'eligible_companies': eligible_count,
                      'distinct_codes': len({c['valid_code'] for c in selected}),
                      'tag_coverage': len(set(t for c in companies for t in c['event_counts'])),
                      'max_tags': max(c['tag_count'] for c in companies),
                      'max_events': max(c['event_count'] for c in companies)}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--private-mapping', required=True, type=Path)
    a = p.parse_args()
    build(a.run_dir, a.output, a.private_mapping)
