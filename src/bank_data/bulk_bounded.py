"""Finite object slots avoid unbounded entity/event array generation."""
import copy,json

from .bulk_client import BatchClient
from .bulk_references import ReferenceClient,PROMPT
from .common import file_hash,stable_id
from .extract import obj

CAPACITY=8
INSTRUCTION='''输出采用有界槽位，替代前面的数组格式说明。records 的 r0 等键不变，每条 status 仍为 EXTRACTED/NO_EVENT/REVIEW。
entities 是对象，最多 e0 到 e7 八个可选槽位；每个值仍是 role、kind、name 和可选 credit_code、address。只填真实具名机构，同一机构同一角色不得重复。缺失值可 null，空槽位省略。不能为了填充槽位虚构 authority；“行政处罚”“高新技术企业认定”“监督检查结果”等是事件或结果名称，绝不是机构，不能列入 entities。只有明确具名的真实机关才可作为 authority。
events 是对象，最多 v0 到 v7 八个可选槽位；每项用 subject_slot="e0" 等引用本条实体槽位，不能用 record_key 或其他记录的槽位。
evidence 是字段名到布尔值的对象，选用的来源字段为 true，无需列无关字段，程序复制全文。没有事件时省略 events。
如果实际需要超过八个主体或八个事件，needs_review=true 并输出 REVIEW，不默默只取前八个。没有事件或主体时省略对应对象；REVIEW 不输出事实。只输出 JSON。
示例：{"records":{"r0":{"status":"EXTRACTED","entities":{"e0":{"role":"subject","kind":"business","name":{"field":"企业名称","value":"合成甲公司"},"credit_code":null}},"events":{"v0":{"subject_slot":"e0","event_type":"innovation","status":"proposed","evidence":{"结果":true},"date":null}}},"r1":{"status":"NO_EVENT"}}}'''


def wire_schema(contract):
    contract=copy.deepcopy(contract)
    for row in contract['properties']['records']['properties'].values():
        props=row['properties'];entity=props['entities']['items'];event=props['events']['items'];event_props=event['properties']
        fields=event_props['evidence']['items']['enum'];event_props.pop('subject_index')
        event_props['subject_slot']={'type':'string','enum':['e'+str(i) for i in range(CAPACITY)]}
        event['required']=['subject_slot' if key=='subject_index' else key for key in event['required']]
        event_props['evidence']={'type':'object','properties':{field:{'type':'boolean'} for field in fields},'additionalProperties':False}
        props['entities']={'type':'object','properties':{'e'+str(i):copy.deepcopy(entity) for i in range(CAPACITY)},'additionalProperties':False}
        props['events']={'type':'object','properties':{'v'+str(i):copy.deepcopy(event) for i in range(CAPACITY)},'additionalProperties':False}
        props['needs_review']={'type':'boolean'}
    return contract


def normalize(data,contract):
    from jsonschema import Draft202012Validator
    try:Draft202012Validator(wire_schema(contract)).validate(data)
    except Exception as error:raise ValueError('Invalid bounded source schema') from error
    result={'records':{}};reasons={};slot_maps={}
    for key,value in data['records'].items():
        if value.get('needs_review'):
            result['records'][key]={'status':'REVIEW'};reasons[key]='bounded_output_capacity_or_uncertainty_requires_review';continue
        reason=None
        if value['status']=='REVIEW' and (value.get('entities') or value.get('events')):reason='model_review_candidates_not_published'
        elif value['status']=='EXTRACTED' and not value.get('events'):reason='extracted_status_without_event_requires_review'
        elif value['status']=='NO_EVENT' and value.get('events'):reason='no_event_status_conflicts_with_events_requires_review'
        elif value.get('events') and any(not any(event['evidence'].values()) for event in value['events'].values()):reason='extracted_event_without_evidence_requires_review'
        if reason:
            result['records'][key]={'status':'REVIEW'};reasons[key]=reason;continue
        entities=[];entity_keys={};slots={}
        for i in range(CAPACITY):
            slot='e'+str(i)
            if slot not in value.get('entities',{}):continue
            entity=value['entities'][slot];fingerprint=stable_id(entity)
            if fingerprint not in entity_keys:entity_keys[fingerprint]=len(entities);entities.append(entity)
            slots[slot]=entity_keys[fingerprint]
        events=[];event_keys=set()
        for i in range(CAPACITY):
            slot='v'+str(i)
            if slot not in value.get('events',{}):continue
            event=copy.deepcopy(value['events'][slot]);subject=event.pop('subject_slot')
            if subject not in slots:raise ValueError('Event references a missing subject slot')
            event['subject_index']=slots[subject];event['evidence']=[field for field,use in event['evidence'].items() if use]
            fingerprint=stable_id(event)
            if fingerprint not in event_keys:event_keys.add(fingerprint);events.append(event)
        result['records'][key]={'status':value['status'],'entities':entities,'events':events};slot_maps[key]=slots
    return result,reasons,slot_maps


class BoundedTransport:
    def __init__(self,*args,**kwargs):
        self.inner=BatchClient(*args,**kwargs);self.cache=self.inner.cache;self.tokenizer=self.inner.tokenizer;self.token_counts=self.inner.token_counts
        self.contracts={}

    @staticmethod
    def signature():return stable_id('bounded-object-slots-v1',file_hash(__file__),CAPACITY,INSTRUCTION)

    def request(self,system,payload,contract,maximum):
        system=system.replace(PROMPT,PROMPT.split('示例：')[0])+INSTRUCTION
        request=self.inner.request(system,payload,wire_schema(contract),maximum);self.contracts[stable_id(request)]=contract
        return request

    def call(self,requests):
        raw=self.inner.call(requests);results=[]
        for request,item in zip(requests,raw):
            if not item.get('ok'):results.append(item);continue
            try:
                choice=item['response']['choices'][0]
                if choice['finish_reason']!='stop':results.append(item);continue
                def pairs(items):
                    if len({key for key,_ in items})!=len(items):raise ValueError('Duplicate JSON object key')
                    return dict(items)
                value=json.loads(choice['message']['content'],object_pairs_hook=pairs);normalized,reasons,slots=normalize(value,self.contracts[stable_id(request)])
                output=copy.deepcopy(item);output['wire_response_item']=copy.deepcopy(item)
                output['wire_review_reasons']=reasons;output['wire_subject_slots']=slots
                output['response']['choices'][0]['message']['content']=json.dumps(normalized,ensure_ascii=False);results.append(output)
            except (ValueError,TypeError,KeyError) as error:results.append({'ok':False,'error':type(error).__name__+': '+str(error)[:150],'wire_response_item':item})
        for request in requests:self.contracts.pop(stable_id(request),None)
        return results


class BoundedReferenceClient(ReferenceClient):
    method='local_llm_bounded_source_references'
    transport_class=BoundedTransport
