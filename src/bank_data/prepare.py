import json
import random
from collections import Counter
from pathlib import Path

from .common import dump, file_hash, stable_id
from .readers import READER_VERSION, detect, discover, read_records


def source_metadata(path):
    p = path.parent / 'provenance.json'
    if not p.exists(): return {}
    data = json.loads(p.read_text(encoding='utf-8'))
    return {k: data[k] for k in ('dataset_url', 'file_name', 'expected_name', 'sha256', 'attachment_id',
                               'attachment_href', 'task_id', 'snapshot_id', 'archive_member', 'parent_sha256',
                               'page_version_hint', 'format_mismatch') if k in data}


def build_cards(store, file_id):
    scopes = store.db.execute('SELECT scope,sheet,COUNT(*) n FROM records WHERE file_id=? GROUP BY scope,sheet', (file_id,)).fetchall()
    file = store.db.execute('SELECT * FROM files WHERE id=?', (file_id,)).fetchone()
    for scope in scopes:
        n = scope['n']
        positions = set(range(min(3, n))) | set(range(max(0, n // 2 - 1), min(n, n // 2 + 2))) | set(range(max(0, n - 3), n))
        positions.update(random.Random(42).sample(range(n), min(n, 5)))
        samples, columns, flags, counts = [], set(), set(), Counter()
        for i, row in enumerate(store.scope_records(scope['scope'])):
            if len(columns) < 2000: columns.update(row['cells'])
            for key, value in row['context'].items():
                if key in ('header_uncertain', 'width_mismatch') and value: flags.add(key)
            if i in positions: samples.append(row)
        if len(columns) > 2000: flags.add('very_wide_schema')
        card = {'scope_id': scope['scope'], 'file_id': file_id, 'filename': file['name'],
                'sheet': scope['sheet'], 'row_count': n, 'columns': sorted(columns),
                'sampling': {'seed': 42, 'method': 'head/middle/tail + deterministic random; not a semantic recall guarantee'},
                'quality_flags': sorted(flags), 'source': json.loads(file['source']), 'sample': samples}
        store.db.execute('INSERT OR REPLACE INTO scopes VALUES(?,?,?)', (scope['scope'], file_id, json.dumps(card, ensure_ascii=False)))


def prepare(store, input_dir, selected_paths=None):
    input_dir = Path(input_dir).resolve()
    if store.root == input_dir or store.root.is_relative_to(input_dir):
        raise ValueError('Work directory must be outside the input data directory')
    files = list(discover(input_dir))
    if selected_paths is not None:
        selected_paths = {str(Path(p).resolve()) for p in selected_paths}
        files = [p for p in files if str(p.resolve()) in selected_paths]
    inventory = []
    store.db.execute('DELETE FROM active_files')
    store.db.commit()
    for path in files:
        sha = file_hash(path)
        fid = stable_id(READER_VERSION, path.relative_to(input_dir).as_posix(), sha)
        store.db.execute('INSERT OR IGNORE INTO active_files VALUES(?)', (fid,))
        previous = store.db.execute('SELECT status FROM files WHERE id=?', (fid,)).fetchone()
        if previous and previous['status'] == 'prepared':
            store.db.commit()
            inventory.append({'file_id': fid, 'path': str(path), 'sha256': sha, 'status': 'cached_prepared'})
            continue
        metadata = {}
        name = path.name
        kind = 'unknown'
        try:
            metadata = source_metadata(path)
            name = metadata.get('file_name', metadata.get('expected_name', path.name))
            kind = detect(path)
            if metadata.get('sha256') and metadata['sha256'] != sha:
                raise ValueError('Source checksum differs from provenance manifest')
            store.db.commit()
            store.db.execute('BEGIN')
            store.db.execute('DELETE FROM records WHERE file_id=?', (fid,))
            store.db.execute('DELETE FROM scopes WHERE file_id=?', (fid,))
            for sheet, ordinal, cells, context in read_records(path, kind):
                rid = stable_id(fid, sheet, ordinal)
                scope = stable_id(fid, sheet)
                store.db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?)',
                    (rid, scope, fid, sheet, ordinal, json.dumps(cells, ensure_ascii=False), json.dumps(context, ensure_ascii=False)))
            store.db.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?,?)',
                (fid, str(path), sha, name, kind, 'prepared', None, json.dumps(metadata, ensure_ascii=False)))
            build_cards(store, fid)
            store.db.commit()
            status = 'prepared'
        except Exception as error:
            store.db.rollback()
            # Entire file is quarantined; a parse failure never becomes silent row loss.
            store.db.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?,?)',
                (fid, str(path), sha, name, kind, 'review', type(error).__name__ + ': ' + str(error)[:180], json.dumps(metadata, ensure_ascii=False)))
            store.db.commit()
            status = 'review'
        inventory.append({'file_id': fid, 'path': str(path), 'sha256': sha, 'kind': kind, 'status': status})
    dump(store.root / 'inventory.json', inventory)
    with (store.root / 'file_cards.jsonl').open('w', encoding='utf-8') as out:
        for row in store.active_scopes(): out.write(row['card'] + '\n')
    with (store.root / 'prepared_chunks.jsonl').open('w', encoding='utf-8') as out:
        for scope in store.active_scopes():
            batch, size = [], 0
            for row in store.scope_records(scope['id']):
                length = len(json.dumps(row, ensure_ascii=False).encode())
                if batch and (size + length > 6000 or len(batch) >= 12):
                    out.write(json.dumps({'scope_id': scope['id'], 'records': batch}, ensure_ascii=False) + '\n'); batch, size = [], 0
                batch.append(row); size += length
            if batch: out.write(json.dumps({'scope_id': scope['id'], 'records': batch}, ensure_ascii=False) + '\n')
    counts = store.db.execute('SELECT f.status,COUNT(*) n FROM files f JOIN active_files a ON f.id=a.id GROUP BY f.status').fetchall()
    report = {'files': len(inventory), 'status_counts': {r['status']: r['n'] for r in counts},
              'records': store.db.execute('SELECT COUNT(*) FROM records r JOIN active_files a ON r.file_id=a.id').fetchone()[0],
              'llm_called': False, 'note': 'Byte-bounded preparation chunks are rechecked with the actual chat tokenizer before LLM inference.'}
    dump(store.root / 'prepare_summary.json', report)
    return report
