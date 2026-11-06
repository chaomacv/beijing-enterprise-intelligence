import ipaddress
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .common import resource, stable_id
from .extract import EXTRACTION_SCHEMA, SCREEN_SCHEMA, validate_results, validate_screen


class ModelFailure(RuntimeError): pass
class TruncatedOutput(ModelFailure): pass


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
        self.name = 'local-qwen-' + stable_id(model, str(Path(tokenizer_dir).resolve()), context, max_output,
                                             resource('screen.md'), resource('extract.md'))
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

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
        if cached: return json.loads(cached['result'])
        headers = {'Content-Type': 'application/json'}
        if os.environ.get('BANK_LLM_API_KEY'): headers['Authorization'] = 'Bearer ' + os.environ['BANK_LLM_API_KEY']
        req = urllib.request.Request(self.endpoint + '/chat/completions', json.dumps(request).encode(), headers)
        try:
            with self.opener.open(req, timeout=180) as r: response = json.load(r)
        except Exception as e:
            raise ModelFailure('Local inference request failed; no external fallback') from e
        choice = response['choices'][0]
        if choice.get('finish_reason') != 'stop': raise TruncatedOutput('Nonterminal or truncated model output')
        data = json.loads(choice['message']['content'])
        self.store.db.execute('INSERT OR REPLACE INTO llm_cache VALUES(?,?)', (key, json.dumps(data, ensure_ascii=False)))
        self.store.db.commit()
        return data

    def screen(self, card):
        # Shrink sample only. Never truncate column names or silently alter cell values.
        payload = dict(card)
        while payload['sample'] and not self.fits(self.messages('screen', payload)):
            payload['sample'] = payload['sample'][::2] if len(payload['sample']) > 1 else []
        data = self.call('screen', payload, SCREEN_SCHEMA)
        return validate_screen(data, card)

    def extract(self, records, card):
        context = {k: card[k] for k in ('filename', 'sheet', 'columns', 'source')}
        payload = {'context': context, 'event_types': list(EXTRACTION_SCHEMA['properties']['results']['items']['properties']['events']['items']['properties']['event_type']['enum']), 'records': records}
        data = self.call('extract', payload, EXTRACTION_SCHEMA)
        return validate_results(data, records)
