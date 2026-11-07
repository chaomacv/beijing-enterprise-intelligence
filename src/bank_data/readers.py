"""Streaming readers. Preserve source positions, role-bearing headers and raw values."""
import codecs
import csv
import io
import itertools
import json
from pathlib import Path

from .common import ontology, text

SUPPORTED = {'.csv', '.xlsx', '.xls', '.json', '.jsonl', '.ndjson', '.xml', '.rdf'}
READER_VERSION = 'reader-v2'


def reader_version(kind):
    if kind in ('pdf','docx','legacy_word','txt','text','html','htm'):return 'reader-v1-native-documents'
    return 'reader-v3-xlsx-dimensions' if kind == 'xlsx' else READER_VERSION


CONTROL_FILES = {'provenance.json', 'datasets.json', 'normalized-catalog.json', 'catalog-change.json'}
SKIP_DIRS = {'catalog', 'runtime', 'cache', 'driver-cache', 'browser-profile', 'chrome-profile',
             'recovery', 'interrupted', 'temp', '.git', '.venv', '__pycache__'}


def discover(root):
    import os
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError('Input must be a dedicated data/download-work directory')
    # Known download layouts exclude browsers, package caches, exports and logs.
    locations = [p for p in (root / 'all-files', root / 'files') if p.is_dir()]
    if not locations:
        locations = [root]
    for location in locations:
        for directory, dirs, names in os.walk(location, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith('.'))
            for name in sorted(names):
                p = Path(directory) / name
                if p.is_symlink() or name in CONTROL_FILES or p.suffix in {'.part', '.crdownload', '.tmp', '.log', '.sqlite', '.db'}:
                    continue
                if not locations == [root] and p.parent == root:
                    continue
                if p.suffix.lower() in SUPPORTED or p.parent != root:
                    yield p
                elif name not in {'RUNNING.lock', 'download-policy.json', 'login-confirmed.json'}:
                    yield p


def detect(path):
    with path.open('rb') as f:
        prefix = f.read(8)
    if prefix.startswith(b'PK\x03\x04'):
        import zipfile
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            if 'xl/workbook.xml' in names: return 'xlsx'
            if 'word/document.xml' in names: return 'docx'
            return 'unsupported_archive'
    if prefix.startswith(b'\xd0\xcf\x11\xe0'):
        if path.suffix.lower() == '.doc': return 'legacy_word'
        return 'xls'
    if prefix.startswith(b'%PDF-'): return 'pdf'
    if prefix.lstrip().lower().startswith((b'<html',b'<!doctyp')):return 'html'
    if prefix.startswith((b'\x1f\x8b',b'7z\xbc\xaf\x27\x1c')):return 'unsupported_archive'
    if not path.suffix:
        with path.open('rb') as stream: probe = stream.read(8192).lstrip(b'\xef\xbb\xbf \r\n\t')
        if probe.startswith((b'<?xml', b'<rdf:', b'<RDF')): return 'xml'
        if probe.startswith((b'{', b'[')): return 'json'
        if probe.lower().startswith((b'<html',b'<!doctype html')):return 'html'
        try:
            value = probe.decode('utf-8-sig')
            csv.Sniffer().sniff(value, delimiters=',\t;|')
            return 'csv'
        except (UnicodeDecodeError, csv.Error): pass
    return path.suffix.lower().lstrip('.')


def encoding_for(path):
    with path.open('rb') as stream: bom = stream.read(2)
    encodings = ('utf-16',) if bom in (b'\xff\xfe', b'\xfe\xff') else ('utf-8-sig', 'gb18030')
    for encoding in encodings:
        decoder = codecs.getincrementaldecoder(encoding)()
        try:
            with path.open('rb') as f:
                for block in iter(lambda: f.read(1024 * 1024), b''):
                    decoder.decode(block, final=False)
            decoder.decode(b'', final=True)
            return encoding
        except UnicodeDecodeError:
            continue
    raise ValueError('Unsupported text encoding; no lossy decoder fallback')


def cells_as_text(values):
    return ['' if v is None else str(v) for v in values]


