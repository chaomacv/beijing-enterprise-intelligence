"""Deterministic synthetic enterprises for explaining tag similarity, never real relations."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from bank_data.event_taxonomy import LABELS

families=[
 ['business_permit','product_registration','regulatory_inspection'],
 ['enterprise_qualification','personnel_qualification','project_approval'],
 ['equipment_inspection','industry_assessment','qualification_application'],
 ['business_permit','equipment_inspection','qualification_review'],
]
companies=[]
for group,base in enumerate(families):
    for i in range(6):
        tags=base[:2] if i==0 else list(base)
        if i in (2,4):tags.append(families[(group+1)%4][0])
        if i==5:tags+=families[(group+2)%4][:2]
        companies.append({'id':f'demo-{len(companies)+1:02}',
                          'name':f'合成企业{len(companies)+1:02}', 'tags':sorted(set(tags))})
value={'schema_version':1,'kind':'synthetic_enterprise_network',
       'provenance':'generated_method_example_not_real_enterprise_relationships',
       'categories':[{'id':key,'label':label} for key,label in LABELS.items()],
       'companies':companies,'similarity':'binary_jaccard_excluding_qualification_review',
       'real_entity_overlap_available':False}
out=Path(__file__).resolve().parents[1]/'showcase/assets/network-demo.json'
out.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Synthetic network:',len(companies),'enterprises; no real business connections.')
