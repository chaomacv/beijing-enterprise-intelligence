"""Publish only verified category counts; never synthesize business subcategories."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from bank_data.event_taxonomy import LABELS

root=Path(__file__).resolve().parents[1]/'showcase/assets'
source=json.loads((root/'event-classification.json').read_text(encoding='utf-8'))
counts={key:sum(r['observed_events'] for r in source['category_status'] if r['event_type']==key) for key in LABELS}
assert sum(counts.values())==source['legacy_qualification_events']
result={'schema_version':1,'kind':'verified_event_hierarchy','unit':'event_observation',
    'scope':'completed_1884_file_subset_legacy_qualification_only',
    'snapshot_at':source['created_at'],'source':'event-classification.json',
    'excluded_other_event_observations':source['total_events']-sum(counts.values()),
    'available_levels':['event_category'],'pending_levels':['business_subcategory','event_label'],
    'tree':{'id':'all','name':'全部事件（当前十类范围）','value':sum(counts.values()),
      'children':[{'id':key,'name':LABELS[key],'value':value} for key,value in counts.items()]}}
(root/'event-hierarchy.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Verified event hierarchy:',sum(counts.values()),'observations; no invented descendants.')
