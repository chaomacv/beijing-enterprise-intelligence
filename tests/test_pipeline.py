import csv
import json
import tempfile
import unittest
from pathlib import Path

from bank_data.cli import demo_input
from bank_data.extract import RuleBaseline, validate_results
from bank_data.llm import validate_endpoint
from bank_data.pipeline import extract_batch, run
from bank_data.prepare import prepare
from bank_data.readers import detect, read_records
from bank_data.resolve import CODE_CHARS, CODE_WEIGHTS, Resolver, valid_code
from bank_data.store import Store


def code(base):
    assert len(base) == 17
    return base + CODE_CHARS[(31 - sum(CODE_CHARS.index(c) * w for c, w in zip(base, CODE_WEIGHTS)) % 31) % 31]


def mention(identifier, name='示例甲有限公司', address='北京市测试地址', credit=None):
    return {'mention_id': identifier, 'name': name, 'address': address, 'credit_code': credit}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root / 'input'
        self.work = self.root / 'private_work'
        self.input.mkdir()
        self.store = Store(self.work)

    def tearDown(self):
        self.store.close(); self.temp.cleanup()

    def test_demo_end_to_end_and_rerun_are_idempotent(self):
        demo_input(self.input)
        prepared = prepare(self.store, self.input)
        self.assertEqual(prepared['records'], 5)
        first = run(self.store, RuleBaseline())
        self.assertEqual(first['events'], 3)
        self.assertEqual(first['entities'], 2)
        self.assertEqual(first['excluded_records'], 1)
        self.assertTrue(first['status_coverage_complete'])
        before = (self.work / 'events.json').read_bytes()
        prepare(self.store, self.input)
        second = run(self.store, RuleBaseline())
        self.assertEqual(first, second)
        self.assertEqual(before, (self.work / 'events.json').read_bytes())

    def test_multiline_header_and_second_sheet_keep_all_data(self):
        import openpyxl
        book = openpyxl.Workbook()
        one = book.active; one.title = '一'
        one.append(['表格标题']); one.append(['企业名称', '统一社会信用代码'])
        one.append(['示例甲有限公司', '0000123'])
        two = book.create_sheet('二'); two.append(['企业名称', '统一社会信用代码']); two.append(['示例乙有限公司', '0000456'])
        p = self.input / 'misnamed.csv'; book.save(p); book.close()
        self.assertEqual(detect(p), 'xlsx')
        rows = list(read_records(p, 'xlsx'))
        self.assertEqual(len(rows), 2)
        self.assertEqual({r[0] for r in rows}, {'一', '二'})
        self.assertEqual(rows[0][2]['统一社会信用代码'], '0000123')
        self.assertEqual(rows[0][3]['header_record'], 2)

    def test_xlsx_oversized_dimensions_do_not_become_phantom_fields(self):
        import openpyxl
        book=openpyxl.Workbook();sheet=book.active
        sheet.append(['企业名称','状态']);sheet.append(['合成甲公司','正常'])
        sheet.cell(row=2,column=16384).number_format='0.00'
        path=self.input/'styled.xlsx';book.save(path);book.close()
        rows=list(read_records(path,'xlsx'))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][2],{'企业名称':'合成甲公司','状态':'正常'})
        self.assertFalse(rows[0][3]['width_mismatch'])

    def test_xlsx_underreported_dimensions_do_not_truncate_records(self):
        import openpyxl,re,zipfile
        book=openpyxl.Workbook();sheet=book.active
        sheet.append(['企业名称','状态']);sheet.append(['合成甲公司','正常']);sheet.append(['合成乙公司','正常'])
        original=self.root/'original.xlsx';path=self.input/'undersized.xlsx';book.save(original);book.close()
        with zipfile.ZipFile(original) as source,zipfile.ZipFile(path,'w') as target:
            for name in source.namelist():
                value=source.read(name)
                if name=='xl/worksheets/sheet1.xml':value=re.sub(rb'<dimension ref="[^"]+"',b'<dimension ref="A1:A1"',value)
                target.writestr(name,value)
        rows=list(read_records(path,'xlsx'))
        self.assertEqual([row[1] for row in rows],[2,3])
        self.assertEqual([row[2]['企业名称'] for row in rows],['合成甲公司','合成乙公司'])

    def test_failed_file_does_not_publish_partial_records(self):
        p = self.input / 'broken.csv'
        p.write_text('企业名称,状态\n示例甲有限公司,正常\n"unterminated,字段', encoding='utf-8')
        result = prepare(self.store, self.input)
        self.assertEqual(result['status_counts'], {'review': 1})
        self.assertEqual(result['records'], 0)

    def test_source_reference_and_id_coverage_are_enforced(self):
        row = {'record_id': 'r1', 'cells': {'企业名称': '示例甲有限公司'}}
        bad = {'record_id': 'r1', 'status': 'NO_EVENT', 'entities': [
            {'role': 'subject', 'name': {'field': '企业名称', 'value': '编造企业'}, 'credit_code': None, 'address': None}], 'events': []}
        with self.assertRaises(ValueError): validate_results({'results': [bad]}, [row])
        with self.assertRaises(ValueError): validate_results({'results': []}, [row])
        good = {'record_id': 'r1', 'status': 'NO_EVENT', 'entities': [], 'events': []}
        with self.assertRaises(ValueError): validate_results({'results': [good, good]}, [row])
        with self.assertRaises(ValueError): validate_results({'results': [{**good, 'status':'EXTRACTED'}]}, [row])

    def test_changed_provenance_invalidates_preparation_and_bad_checksum_quarantines_old_rows(self):
        demo_input(self.input)
        prepare(self.store,self.input)
        sidecar=self.input/'provenance.json'
        sidecar.write_text(json.dumps({'dataset_url':'https://example.test/revised'}),encoding='utf-8')
        prepare(self.store,self.input)
        cards=[json.loads(r['card']) for r in self.store.active_scopes()]
        self.assertTrue(all(c['source']['dataset_url'].endswith('/revised') for c in cards))
        sidecar.write_text(json.dumps({'sha256':'incorrect'}),encoding='utf-8')
        report=prepare(self.store,self.input)
        self.assertEqual(report['records'],0)
        self.assertEqual(report['status_counts'],{'review':3})
        self.assertEqual(list(self.store.active_scopes()),[])

    def test_semantic_review_is_exported_to_review_queue(self):
        demo_input(self.input)
        prepare(self.store,self.input)
        class Uncertain(RuleBaseline):
            name='uncertain-test'
            def extract(self,records,card):
                return [{'record_id':r['record_id'],'status':'REVIEW','entities':[],'events':[]} for r in records]
        report=run(self.store,Uncertain())
        queue=json.loads((self.work/'review_queue.json').read_text(encoding='utf-8'))
        self.assertEqual(report['review_records'],4)
        self.assertEqual(len(queue),4)

    def test_filename_evidence_is_source_bound_and_only_allowed_for_events(self):
        row={'record_id':'r','cells':{'企业名称':'合成甲公司'}}
        name={'field':'企业名称','value':'合成甲公司'}
        entity={'role':'subject','name':name,'credit_code':None,'address':None}
        event={'subject_index':0,'event_type':'innovation','status':'proposed','date':None,
               'amount':None,'document_no':None,'evidence':[name,{'field':'__filename__','value':'拟认定名单'}]}
        result={'record_id':'r','status':'EXTRACTED','entities':[entity],'events':[event]}
        card={'filename':'合成_创新型企业拟认定名单.csv'}
        validate_results({'results':[result]},[row],card)
        with self.assertRaises(ValueError):validate_results({'results':[result]},[row],{'filename':'其他.csv'})
        entity['name']={'field':'__filename__','value':'拟认定名单'}
        with self.assertRaises(ValueError):validate_results({'results':[result]},[row],card)

    def test_removed_and_revoked_facts_remain_visible_in_tag_labels(self):
        (self.input/'经营异常.csv').write_text('企业名称,事件内容\n合成甲公司,移出经营异常名录\n合成乙公司,撤销经营异常决定\n',encoding='utf-8')
        prepare(self.store,self.input)
        run(self.store,RuleBaseline())
        profiles=json.loads((self.work/'profiles.json').read_text(encoding='utf-8'))
        labels=[tag['label'] for profile in profiles for tag in profile['tags']]
        self.assertTrue(any(v.startswith('已移出：') for v in labels))
        self.assertTrue(any(v.startswith('已撤销：') for v in labels))

    def test_shared_document_number_does_not_collapse_distinct_payment_facts(self):
        (self.input/'项目补贴.csv').write_text('企业名称,地址,事件内容,项目编号,日期,金额\n合成甲公司,测试路1号,已拨付,TEST-1,2026-01-01,100\n合成甲公司,测试路1号,已拨付,TEST-1,2026-02-01,200\n',encoding='utf-8')
        prepare(self.store,self.input)
        report=run(self.store,RuleBaseline())
        self.assertEqual(report['entities'],1)
        self.assertEqual(report['events'],2)
        events=json.loads((self.work/'events.json').read_text(encoding='utf-8'))
        self.assertEqual({e['amount']['value'] for e in events},{'100','200'})

    def test_truncated_batches_split_then_keep_review_for_single_failure(self):
        class Backend:
            def extract(self, records, card):
                if len(records) > 1 or records[0]['record_id'] == 'bad': raise ValueError('truncated')
                return [{'record_id': records[0]['record_id'], 'status': 'NO_EVENT', 'entities': [], 'events': []}]
        rows = [{'record_id': r, 'cells': {}} for r in ['one', 'bad', 'three']]
        results, issues = extract_batch(Backend(), rows, {})
        self.assertEqual({r['record_id'] for r in results}, {'one', 'bad', 'three'})
        self.assertEqual(next(r['status'] for r in results if r['record_id'] == 'bad'), 'REVIEW')
        self.assertEqual(len(issues), 1)

    def test_endpoint_never_falls_back_to_public_cloud(self):
        self.assertEqual(validate_endpoint('http://127.0.0.1:8000/v1'), 'http://127.0.0.1:8000/v1')
        self.assertEqual(validate_endpoint('http://10.0.0.1:8000/v1'), 'http://10.0.0.1:8000/v1')
        for value in ['https://api.openai.com/v1', 'https://8.8.8.8/v1', 'http://user:pass@localhost/v1', 'http://169.254.169.254/v1']:
            with self.subTest(value=value), self.assertRaises(ValueError): validate_endpoint(value)

    def test_credit_codes_with_conflicting_identities_do_not_merge(self):
        a = code('91110108000000001'); b = code('91110108000000002')
        self.assertEqual(valid_code(a), a)
        self.assertIsNone(valid_code(a[:-1] + ('0' if a[-1] != '0' else '1')))
        resolver = Resolver()
        one = resolver.assign(mention('m1', credit=a))
        two = resolver.assign(mention('m2', credit=b))
        self.assertNotEqual(one, two)
        self.assertTrue(any(c['credit_code_conflict'] for c in resolver.decisions[-1]['candidates']))

    def test_fuzzy_names_and_name_only_are_not_auto_merged(self):
        resolver = Resolver()
        one = resolver.assign(mention('m1', address=''))
        two = resolver.assign(mention('m2', address=''))
        three = resolver.assign(mention('m3', name='示例甲科技有限公司', address=''))
        self.assertEqual(len({one, two, three}), 3)
        self.assertEqual(resolver.decisions[-1]['decision'], 'REVIEW')

    def test_strong_code_and_exact_name_address_matching(self):
        resolver = Resolver(); c = code('91110108000000001')
        one = resolver.assign(mention('a', credit=c))
        self.assertEqual(resolver.assign(mention('b', credit=c)), one)
        self.assertEqual(resolver.assign(mention('c')), one)

    def test_changed_file_does_not_leave_old_records_active(self):
        p = self.input / '行政处罚.csv'
        p.write_text('企业名称,事件内容\n示例甲有限公司,罚款\n', encoding='utf-8')
        prepare(self.store, self.input)
        p.write_text('企业名称,事件内容\n示例乙有限公司,罚款\n', encoding='utf-8')
        prepared = prepare(self.store, self.input)
        self.assertEqual(prepared['records'], 1)
        report = run(self.store, RuleBaseline())
        entities = json.loads((self.work / 'entities.json').read_text(encoding='utf-8'))
        self.assertEqual(report['entities'], 1)
        self.assertEqual(entities[0]['names'], ['示例乙有限公司'])

    def test_xml_records_have_unique_positions(self):
        p = self.input / 'test.rdf'
        p.write_text('<root><record><企业名称>甲</企业名称></record><record><企业名称>乙</企业名称></record></root>', encoding='utf-8')
        rows = list(read_records(p, 'rdf'))
        self.assertEqual([r[1] for r in rows], [1, 2])


if __name__ == '__main__':
    unittest.main()
