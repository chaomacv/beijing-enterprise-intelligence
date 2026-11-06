import json
import os
import sqlite3
from pathlib import Path


SCHEMA = '''
CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY,path TEXT,sha TEXT,name TEXT,kind TEXT,status TEXT,error TEXT,source TEXT);
CREATE TABLE IF NOT EXISTS active_files(id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,scope TEXT,file_id TEXT,sheet TEXT,ordinal INTEGER,cells TEXT,context TEXT);
CREATE INDEX IF NOT EXISTS record_scope ON records(scope,ordinal);
CREATE TABLE IF NOT EXISTS scopes(id TEXT PRIMARY KEY,file_id TEXT,card TEXT);
CREATE TABLE IF NOT EXISTS decisions(scope TEXT,backend TEXT,result TEXT,PRIMARY KEY(scope,backend));
CREATE TABLE IF NOT EXISTS extractions(record_id TEXT,backend TEXT,result TEXT,PRIMARY KEY(record_id,backend));
CREATE TABLE IF NOT EXISTS llm_cache(id TEXT PRIMARY KEY,result TEXT);
'''


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        if os.name != 'nt': self.root.chmod(0o700)
        self.db = sqlite3.connect(self.root / 'state.sqlite')
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self):
        self.db.close()

    def active_scopes(self):
        return self.db.execute('SELECT s.* FROM scopes s JOIN active_files a ON s.file_id=a.id ORDER BY s.id')

    def scope_records(self, scope):
        for row in self.db.execute('SELECT * FROM records WHERE scope=? ORDER BY ordinal,id', (scope,)):
            yield {'record_id': row['id'], 'sheet': row['sheet'], 'row': row['ordinal'],
                   'cells': json.loads(row['cells']), 'context': json.loads(row['context'])}
