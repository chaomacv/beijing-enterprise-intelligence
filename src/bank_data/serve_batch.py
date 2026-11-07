"""Local batch inference, with independent constrained decoders per prompt."""
import argparse
import ipaddress
import json
import os
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

from .serve import RequestError, TransformersBackend, handler_for


class BatchBackend(TransformersBackend):
    def generate_many(self, requests):
        from jsonschema import Draft202012Validator
        from lmformatenforcer import JsonSchemaParser
        from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn
        if not isinstance(requests,list) or not 1 <= len(requests) <= 4:
            raise RequestError('Batch size must be 1..4')
        maximum=requests[0].get('max_tokens',1024)
        if type(maximum) is not int or not 1 <= maximum <= 4096:raise RequestError('Invalid output budget')
        texts,schemas=[],[]
        for request in requests:
            if request.get('model')!=self.model_id or request.get('max_tokens',1024)!=maximum:
                raise RequestError('Batch model/output budgets must agree')
            messages=request.get('messages')
            if not isinstance(messages,list) or not messages:raise RequestError('Missing messages')
            schema=request['response_format']['json_schema']['schema'];Draft202012Validator.check_schema(schema)
            value=self.tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
            if len(self.tokenizer.encode(value,add_special_tokens=False))+maximum+256>self.context:
                raise RequestError('Context budget exceeded')
            texts.append(value);schemas.append(schema)
        if not self.lock.acquire(timeout=1):raise BlockingIOError('Local model is busy')
        start=time.monotonic()
        try:
            self.tokenizer.padding_side='left'
            if self.tokenizer.pad_token_id is None:self.tokenizer.pad_token=self.tokenizer.eos_token
            inputs=self.tokenizer(texts,padding=True,add_special_tokens=False,return_tensors='pt').to(self.model.device)
            width=inputs['input_ids'].shape[1]
            decoders=[build_transformers_prefix_allowed_tokens_fn(self.tokenizer_data,JsonSchemaParser(schema)) for schema in schemas]
            def allowed(batch_id,tokens):return decoders[batch_id](batch_id,tokens)
            self.torch.manual_seed(42)
            with self.torch.inference_mode():
                outputs=self.model.generate(**inputs,max_new_tokens=maximum,do_sample=False,
                    prefix_allowed_tokens_fn=allowed,pad_token_id=self.tokenizer.eos_token_id,logits_to_keep=1)
            eos=self.model.generation_config.eos_token_id;eos=eos if isinstance(eos,list) else [eos]
            items=[]
            for index,generated in enumerate(outputs[:,width:]):
                tokens=generated.tolist();end=next((i+1 for i,t in enumerate(tokens) if t in eos),len(tokens));tokens=tokens[:end]
                content=self.tokenizer.decode(tokens,skip_special_tokens=True)
                finish='stop' if tokens and tokens[-1] in eos else 'length'
                try:
                    if finish=='stop':Draft202012Validator(schemas[index]).validate(json.loads(content))
                    prompt=int(inputs['attention_mask'][index].sum())
                    items.append({'ok':True,'response':{'model':self.model_id,
                        'choices':[{'message':{'role':'assistant','content':content},'finish_reason':finish}],
                        'usage':{'prompt_tokens':prompt,'completion_tokens':len(tokens),'total_tokens':prompt+len(tokens)}}})
                except Exception as error:items.append({'ok':False,'error':type(error).__name__})
            print(json.dumps({'event':'batch_inference','items':len(items),'seconds':round(time.monotonic()-start,3),
                              'completion_tokens':sum(x.get('response',{}).get('usage',{}).get('completion_tokens',0) for x in items)}),flush=True)
            return {'items':items}
        except self.torch.cuda.OutOfMemoryError:
            self.torch.cuda.empty_cache();raise
        finally:self.lock.release()


def batch_handler(backend,key=None):
    class Handler(handler_for(backend,key)):
        def do_POST(self):
            if self.path!='/v1/batch/chat/completions':return super().do_POST()
            if not self.authorized():return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4*1024*1024:raise RequestError('Batch body exceeds limit')
                self.connection.settimeout(30)
                self.reply(200,backend.generate_many(json.loads(self.rfile.read(size))['requests']))
            except (BrokenPipeError,ConnectionResetError):pass
            except BlockingIOError:self.reply(503,{'error':{'type':'model_busy'}})
            except (ValueError,TypeError,KeyError):self.reply(400,{'error':{'type':'invalid_batch'}})
            except Exception as error:
                print(json.dumps({'event':'batch_error','type':type(error).__name__}),flush=True)
                self.reply(500,{'error':{'type':type(error).__name__}})
    return Handler


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir',type=Path,required=True);parser.add_argument('--model-id',required=True)
    parser.add_argument('--device',default='cuda:0');parser.add_argument('--port',type=int,default=18180)
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--context',type=int,default=8192)
    args=parser.parse_args()
    if not ipaddress.ip_address(args.host).is_loopback:raise ValueError('Loopback required')
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    backend=BatchBackend(args.model_dir,args.model_id,args.device,args.context,4)
    server=ThreadingHTTPServer((args.host,args.port),batch_handler(backend,os.environ.get('BANK_LLM_API_KEY')))
    print(json.dumps({'event':'ready','port':args.port,**backend.metadata()}),flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
