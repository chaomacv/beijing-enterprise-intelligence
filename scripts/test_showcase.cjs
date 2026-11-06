const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {sampleRows, chunkRows, classifyIdentity} = require('../showcase/model.js');
const root = path.resolve(__dirname, '..');

test('stratified samples retain head, middle, tail and fixed random coverage', () => {
  const basic = sampleRows(120, 3, false);
  assert.equal(basic.size, 9);
  for (const i of [0, 1, 2, 58, 59, 60, 117, 118, 119]) assert.equal(basic.get(i), 'stratified');
  const enriched = sampleRows(120, 3, true);
  assert.equal(enriched.size, 15);
  assert.deepEqual(enriched, sampleRows(120, 3, true));
  for (const count of [1, 4, 10]) {
    const sample = sampleRows(120, count, true);
    assert.equal(sample.size, 3 * count + 6);
    assert.ok([...sample.keys()].every(i => i >= 0 && i < 120));
  }
});

test('small samples deduplicate overlapping head, middle and tail', () => {
  assert.equal(sampleRows(1, 8, true).size, 1);
  assert.equal(sampleRows(5, 3, true).size, 5);
  assert.throws(() => sampleRows(0, 3), RangeError);
});

test('changing chunk boundaries never loses or repeats a record', () => {
  const rows = Array.from({length: 12}, (_, id) => ({id}));
  for (let size = 2; size <= 6; size++) {
    const chunks = chunkRows(rows, size);
    assert.deepEqual(chunks.flat(), rows);
    assert.ok(chunks.every(chunk => chunk.length <= size));
  }
  assert.throws(() => chunkRows(rows, 0), RangeError);
});

test('identity conflicts veto name and address agreement', () => {
  const a = {name: '合成甲科技', address: '示例路1号', code: '示意A'};
  assert.equal(classifyIdentity(a, {...a, code: '示意B'}), 'conflict');
  assert.equal(classifyIdentity(a, {...a}), 'same');
  assert.equal(classifyIdentity({...a, code: ''}, {...a, code: ''}), 'same');
  assert.equal(classifyIdentity({name: a.name}, {name: a.name}), 'uncertain');
});

test('public demo is actual synthetic rule output with exact evidence and explicit proposed status', () => {
  const demo = JSON.parse(fs.readFileSync(path.join(root, 'showcase/assets/demo.json'), 'utf8'));
  assert.equal(demo.provenance.kind, 'synthetic');
  assert.equal(demo.summary.rule_baseline, true);
  assert.equal(demo.summary.semantic_accuracy_evaluated, false);
  assert.equal(demo.files.length, 3);
  assert.equal(demo.records.length, 5);
  assert.equal(demo.profiles.length, 2);
  assert.equal(demo.events.length, 3);
  const input = new Map(demo.records.map(row => [row.record_id, row]));
  assert.deepEqual(new Set(demo.record_results.map(row => row.record_id)), new Set(input.keys()));
  for (const event of demo.events) {
    for (const source of event.sources) {
      const row = input.get(source.record_id);
      assert.ok(row);
      assert.equal(row.row, source.row);
      for (const evidence of event.evidence) assert.equal(row.cells[evidence.field], evidence.value);
    }
  }
  const proposed = demo.events.find(event => event.status === 'proposed');
  assert.ok(proposed);
  assert.ok(demo.profiles.some(p => p.tags.some(tag => tag.evidence_event_id === proposed.event_id && tag.event_status === 'proposed' && tag.label.startsWith('拟议'))));
  assert.ok(demo.profiles.every(p => p.credit_score === null && p.identity_status === 'provisional'));
});

test('all HTML anchors and local assets resolve, and public UI has no remote scripts', () => {
  const html = fs.readFileSync(path.join(root, 'showcase/index.html'), 'utf8');
  const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]);
  assert.equal(ids.length, new Set(ids).size, 'Duplicate HTML id');
  for (const [, target] of html.matchAll(/\b(?:href|src)="([^"]+)"/g)) {
    if (target.startsWith('#')) assert.ok(ids.includes(target.slice(1)), target);
    else if (!/^https?:/.test(target)) assert.ok(fs.existsSync(path.join(root, 'showcase', target)), target);
  }
  for (const [, target] of html.matchAll(/aria-(?:controls|labelledby)="([^"]+)"/g)) {
    for (const id of target.split(/\s+/)) assert.ok(ids.includes(id), id);
  }
  assert.ok(!/<script[^>]+src="https?:/.test(html));
  for (const id of ['panel-sample', 'panel-chunk', 'panel-match']) assert.ok(ids.includes(id));
});
