import json
import tempfile
import unittest
from pathlib import Path

from bank_data.cli import demo_input
from bank_data.common import file_hash
from bank_data.extract import RuleBaseline
from bank_data.llm import ModelUnavailable
from bank_data.prepare import prepare
from bank_data.scan import profile_file, scan
from bank_data.store import Store
from bank_data.workflow import workflow


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.input = self.root/'input'; self.input.mkdir()
        self.work = self.root/'work'

    def tearDown(self): self.temporary.cleanup()

    def test_cards_cover_head_middle_tail_without_a_raw_record_store(self):
        path = self.input/'企业.csv'
        path.write_text('企业名称,序号\n' + ''.join(f'合成公司{i},{i}\n' for i in range(20)), encoding='utf-8')
        before = file_hash(path)
        profiles, report = scan(self.input,self.work)
        card = profiles[0]['cards'][0]
        self.assertEqual(card['row_count'],20)
        self.assertTrue({2,3,4,11,12,13,19,20,21}.issubset({r['row'] for r in card['sample']}))
        self.assertFalse((self.work/'facts/state.sqlite').exists())
        self.assertFalse(report['raw_record_store_created'])
        self.assertEqual(file_hash(path),before)
        store = Store(self.root/'prepared')
        try:
            prepare(store,self.input)
            actual = {r['record_id'] for row in store.active_scopes() for r in store.scope_records(row['id'])}
        finally: store.close()
        self.assertTrue({r['record_id'] for r in card['sample']}.issubset(actual))

    def test_changed_input_rebuilds_profile_and_failed_file_has_no_partial_card(self):
        path = self.input/'企业.csv'; cache=self.root/'cache'; cache.mkdir()
        path.write_text('企业名称,序号\n合成甲,1\n',encoding='utf-8')
        first=profile_file(path,path.name,cache)
        path.write_text('企业名称,序号\n合成甲,1\n合成乙,2\n',encoding='utf-8')
        second=profile_file(path,path.name,cache)
        self.assertNotEqual(first['file_id'],second['file_id'])
        self.assertEqual(second['records'],2)
        path.write_text('企业名称,序号\n合成甲,1\n"broken,2',encoding='utf-8')
        failed=profile_file(path,path.name,cache)
        self.assertEqual(failed['status'],'REVIEW')
        self.assertEqual(failed['cards'],[])

    def test_scan_only_does_not_construct_a_model(self):
        demo_input(self.input)
        def forbidden(_): raise AssertionError('No inference during scan')
        result=workflow(self.input,self.work,forbidden,through='scan')
        self.assertEqual(result['scan']['profiled_records'],5)
        self.assertFalse(result['extraction_complete'])

    def test_complete_rule_workflow_is_resumable_and_retains_file_dispositions(self):
        demo_input(self.input)
        result=workflow(self.input,self.work,lambda _:RuleBaseline())
        self.assertEqual(result['file_status_counts'],{'KEEP':2,'DROP':1})
        self.assertEqual(result['result']['records'],4)
        self.assertEqual(result['result']['events'],3)
        self.assertEqual(result['result']['entities'],2)
        self.assertTrue(result['extraction_complete'])
        first=(self.work/'facts/events.json').read_bytes()
        again=workflow(self.input,self.work,lambda _:RuleBaseline())
        self.assertEqual(again['result']['records'],4)
        self.assertEqual((self.work/'facts/events.json').read_bytes(),first)
        self.assertEqual(len(json.loads((self.work/'file_decisions.json').read_text(encoding='utf-8'))),3)

    def test_unavailable_model_stops_instead_of_publishing_review_for_every_record(self):
        demo_input(self.input)
        class Down(RuleBaseline):
            name='local-model-unavailable-test'
            def screen(self,card): raise ModelUnavailable('test outage')
        with self.assertRaises(ModelUnavailable): workflow(self.input,self.work,lambda _:Down())
        self.assertFalse((self.work/'facts/profiles.json').exists())

    def test_unsupported_files_have_an_explicit_disposition(self):
        (self.input/'scan.pdf').write_bytes(b'%PDF-1.7\nsynthetic placeholder')
        result=workflow(self.input,self.work,lambda _:RuleBaseline())
        self.assertEqual(result['file_status_counts'],{'REVIEW':1})
        self.assertTrue(result['completed_with_review'])
        self.assertEqual(result['unresolved_files'],1)


if __name__=='__main__': unittest.main()
