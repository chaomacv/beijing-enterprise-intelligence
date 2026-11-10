"""Expand source containers locally and retain an explicit parent/member ledger."""
import argparse
import base64
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path,PurePosixPath
import shutil

from .common import dump,file_hash,stable_id
from .readers import detect
from .scan import profile_file


def member_name(value):
    """libarchive returns bytes when its locale cannot decode an entry name."""
    if isinstance(value, bytes):
        encoded=base64.b64encode(value).decode('ascii')
        for encoding in ('utf-8','gb18030','latin-1'):
            try:return value.decode(encoding),{'pathname_bytes_base64':encoded,'pathname_encoding':encoding}
            except UnicodeDecodeError:continue
    return str(value),{}


def expand_one(profile,root,depth=0):
    import libarchive
    root=Path(root);fid=profile['file_id'];origin=profile.get('root_file_id') or fid
    stage=root/'01_inputs/expanded'/fid;stage.mkdir(parents=True,exist_ok=True)
    ledger=stage/'members.json'
    if ledger.exists():return json.loads(ledger.read_text(encoding='utf-8'))
    members=[];total=0
    if depth>3:raise ValueError('Nested archive depth exceeds 3')
    with libarchive.file_reader(profile['path']) as archive:
        for index,entry in enumerate(archive,1):
            if index>10000:raise ValueError('Archive member count exceeds 10000')
            name,name_metadata=member_name(entry.pathname);name=name.replace('\\','/');relative=PurePosixPath(name)
            value={'member':name,**name_metadata,'member_index':index,'root_file_id':origin,'parent_file_id':fid,'status':'PENDING'}
            if entry.isdir:continue
            if not entry.isfile or relative.is_absolute() or '..' in relative.parts:
                value.update(status='REVIEW',reason='Nonregular or unsafe archive member');members.append(value);continue
            target=stage/(str(index)+'_'+stable_id(name));target.mkdir(exist_ok=True)
            path=target/(relative.name or 'unnamed')
            temporary=path.with_name(path.name+'.part');written=0
            try:
                with temporary.open('wb') as out:
                    for block in entry.get_blocks():
                        written+=len(block);total+=len(block)
                        if written>2*1024**3 or total>16*1024**3:raise ValueError('Archive expansion byte limit exceeded')
                        out.write(block)
                temporary.replace(path)
                sha=file_hash(path)
                metadata={**profile.get('source',{}),'root_file_id':origin,'parent_file_id':fid,
                    'parent_filename':profile['filename'],'parent_sha256':profile['sha256'],
                    'archive_member':name,'archive_member_ordinal':index,'sha256':sha,
                    'file_name':profile['filename']+' / '+name}
                dump(target/'provenance.json',metadata)
                value.update(path=str(path),bytes=written,sha256=sha,status='EXPANDED')
            except Exception as error:
                value.update(status='REVIEW',reason=type(error).__name__+': '+str(error)[:200])
            members.append(value)
    dump(ledger,members);return members


def profile_member(args):
    path,relative,cache,origin=args
    result=profile_file(path,relative,cache,retry_review=True)
    result['root_file_id']=origin
    return result


def prepare_inputs(profiles,root,workers=4):
    root=Path(root);stage=root/'02_profiles';stage.mkdir(parents=True,exist_ok=True)
    cache=stage/'extended_cache';cache.mkdir(exist_ok=True)
    output=[];members=[];tasks=[]
    def accept(profile,depth=0):
        profile={**profile,'root_file_id':profile.get('root_file_id') or profile['file_id']}
        kind=profile.get('kind')
        if kind in ('unsupported_archive','rar'):
            try:
                entries=expand_one(profile,root,depth);members.extend(entries)
                output.append({**profile,'status':'CONTAINER','cards':[],'records':0,'expanded_members':len(entries)})
                for entry in entries:
                    if entry['status']!='EXPANDED':continue
                    path=Path(entry['path']);relative='archive/'+profile['file_id']+'/'+str(entry['member_index'])+'/'+path.name
                    child=profile_file(path,relative,cache,retry_review=True);child['root_file_id']=profile['root_file_id']
                    if child.get('kind') in ('unsupported_archive','rar'):accept(child,depth+1)
                    else:output.append(child)
            except Exception as error:
                output.append({**profile,'status':'REVIEW','cards':[],'error':type(error).__name__+': '+str(error)[:180]})
        elif profile['status']=='REVIEW':tasks.append((profile['path'],profile['relative_path'],str(cache),profile['root_file_id']))
        else:output.append(profile)
    for index,profile in enumerate(profiles,1):
        accept(profile)
        if index%100==0:print(json.dumps({'stage':'02_profiles','original_files':index,'total':len(profiles),'expanded_entries':len(members)}),flush=True)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(profile_member,tasks):output.append(result)
    output=sorted({p['file_id']:p for p in output}.values(),key=lambda p:p['relative_path'])
    dump(root/'01_inputs/archive_members.json',members)
    dump(stage/'all_profiles.json',output)
    with (stage/'file_cards.jsonl').open('w',encoding='utf-8') as f:
        for p in output:
            for c in p['cards']:f.write(json.dumps(c,ensure_ascii=False)+'\n')
    summary={'original_files':len(profiles),'all_logical_files':len(output),'archive_members':len(members),
        'statuses':dict(Counter(p['status'] for p in output)),'scopes':sum(len(p['cards']) for p in output),
        'profiled_records':sum(p['records'] for p in output),'all_original_files_accounted_for':len({p['root_file_id'] for p in output})==len(profiles)}
    dump(stage/'summary.json',summary);print(json.dumps(summary),flush=True)
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profiles',type=Path,required=True)
    p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--workers',type=int,default=4);a=p.parse_args()
    prepare_inputs(json.loads(a.profiles.read_text(encoding='utf-8')),a.work_dir,a.workers)


if __name__=='__main__':main()
