import ctypes.util
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from bank_data.bulk_aggregate import aggregate
from bank_data.bulk_inputs import prepare_inputs,member_name
from bank_data.bulk_plan import validate_plan
from bank_data.bulk_rows import apply_plan,materialize
from bank_data.bulk_semantics import finalize_validation
from bank_data.common import dump,file_hash
from bank_data.document_readers import document_records,text_fragments
from bank_data.scan import scan


def mapping():
    return {'mode':'map','reason':'synthetic fixture','entities':[{'role':'subject','kind':'business',
        'name_field':'企业名称','code_field':None,'address_field':'地址'}],
        'events':[{'subject_index':0,'event_type':'innovation','default_status':'confirmed','date_field':'日期',
            'amount_field':None,'document_field':None,'evidence_fields':['事件内容','__filename__'],
            'when':[],'unless':[],'status_rules':[]}]}


class BulkTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.raw=self.root/'input';self.raw.mkdir();self.work=self.root/'results'
    def tearDown(self):self.temp.cleanup()

    def test_long_text_fragments_preserve_every_character_and_positions(self):
        value='合成文字'*2000;spans=list(text_fragments(value));coverage=set()
        for start,end,text in spans:
            self.assertEqual(text,value[start:end]);coverage.update(range(start,end));self.assertLessEqual(len(text),2000)
        self.assertEqual(len(coverage),len(value))

    def test_budget_reduction_retains_head_middle_tail_samples(self):
        from bank_data.bulk_plan import reduce_sample
        rows=list(range(13));selected=reduce_sample(rows)
        self.assertEqual(selected[0],0);self.assertEqual(selected[-1],12)
        self.assertIn(6,selected)

    def test_archive_byte_names_preserve_original_encoding(self):
        original='目录/企业名单.csv'.encode('gb18030')
        name,metadata=member_name(original)
        import base64
        self.assertEqual(name,'目录/企业名单.csv')
        self.assertEqual(base64.b64decode(metadata['pathname_bytes_base64']),original)

    def test_multiline_model_json_keeps_column_values_and_rejects_broken_syntax(self):
        from bank_data.common import decode_model_json
        raw='{"field":"多行'+chr(10)+'表头","value":"制表'+chr(9)+'原值"}'
        data,repaired=decode_model_json(raw)
        self.assertTrue(repaired)
        self.assertEqual(data['field'],'多行\n表头')
        self.assertEqual(json.loads(json.dumps(data,ensure_ascii=False)),data)
        with self.assertRaises(json.JSONDecodeError):decode_model_json('{"field":}')

    def test_document_table_and_paragraphs_keep_source_structure(self):
        path=self.raw/'synthetic.docx'
        xml='''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
        <w:p><w:r><w:t>合成说明</w:t></w:r></w:p><w:tbl>
        <w:tr><w:tc><w:p><w:r><w:t>企业名称</w:t></w:r></w:p></w:tc></w:tr>
        <w:tr><w:tc><w:p><w:r><w:t>合成甲公司</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'''
        with zipfile.ZipFile(path,'w') as archive:archive.writestr('word/document.xml',xml)
        rows=list(document_records(path,'docx'))
        self.assertTrue(any(r[2].get('企业名称')=='合成甲公司' for r in rows))
        self.assertTrue(any(r[2].get('__text__')=='合成说明' for r in rows))

    @unittest.skipUnless(ctypes.util.find_library('archive') and importlib.util.find_spec('libarchive'),'native archive runtime not installed')
    def test_archive_members_have_lineage_and_unsafe_paths_are_not_extracted(self):
        path=self.raw/'synthetic.zip'
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('folder/名单.csv','企业名称,地址\n合成甲公司,示例路1号\n')
            archive.writestr('../escape.csv','企业名称\n不应写出\n')
        before=file_hash(path);profiles,_=scan(self.raw,self.work/'initial')
        expanded=prepare_inputs(profiles,self.work,workers=1)
        self.assertEqual(file_hash(path),before)
        self.assertEqual(len([p for p in expanded if p['status']=='PROFILED']),1)
        child=next(p for p in expanded if p['status']=='PROFILED')
        self.assertEqual(child['root_file_id'],profiles[0]['file_id'])
        self.assertEqual(child['source']['archive_member'],'folder/名单.csv')
        ledger=json.loads((self.work/'01_inputs/archive_members.json').read_text(encoding='utf-8'))
        self.assertTrue(any(v['status']=='REVIEW' for v in ledger))
        self.assertFalse((self.root/'escape.csv').exists())

    def test_source_mapping_preserves_proposed_stage_and_rejects_authority_code(self):
        card={'filename':'合成创新企业拟认定名单.csv','columns':['企业名称','地址','事件内容','日期','处罚机关代码']}
        plan=mapping();validate_plan(plan,card)
        row={'record_id':'synthetic','cells':{'企业名称':'合成甲公司','地址':'示例路1号','事件内容':'认定','日期':'2026年1月1日'}}
        result,reason,_=apply_plan(row,card,plan)
        self.assertEqual(result['events'][0]['status'],'proposed')
        self.assertEqual(result['events'][0]['date']['value'],'2026年1月1日')
        plan['entities'][0]['code_field']='处罚机关代码'
        with self.assertRaises(ValueError):validate_plan(plan,card)

    def test_contradictory_stage_mapping_is_rejected(self):
        card={'filename':'合成行政处罚.csv','columns':['企业名称','地址','事件内容','日期','状态']}
        plan=mapping();plan['events'][0]['status_rules']=[{'field':'状态','contains':'已处罚','status':'proposed'}]
        with self.assertRaises(ValueError):validate_plan(plan,card)

    def test_native_xml_keeps_repeated_fields_and_attributes(self):
        from bank_data.bulk_native import native_one
        path=self.raw/'合成监测.xml';path.write_text('<stations><station id="A"><reading>1</reading><reading>2</reading></station></stations>',encoding='utf-8')
        profile={'file_id':'synthetic-root','root_file_id':'synthetic-root','path':str(path),'sha256':file_hash(path),
            'kind':'xml','filename':path.name,'relative_path':path.name,'source':{},'status':'REVIEW','cards':[],'records':0}
        profiles=native_one((profile,str(self.work)))
        self.assertEqual(profiles[0]['status'],'CONVERTED')
        data=json.loads(Path(profiles[1]['path']).read_text(encoding='utf-8'))
        self.assertEqual(data['station/@id'],'A')
        self.assertEqual(data['station/reading[1]/text()'],'1')
        self.assertEqual(data['station/reading[2]/text()'],'2')

    def test_model_results_are_assigned_by_id_even_when_reordered(self):
        from bank_data.bulk_semantics import infer
        from unittest.mock import Mock,patch
        from bank_data.extract import review_result
        records=[{'record_id':'a','cells':{}},{'record_id':'b','cells':{}}]
        client=Mock();client.call.return_value=[{}]
        client.content.return_value={'results':[review_result('b'),review_result('a')]}
        with patch('bank_data.bulk_semantics.extract_request',return_value={}):
            results,_=infer(client,records,{})
        self.assertEqual([r['record_id'] for r in results],['a','b'])

    def test_passed_inspection_does_not_become_a_penalty(self):
        card={'filename':'合成检查结果.csv','columns':['企业名称','地址','事件内容','日期','检查结果']}
        plan=mapping();plan['events'][0]['event_type']='administrative_penalty'
        row={'record_id':'synthetic','cells':{'企业名称':'合成甲公司','地址':'示例路1号','事件内容':'检查','日期':'2026-01-01','检查结果':'合格'}}
        result,_,_=apply_plan(row,card,plan)
        self.assertEqual(result['status'],'NO_EVENT');self.assertEqual(result['events'],[])

    @unittest.skipUnless(importlib.util.find_spec('duckdb'),'bulk SQL runtime not installed')
    def test_streamed_mapping_matching_exports_and_coverage(self):
        path=self.raw/'合成高新认定.csv'
        path.write_text('企业名称,地址,事件内容,日期,__text_source__,__ocr_min_confidence__\n合成甲公司,示例路1号,已认定,2026-01-01,rapidocr_cpu,0.42\n合成甲公司,示例路1号,已认定,2026-02-01,pdf_native_text,1.0\n',encoding='utf-8')
        profiles,_=scan(self.raw,self.work/'02_profiles');card=profiles[0]['cards'][0]
        dump(self.work/'04_plans/scopes'/(card['scope_id']+'.json'),{'signature':'synthetic','plan':mapping()})
        materialize(profiles,self.work,workers=1)
        summary=finalize_validation(profiles,self.work)
        self.assertEqual(summary['records'],2)
        result=aggregate(self.work,profiles)
        self.assertEqual(result['counts']['entities'],1)
        self.assertEqual(result['counts']['events'],2)
        self.assertEqual(result['counts']['record_ledger'],2)
        self.assertTrue((self.work/'08_results/profiles.parquet').exists())
        import duckdb
        db=duckdb.connect(str(self.work/'07_entities/results.duckdb'),read_only=True)
        try:
            self.assertEqual(db.execute("SELECT count(*) FROM event_sources WHERE source_quality='OCR_UNVERIFIED' AND ocr_min_confidence=0.42").fetchone()[0],1)
            self.assertIn('OCR_UNVERIFIED',db.execute('SELECT observed_source_quality FROM profiles').fetchone()[0])
        finally:db.close()


if __name__=='__main__':unittest.main()
