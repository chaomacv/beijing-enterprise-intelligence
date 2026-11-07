"""Local OCR, XML metadata and FileGDB conversion with original-member lineage."""
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor,as_completed
from functools import lru_cache
import csv
import hashlib
import json
import math
import os
from pathlib import Path,PurePosixPath
import time

from .common import dump,file_hash,stable_id
from .document_readers import text_fragments
from .scan import profile_file


def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+str(os.getpid())+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,default=lambda v:v.tolist() if hasattr(v,'tolist') else str(v)),encoding='utf-8');temp.replace(path)


@lru_cache(maxsize=1)
def ocr_engine():
    import onnxruntime
    onnxruntime.disable_telemetry_events()
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR(intra_op_num_threads=1,inter_op_num_threads=1,det_limit_side_len=1400)


def ocr_file(profile,root):
    import numpy as np
    root=Path(root);cache=root/'01_inputs/ocr_cache';cache.mkdir(parents=True,exist_ok=True)
    key=stable_id('rapidocr-onnx-1.4.4-side1400-v1',profile['sha256'])
    saved=cache/(key+'.json')
    if saved.exists():return json.loads(saved.read_text(encoding='utf-8'))
    pages=[];engine=ocr_engine()
    if profile['kind']=='pdf':
        import pymupdf
        with pymupdf.open(profile['path']) as document:
            for index,page in enumerate(document,1):
                native=page.get_text(sort=True)
                if native.strip():pages.append({'page':index,'source':'pdf_native_text','text':native,'lines':[]});continue
                pix=page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5),alpha=False)
                image=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,pix.n)
                if pix.n>=3:image=image[:,:,:3][:,:,::-1].copy()
                lines,_=engine(image)
                if not lines:raise ValueError('OCR_NO_TEXT_ON_PAGE_'+str(index))
                pages.append({'page':index,'source':'rapidocr_cpu','text':'\n'.join(v[1] for v in lines),'lines':lines})
    else:
        lines,_=engine(profile['path'])
        if not lines:raise ValueError('OCR_NO_RECOGNIZED_TEXT')
        pages.append({'page':1,'source':'rapidocr_cpu','text':'\n'.join(v[1] for v in lines),'lines':lines})
    value={'source_sha256':profile['sha256'],'engine':'rapidocr_onnxruntime_1.4.4','signature':key,'pages':pages,
           'ocr_is_unverified_recognition':True}
    atomic(saved,value);return value


