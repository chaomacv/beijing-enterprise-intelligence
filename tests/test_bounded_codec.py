import copy,json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bank_data.bulk_bounded import normalize,wire_schema,BoundedReferenceClient
from bank_data.bulk_references import schema


class BoundedCodecTests(unittest.TestCase):
    def setUp(self):
        self.rows=[{'record_id':'source-A','sheet':'Sheet1','row':2,'cells':{'企业名称':'合成甲公司','结果':'拟认定'},'context':{}}]
        self.card={'filename':'合成拟认定.csv','sheet':'Sheet1','columns':['企业名称','结果'],'source':{}}
        self.entity={'role':'subject','kind':'business','name':{'field':'企业名称','value':'合成甲公司'},'credit_code':None,'address':None}
        event={'subject_slot':'e7','event_type':'innovation','status':'proposed','evidence':{'结果':True,'企业名称':False},'date':None}
        self.value={'records':{'r0':{'status':'EXTRACTED','entities':{'e0':self.entity,'e7':copy.deepcopy(self.entity)},'events':{'v0':event,'v7':copy.deepcopy(event)}}}}

    def test_exact_duplicate_slots_merge_and_event_subjects_are_remapped(self):
        result,reasons,slots=normalize(self.value,schema(self.rows));row=result['records']['r0']
        self.assertEqual(len(row['entities']),1);self.assertEqual(len(row['events']),1)
        self.assertEqual(row['events'][0]['subject_index'],0);self.assertEqual(row['events'][0]['evidence'],['结果'])
        self.assertEqual(slots['r0'],{'e0':0,'e7':0});self.assertEqual(reasons,{})

    def test_foreign_and_missing_subject_slots_are_rejected(self):
        value=copy.deepcopy(self.value);value['records']['r0']['entities']['e8']=self.entity
        with self.assertRaises(ValueError):normalize(value,schema(self.rows))
        value=copy.deepcopy(self.value);value['records']['r0']['events']['v0']['subject_slot']='e6'
        with self.assertRaisesRegex(ValueError,'missing subject'):normalize(value,schema(self.rows))

    def test_reported_capacity_excess_is_reviewed_without_publishing_partial_facts(self):
        value=copy.deepcopy(self.value);value['records']['r0']['needs_review']=True
        result,reasons,_=normalize(value,schema(self.rows))
        self.assertEqual(result['records']['r0'],{'status':'REVIEW'});self.assertIn('r0',reasons)

    def test_wire_schema_uses_finite_objects_instead_of_unbounded_output_arrays(self):
        contract=wire_schema(schema(self.rows));props=contract['properties']['records']['properties']['r0']['properties']
        self.assertEqual(set(props['entities']['properties']),{'e'+str(i) for i in range(8)})
        self.assertEqual(set(props['events']['properties']),{'v'+str(i) for i in range(8)})
        self.assertEqual(props['events']['properties']['v0']['properties']['evidence']['type'],'object')

    def test_raw_wire_response_and_slot_mapping_survive_canonical_conversion(self):
        value=self.value
        class Transport:
            def __init__(self,*args,**kwargs):self.cache=Path(args[3]);self.tokenizer=object();self.token_counts={}
            def request(self,system,payload,contract,maximum):return {'messages':[{'role':'user','content':json.dumps(payload)}],'response_format':{'json_schema':{'schema':contract}}}
            def call(self,requests):return [{'ok':True,'response':{'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}]}} for _ in requests]
        with tempfile.TemporaryDirectory() as temporary,patch('bank_data.bulk_bounded.BatchClient',Transport):
            client=BoundedReferenceClient('http://127.0.0.1:18080/v1','synthetic',Path(temporary),Path(temporary)/'model_cache')
            request=client.request('unused',{'context':self.card,'records':self.rows},{},2048);answer=client.call([request])[0]
            self.assertTrue(answer['ok']);result=client.content(answer)['results'][0]
            self.assertEqual(result['record_id'],'source-A');self.assertEqual(len(result['entities']),1);self.assertEqual(result['events'][0]['subject_index'],0)
            provenance=client.record_provenance['source-A'];stored=json.loads(Path(provenance['raw_response_path']).read_text(encoding='utf-8'))
            self.assertEqual(json.loads(stored['response']['choices'][0]['message']['content']),value)
            self.assertEqual(provenance['wire_subject_slots'],{'e0':0,'e7':0})

    def test_duplicate_wire_keys_are_rejected_before_normalization(self):
        class Transport:
            def __init__(self,*args,**kwargs):self.cache=Path(args[3]);self.tokenizer=object();self.token_counts={}
            def request(self,system,payload,contract,maximum):return {'synthetic':'duplicate-key-request'}
            def call(self,requests):return [{'ok':True,'response':{'choices':[{'finish_reason':'stop','message':{'content':'{"records":{"r0":{"status":"NO_EVENT"},"r0":{"status":"NO_EVENT"}}}'}}]}}]
        with tempfile.TemporaryDirectory() as temporary,patch('bank_data.bulk_bounded.BatchClient',Transport):
            client=BoundedReferenceClient('http://127.0.0.1:18080/v1','synthetic',Path(temporary),Path(temporary)/'model_cache')
            request=client.request('unused',{'context':self.card,'records':self.rows},{},2048);answer=client.call([request])[0]
            self.assertFalse(answer['ok']);self.assertIn('Duplicate JSON object key',answer['error'])
            self.assertFalse(client.record_provenance['source-A']['canonical_validation_passed'])


if __name__=='__main__':unittest.main()
