import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bank_data.bulk_references import ReferenceClient
from bank_data.bulk_rows import materialize_file
from bank_data.bulk_semantics import resolve_pending,finalize_validation
from bank_data.common import dump
from bank_data.scan import scan


class ReferenceFlowTests(unittest.TestCase):
    def test_one_ambiguous_subject_is_reviewed_without_repeating_the_batch(self):
        class Transport:
            calls=0
            def __init__(self,*args):self.cache=Path(args[3])
            def request(self,system,payload,contract,maximum):return {'messages':[{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]}
            def call(self,requests):
                Transport.calls+=1;answers=[]
                for request in requests:
                    payload=json.loads(request['messages'][0]['content']);records={}
                    for row in payload['records']:
                        name=row['cells']['企业名称'];kind='person' if name=='合成个人' else 'business'
                        records[row['record_key']]={'status':'NO_EVENT','entities':[{'role':'subject','kind':kind,'name':{'field':'企业名称','value':name}}]}
                    answers.append({'ok':True,'response':{'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'records':records},ensure_ascii=False)}}]}})
                return answers
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);raw=base/'input';raw.mkdir();work=base/'work'
            (raw/'合成混合主体.csv').write_bytes('企业名称\n合成甲公司\n合成个人\n合成乙公司\n'.encode('utf-8'))
            profiles,_=scan(raw,work/'02_profiles');profile=profiles[0];scope=profile['cards'][0]['scope_id']
            dump(work/'04_plans/scopes'/(scope+'.json'),{'signature':'synthetic','plan':{'mode':'row_llm','reason':'synthetic','entities':[],'events':[]}})
            mapped=materialize_file((profile,str(work)));dump(work/'06_validation/mapping_files.json',[mapped])
            with patch('bank_data.bulk_references.BatchClient',Transport):
                report=resolve_pending(profiles,work,['http://127.0.0.1:18080/v1'],'synthetic',raw,client_class=ReferenceClient)
            self.assertEqual(Transport.calls,1);self.assertEqual(report['completed_records'],3)
            finalize_validation(profiles,work)
            directory=work/'06_validation'/profile['file_id'];values=[json.loads(line) for line in (directory/'record_results.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual([v['status'] for v in values],['NO_EVENT','REVIEW','NO_EVENT'])
            self.assertIn('subject_kind_person_requires_review',[e['reason'] for e in values[1]['reason']])
            self.assertFalse(values[1]['model_provenance']['canonical_validation_passed'])
            for value in values:
                provenance=value['model_provenance']
                self.assertTrue(Path(provenance['request_path']).exists());self.assertTrue(Path(provenance['raw_response_path']).exists())
            self.assertEqual([values[i]['entities'][0]['name']['value'] for i in [0,2]],['合成甲公司','合成乙公司'])


if __name__=='__main__':unittest.main()
