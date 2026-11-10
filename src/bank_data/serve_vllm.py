"""Optional vLLM implementation of the existing loopback batch protocol."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import threading
import time
from http.server import ThreadingHTTPServer

from .common import decode_model_json
from .serve import RequestError
from .serve_batch import batch_handler


def decoding_schema(schema):
    """Old XGrammar handles structure; the full original schema is checked below."""
    if isinstance(schema,list):return [decoding_schema(value) for value in schema]
    if not isinstance(schema,dict):return schema
    output={}
    for key,value in schema.items():
        if key in {'minItems','maxItems','minimum','maximum'}:continue
        if key in {'properties','patternProperties','$defs','definitions'}:
            output[key]={name:decoding_schema(child) for name,child in value.items()}
        elif key in {'enum','const','default','examples'}:output[key]=value
        else:output[key]=decoding_schema(value)
    return output


class VLLMBackend:
    def __init__(self,model_dir,model_id,context=8192,enforce_eager=False):
        import vllm
        from vllm.sampling_params import GuidedDecodingParams
        from transformers import AutoTokenizer
        self.model_id,self.context=model_id,context;self.enforce_eager=enforce_eager
        self.version=vllm.__version__;self.lock=threading.Lock()
        self.tokenizer=AutoTokenizer.from_pretrained(model_dir,local_files_only=True,trust_remote_code=False)
        self.parameters,self.guidance=vllm.SamplingParams,GuidedDecodingParams
        self.engine=vllm.LLM(model=str(model_dir),tokenizer=str(model_dir),trust_remote_code=False,
            dtype='bfloat16',max_model_len=context,max_num_seqs=4,gpu_memory_utilization=0.90,
            enforce_eager=enforce_eager,enable_prefix_caching=True,disable_log_stats=True,seed=42)

    def metadata(self):
        return {'model':self.model_id,'backend':'vllm-schema','version':self.version,'context':self.context,
            'max_batch_requests':4,'enable_thinking':False,'weight_format':'original_bfloat16',
            'numeric_and_array_bounds':'full_original_schema_validated_after_generation',
            'cuda_graphs':not self.enforce_eager}

    def generate(self,request):
        item=self.generate_many([request])['items'][0]
        if not item['ok']:raise RequestError(item['error'])
        return item['response']

    def generate_many(self,requests):
        from jsonschema import Draft202012Validator
        if not isinstance(requests,list) or not 1<=len(requests)<=4:raise RequestError('Batch size must be 1..4')
        prompts=[];parameters=[];schemas=[]
        for request in requests:
            maximum=request.get('max_tokens',1024)
            if request.get('model')!=self.model_id or type(maximum) is not int or not 1<=maximum<=4096:
                raise RequestError('Invalid model or output budget')
            if request.get('temperature',0)!=0:raise RequestError('Corpus inference requires greedy decoding')
            schema=request['response_format']['json_schema']['schema'];Draft202012Validator.check_schema(schema)
            prompt=self.tokenizer.apply_chat_template(request['messages'],tokenize=False,add_generation_prompt=True,enable_thinking=False)
            if len(self.tokenizer.encode(prompt,add_special_tokens=False))+maximum+256>self.context:
                raise RequestError('Context budget exceeded')
            prompts.append(prompt);schemas.append(schema)
            parameters.append(self.parameters(temperature=0,max_tokens=maximum,seed=42,
                guided_decoding=self.guidance(json=decoding_schema(schema),backend='xgrammar:disable-any-whitespace')))
        if not self.lock.acquire(timeout=1):raise BlockingIOError('Local model is busy')
        started=time.monotonic()
        try:
            outputs=self.engine.generate(prompts,parameters,use_tqdm=False)
            if len(outputs)!=len(requests):raise RuntimeError('Engine batch count mismatch')
            items=[]
            for output,schema in zip(outputs,schemas):
                generated=output.outputs[0];content=generated.text;raw=content;repaired=False
                try:
                    if generated.finish_reason=='stop':
                        value,repaired=decode_model_json(content);Draft202012Validator(schema).validate(value)
                        content=json.dumps(value,ensure_ascii=False)
                    prompt_tokens=len(output.prompt_token_ids);completion_tokens=len(generated.token_ids)
                    items.append({'ok':True,'response':{'model':self.model_id,'backend':'vllm-schema-'+self.version,
                        'choices':[{'message':{'role':'assistant','content':content},'finish_reason':generated.finish_reason}],
                        'usage':{'prompt_tokens':prompt_tokens,'completion_tokens':completion_tokens,'total_tokens':prompt_tokens+completion_tokens}},
                        'json_string_controls_escaped':repaired,**({'raw_generation':raw} if repaired else {})})
                except Exception as error:
                    items.append({'ok':False,'error':type(error).__name__,'invalid_content':content})
            print(json.dumps({'event':'batch_inference','backend':'vllm','items':len(items),
                'seconds':round(time.monotonic()-started,3),
                'completion_tokens':sum(v.get('response',{}).get('usage',{}).get('completion_tokens',0) for v in items)}),flush=True)
            return {'items':items}
        finally:self.lock.release()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir',type=Path,required=True);parser.add_argument('--model-id',required=True)
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=18183)
    parser.add_argument('--context',type=int,default=8192);parser.add_argument('--enforce-eager',action='store_true');args=parser.parse_args()
    if not ipaddress.ip_address(args.host).is_loopback:raise ValueError('Loopback required')
    for key,value in {'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','VLLM_NO_USAGE_STATS':'1',
                      'DO_NOT_TRACK':'1','VLLM_USE_V1':'0','TOKENIZERS_PARALLELISM':'false'}.items():os.environ[key]=value
    backend=VLLMBackend(args.model_dir,args.model_id,args.context,args.enforce_eager)
    server=ThreadingHTTPServer((args.host,args.port),batch_handler(backend,os.environ.get('BANK_LLM_API_KEY')))
    print(json.dumps({'event':'ready','port':args.port,**backend.metadata()}),flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
