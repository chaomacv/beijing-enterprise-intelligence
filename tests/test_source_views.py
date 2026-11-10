import copy,hashlib,json
import unittest

from bank_data.source_views import PREFIX,html_view,project_records,source_cell
from bank_data.extract import validate_ref
from bank_data.bulk_references import unpack


class SourceViewTests(unittest.TestCase):
    def test_inline_names_and_entities_are_reconstructed_without_mutating_original_cells(self):
        raw='<style>.x { color:red }</style><p class="x">合成<span>HTML</span><span>有限公司</span>&nbsp;已处罚。</p><a href="https://example.invalid/document">文书</a>'
        row={'record_id':'source-A','sheet':'Sheet1','row':2,'cells':{'正文':raw,'日期':'2026-01-01'},'context':{'header_record':1}}
        before=copy.deepcopy(row);projected,views=project_records([row]);view=projected[0]['cells'][PREFIX+'正文']
        self.assertEqual(row,before);self.assertNotIn('正文',projected[0]['cells']);self.assertIn('合成HTML有限公司',view)
        self.assertIn('https://example.invalid/document',view);self.assertNotIn('color:red',view)
        self.assertEqual(views['source-A'][0]['source_sha256'],hashlib.sha256(raw.encode()).hexdigest())
        self.assertGreater(views['source-A'][0]['presentation_style_chars_omitted_from_model'],0)
        validate_ref({'field':PREFIX+'正文','value':'合成HTML有限公司'},row)
        with self.assertRaises(ValueError):validate_ref({'field':'正文','value':'合成HTML有限公司'},row)

    def test_source_binding_still_rejects_another_record_and_an_unknown_projection(self):
        row={'cells':{'正文':'<p>合成甲<span>有限公司</span></p>'}}
        with self.assertRaises(ValueError):validate_ref({'field':PREFIX+'正文','value':'合成乙有限公司'},row)
        with self.assertRaises(ValueError):validate_ref({'field':PREFIX+'不存在','value':'合成甲有限公司'},row)

    def test_scripts_comments_and_meaningful_attributes_stay_data_without_network_execution(self):
        raw='<p title="合成属性公司">正文</p><!--合成注释公司--><script>window.name="合成脚本公司";</script><img src="https://example.invalid/image" alt="合成替代说明">'
        view,_,_=html_view(raw)
        for expected in ['合成属性公司','合成注释公司','合成脚本公司','合成替代说明','https://example.invalid/image']:self.assertIn(expected,view)

    def test_plain_rows_stay_identical_and_reserved_source_column_collisions_are_rejected(self):
        row={'record_id':'plain','cells':{'公司名称':'合成公司','数学描述':'a < b 且 c > d'},'context':{}}
        projected,views=project_records([row]);self.assertEqual(projected,[row]);self.assertEqual(views,{})
        row={'record_id':'collision','cells':{'正文':'<p>合成公司</p>',PREFIX+'正文':'original source column'},'context':{}}
        with self.assertRaisesRegex(ValueError,'collides'):project_records([row])

    def test_projected_reference_expands_to_a_canonical_fact_bound_to_the_original_html(self):
        row={'record_id':'html-record','sheet':'Sheet1','row':2,'cells':{'正文':'<p>合成<span>HTML</span>有限公司已处罚。</p>'},'context':{}}
        value={'records':{'r0':{'status':'EXTRACTED','entities':[{'role':'subject','kind':'business','name':{'field':PREFIX+'正文','value':'合成HTML有限公司'}}],
            'events':[{'subject_index':0,'event_type':'administrative_penalty','status':'confirmed','evidence':[PREFIX+'正文']}]}}}
        result=unpack(value,[row],{'filename':'合成处罚公告.csv'})[0]
        self.assertEqual(result['record_id'],'html-record');self.assertEqual(result['entities'][0]['name']['value'],'合成HTML有限公司')
        self.assertEqual(result['events'][0]['evidence'][0]['value'],source_cell(row['cells'],PREFIX+'正文'))

    def test_scalar_values_require_explicit_substrings_instead_of_copying_the_whole_view(self):
        row={'record_id':'html','cells':{'正文':'<p>合成HTML有限公司于2026-01-01罚款100元。</p>'},'context':{}}
        value={'records':{'r0':{'status':'EXTRACTED','entities':[{'role':'subject','kind':'business','name':{'field':PREFIX+'正文','value':'合成HTML有限公司'}}],
            'events':[{'subject_index':0,'event_type':'administrative_penalty','status':'confirmed','date':PREFIX+'正文','evidence':[PREFIX+'正文']}]}}}
        with self.assertRaises(ValueError):unpack(value,[row],{'filename':'合成处罚'})
        value['records']['r0']['events'][0]['date']={'field':PREFIX+'正文','value':'2026-01-01'}
        self.assertEqual(unpack(value,[row],{'filename':'合成处罚'})[0]['events'][0]['date']['value'],'2026-01-01')

    def test_a_raw_html_field_hidden_from_one_model_record_cannot_be_selected_from_another_slot(self):
        rows=[{'record_id':'html','cells':{'正文':'<p>合成甲公司</p>'},'context':{}},{'record_id':'plain','cells':{'正文':'合成乙公司'},'context':{}}]
        value={'records':{'r0':{'status':'NO_EVENT','entities':[{'role':'subject','kind':'business','name':{'field':'正文','value':'合成甲公司'}}]},'r1':{'status':'NO_EVENT'}}}
        with self.assertRaisesRegex(ValueError,'model view'):unpack(value,rows,{'filename':'合成公告'})

    def test_schema_projects_original_html_once_even_when_its_text_contains_encoded_markup(self):
        from bank_data.bulk_references import ReferenceClient
        from pathlib import Path
        import tempfile
        from unittest.mock import patch
        row={'record_id':'encoded','cells':{'正文':'<p>&lt;p&gt;合成甲公司&lt;/p&gt;&lt;p&gt;已处罚&lt;/p&gt;</p>'},'context':{}}
        class Transport:
            def __init__(self,*args,**kwargs):self.cache=Path(args[3])
            def request(self,system,payload,contract,maximum):return {'payload':payload,'contract':contract}
        with tempfile.TemporaryDirectory() as temporary,patch('bank_data.bulk_references.BatchClient',Transport):
            client=ReferenceClient(None,None,None,Path(temporary)/'model_cache')
            request=client.request('unused',{'context':{'filename':'合成公告'},'records':[row]},{},2048)
            fields=request['contract']['properties']['records']['properties']['r0']['properties']['entities']['items']['properties']['name']['properties']['field']['enum']
            self.assertEqual(fields,[PREFIX+'正文'])
            self.assertEqual(set(request['payload']['records'][0]['cells']),set(fields))


if __name__=='__main__':unittest.main()
