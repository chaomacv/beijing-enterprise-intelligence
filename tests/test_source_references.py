import copy,json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bank_data.bulk_references import ReferenceClient,schema,unpack


class SourceReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.cache=Path(self.temp.name)/'model_cache'
        self.rows=[{'record_id':'original-A','sheet':'Sheet1','row':2,'cells':{'企业名称':'合成甲公司','正文':'合成甲公司拟认定为创新型中小企业','日期':'2026-01-01'},'context':{}},
                   {'record_id':'original-B','sheet':'Sheet1','row':3,'cells':{'描述':'道路垃圾堆积'},'context':{}}]
        self.card={'filename':'合成拟认定.csv','sheet':'Sheet1','columns':['企业名称','正文','日期','描述'],'source':{}}
        self.value={'records':{'r0':{'status':'EXTRACTED','entities':[{'role':'subject','kind':'business','name':{'field':'企业名称','value':'合成甲公司'}}],
            'events':[{'subject_index':0,'event_type':'innovation','status':'proposed','date':'日期','evidence':[{'field':'正文','value':'拟认定为创新型中小企业'},'__filename__']}]},'r1':{'status':'NO_EVENT'}}}

    def test_sparse_fields_expand_to_canonical_source_values_and_original_ids(self):
        values=unpack(self.value,self.rows,self.card)
        self.assertEqual([v['record_id'] for v in values],['original-A','original-B'])
        self.assertEqual(values[0]['entities'][0]['name'],{'field':'企业名称','value':'合成甲公司'})
        self.assertIsNone(values[0]['entities'][0]['credit_code']);self.assertIsNone(values[0]['events'][0]['amount'])
        self.assertEqual(values[0]['events'][0]['date']['value'],'2026-01-01')
        self.assertEqual(values[1]['entities'],[]);self.assertEqual(values[1]['events'],[])

    def test_missing_foreign_or_renamed_slots_cannot_silently_drop_or_reassign_records(self):
        for change in ['missing','foreign']:
            value=copy.deepcopy(self.value);value['records'].pop('r1')
            if change=='foreign':value['records']['r2']={'status':'NO_EVENT'}
            with self.assertRaises(ValueError):unpack(value,self.rows,self.card)

    def test_absent_field_in_one_record_cannot_be_copied_from_another(self):
        value=copy.deepcopy(self.value);value['records']['r1']['entities']=[{'role':'subject','kind':'business','name':{'field':'企业名称','value':'合成甲公司'}}]
        with self.assertRaisesRegex(ValueError,'absent from its source'):unpack(value,self.rows,self.card)

    def test_invented_substring_and_filename_identity_are_rejected(self):
        value=copy.deepcopy(self.value);value['records']['r0']['entities'][0]['name']={'field':'企业名称','value':'合成乙公司'}
        with self.assertRaises(ValueError):unpack(value,self.rows,self.card)
        value=copy.deepcopy(self.value);value['records']['r0']['entities'][0]['name']='__filename__'
        with self.assertRaises(ValueError):unpack(value,self.rows,self.card)

    def test_status_and_subject_guards_still_apply_after_expansion(self):
        for mode in ['missing_event','wrong_subject','review_with_fact']:
            value=copy.deepcopy(self.value);row=value['records']['r0']
            if mode=='missing_event':row.pop('events')
            if mode=='wrong_subject':row['events'][0]['subject_index']=5
            if mode=='review_with_fact':row['status']='REVIEW'
            with self.assertRaises(ValueError):unpack(value,self.rows,self.card)

    def test_basic_entities_are_preserved_without_inventing_events(self):
        value=copy.deepcopy(self.value);row=value['records']['r0'];row['status']='NO_EVENT';row.pop('events')
        result=unpack(value,self.rows,self.card)[0]
        self.assertEqual(result['entities'][0]['name']['value'],'合成甲公司');self.assertEqual(result['events'],[])

    def test_transport_preserves_raw_cache_response_and_links_each_canonical_record(self):
        cache=self.cache
        class Transport:
            def __init__(self,*args,**kwargs):self.cache=cache
            def request(self,system,payload,contract,maximum):return {'messages':[{'role':'user','content':json.dumps(payload)}]}
            def call(transport,requests):return [copy.deepcopy(raw) for _ in requests]
        raw={'ok':True,'response':{'choices':[{'finish_reason':'stop','message':{'content':json.dumps(self.value)}}]}}
        before=copy.deepcopy(raw)
        with patch('bank_data.bulk_references.BatchClient',Transport):client=ReferenceClient()
        payload={'context':self.card,'records':self.rows}
        request=client.request('unused',payload,{},2048);answer=client.call([request])[0]
        self.assertTrue(answer['ok']);self.assertEqual(raw,before)
        self.assertEqual(client.content(answer)['results'][0]['record_id'],'original-A')
        self.assertIn('model_cache_key',client.record_provenance['original-A'])
        self.assertEqual(client.record_provenance['original-A']['model_cache_key'],client.record_provenance['original-B']['model_cache_key'])
        self.assertEqual(client.record_provenance['original-A']['entity_kinds'],['business'])
        self.assertTrue(client.record_provenance['original-A']['canonical_validation_passed'])
        provenance=client.record_provenance['original-A']
        self.assertEqual(json.loads(Path(provenance['request_path']).read_text(encoding='utf-8')),request)
        self.assertEqual(json.loads(Path(provenance['raw_response_path']).read_text(encoding='utf-8')),raw)
        rebuilt=client.request('unused',payload,{},2048);self.assertEqual(rebuilt,request);self.assertTrue(client.call([rebuilt])[0]['ok'])

    def test_duplicate_json_keys_are_rejected_at_the_adapter_boundary(self):
        cache=self.cache
        class Transport:
            def __init__(self,*args,**kwargs):self.cache=cache
            def request(self,*args):return {'synthetic':'request'}
            def call(self,requests):return [{'ok':True,'response':{'choices':[{'finish_reason':'stop','message':{'content':'{"records":{"r0":{"status":"NO_EVENT"},"r0":{"status":"NO_EVENT"},"r1":{"status":"NO_EVENT"}}}'}}]}}]
        with patch('bank_data.bulk_references.BatchClient',Transport):client=ReferenceClient()
        request=client.request('unused',{'context':self.card,'records':self.rows},{},2048)
        self.assertFalse(client.call([request])[0]['ok'])
        provenance=client.record_provenance['original-A']
        self.assertFalse(provenance['canonical_validation_passed']);self.assertTrue(Path(provenance['raw_response_path']).exists())

    def test_entity_names_require_explicit_source_substrings(self):
        value=copy.deepcopy(self.value);value['records']['r0']['entities'][0]['name']='企业名称'
        with self.assertRaises(ValueError):unpack(value,self.rows,self.card)

    def test_person_uncertain_and_unrecognizable_subjects_require_review(self):
        rows=copy.deepcopy(self.rows);rows[0]['cells']['企业名称']='合成个人'
        for kind in ['person','unknown','business']:
            value=copy.deepcopy(self.value);entity=value['records']['r0']['entities'][0];entity['kind']=kind;entity['name']['value']='合成个人'
            with self.assertRaises(ValueError):unpack(value,rows,self.card)

    def test_school_and_english_legal_names_are_retained_without_matching_person_substrings(self):
        from bank_data.bulk_references import recognizable_organization
        for name in ['合成第二中学','合成第三小学','Synthetic Example Ltd.']:
            rows=copy.deepcopy(self.rows);rows[0]['cells']['企业名称']=name
            value=copy.deepcopy(self.value);row=value['records']['r0'];row['status']='NO_EVENT';row.pop('events');row['entities'][0]['name']['value']=name
            self.assertEqual(unpack(value,rows,self.card)[0]['entities'][0]['name']['value'],name)
        self.assertFalse(recognizable_organization('Vincent'))


if __name__=='__main__':unittest.main()