def native_one(args):
    profile,root=args;root=Path(root);fid=profile['file_id']
    try:
        if profile['kind']=='xml':
            from defusedxml.ElementTree import parse
            tree=parse(profile['path']);node=tree.getroot();tag=node.tag.rsplit('}',1)[-1].lower()
            if tag not in ('metadata','md_metadata'):
                target=root/'01_inputs/xml_tables'/fid;target.mkdir(parents=True,exist_ok=True)
                output=target/'records.jsonl'
                def flatten(element,path,result):
                    for key,value in element.attrib.items():result[path+'/@'+key]=value
                    if element.text and element.text.strip():result[path+'/text()']=element.text
                    numbers=Counter()
                    for child in element:
                        numbers[child.tag]+=1
                        flatten(child,path+'/'+child.tag+'['+str(numbers[child.tag])+']',result)
                    if element.tail and element.tail.strip():result[path+'/tail()']=element.tail
                with output.with_suffix('.part').open('w',encoding='utf-8') as stream:
                    for index,child in enumerate(list(node) or [node],1):
                        fields={};flatten(child,child.tag,fields)
                        fields['__xml_record_index__']=str(index)
                        for key,value in node.attrib.items():fields['__root_attribute__/@'+key]=value
                        stream.write(json.dumps(fields,ensure_ascii=False)+'\n')
                output.with_suffix('.part').replace(output)
                metadata={**profile.get('source',{}),'root_file_id':profile.get('root_file_id') or fid,
                    'parent_file_id':fid,'file_name':profile['filename'],'sha256':file_hash(output),
                    'source_kind':'xml_xpath_fields','derived_from_sha256':profile['sha256']}
                dump(target/'provenance.json',metadata)
                child=profile_file(output,'xml/'+fid+'/records.jsonl',root/'02_profiles/native_cache',retry_review=True)
                child['root_file_id']=metadata['root_file_id']
                return [{**profile,'status':'CONVERTED','cards':[],'records':0,'derived_file_id':child['file_id']},child]
            values=[]
            def walk(element,path):
                name=element.tag.rsplit('}',1)[-1];current=path+'/'+name
                if element.text and element.text.strip():values.append({'path':current,'text':element.text,'attributes':element.attrib})
                for child in element:walk(child,current)
            walk(node,'')
            path=root/'01_inputs/xml_metadata'/(fid+'.json');atomic(path,{'file_id':fid,'source_sha256':profile['sha256'],'fields':values})
            return [{**profile,'status':'METADATA','cards':[],'records':0,'metadata_artifact':str(path),
                     'interpretation':'Structured dataset metadata; not a business-record table'}]
        data=ocr_file(profile,root)
        target=root/'01_inputs/native_text'/fid;target.mkdir(parents=True,exist_ok=True)
        output=target/'records.jsonl'
        with output.with_suffix('.part').open('w',encoding='utf-8') as stream:
            for page in data['pages']:
                confidence=min((float(v[2]) for v in page['lines']),default=1.0)
                for start,end,text in text_fragments(page['text']):
                    stream.write(json.dumps({'__text__':text,'__page__':str(page['page']),
                        '__char_start__':str(start),'__char_end__':str(end),'__ocr_min_confidence__':str(confidence),
                        '__text_source__':page['source']},ensure_ascii=False)+'\n')
        output.with_suffix('.part').replace(output)
        metadata={**profile.get('source',{}),'root_file_id':profile.get('root_file_id') or fid,'parent_file_id':fid,
            'file_name':profile['filename'],'sha256':file_hash(output),'source_kind':'native_document_or_ocr_text',
            'derived_from_sha256':profile['sha256'],'ocr_engine':data['engine'],'ocr_signature':data['signature']}
        dump(target/'provenance.json',metadata)
        child=profile_file(output,'native/'+fid+'/records.jsonl',root/'02_profiles/native_cache',retry_review=True)
        child['root_file_id']=metadata['root_file_id']
        return [{**profile,'status':'CONVERTED','cards':[],'records':0,'derived_file_id':child['file_id']},child]
    except Exception as error:
        return [{**profile,'native_attempt':'attempted','native_error':type(error).__name__+': '+str(error)[:200]}]


