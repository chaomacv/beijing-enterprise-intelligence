import json
from pathlib import Path
import tempfile
import unittest

from bank_data.bulk_dedup import prepare_view,expand_file,semantic_key
from bank_data.bulk_rows import materialize_file
from bank_data.bulk_semantics import finalize_validation,load_row
from bank_data.common import dump,file_hash
from bank_data.scan import scan


class ExactDedupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.raw=self.root/'input';self.raw.mkdir();self.work=self.root/'work'
        path=self.raw/'合成拟认定.csv';path.write_text('企业名称,日期\n合成甲公司,2026-01-01\n合成甲公司,2026-01-01\n合成甲公司,2026-01-01\n',encoding='utf-8')
        self.profiles,_=scan(self.raw,self.work/'02_profiles');self.profile=self.profiles[0];self.card=self.profile['cards'][0]
        dump(self.work/'04_plans/scopes'/(self.card['scope_id']+'.json'),{'signature':'synthetic',
            'plan':{'mode':'row_llm','reason':'synthetic fixture','entities':[],'events':[]}})
        mapped=materialize_file((self.profile,str(self.work)));dump(self.work/'06_validation/mapping_files.json',[mapped])

    def tearDown(self):self.temp.cleanup()

    def checkpoint(self,view,review=False):
        fid=self.profile['file_id'];task=json.loads((view/'06_validation'/fid/'pending_llm.jsonl').read_text(encoding='utf-8').splitlines()[0]);row=load_row(self.work,task)
        value={'record_id':task['record_id'],'status':'REVIEW' if review else 'EXTRACTED','entities':[],'events':[]}
        if not review:
            value['entities']=[{'role':'subject','name':{'field':'企业名称','value':row['cells']['企业名称']},'credit_code':None,'address':None}]
            value['events']=[{'subject_index':0,'event_type':'innovation','status':'proposed','date':{'field':'日期','value':row['cells']['日期']},
                'amount':None,'document_no':None,'evidence':[{'field':'__filename__','value':self.card['filename']}]}]
        dump(self.work/'06_validation'/fid/'llm_results'/(task['record_id']+'.json'),
            {'signature':'synthetic','task':task,'result':value,'errors':[],'method':'local_llm_record'})
        return task

    def test_index_infers_one_content_and_preserves_all_three_source_records(self):
        rawpath=self.work/'05_records'/self.profile['file_id']/'rows.jsonl';before=file_hash(rawpath)
        view,manifests,summary=prepare_view(self.profiles,self.work)
        self.assertEqual((summary['source_records'],summary['unique_model_records'],summary['exact_duplicate_records']),(3,1,2))
        self.assertEqual(json.loads((self.work/'06_validation/mapping_files.json').read_text(encoding='utf-8'))[0]['pending_llm'],3)
        self.assertEqual(json.loads((view/'06_validation/mapping_files.json').read_text(encoding='utf-8'))[0]['pending_llm'],1)
        representative=self.checkpoint(view)
        result=expand_file((str(self.work),manifests[0],{self.card['scope_id']:self.card},'synthetic'))
        self.assertEqual(result['source_records'],3);self.assertEqual(result['newly_expanded_records'],2)
        summary=finalize_validation(self.profiles,self.work);self.assertEqual(summary['records'],3)
        values=[json.loads(line) for line in (self.work/'06_validation'/self.profile['file_id']/'record_results.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual(len({v['record_id'] for v in values}),3)
        self.assertEqual({v['row'] for v in values},{2,3,4});self.assertTrue(all(v['status']=='EXTRACTED' for v in values))
        self.assertEqual(file_hash(rawpath),before)
        checkpoints=[json.loads(p.read_text(encoding='utf-8')) for p in (self.work/'06_validation'/self.profile['file_id']/'llm_results').glob('*.json')]
        self.assertEqual(sum(v.get('representative_record_id')==representative['record_id'] for v in checkpoints),2)

    def test_scope_context_and_relative_statements_prevent_unsafe_reuse(self):
        task={'scope_id':'scope-A','record_id':'record-A'};cells={'text':'合成甲公司'}
        key=semantic_key(task,cells,{'note':'拟认定'},'card')
        self.assertNotEqual(key,semantic_key({**task,'scope_id':'scope-B'},cells,{'note':'拟认定'},'card'))
        self.assertNotEqual(key,semantic_key(task,cells,{'note':'已撤销'},'card'))
        self.assertEqual(key,semantic_key({**task,'record_id':'record-B'},cells,{'note':'拟认定'},'card'))
        self.assertNotEqual(semantic_key(task,{'text':'同上'}, {},'card'),semantic_key({**task,'record_id':'record-B'},{'text':'同上'}, {},'card'))

    def test_changed_source_is_rejected_even_when_a_review_result_has_no_references(self):
        view,manifests,_=prepare_view(self.profiles,self.work);self.checkpoint(view,review=True)
        path=self.work/'05_records'/self.profile['file_id']/'rows.jsonl';lines=path.read_text(encoding='utf-8').splitlines();last=json.loads(lines[-1]);last['cells']['企业名称']='合成乙公司'
        lines[-1]=json.dumps(last,ensure_ascii=False);path.write_bytes(('\n'.join(lines)+'\n').encode('utf-8'))
        with self.assertRaisesRegex(ValueError,'Source content changed'):
            expand_file((str(self.work),manifests[0],{self.card['scope_id']:self.card},'synthetic'))

    def test_unchanged_view_resumes_and_a_changed_raw_store_rebuilds_the_index(self):
        _,first,_=prepare_view(self.profiles,self.work);_,second,summary=prepare_view(self.profiles,self.work)
        self.assertEqual(first[0]['fingerprint'],second[0]['fingerprint']);self.assertEqual(summary['unique_model_records'],1)
        path=self.work/'05_records'/self.profile['file_id']/'rows.jsonl';lines=path.read_text(encoding='utf-8').splitlines();last=json.loads(lines[-1]);last['cells']['企业名称']='合成乙公司'
        lines[-1]=json.dumps(last,ensure_ascii=False);path.write_bytes(('\n'.join(lines)+'\n').encode('utf-8'))
        _,third,summary=prepare_view(self.profiles,self.work)
        self.assertNotEqual(first[0]['fingerprint'],third[0]['fingerprint']);self.assertEqual(summary['unique_model_records'],2)


if __name__=='__main__':unittest.main()
