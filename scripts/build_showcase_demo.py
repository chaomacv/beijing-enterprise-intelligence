"""Build the public, synthetic-only example from the real offline pipeline."""
import json
import tempfile
from pathlib import Path

from bank_data.cli import demo_input
from bank_data.extract import RuleBaseline
from bank_data.pipeline import run
from bank_data.prepare import prepare
from bank_data.store import Store


def build():
    with tempfile.TemporaryDirectory(prefix='bei-showcase-') as temporary:
        root = Path(temporary)
        demo_input(root / 'input')
        store = Store(root / 'output')
        try:
            prepare(store, root / 'input')
            summary = run(store, RuleBaseline())
        finally:
            store.close()
        def read(name):
            return json.loads((root / 'output' / name).read_text(encoding='utf-8'))
        cards = [json.loads(line) for line in (root / 'output/file_cards.jsonl').read_text(encoding='utf-8').splitlines()]
        decisions = {row['scope_id']: row for row in read('screening.json')}
        records = [{**record, 'file_id': card['file_id'], 'filename': card['filename']}
                   for card in cards for record in card['sample']]
        assert len(records) == summary['records'] == 5
        assert summary['entities'] == 2 and summary['events'] == 3
        return {
            'provenance': {'kind': 'synthetic', 'backend': summary['backend'],
                           'generator': 'scripts/build_showcase_demo.py',
                           'description': '合成企业与虚构事实；现有 Python 规则基线的实际输出，不是 Qwen 推理或全量运行结果。'},
            'summary': summary,
            'files': [{**card, 'decision': decisions[card['scope_id']]['decision']} for card in cards],
            'records': records,
            'record_results': read('record_results.json'),
            'events': read('events.json'),
            'profiles': read('profiles.json'),
            'match_decisions': read('match_decisions.json')
        }


if __name__ == '__main__':
    target = Path(__file__).resolve().parents[1] / 'showcase/assets/demo.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Built synthetic showcase: 3 files, 5 records, 2 provisional entities, 3 events.')
