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
            'events':[{'subject_index':0,'event_type':'innovation','status':'proposed','date':'日期','evidence':['正文','__filename__']}]},'r1':{'status':'NO_EVENT'}}}

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
            if mode=='wrong_subject':
                with self.assertRaises(ValueError):unpack(value,self.rows,self.card)
            else:
                issues={};result=unpack(value,self.rows,self.card,issues)[0]
                self.assertEqual(result['status'],'REVIEW');self.assertEqual(result['events'],[]);self.assertIn('original-A',issues)

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
            issues={};result=unpack(value,rows,self.card,issues)[0]
            self.assertEqual(result['status'],'REVIEW');self.assertEqual(result['entities'],[]);self.assertEqual(result['events'],[])
            self.assertIn(rows[0]['record_id'],issues)

    def test_school_and_english_legal_names_are_retained_without_matching_person_substrings(self):
        from bank_data.bulk_references import recognizable_organization
        for name in ['合成第二中学','合成第三小学','Synthetic Example Ltd.']:
            rows=copy.deepcopy(self.rows);rows[0]['cells']['企业名称']=name
            value=copy.deepcopy(self.value);row=value['records']['r0'];row['status']='NO_EVENT';row.pop('events');row['entities'][0]['name']['value']=name
            self.assertEqual(unpack(value,rows,self.card)[0]['entities'][0]['name']['value'],name)
        self.assertFalse(recognizable_organization('Vincent'))

    def test_one_ambiguous_subject_preserves_the_other_valid_record(self):
        rows=copy.deepcopy(self.rows);rows[1]['cells']['姓名']='合成个人'
        value=copy.deepcopy(self.value);value['records']['r1']={'status':'NO_EVENT','entities':[{'role':'subject','kind':'person','name':{'field':'姓名','value':'合成个人'}}]}
        issues={};result=unpack(value,rows,self.card,issues)
        self.assertEqual([v['status'] for v in result],['EXTRACTED','REVIEW'])
        self.assertEqual(result[0]['entities'][0]['name']['value'],'合成甲公司')
        self.assertEqual(set(issues),{'original-B'})

    def test_html_input_is_projected_and_the_response_remains_bound_to_its_raw_cell(self):
        from bank_data.source_views import PREFIX
        cache=self.cache;rows=copy.deepcopy(self.rows)
        rows[0]['cells']['正文']='<p>合成甲公司拟认定为<span>创新型</span>中小企业</p>'
        before=copy.deepcopy(rows);value=copy.deepcopy(self.value)
        value['records']['r0']['events'][0]['evidence'][0]=PREFIX+'正文'
        class Transport:
            def __init__(self,*args,**kwargs):self.cache=cache
            def request(self,system,payload,contract,maximum):return {'messages':[{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]}
            def call(self,requests):return [{'ok':True,'response':{'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value,ensure_ascii=False)}}]}} for _ in requests]
        with patch('bank_data.bulk_references.BatchClient',Transport):client=ReferenceClient()
        request=client.request('unused',{'context':self.card,'records':rows},{},2048)
        payload=json.loads(request['messages'][0]['content'])
        self.assertNotIn('正文',payload['records'][0]['cells']);self.assertIn(PREFIX+'正文',payload['records'][0]['cells'])
        response=client.call([request])[0];self.assertTrue(response['ok']);self.assertEqual(rows,before)
        self.assertEqual(client.content(response)['results'][0]['events'][0]['evidence'][0]['value'],'合成甲公司拟认定为创新型中小企业')
        self.assertEqual(client.record_provenance['original-A']['input_field_views'][0]['source_field'],'正文')

    def test_missing_optional_values_can_be_null_without_fabricating_empty_references(self):
        value=copy.deepcopy(self.value);row=value['records']['r0']
        row['entities'][0].update(credit_code=None,address=None);row['events'][0].update(date=None,amount=None,document_no=None)
        result=unpack(value,self.rows,self.card)[0]
        self.assertEqual(result['status'],'EXTRACTED');self.assertIsNone(result['entities'][0]['credit_code'])
        self.assertIsNone(result['entities'][0]['address']);self.assertIsNone(result['events'][0]['date'])
        self.assertEqual(result['events'][0]['evidence'][0]['value'],self.rows[0]['cells']['正文'])

    def test_generic_categories_and_document_titles_are_not_named_organizations(self):
        from bank_data.bulk_references import recognizable_organization
        for name in ['中小企业','小微企业','有限公司','中小企业声明函','政府采购文件','LLC','合成高新技术企业认定','合成行政处罚','合成监督检查结果']:
            self.assertFalse(recognizable_organization(name))
        self.assertTrue(recognizable_organization('合成中小企业服务有限公司'))

    def test_invalid_unreferenced_authority_is_audited_without_discarding_valid_subject(self):
        rows=copy.deepcopy(self.rows);rows[0]['cells']['结果标题']='合成行政处罚'
        value=copy.deepcopy(self.value);row=value['records']['r0']
        row['entities'].insert(0,{'role':'authority','kind':'institution','name':{'field':'结果标题','value':'合成行政处罚'}})
        row['events'][0]['subject_index']=1;rejected={};retained={}
        result=unpack(value,rows,self.card,{},rejected,retained)[0]
        self.assertEqual(result['status'],'EXTRACTED');self.assertEqual(len(result['entities']),1)
        self.assertEqual(result['events'][0]['subject_index'],0);self.assertEqual(retained['original-A'],[1])
        self.assertEqual(rejected['original-A'][0]['entity_index'],0)

    def test_invalid_referenced_authority_cannot_be_pruned_to_change_event_subject(self):
        rows=copy.deepcopy(self.rows);rows[0]['cells']['结果标题']='合成行政处罚'
        value=copy.deepcopy(self.value);value['records']['r0']['entities'][0]={'role':'authority','kind':'institution','name':{'field':'结果标题','value':'合成行政处罚'}}
        issues={};result=unpack(value,rows,self.card,issues)[0]
        self.assertEqual(result['status'],'REVIEW');self.assertEqual(result['events'],[]);self.assertIn('original-A',issues)


if __name__=='__main__':unittest.main()