def gdb_groups(profiles,root):
    import pyogrio
    import pyogrio.raw
    root=Path(root);groups=defaultdict(list);output=[];consumed={}
    for p in profiles:
        source=p.get('source',{});member=source.get('archive_member','').replace('\\','/')
        parts=PurePosixPath(member).parts
        index=next((i for i,value in enumerate(parts) if value.lower().endswith('.gdb')),None)
        if index is not None:groups[(source.get('parent_file_id'),'/'.join(parts[:index+1]))].append((p,parts[index+1:]))
    ledger=[]
    for (parent,prefix),entries in groups.items():
        key=stable_id(parent,prefix);directory=root/'01_inputs/geodatabases'/key/PurePosixPath(prefix).name
        directory.mkdir(parents=True,exist_ok=True)
        try:
            for profile,relative in entries:
                if not relative:continue
                target=directory.joinpath(*relative);target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists():
                    if file_hash(target)!=profile['sha256']:raise ValueError('Conflicting FileGDB member')
                else:os.link(profile['path'],target)
            layers=pyogrio.list_layers(directory)
            children=[]
            for layer_number,(name,geometry_type) in enumerate(layers):
                destination=root/'01_inputs/geodatabase_tables'/key/str(layer_number);destination.mkdir(parents=True,exist_ok=True)
                csvpath=destination/'attributes.csv';binary=destination/'geometry.wkb'
                info=pyogrio.read_info(directory,layer=name)
                fields=[str(v) for v in info['fields']]
                with csvpath.open('w',encoding='utf-8-sig',newline='') as f,binary.open('wb') as geometry:
                    writer=csv.writer(f);writer.writerow(fields+['__feature_id__','__geometry_offset__','__geometry_bytes__'])
                    offset=0
                    while True:
                        meta,fids,geometries,arrays=pyogrio.raw.read(directory,layer=name,return_fids=True,
                            skip_features=offset,max_features=10000,read_geometry=True)
                        count=len(fids)
                        if not count:break
                        for i in range(count):
                            values=[]
                            for array in arrays:
                                value=array[i]
                                if hasattr(value,'item'):value=value.item()
                                if value is None or isinstance(value,float) and math.isnan(value):value=''
                                values.append(str(value))
                            data=geometries[i] if geometries is not None and geometries[i] is not None else b''
                            position=geometry.tell();geometry.write(data)
                            writer.writerow(values+[str(fids[i]),position,len(data)])
                        offset+=count
                first=entries[0][0]
                metadata={**first.get('source',{}),'root_file_id':first.get('root_file_id') or first['file_id'],
                    'parent_file_id':parent,'file_name':prefix+' / '+str(name),'sha256':file_hash(csvpath),
                    'source_kind':'gdal_filegdb_attributes','geometry_source':str(binary),'geometry_crs':str(info.get('crs')),
                    'native_member_ids':[p['file_id'] for p,_ in entries]}
                dump(destination/'provenance.json',metadata)
                child=profile_file(csvpath,'geodatabase/'+key+'/'+str(layer_number),root/'02_profiles/native_cache',retry_review=True)
                child['root_file_id']=metadata['root_file_id'];children.append(child);output.append(child)
            for p,_ in entries:consumed[p['file_id']]={'status':'COMPONENT','consumed_by':[c['file_id'] for c in children],'cards':[],'records':0}
            ledger.append({'group_id':key,'source_members':[p['file_id'] for p,_ in entries],'layers':len(children),
                'records':sum(p['records'] for p in children),'status':'DECODED'})
        except Exception as error:ledger.append({'group_id':key,'status':'REVIEW','reason':type(error).__name__+': '+str(error)[:200]})
    dump(root/'01_inputs/geodatabase_groups.json',ledger);return output,consumed


def enrich(profiles,root,workers=6):
    root=Path(root);cache=root/'02_profiles/native_cache';cache.mkdir(parents=True,exist_ok=True)
    geo,consumed=gdb_groups(profiles,root);output=list(geo);tasks=[]
    for profile in profiles:
        if profile['file_id'] in consumed:output.append({**profile,**consumed[profile['file_id']]})
        elif profile['status']=='REVIEW' and profile.get('kind') in ('jpg','jpeg','png','pdf','xml'):
            tasks.append((profile,str(root)))
        elif profile.get('kind') in ('htm',):
            try:
                fixed=profile_file(profile['path'],profile['relative_path'],cache,retry_review=True)
                output.append({**fixed,'root_file_id':profile.get('root_file_id') or profile['file_id']})
            except Exception:output.append(profile)
        else:output.append(profile)
    start=time.monotonic();completed=0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(native_one,item) for item in tasks]
        for future in as_completed(futures):
            output.extend(future.result());completed+=1
            if completed%20==0 or completed==len(tasks):
                value={'stage':'02_native','completed_files':completed,'total_files':len(tasks),'seconds':round(time.monotonic()-start,1)}
                dump(root/'02_profiles/native_progress.json',value);print(json.dumps(value),flush=True)
    output=sorted({p['file_id']:p for p in output}.values(),key=lambda p:p['relative_path'])
    dump(root/'02_profiles/all_profiles_native.json',output)
    with (root/'02_profiles/file_cards_native.jsonl').open('w',encoding='utf-8') as stream:
        for profile in output:
            for card in profile['cards']:stream.write(json.dumps(card,ensure_ascii=False)+'\n')
    summary={'complete':True,'logical_files':len(output),'scopes':sum(len(p['cards']) for p in output),
        'statuses':dict(Counter(p['status'] for p in output)),'records':sum(p['records'] for p in output),'seconds':round(time.monotonic()-start,2)}
    dump(root/'02_profiles/native_summary.json',summary);print(json.dumps(summary),flush=True);return output
