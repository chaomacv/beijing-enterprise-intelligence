"""Bounded-memory file cards before raw records are admitted to the fact store."""
import json
import random
import time
from collections import Counter, deque
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from .common import dump, file_hash, stable_id
from .prepare import source_metadata
from .readers import READER_VERSION, detect, discover, read_records, reader_version

PROFILE_VERSION = 'profile-v1-head3-middle3-tail3-reservoir5'
KINDS = {'csv', 'xlsx', 'xls', 'json', 'jsonl', 'ndjson', 'xml', 'rdf'}


def profile_file(path, relative, cache_dir, retry_review=False):
    path, cache_dir = Path(path), Path(cache_dir)
    try:
        digest = file_hash(path)
        source = source_metadata(path)
    except Exception as error:
        return {'file_id':stable_id(READER_VERSION,relative,'unreadable'),'relative_path':relative,
                'path':str(path),'sha256':None,'bytes':None,'filename':path.name,'source':{},
                'cards':[],'records':0,'status':'REVIEW','error':type(error).__name__}
    kind, detection_error = 'unknown', None
    try: kind = detect(path)
    except Exception as error: detection_error = error
    version = reader_version(kind)
    fid = stable_id(version, relative, digest)
    key = stable_id(PROFILE_VERSION, fid, source)
    cache = cache_dir / (key + '.json')
    if cache.exists():
        previous = json.loads(cache.read_text(encoding='utf-8'))
        if not retry_review or previous['status'] != 'REVIEW':
            return {**previous,'path':str(path)}
    profile = {'file_id': fid, 'relative_path': relative, 'path': str(path), 'sha256': digest,
               'bytes': path.stat().st_size, 'filename': source.get('file_name', path.name),
               'source': source, 'reader_version': version, 'cards': [], 'records': 0}
    try:
        if source.get('sha256') and source['sha256'] != digest:
            raise ValueError('Input differs from its provenance checksum')
        if detection_error: raise detection_error
        profile['kind'] = kind
        if kind not in KINDS: raise ValueError('Reader not enabled for format: ' + kind)
        scopes = {}
        for sheet, ordinal, cells, context in read_records(path, kind):
            if sheet not in scopes:
                scopes[sheet] = {'n': 0, 'columns': set(), 'flags': set(), 'head': [],
                                 'tail': deque(maxlen=3), 'random': [], 'rng': random.Random(42)}
            scope = scopes[sheet]; scope['n'] += 1
            if len(scope['columns']) <= 2000: scope['columns'].update(cells)
            if len(scope['columns']) > 2000: scope['flags'].add('very_wide_schema')
            scope['flags'].update(k for k in ('header_uncertain', 'width_mismatch') if context.get(k))
            record = {'record_id': stable_id(fid, sheet, ordinal), 'sheet': sheet,
                      'row': ordinal, 'cells': cells, 'context': context}
            if len(scope['head']) < 3: scope['head'].append(record)
            scope['tail'].append(record)
            if len(scope['random']) < 5: scope['random'].append(record)
            else:
                candidate = scope['rng'].randrange(scope['n'])
                if candidate < 5: scope['random'][candidate] = record
        # Exact middle records require a second pass; no large table is buffered.
        wanted = {sheet: set(range(max(0, s['n']//2-1), min(s['n'], s['n']//2+2))) for sheet,s in scopes.items()}
        positions, middles = Counter(), {sheet: [] for sheet in scopes}
        if scopes:
            for sheet, ordinal, cells, context in read_records(path, kind):
                index = positions[sheet]; positions[sheet] += 1
                if index in wanted[sheet]:
                    middles[sheet].append({'record_id': stable_id(fid,sheet,ordinal), 'sheet':sheet,
                                           'row':ordinal,'cells':cells,'context':context})
                    wanted[sheet].remove(index)
                if all(not value for value in wanted.values()): break
        for sheet, scope in scopes.items():
            samples = {r['record_id']: r for r in scope['head'] + middles[sheet] + list(scope['tail']) + scope['random']}
            profile['cards'].append({'scope_id': stable_id(fid,sheet), 'file_id': fid,
                'filename': profile['filename'], 'sheet':sheet, 'row_count':scope['n'],
                'columns':sorted(scope['columns']), 'quality_flags':sorted(scope['flags']),
                'sampling':{'seed':42,'method':PROFILE_VERSION}, 'source':source,
                'sample':sorted(samples.values(),key=lambda r:r['row'])})
        profile.update(records=sum(s['n'] for s in scopes.values()), status='PROFILED' if scopes else 'EMPTY')
    except Exception as error:
        profile.update(status='REVIEW', error=type(error).__name__ + ': ' + str(error)[:200], cards=[])
    dump(cache, profile)
    return profile


def scan(input_dir, work_dir, workers=1, retry_review=False):
    input_dir, work_dir = Path(input_dir).resolve(), Path(work_dir).resolve()
    if work_dir == input_dir or work_dir.is_relative_to(input_dir):
        raise ValueError('Processing output must be outside the raw input directory')
    work_dir.mkdir(parents=True,exist_ok=True)
    cache = work_dir/'profile-cache'; cache.mkdir(exist_ok=True)
    if not 1 <= workers <= 16: raise ValueError('scan workers must be in 1..16')
    paths = list(discover(input_dir))
    args = [(str(path),path.relative_to(input_dir).as_posix(),str(cache),retry_review) for path in paths]
    profiles, started = [], time.monotonic()
    def accept(value):
        profiles.append(value)
        if len(profiles) % 25 == 0 or len(profiles) == len(paths):
            print(json.dumps({'stage':'scan','files':len(profiles),'total':len(paths),
                              'seconds':round(time.monotonic()-started,1)}),flush=True)
    if workers == 1:
        for item in args: accept(profile_file(*item))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            pending = [pool.submit(profile_file,*item) for item in args]
            for future in as_completed(pending): accept(future.result())
    profiles.sort(key=lambda row:row['relative_path'])
    dump(work_dir/'file_profiles.json', profiles)
    with (work_dir/'scan_cards.jsonl').open('w',encoding='utf-8') as stream:
        for profile in profiles:
            for card in profile['cards']: stream.write(json.dumps(card,ensure_ascii=False)+'\n')
    report = {'files':len(profiles),'status_counts':dict(Counter(p['status'] for p in profiles)),
              'profiled_records':sum(p['records'] for p in profiles),
              'scopes':sum(len(p['cards']) for p in profiles),'seconds':round(time.monotonic()-started,2),
              'reader_versions':sorted({p.get('reader_version',READER_VERSION) for p in profiles}),
              'raw_record_store_created':False,'llm_called':False}
    dump(work_dir/'scan_summary.json', report)
    return profiles, report
