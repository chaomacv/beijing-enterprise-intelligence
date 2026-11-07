import contextlib
import io
import json
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from bank_data.bulk_client import BatchClient
from bank_data.serve import RequestError
from bank_data.serve_vllm import VLLMBackend


def request(value):
    return {'model':'synthetic','messages':[{'role':'user','content':'synthetic'}],'max_tokens':64,'temperature':0,
        'response_format':{'type':'json_schema','json_schema':{'schema':{'type':'object',
            'properties':{'value':{'type':'string','enum':[value]}},'required':['value'],'additionalProperties':False}}}}


def output(text,finish='stop'):
    return SimpleNamespace(prompt_token_ids=[1,2],outputs=[SimpleNamespace(text=text,finish_reason=finish,token_ids=[3,4])])


class VLLMAdapterTests(unittest.TestCase):
    def backend(self,outputs):
        backend=VLLMBackend.__new__(VLLMBackend)
        backend.model_id='synthetic';backend.version='synthetic';backend.context=8192;backend.lock=threading.Lock()
        backend.tokenizer=SimpleNamespace(apply_chat_template=Mock(return_value='synthetic'),encode=Mock(return_value=[1]))
        backend.parameters=SimpleNamespace;backend.guidance=SimpleNamespace
        backend.engine=SimpleNamespace(generate=Mock(return_value=outputs))
        return backend

    def test_per_request_schemas_are_independent_and_thinking_is_disabled(self):
        backend=self.backend([output('{"value":"A"}'),output('{"value":"B"}')])
        result=backend.generate_many([request('A'),request('B')])
        self.assertEqual([BatchClient.content(v) for v in result['items']],[{'value':'A'},{'value':'B'}])
        parameters=backend.engine.generate.call_args.args[1]
        self.assertEqual([p.guided_decoding.json['properties']['value']['enum'] for p in parameters],[['A'],['B']])
        self.assertTrue(all(p.temperature==0 and p.seed==42 for p in parameters))
        self.assertTrue(all(c.kwargs['enable_thinking'] is False for c in backend.tokenizer.apply_chat_template.call_args_list))

    def test_schema_failure_is_private_and_does_not_poison_other_items(self):
        backend=self.backend([output('{"value":"PRIVATE_BAD_VALUE"}'),output('{"value":"B"}')])
        logs=io.StringIO()
        with contextlib.redirect_stdout(logs):result=backend.generate_many([request('A'),request('B')])
        self.assertFalse(result['items'][0]['ok']);self.assertTrue(result['items'][1]['ok'])
        self.assertNotIn('PRIVATE_BAD_VALUE',logs.getvalue())
        with self.assertRaises(ValueError):BatchClient.content(result['items'][0])

    def test_truncation_and_oversized_input_are_not_reported_as_valid_completion(self):
        backend=self.backend([output('{"value":','length')])
        result=backend.generate_many([request('A')])
        with self.assertRaises(ValueError):BatchClient.content(result['items'][0])
        backend.context=100
        with self.assertRaises(RequestError):backend.generate_many([request('A')])
        self.assertEqual(backend.engine.generate.call_count,1)

    def test_numeric_and_array_bounds_are_still_enforced_after_decoding(self):
        value=request('A');schema={'type':'object','properties':{'minItems':{'type':'array',
            'items':{'type':'integer','minimum':0},'maxItems':1}},'required':['minItems'],'additionalProperties':False}
        value['response_format']['json_schema']['schema']=schema
        backend=self.backend([output('{"minItems":[-1,2]}')]);result=backend.generate_many([value])
        self.assertFalse(result['items'][0]['ok'])
        decoded=backend.engine.generate.call_args.args[1][0].guided_decoding.json
        self.assertIn('minItems',decoded['properties'])
        self.assertNotIn('maxItems',decoded['properties']['minItems'])
        self.assertNotIn('minimum',decoded['properties']['minItems']['items'])
        self.assertEqual(schema['properties']['minItems']['maxItems'],1)
        self.assertEqual(schema['properties']['minItems']['items']['minimum'],0)


if __name__=='__main__':unittest.main()
