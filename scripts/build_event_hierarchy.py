"""Validate the published exploration trees; generation runs on the private server.

See build_exploration_hierarchies.py for the source-backed generation command.
This former subset-only entry point cannot overwrite the completed-run manifest.
"""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'showcase/assets'
manifest = json.loads((root / 'event-hierarchy.json').read_text(encoding='utf-8'))


def check(node):
    count = sum(check(n) for n in node['children']) if node.get('children') else node['value']
    assert count == node['value'] and isinstance(count, int) and count > 0
    return count


assert manifest['kind'] == 'verified_exploration_manifest'
for mode in manifest['modes']:
    raw = (root / mode['file']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == mode['sha256']
    assert check(json.loads(raw)['tree']) == mode['total']
print('Three verified exploration trees reconcile:', [m['total'] for m in manifest['modes']])
