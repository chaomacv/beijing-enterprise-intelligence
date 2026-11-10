import json
from pathlib import Path
import tempfile
import unittest

from bank_data.bulk_client import BatchClient
from bank_data.bulk_rows import materialize_file
from bank_data.bulk_semantics import budgeted_requests,extract_request,resolve_pending,finalize_validation
from bank_data.common import dump,file_hash
from bank_data.scan import scan


class BudgetClient:
    method='synthetic_budget_client'
    calls=[]
    seen=[]
    def __init__(self,*args):pass
    def request(self,system,payload,contract,maximum):
        if len(payload['records'])>1 or any(row['cells'].get('企业名称')=='合成不可装入公司' for row in payload['records']):
            raise ValueError('context_budget_exceeded')
        return {'system':system,'payload':payload,'schema':contract,'max_tokens':maximum}
    def call(self,requests):
        self.calls.append(len(requests));answers=[]
        for request in requests:
            rows=request['payload']['records'];self.seen.extend(row['record_id'] for row in rows)
            results=[{'record_id':row['record_id'],'status':'NO_EVENT','entities':[],'events':[]} for row in rows]
            answers.append({'ok':True,'response':{'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'results':results})}}]}})
        return answers
    content=staticmethod(BatchClient.content)


class BudgetedBatchTests(unittest.TestCase):
    def run_case(self,names):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        base=Path(temporary.name);raw=base/'input';raw.mkdir();work=base/'work'
        (raw/'合成超预算.csv').write_bytes(('企业名称\n'+'\n'.join(names)+'\n').encode('utf-8'))
        profiles,_=scan(raw,work/'02_profiles');profile=profiles[0];scope=profile['cards'][0]['scope_id']
        dump(work/'04_plans/scopes'/(scope+'.json'),{'signature':'synthetic','plan':{'mode':'row_llm','reason':'synthetic','entities':[],'events':[]}})
        mapped=materialize_file((profile,str(work)));dump(work/'06_validation/mapping_files.json',[mapped])
        source=work/'05_records'/profile['file_id']/'rows.jsonl';before=file_hash(source)
        BudgetClient.calls=[];BudgetClient.seen=[]
        report=resolve_pending(profiles,work,['http://127.0.0.1:18080/v1'],'synthetic',raw,client_class=BudgetClient)
        self.assertEqual(file_hash(source),before);finalize_validation(profiles,work)
        values=[json.loads(line) for line in (work/'06_validation'/profile['file_id']/'record_results.jsonl').read_text(encoding='utf-8').splitlines()]
        return report,values

    def test_over_budget_groups_use_four_request_batches_instead_of_serial_inference(self):
        report,values=self.run_case(['合成第'+str(i)+'公司' for i in range(8)])
        self.assertEqual(BudgetClient.calls,[4,4]);self.assertEqual(report['completed_records'],8)
        self.assertEqual(len(set(BudgetClient.seen)),8);self.assertEqual(set(BudgetClient.seen),{row['record_id'] for row in values})
        self.assertTrue(all(row['status']=='NO_EVENT' for row in values))

    def test_a_single_oversized_record_does_not_force_fitting_neighbors_into_serial_calls(self):
        report,values=self.run_case(['合成甲公司','合成不可装入公司','合成乙公司','合成丙公司'])
        self.assertEqual(BudgetClient.calls,[3]);self.assertEqual(report['completed_records'],4)
        self.assertEqual([row['status'] for row in values],['NO_EVENT','REVIEW','NO_EVENT','NO_EVENT'])
        self.assertEqual(len(BudgetClient.seen),3)

    def test_packing_preserves_the_exact_individual_requests_used_by_recursive_fallback(self):
        client=BudgetClient();records=[{'record_id':'original-'+str(i),'sheet':'Sheet1','row':i+2,'cells':{'企业名称':'合成公司'+str(i)},'context':{'note':'完整保留'}} for i in range(4)]
        card={'filename':'合成.csv','sheet':'Sheet1','columns':['企业名称'],'source':{}}
        tasks=[{'record_id':row['record_id']} for row in records]
        packed,oversized=budgeted_requests(client,tasks,records,card)
        self.assertEqual(oversized,[]);self.assertEqual(len(packed),4)
        for i,(group,rows,context,request,depth) in enumerate(packed):
            self.assertEqual(group,[tasks[i]]);self.assertEqual(rows,[records[i]]);self.assertEqual(context,card)
            self.assertEqual(request,extract_request(client,[records[i]],card))
            self.assertEqual(depth,2)

    def test_oversized_fallback_retains_its_original_recursion_depth(self):
        client=BudgetClient();records=[{'record_id':str(i),'cells':{'企业名称':'合成不可装入公司' if i==2 else '合成公司'},'context':{}} for i in range(4)]
        card={'filename':'合成.csv','sheet':'Sheet1','columns':['企业名称'],'source':{}};tasks=[{'record_id':row['record_id']} for row in records]
        packed,oversized=budgeted_requests(client,tasks,records,card)
        self.assertEqual(len(packed),3);self.assertEqual(len(oversized),1);self.assertEqual(oversized[0][-1],2)
        _,single=budgeted_requests(client,tasks[2:3],records[2:3],card);self.assertEqual(single[0][-1],0)


if __name__=='__main__':unittest.main()
