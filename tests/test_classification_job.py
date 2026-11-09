import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec=importlib.util.spec_from_file_location('classification_job',Path(__file__).resolve().parents[1]/'scripts/refine_completed_run.py')
job=importlib.util.module_from_spec(spec)
spec.loader.exec_module(job)


class ClassificationJobTests(unittest.TestCase):
    def test_waiting_stage_starts_only_after_successful_full_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def write(state):
                (root/'run_status.json').write_text(json.dumps({'status':state,'current_stage':'06_validation'}))
            write('RUNNING')
            def complete(seconds):
                self.assertEqual(seconds,30)
                (root/'audit.json').write_text(json.dumps({'all_readable_records_accounted_for':True,'all_original_files_accounted_for':True}))
                write('COMPLETED_WITH_REVIEW')
            with patch.object(job.time,'sleep',side_effect=complete),patch.object(job,'refine',return_value={'version':'fixture','total_events':3}) as refine:
                job.run(root,root/'corrected',wait=True)
                refine.assert_called_once_with(root/'07_entities/results.duckdb',root/'corrected')
            self.assertEqual(json.loads((root/'classification_job.json').read_text())['status'],'COMPLETE')

    def test_failed_or_unaccounted_run_never_reaches_classification(self):
        for state,readable in [('FAILED',True),('COMPLETED',False)]:
            with self.subTest(state=state),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                (root/'run_status.json').write_text(json.dumps({'status':state,'current_stage':'09_review'}))
                (root/'audit.json').write_text(json.dumps({'all_readable_records_accounted_for':readable,'all_original_files_accounted_for':True}))
                with patch.object(job,'refine') as refine:
                    with self.assertRaises(ValueError):job.run(root,root/'corrected',wait=True)
                    refine.assert_not_called()
