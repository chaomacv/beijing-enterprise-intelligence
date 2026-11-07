import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bank_data.bulk_rows import materialize_file
from bank_data.common import dump,file_hash
from bank_data.scan import scan


class MaterializeResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);raw=self.root/'input';raw.mkdir();self.work=self.root/'work'
        (raw/'合成名单.csv').write_bytes('企业名称\n合成甲公司\n合成乙公司\n'.encode('utf-8'))
        profiles,_=scan(raw,self.work/'02_profiles');self.profile=profiles[0];self.scope=self.profile['cards'][0]['scope_id']
        self.plan=self.work/'04_plans/scopes'/(self.scope+'.json')
        dump(self.plan,{'signature':'synthetic','plan':{'mode':'row_llm','reason':'synthetic','entities':[],'events':[]}})

    def tearDown(self):self.temp.cleanup()

    def test_second_run_reuses_prepared_rows_without_reading_input_again(self):
        args=(self.profile,str(self.work));first=materialize_file(args)
        self.assertNotEqual(first['key'],'pending')
        raw=self.work/'05_records'/self.profile['file_id']/'rows.jsonl';before=file_hash(raw)
        with patch('bank_data.bulk_rows.read_records',side_effect=AssertionError('Reopened cached input')):
            second=materialize_file(args)
        self.assertEqual(first,second);self.assertEqual(file_hash(raw),before)

    def test_changed_plan_invalidates_prepared_rows(self):
        args=(self.profile,str(self.work));first=materialize_file(args);data=json.loads(self.plan.read_text(encoding='utf-8'))
        data['plan']={'mode':'entity_only','reason':'synthetic refined mapping','entities':[{'role':'subject','kind':'business','name_field':'企业名称','code_field':None,'address_field':None}],'events':[]}
        dump(self.plan,data);second=materialize_file(args)
        self.assertNotEqual(first['key'],second['key'])
        self.assertEqual((first['pending_llm'],second['pending_llm'],second['mapped_records']),(2,0,2))


if __name__=='__main__':unittest.main()
