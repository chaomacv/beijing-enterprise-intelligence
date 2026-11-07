import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from bank_data.readers import detect, read_records
from bank_data.extract import EXTRACTION_SCHEMA
from bank_data.llm import LocalQwen
from bank_data.serve import RequestError, handler_for
from bank_data.store import Store


class ReaderRegressionTests(unittest.TestCase):
    def test_portal_typed_rdf_nodes_are_records(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'typed.rdf'
            path.write_text('''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:t="https://example.test/">
              <t:企业名单 rdf:about="urn:test:1"><t:企业名称>合成示例甲</t:企业名称><t:年份>2026</t:年份></t:企业名单>
              <t:企业名单 rdf:about="urn:test:2"><t:企业名称>合成示例乙</t:企业名称><t:年份>2025</t:年份></t:企业名单>
              </rdf:RDF>''', encoding='utf-8')
            rows = list(read_records(path, 'rdf'))
            self.assertEqual([r[1] for r in rows], [1, 2])
            self.assertEqual([r[2]['企业名称'] for r in rows], ['合成示例甲', '合成示例乙'])

    def test_unrecognized_nonempty_xml_is_not_an_empty_success(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'unknown.xml'
            path.write_text('<root><unexpected><name>合成示例甲</name></unexpected></root>', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'unrecognized record structure'):
                list(read_records(path, 'xml'))
            path.write_text('<root/>', encoding='utf-8')
            self.assertEqual(list(read_records(path, 'xml')), [])

    def test_utf16_csv_preserves_text_and_positions(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'wide.csv'
            path.write_text('企业名称,金额\n合成甲,00123\n', encoding='utf-16')
            rows = list(read_records(path, 'csv'))
            self.assertEqual(rows[0][1], 2)
            self.assertEqual(rows[0][2], {'企业名称': '合成甲', '金额': '00123'})

    def test_extensionless_csv_and_legacy_word_are_distinguished(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'no_suffix'
            path.write_text('企业名称,状态\n合成甲,已认定\n', encoding='utf-8')
            self.assertEqual(detect(path), 'csv')
            path = Path(name) / 'legacy.doc'
            path.write_bytes(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1')
            self.assertEqual(detect(path), 'legacy_word')


class FakeBackend:
    model_id = 'synthetic-test-backend'
    def metadata(self): return {'model': self.model_id, 'context': 8192}
    def generate(self, payload):
        if payload.get('busy'): raise BlockingIOError()
        if payload.get('invalid'): raise RequestError('Rejected test request')
        return {'model': self.model_id, 'choices': [{'finish_reason': 'stop', 'message': {'content': '{}'}}]}


class ModelHTTPTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.backend, 'test-only-key'))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def request(self, path, payload=None, authenticated=True):
        headers = {'Authorization': 'Bearer test-only-key'} if authenticated else {}
        data = json.dumps(payload).encode() if payload is not None else None
        return self.opener.open(urllib.request.Request(self.url + path, data, headers), timeout=5)

    def test_health_and_model_list_require_auth_and_are_bounded(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/healthz', authenticated=False)
        self.assertEqual(caught.exception.code, 401)
        with self.request('/healthz') as response: self.assertEqual(json.load(response)['status'], 'ready')
        with self.request('/v1/models') as response:
            self.assertEqual(json.load(response)['data'][0]['id'], FakeBackend.model_id)

    def test_busy_invalid_and_missing_routes_have_distinct_statuses(self):
        for path, payload, status in [('/v1/chat/completions', {'busy': True}, 503),
                                      ('/v1/chat/completions', {'invalid': True}, 400),
                                      ('/external', {}, 404)]:
            with self.assertRaises(urllib.error.HTTPError) as caught: self.request(path, payload)
            self.assertEqual(caught.exception.code, status)

    def test_inference_handler_does_not_log_business_payloads(self):
        captured = io.StringIO()
        with redirect_stdout(captured), self.request('/v1/chat/completions', {'messages': ['SYNTHETIC_PRIVATE_SENTINEL']}) as response:
            self.assertEqual(json.load(response)['model'], FakeBackend.model_id)
        self.assertNotIn('SYNTHETIC_PRIVATE_SENTINEL', captured.getvalue())

    def test_invalid_record_ids_never_poison_the_inference_cache(self):
        calls = []
        def answer(_):
            calls.append(1)
            data = {'results':[{'record_id':'foreign' if len(calls)==1 else 'r1',
                                'status':'NO_EVENT','entities':[],'events':[]}]}
            return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(data)}}]}
        self.backend.generate = answer
        with tempfile.TemporaryDirectory() as name, patch.dict(os.environ,{'BANK_LLM_API_KEY':'test-only-key'}):
            store = Store(Path(name))
            client = LocalQwen.__new__(LocalQwen)
            client.store, client.name, client.model = store, 'cache-test', FakeBackend.model_id
            client.endpoint, client.opener, client.max_output = self.url+'/v1', self.opener, 128
            client.fits = lambda _:True
            payload = {'records':[{'record_id':'r1','cells':{'企业名称':'合成甲'}}]}
            try:
                with self.assertRaises(ValueError): client.call('extract',payload,EXTRACTION_SCHEMA)
                self.assertEqual(store.db.execute('SELECT COUNT(*) FROM llm_cache').fetchone()[0],0)
                client.call('extract',payload,EXTRACTION_SCHEMA)
                client.call('extract',payload,EXTRACTION_SCHEMA)
                self.assertEqual(len(calls),2)
                self.assertEqual(store.db.execute('SELECT COUNT(*) FROM llm_cache').fetchone()[0],1)
            finally: store.close()


if __name__ == '__main__': unittest.main()