def table_records(rows, sheet, pad_missing=False):
    top = list(itertools.islice(rows, 20))
    if not top:
        return
    names = set(ontology()['name_fields'])
    known = names | set(ontology()['code_fields']) | {'序号', '项目名称', '日期', '批次'}
    def score(item):
        values = [str(v or '').strip() for v in item[1]]
        return sum(v in known for v in values) + 2 * sum(v in names for v in values)
    candidates = [(i, values) for i, values in enumerate(top)]
    best = max(candidates, key=score)
    header_uncertain = score(best) == 0
    index = best[0] if not header_uncertain else 0
    original_header = cells_as_text(top[index])
    keys, used = [], set()
    for i, label in enumerate(original_header):
        label = label.strip() or f'__column_{i + 1}'
        key = label
        while key in used:
            key += '__duplicate'
        used.add(key); keys.append(key)
    context = {'original_header': original_header, 'header_record': index + 1,
               'preamble': [cells_as_text(r) for r in top[:index]], 'header_uncertain': header_uncertain}
    for number, values in enumerate(itertools.chain(top[index + 1:], rows), index + 2):
        values = cells_as_text(values)
        if pad_missing and len(values) < len(keys): values.extend([''] * (len(keys)-len(values)))
        if not any(v.strip() for v in values):
            continue
        if values == original_header:
            continue  # Repeated structural header, not a business record.
        cells = {keys[i] if i < len(keys) else f'__extra_{i + 1}': value for i, value in enumerate(values)}
        yield sheet, number, cells, {**context, 'width_mismatch': len(values) != len(keys)}


def read_records(path, kind):
    if kind == 'csv':
        encoding = encoding_for(path)
        with path.open(encoding=encoding, newline='') as f:
            sample = f.read(16384); f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=',\t;|')
            except csv.Error:
                dialect = csv.excel
            csv.field_size_limit(16 * 1024 * 1024)
            yield from table_records(csv.reader(f, dialect=dialect, strict=True), 'csv')
    elif kind == 'xlsx':
        import openpyxl
        with path.open('rb') as f:
            book = openpyxl.load_workbook(f, read_only=True, data_only=True)
            try:
                for sheet in book:
                    # Declared dimensions can span a million styled but empty rows/columns,
                    # or incorrectly omit populated cells. Read actual XML coordinates.
                    sheet.reset_dimensions()
                    def trimmed_rows():
                        for values in sheet.iter_rows(values_only=True):
                            values = list(values)
                            while values and values[-1] is None: values.pop()
                            yield values
                    yield from table_records(trimmed_rows(), sheet.title, pad_missing=True)
            finally:
                book.close()
    elif kind == 'xls':
        import xlrd
        book = xlrd.open_workbook(str(path), on_demand=True)
        try:
            for sheet in book.sheets():
                yield from table_records((sheet.row_values(i) for i in range(sheet.nrows)), sheet.name)
        finally:
            book.release_resources()
    elif kind in ('jsonl', 'ndjson'):
        with path.open(encoding=encoding_for(path)) as f:
            for n, line in enumerate(f, 1):
                if not line.strip(): continue
                row = json.loads(line)
                if not isinstance(row, dict): raise ValueError('JSONL record must be an object')
                yield 'jsonl', n, {k: text(v) for k, v in row.items()}, {}
    elif kind == 'json':
        if path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError('JSON >64 MiB requires streaming conversion; file queued for review')
        data = json.loads(path.read_text(encoding=encoding_for(path)))
        if isinstance(data, dict): data = data.get('data', data.get('records', [data]))
        if not isinstance(data, list): raise ValueError('Unsupported JSON structure')
        for n, row in enumerate(data, 1):
            if not isinstance(row, dict): raise ValueError('JSON row must be an object')
            yield 'json', n, {k: text(v) for k, v in row.items()}, {}
    elif kind in ('rdf', 'xml'):
        from defusedxml.ElementTree import iterparse
        ordinal, nonempty = 0, False
        for _, element in iterparse(str(path), events=('end',)):
            tag = element.tag.rsplit('}', 1)[-1]
            if element.text and element.text.strip(): nonempty = True
            if tag not in ('Description', 'record', 'row') and '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about' not in element.attrib:
                continue
            cells = {}
            for child in element:
                key = child.tag.rsplit('}', 1)[-1]
                if key in cells: key += f'__duplicate_{len(cells)}'
                cells[key] = ''.join(child.itertext()) or json.dumps(child.attrib, ensure_ascii=False)
            if cells:
                ordinal += 1
                yield 'xml', ordinal, cells, {'xml_tag': tag}
            element.clear()
        if not ordinal and nonempty:
            raise ValueError('Nonempty XML has an unrecognized record structure; review required')
    elif kind in ('pdf','docx','legacy_word','txt','text','html','htm'):
        from .document_readers import document_records
        yield from document_records(path,'html' if kind=='htm' else kind)
    else:
        raise ValueError('Unsupported format; OCR/archive handling is not enabled')
