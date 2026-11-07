"""Private, source-budgeted batched inference transport for corpus jobs."""
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

from .common import dump,ontology,resource,stable_id
from .llm import NoRedirect,validate_endpoint


class BatchClient:
    def __init__(self,endpoint,model,tokenizer_dir,cache,context=8192):
        from transformers import AutoTokenizer
        self.endpoint=validate_endpoint(endpoint);self.model=model;self.context=context
        self.tokenizer=AutoTokenizer.from_pretrained(tokenizer_dir,local_files_only=True,trust_remote_code=False)
        self.cache=Path(cache);self.cache.mkdir(parents=True,exist_ok=True)
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())

    def request(self,system,payload,schema,maximum):
        messages=[{'role':'system','content':system},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]
        tokens=self.tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False)
        if len(tokens)+maximum+256>self.context:raise ValueError('context_budget_exceeded')
        return {'model':self.model,'messages':messages,'max_tokens':maximum,
                'temperature':0,'response_format':{'type':'json_schema','json_schema':{'name':'corpus','strict':True,'schema':schema}}}

    def screen_request(self,card,schema,prompt=None):
        if len(card['columns'])>512:raise ValueError('very_wide_schema_requires_header_review')
        payload={k:v for k,v in card.items() if k!='sample'}
        payload['table_context']=card['sample'][0].get('context',{}) if card['sample'] else {}
        payload['sample']=[{k:v for k,v in row.items() if k!='context'} for row in card['sample']]
        payload['label_definitions']=ontology()['events']
        while True:
            if len(json.dumps(payload,ensure_ascii=False))>100000:
                if payload['sample']:
                    payload['sample']=payload['sample'][::2] if len(payload['sample'])>1 else []
                    continue
                raise ValueError('file_card_char_budget_exceeded')
            try:return self.request(prompt or resource('screen.md')+'\nreason 简洁，不超过60个汉字。',payload,schema,512)
            except ValueError:
                if not payload['sample']:raise
                payload['sample']=payload['sample'][::2] if len(payload['sample'])>1 else []

    def call(self,requests):
        output=[None]*len(requests);pending=[]
        for i,request in enumerate(requests):
            key=stable_id('batch-greedy-v1',request)
            path=self.cache/(key+'.json')
            if path.exists():output[i]=json.loads(path.read_text(encoding='utf-8'))
            else:pending.append((i,request,path))
        if pending:
            batch=[r for _,r,_ in pending]
            req=urllib.request.Request(self.endpoint+'/batch/chat/completions',
                json.dumps({'requests':batch},ensure_ascii=False).encode('utf-8'),{'Content-Type':'application/json'})
            result=None
            for attempt in range(6):
                try:
                    with self.opener.open(req,timeout=300) as response:result=json.load(response)
                    if len(result['items'])!=len(pending):raise ValueError('batch_count_mismatch')
                    break
                except Exception as error:
                    if isinstance(error,urllib.error.HTTPError) and error.code==400:
                        if len(pending)>1:result={'items':[self.call([r])[0] for r in batch]}
                        else:result={'items':[{'ok':False,'error':'http_400_invalid_input'}]}
                        break
                    if isinstance(error,urllib.error.HTTPError) and error.code==500 and len(pending)>1:
                        smaller=self.call(batch[:len(batch)//2])+self.call(batch[len(batch)//2:])
                        result={'items':smaller};break
                    if attempt==5:
                        if len(pending)>1:
                            smaller=self.call(batch[:len(batch)//2])+self.call(batch[len(batch)//2:])
                            result={'items':smaller};break
                        raise
                    time.sleep(min(15,3*(attempt+1)))
            for (i,request,path),item in zip(pending,result['items']):
                output[i]=item
                if item.get('ok') and item['response']['choices'][0]['finish_reason']=='stop':dump(path,item)
        return output

    @staticmethod
    def content(item):
        if not item.get('ok'):raise ValueError('inference_'+item.get('error','failed'))
        choice=item['response']['choices'][0]
        if choice['finish_reason']!='stop':raise ValueError('truncated_output')
        return json.loads(choice['message']['content'])
