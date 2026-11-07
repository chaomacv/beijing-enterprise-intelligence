import ipaddress
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from .common import ontology, resource, stable_id
from .extract import EXTRACTION_SCHEMA, SCREEN_SCHEMA, validate_results, validate_screen


class ModelFailure(RuntimeError): pass
class TruncatedOutput(ModelFailure): pass
class ModelUnavailable(ModelFailure): pass


def validate_endpoint(endpoint):
    p = urllib.parse.urlparse(endpoint)
    if p.scheme not in ('http', 'https') or p.username or p.password or p.query or p.fragment:
        raise ValueError('Expected a credential-free local inference URL')
    host = p.hostname
    if host != 'localhost':
        try: ip = ipaddress.ip_address(host)
        except ValueError as e: raise ValueError('Use localhost or an explicit private/loopback IP') from e
        private_ranges = [ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.0/8', '::1/128')]
        if not any(ip.version == n.version and ip in n for n in private_ranges):
            raise ValueError('Public cloud endpoints are not allowed')
    if p.path.rstrip('/') != '/v1': raise ValueError('Endpoint must end with /v1')
    return endpoint.rstrip('/')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ModelFailure('Inference redirects are disabled')


class LocalQwen:
    def __init__(self, store, endpoint, model, tokenizer_dir, context=8192, max_output=2048):
        self.endpoint = validate_endpoint(endpoint)
        from pathlib import Path
        if not tokenizer_dir or not Path(tokenizer_dir).is_dir():
            raise ValueError('Provide a local model/tokenizer directory; automatic downloads are disabled')
        from transformers import AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_dir, local_files_only=True, trust_remote_code=False)
        if context <= max_output + 256: raise ValueError('Insufficient context budget')
        self.store, self.model = store, model
        self.context, self.max_output = context, max_output
        # Reserve an initial 512 output tokens per structured record, then split on failure.
        self.batch_size = min(12,max(1,max_output//512))
        self.name = 'local-qwen-' + stable_id(model, str(Path(tokenizer_dir).resolve()), context, max_output,
                                             resource('screen.md'), resource('extract.md'), ontology(),
                                             SCREEN_SCHEMA, EXTRACTION_SCHEMA)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        headers = {'Authorization':'Bearer ' + os.environ['BANK_LLM_API_KEY']} if os.environ.get('BANK_LLM_API_KEY') else {}
        try:
            with self.opener.open(urllib.request.Request(self.endpoint+'/models',headers=headers),timeout=15) as response:
                models = json.load(response)
            if model not in {row['id'] for row in models['data']}:
                raise ModelUnavailable('Configured local model is not served by this endpoint')
        except ModelUnavailable: raise
        except Exception as error:
            raise ModelUnavailable('Local model preflight failed; no business data was submitted') from error

    def messages(self, task, value):
        return [{'role': 'system', 'content': resource(task + '.md')},
                {'role': 'user', 'content': json.dumps(value, ensure_ascii=False)}]

    def fits(self, messages):
        tokens = self.tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, enable_thinking=False)
        return len(tokens) + self.max_output + 256 <= self.context

    def call(self, task, payload, schema):
        messages = self.messages(task, payload)
        if not self.fits(messages): raise TruncatedOutput('Input does not fit the actual chat-token budget')
        request = {'model': self.model, 'messages': messages, 'temperature': 0.7, 'top_p': 0.8,
                   'max_tokens': self.max_output, 'chat_template_kwargs': {'enable_thinking': False},
                   'response_format': {'type': 'json_schema', 'json_schema': {'name': task, 'strict': True, 'schema': schema}}}
        key = stable_id(self.name, request)
        cached = self.store.db.execute('SELECT result FROM llm_cache WHERE id=?', (key,)).fetchone()
        def validate(data):
            if task == 'screen': validate_screen(data,payload)
            else: validate_results(data,payload['records'],payload.get('context'))
            return data
        if cached:
            try: return validate(json.loads(cached['result']))
            except (ValueError,TypeError,KeyError):
                self.store.db.execute('DELETE FROM llm_cache WHERE id=?',(key,));self.store.db.commit()
        headers = {'Content-Type': 'application/json'}
        if os.environ.get('BANK_LLM_API_KEY'): headers['Authorization'] = 'Bearer ' + os.environ['BANK_LLM_API_KEY']
        req = urllib.request.Request(self.endpoint + '/chat/completions', json.dumps(request).encode(), headers)
        for attempt in range(3):
            try:
                with self.opener.open(req, timeout=180) as r: response = json.load(r)
                break
            except urllib.error.HTTPError as error:
                if error.code not in (429,500,502,503,504):
                    raise ModelFailure('Local inference rejected request: HTTP '+str(error.code)) from error
                if attempt == 2: raise ModelUnavailable('Local inference service is unavailable') from error
            except (urllib.error.URLError,TimeoutError,OSError) as error:
                if attempt == 2: raise ModelUnavailable('Local inference service is unreachable') from error
            time.sleep(attempt+1)
        choice = response['choices'][0]
        if choice.get('finish_reason') != 'stop': raise TruncatedOutput('Nonterminal or truncated model output')
        data = validate(json.loads(choice['message']['content']))
        self.store.db.execute('INSERT OR REPLACE INTO llm_cache VALUES(?,?)', (key, json.dumps(data, ensure_ascii=False)))
        self.store.db.commit()
        return data

    def screen(self, card):
        # Shrink sample only. Never truncate column names or silently alter cell values.
        payload = dict(card)
        payload['label_definitions'] = ontology()['events']
        while payload['sample'] and not self.fits(self.messages('screen', payload)):
            payload['sample'] = payload['sample'][::2] if len(payload['sample']) > 1 else []
        data = self.call('screen', payload, SCREEN_SCHEMA)
        return validate_screen(data, card)

    def extract(self, records, card):
        context = {k: card[k] for k in ('filename', 'sheet', 'columns', 'source')}
        payload = {'context': context, 'event_types': ontology()['events'], 'records': records}
        data = self.call('extract', payload, EXTRACTION_SCHEMA)
        return validate_results(data, records, card)
