import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from bank_data.event_taxonomy import classify_scope, refine


class SourceClassificationTests(unittest.TestCase):
    def test_objects_and_procedures_have_different_categories(self):
        cases = {
            '建筑施工单位主要负责人、项目负责人、专职安全生产管理人员的考核合格信息及监管情况.csv':'personnel_qualification',
            '建造师注册证书信息.csv':'personnel_qualification',
            '特种设备监督检验和定期检验信息.csv':'equipment_inspection',
            '特种设备使用登记.csv':'equipment_inspection',
            '食品经营许可企业.csv':'business_permit',
            '小食杂店备案信息.csv':'business_permit',
            '建筑业企业资质审批结果信息.csv':'enterprise_qualification',
            '建设工程企业资质申请情况.csv':'qualification_application',
            '药品批准信息归集中.csv':'product_registration',
            '化妆品类化妆品基本信息.csv':'product_registration',
            '医疗器械经营备案信息.csv':'business_permit',
            '食品经营许可日常监督检查.csv':'regulatory_inspection',
            '货运行业质量信誉考核信息.csv':'industry_assessment',
            '社会组织年检信息.csv':'industry_assessment',
            '新闻出版领域行政检查信息.csv':'regulatory_inspection',
            '年度施工许可证信息.csv':'project_approval',
            '工程消防验收意见书.csv':'project_approval',
            '特种设备设计单位许可.csv':'business_permit',
            '年度重点工程项目基础信息.csv':'qualification_review',
            '行政许可公示.csv':'qualification_review',
            '建筑业企业资质培训.csv':'qualification_review',
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(classify_scope(title)[0],expected)


try:
    import duckdb
except ImportError:
    duckdb=None


@unittest.skipIf(duckdb is None,'Install the taxonomy extra for DuckDB integration checks')
class RefinementTests(unittest.TestCase):
    def test_evidence_guards_conservation_and_read_only_source(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory); source=base/'original.duckdb'
            db=duckdb.connect(str(source))
            db.execute('CREATE TABLE source_scopes(scope_id VARCHAR,filename VARCHAR,sheet VARCHAR)')
            scopes=[('permit','食品经营许可企业',''),('inspection','日常监督检查信息',''),
                    ('application','建设工程企业资质申请情况',''),('equipment','特种设备监督检验信息',''),
                    ('personnel','建造师注册证书信息',''),('unknown','行政许可公示','')]
            db.executemany('INSERT INTO source_scopes VALUES (?,?,?)',scopes)
            db.execute('''CREATE TABLE events(event_id VARCHAR,entity_id VARCHAR,record_id VARCHAR,
                file_id VARCHAR,scope_id VARCHAR,event_type VARCHAR,status VARCHAR,
                document_no JSON,date JSON,evidence JSON)''')
            def ref(field,value):return json.dumps({'field':field,'value':value},ensure_ascii=False)
            result=json.dumps([{'field':'检验结论','value':'不合格'}],ensure_ascii=False)
            authority=json.dumps([{'field':'检查实施单位','value':'某市场监督管理局'}],ensure_ascii=False)
            rows=[
                ('permit','permit','qualification','confirmed',ref('许可证编号','synthetic-001'),None,'[]'),
                ('expiry','permit','qualification','confirmed',ref('有效期','2028-01-01'),None,'[]'),
                ('inspection','inspection','qualification','confirmed',ref('许可证编号','synthetic-002'),None,authority),
                ('application','application','qualification','proposed',None,None,'[]'),
                ('equipment','equipment','qualification','confirmed',None,None,result),
                ('personnel','personnel','qualification','confirmed',ref('证书编号','synthetic-person'),None,'[]'),
                ('unknown','unknown','qualification','confirmed',ref('许可证编号','synthetic-003'),None,'[]'),
                ('no_promotion','permit','qualification','unknown',ref('许可证编号','synthetic-004'),None,'[]'),
                ('conflict','permit','qualification','confirmed',ref('许可证编号','synthetic-005'),None,'[]'),
                ('penalty','inspection','administrative_penalty','confirmed',None,None,'[]'),
            ]
            for eid,scope,kind,status,doc,date,evidence in rows:
                db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?)',
                           [eid,'synthetic-entity','r-'+eid,'f-'+scope,scope,kind,status,doc,date,evidence])
            db.execute('CREATE TABLE event_sources AS SELECT *,event_id AS fact_id FROM events')
            db.execute("INSERT INTO event_sources SELECT * REPLACE('inspection' AS scope_id,'second-source' AS fact_id) FROM event_sources WHERE event_id='conflict'")
            db.close()
            before=hashlib.sha256(source.read_bytes()).hexdigest()
            summary=refine(source,base/'corrected')
            self.assertEqual(before,hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(summary['total_events'],10)
            self.assertNotIn('legacy_qualification_events',summary)
            self.assertEqual(summary['category_count'],len({x['event_type'] for x in summary['category_status']}))
            self.assertIsNone(summary['unique_licences'])
            db=duckdb.connect(str(base/'corrected/classification.duckdb'),read_only=True)
            corrected={r[0]:r[1:] for r in db.execute('SELECT event_id,event_type,status,current_validity FROM classified_events').fetchall()}
            self.assertEqual(corrected['permit'][:2],('business_permit','confirmed'))
            self.assertEqual(corrected['expiry'][1],'unknown')
            self.assertEqual(corrected['inspection'][:2],('regulatory_inspection','unknown'))
            self.assertEqual(corrected['application'][:2],('qualification_application','unknown'))
            self.assertEqual(corrected['equipment'][:2],('equipment_inspection','confirmed'))
            self.assertEqual(corrected['personnel'][0],'personnel_qualification')
            self.assertEqual(corrected['unknown'][:2],('qualification_review','unknown'))
            self.assertEqual(corrected['no_promotion'][1],'unknown')
            self.assertEqual(corrected['conflict'][:2],('qualification_review','unknown'))
            self.assertEqual(corrected['penalty'][:2],('administrative_penalty','confirmed'))
            self.assertTrue(all(r[2]=='not_verified' for r in corrected.values()))
            self.assertEqual(db.execute('SELECT count(*) FROM classified_event_sources').fetchone()[0],11)
            db.close()
            public=json.dumps(summary)
            for private in ['synthetic-entity','scope_id','record_id','original.duckdb']:
                self.assertNotIn(private,public)
            with self.assertRaises(ValueError):refine(source,base/'corrected')


if __name__=='__main__':unittest.main()
