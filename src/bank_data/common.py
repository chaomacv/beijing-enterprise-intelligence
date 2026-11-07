import hashlib
import json
from functools import lru_cache
from importlib.resources import files
from pathlib import Path


def resource(name):
    return files('bank_data').joinpath('resources', name).read_text(encoding='utf-8')


@lru_cache(maxsize=1)
def ontology():
    return json.loads(resource('ontology.json'))


def stable_id(*values):
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def text(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def decode_model_json(content):
    """Keep literal string control characters, then serialize them with JSON escapes.

    Multiline column enums can cause a constrained decoder to emit raw newlines.
    strict=False permits string controls only; schema validation remains mandatory.
    """
    try:return json.loads(content),False
    except json.JSONDecodeError:return json.loads(content,strict=False),True
