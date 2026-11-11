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

test('public corpus snapshot contains only aggregate metadata and keeps pending results unclaimed', () => {
  const snapshot = JSON.parse(fs.readFileSync(path.join(root, 'showcase/assets/run-summary.json'), 'utf8'));
  assert.equal(snapshot.kind, 'aggregate_run_snapshot');
  assert.equal(snapshot.semantic_accuracy_evaluated, false);
  assert.match(snapshot.source_commit, /^[a-f0-9]{40}$/);
  assert.deepEqual(Object.keys(snapshot).sort(), ['schema_version','kind','snapshot_date','updated_at','source_commit','pipeline_status','semantic_accuracy_evaluated','input','plans','preparation','semantic_work','model','validation','benchmarks','final_counts'].sort());
  const {input, preparation, semantic_work, plans} = snapshot;
  for (const section of [input,preparation,semantic_work,plans]) {
    for (const value of Object.values(section)) assert.ok(Number.isSafeInteger(value) && value >= 0);
  }
  assert.equal(input.known_logical_records, preparation.retained_records + preparation.excluded_records);
  assert.equal(preparation.retained_records, preparation.field_mapped_records + preparation.pending_semantic_source_records);
  assert.equal(preparation.pending_semantic_source_records, semantic_work.representative_records + semantic_work.exact_duplicate_source_records);
  assert.equal(plans.total, plans.map + plans.entity_only + plans.row_llm + plans.exclude + plans.review);
  assert.ok(input.distinct_file_contents <= input.attachments);
  assert.ok(['running','completed','completed_with_review'].includes(snapshot.pipeline_status));
  if (snapshot.pipeline_status === 'running') {
    assert.equal(snapshot.final_counts, null);
    assert.equal(snapshot.validation.final_audit_passed, false);
  } else {
    assert.equal(snapshot.validation.final_audit_passed, true);
    assert.equal(snapshot.final_counts.record_ledger, preparation.retained_records);
    for (const value of Object.values(snapshot.final_counts)) assert.ok(Number.isSafeInteger(value) && value >= 0);
  }
  assert.ok(!/\/opt\/|password|api_key|raw_response_path|request_path|"cells"|"record_id"|10\.126\./i.test(JSON.stringify(snapshot)));
  const benchmark = snapshot.benchmarks.batching;
  assert.equal(benchmark.same_request_keys, true);assert.equal(benchmark.same_canonical_results, true);
  assert.equal(benchmark.review_records, benchmark.records);
  assert.ok(benchmark.packed_seconds < benchmark.serial_seconds);
});

test('locale catalog preserves quantities, technical identifiers and full-scope event semantics',()=>{
 const {translate}=require('../showcase/i18n.js');
 assert.equal(translate('企业经营许可'),'Business permits');
 assert.equal(translate('5,968,620'),'5,968,620');
 assert.equal(translate('EXTRACTED / NO_EVENT / REVIEW'),'EXTRACTED / NO_EVENT / REVIEW');
 assert.match(translate('企业经营许可占当前选择的 18.3% · 共 5,968,620 条事件观察。记录数不能解释为独立证照数。'),/18\.3%.*5,968,620/);
 assert.match(translate('5,202,714 个主体画像，包含 4,364,721 个临时身份。'),/5,202,714.*4,364,721.*provisional/);
});

test('README languages share exact executable commands and reciprocal language navigation',()=>{
 const zh=fs.readFileSync(path.join(root,'README.md'),'utf8'),en=fs.readFileSync(path.join(root,'README.en.md'),'utf8');
 assert.ok(zh.includes('href="README.en.md"'));assert.ok(en.includes('href="README.md"'));
 const commands=s=>[...s.matchAll(/```bash\n([\s\S]*?)```/g)].map(m=>m[1]);
 assert.deepEqual(commands(en),commands(zh));
 for(const count of ['43,653,625','15,861,277','5,968,620','5,202,714','388,349'])assert.ok(zh.includes(count)&&en.includes(count));
});
