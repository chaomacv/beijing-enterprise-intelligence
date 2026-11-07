"""Loopback-only, schema-constrained local Transformers inference."""
import argparse
import hmac
import ipaddress
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class RequestError(ValueError):
    pass


class TransformersBackend:
    def __init__(self, model_dir, model_id, device='cuda:0', context=8192, cpu_threads=4):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        if not torch.cuda.is_available():
            raise RuntimeError('A CUDA-enabled PyTorch environment and available GPU are required')
        self.torch, self.model_id, self.context = torch, model_id, context
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True, trust_remote_code=False)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_dir, local_files_only=True, trust_remote_code=False, use_safetensors=True,
            torch_dtype=torch.bfloat16, device_map={'': device}, attn_implementation='sdpa').eval()
        torch.set_num_threads(cpu_threads)
        from lmformatenforcer.integrations.transformers import build_token_enforcer_tokenizer_data
        self.tokenizer_data = build_token_enforcer_tokenizer_data(self.tokenizer)
        self.lock = threading.Lock()

    def metadata(self):
        return {'model': self.model_id, 'backend': 'transformers-schema', 'context': self.context,
                'torch': self.torch.__version__, 'cuda': self.torch.version.cuda,
                'gpu': self.torch.cuda.get_device_name(self.model.device),
                'cpu_threads':self.torch.get_num_threads()}

    def generate(self, request):
        from jsonschema import Draft202012Validator
        from lmformatenforcer import JsonSchemaParser
        from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn
        if request.get('model') != self.model_id:
            raise RequestError('Unknown model; inspect /v1/models')
        messages = request.get('messages')
        if not isinstance(messages, list) or not messages or len(messages) > 32:
            raise RequestError('Expected a bounded messages array')
        if any(not isinstance(m, dict) or m.get('role') not in ('system', 'user', 'assistant') or not isinstance(m.get('content'), str) for m in messages):
            raise RequestError('Invalid message')
        fmt = request.get('response_format', {})
        if fmt.get('type') != 'json_schema' or not isinstance(fmt.get('json_schema', {}).get('schema'), dict):
            raise RequestError('response_format=json_schema is required')
        schema = fmt['json_schema']['schema']
        Draft202012Validator.check_schema(schema)
        maximum = request.get('max_tokens', 2048)
        if type(maximum) is not int or not 1 <= maximum <= 4096:
            raise RequestError('max_tokens must be an integer in 1..4096')
        temperature, top_p = request.get('temperature', .7), request.get('top_p', .8)
        if not isinstance(temperature, (int, float)) or not 0 <= temperature <= 2:
            raise RequestError('Invalid temperature')
        if not isinstance(top_p, (int, float)) or not 0 < top_p <= 1:
            raise RequestError('Invalid top_p')
        if request.get('chat_template_kwargs', {}).get('enable_thinking', False) is not False:
            raise RequestError('This service uses enable_thinking=false')
        if not self.lock.acquire(timeout=1):
            raise BlockingIOError('Local model is busy; retry later')
        started = time.monotonic()
        try:
            inputs = self.tokenizer.apply_chat_template(messages, tokenize=True, return_tensors='pt',
                return_dict=True, add_generation_prompt=True, enable_thinking=False).to(self.model.device)
            prompt_tokens = inputs['input_ids'].shape[-1]
            if prompt_tokens + maximum + 256 > self.context:
                raise RequestError('Request exceeds the input/output context budget')
            prefix = build_transformers_prefix_allowed_tokens_fn(self.tokenizer_data, JsonSchemaParser(schema))
            options = {'max_new_tokens': maximum, 'do_sample': temperature > 0,
                       'prefix_allowed_tokens_fn': prefix, 'pad_token_id': self.tokenizer.eos_token_id}
            if temperature > 0: options.update(temperature=temperature, top_p=top_p)
            self.torch.manual_seed(42)
            with self.torch.inference_mode():
                generated = self.model.generate(**inputs, **options)[0, prompt_tokens:]
            content = self.tokenizer.decode(generated, skip_special_tokens=True)
            eos = self.model.generation_config.eos_token_id
            eos = eos if isinstance(eos, list) else [eos]
            stopped = len(generated) < maximum or (len(generated) and int(generated[-1]) in eos)
            repaired=False;raw_content=content
            if stopped:
                from .common import decode_model_json
                value,repaired=decode_model_json(content)
                Draft202012Validator(schema).validate(value)
                content=json.dumps(value,ensure_ascii=False)
            response = {'object': 'chat.completion', 'model': self.model_id,
                        'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content},
                                     'finish_reason': 'stop' if stopped else 'length'}],
                        'usage': {'prompt_tokens': prompt_tokens, 'completion_tokens': len(generated),
                                  'total_tokens': prompt_tokens + len(generated)}}
            if repaired:response.update(json_string_controls_escaped=True,raw_generation=raw_content)
            print(json.dumps({'event': 'inference', 'model': self.model_id, **response['usage'],
                              'seconds': round(time.monotonic()-started, 3)}), flush=True)
            return response
        finally:
            self.lock.release()


def handler_for(backend, api_key=None):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *_):
            pass  # Request bodies and business evidence are never written to HTTP logs.

        def reply(self, status, value):
            raw = json.dumps(value, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self):
            if api_key and not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + api_key):
                self.reply(401, {'error': {'type': 'unauthorized'}})
                return False
            return True

        def do_GET(self):
            if not self.authorized(): return
            if self.path == '/healthz': self.reply(200, {'status': 'ready', **backend.metadata()})
            elif self.path == '/v1/models':
                self.reply(200, {'object': 'list', 'data': [{'id': backend.model_id, 'object': 'model'}]})
            else: self.reply(404, {'error': {'type': 'not_found'}})

        def do_POST(self):
            if not self.authorized(): return
            if self.path != '/v1/chat/completions':
                self.reply(404, {'error': {'type': 'not_found'}}); return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 512 * 1024: raise RequestError('Request body exceeds limit')
                self.connection.settimeout(30)
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict): raise RequestError('Expected a JSON object')
                self.reply(200, backend.generate(payload))
            except (BrokenPipeError, ConnectionResetError):
                print(json.dumps({'event':'client_disconnected'}),flush=True)
            except BlockingIOError:
                self.reply(503, {'error': {'type': 'model_busy'}})
            except (ValueError, TypeError, KeyError):
                self.reply(400, {'error': {'type': 'invalid_request'}})
            except Exception as error:
                print(json.dumps({'event': 'inference_error', 'type': type(error).__name__}), flush=True)
                self.reply(500, {'error': {'type': 'local_inference_failed'}})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--model-id', required=True, help='Use a new model ID when weights change')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--device', default='cuda:0')
    parser.add_argument('--context', type=int, default=8192)
    parser.add_argument('--cpu-threads',type=int,default=4)
    args = parser.parse_args()
    if not ipaddress.ip_address(args.host).is_loopback:
        raise ValueError('The model service must bind to a loopback address')
    if not args.model_dir.is_dir() or args.context < 1024 or not 1 <= args.cpu_threads <= 128:
        raise ValueError('Invalid local model path or context')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    backend = TransformersBackend(args.model_dir, args.model_id, args.device, args.context,args.cpu_threads)
    server = ThreadingHTTPServer((args.host, args.port), handler_for(backend, os.environ.get('BANK_LLM_API_KEY')))
    print(json.dumps({'event': 'ready', 'host': args.host, 'port': args.port, **backend.metadata()}), flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == '__main__': main()
