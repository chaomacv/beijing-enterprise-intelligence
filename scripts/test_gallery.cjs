const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {eventGroups, eventView, autoplayStep, loopOrder} = require('../showcase/gallery.js');
const data = JSON.parse(fs.readFileSync(require('node:path').join(__dirname, '../showcase/assets/gallery-data.json'), 'utf8'));
const sum = (rows, key) => rows.reduce((n, r) => n + r[key], 0);

test('gallery aggregates reconcile separately within the completed full corpus', () => {
  assert.equal(data.kind, 'aggregate_notebook_gallery');
  assert.equal(data.final_pipeline_complete, true);
  assert.equal(data.subset.partial_only, false);
  assert.equal(data.subset.semantic_accuracy_evaluated, false);
  assert.equal(sum(data.formats, 'files'), data.corpus.logical_files);
  assert.equal(sum(data.file_space.bins, 'files'), data.corpus.logical_files);
  assert.equal(sum(data.events, 'count'), data.subset.events);
  assert.equal(sum(data.record_statuses, 'count'), data.subset.records);
  assert.equal(sum(data.identities, 'count'), data.subset.profiles);
  assert.equal(data.dedup.source_records, data.dedup.representative_records + data.dedup.exact_duplicate_source_records);
  assert.ok(data.subset.events < data.subset.records);
});
test('public gallery exports counts and observed times without private identifiers or records', () => {
  assert.deepEqual(Object.keys(data).sort(), ['schema_version','kind','generated_at','source_commit','final_pipeline_complete','corpus','subset','formats','file_space','events','taxonomy','record_statuses','identities','matching','dedup','progress'].sort());
  assert.ok(!/\/opt\/|password|api_key|"cells"|"record_id"|"file_id"|"path"|10\.126\./i.test(JSON.stringify(data)));
  for (const bin of data.file_space.bins) {
    assert.deepEqual(Object.keys(bin).sort(), ['format','status','bucket','files'].sort());
    assert.ok(Number.isSafeInteger(bin.files) && bin.files > 0);
    assert.ok(bin.bucket >= 0 && bin.bucket < data.file_space.buckets.length);
  }
});
test('all eighteen event categories reconcile without summing nonadditive profile counts',()=>{
  const selected=eventView(data);
  assert.equal(sum(selected,'count'),5968620);
  assert.equal(selected.length,18);
  assert.equal(data.taxonomy.total_events,5968620);
  assert.equal(data.taxonomy.category_count,18);
  assert.ok(!('legacy_qualification_events' in data.taxonomy));
  assert.ok(!('refined_types' in data.taxonomy));
  const classified=require('../showcase/assets/event-classification.json');
  assert.equal(classified.total_events,sum(selected,'count'));
  assert.equal(classified.category_count,selected.length);
  assert.equal(sum(classified.category_status,'observed_events'),classified.total_events);
  assert.ok(!('legacy_qualification_events' in classified));
  assert.ok(!data.events.some(r=>r.type==='qualification'));
  assert.equal(data.taxonomy.unique_licences,null);
  assert.equal(data.taxonomy.unique_registered_enterprises,null);
  const profiles=eventView(data,'all','profiles');
  for(const row of profiles)assert.equal(row.count,data.taxonomy.category_profiles.find(p=>p.type===row.type).count);
  const original=data.events.map(r=>({...r}));
  const multi={...data,events:[
    {type:'business_permit',label:'企业经营许可',status:'confirmed',count:7,associated_profiles:3},
    {type:'business_permit',label:'企业经营许可',status:'unknown',count:9,associated_profiles:4}],
    taxonomy:{...data.taxonomy,category_profiles:[{type:'business_permit',count:5}]}};
  assert.equal(eventView(multi,'all','profiles')[0].count,5);
  assert.equal(eventView(multi,'unknown','profiles')[0].count,4);
  assert.deepEqual(data.events,original);
});
test('event-stage filters preserve categories and never mix record counts into event totals', () => {
  const all = eventGroups(data.events);
  assert.equal(sum(all,'count'), data.subset.events);
  let total = 0;
  for (const state of new Set(data.events.map(r=>r.status))) {
    const selected = eventGroups(data.events,state);
    assert.equal(selected.length, all.length);
    assert.ok(selected.every(r=>r.count >= 0));
    total += sum(selected,'count');
  }
  assert.equal(total,data.subset.events);
  assert.equal(sum(eventGroups(data.events,'removed'),'count'),0);
});
test('reading pauses the carousel clock and resuming preserves elapsed time', () => {
  assert.deepEqual(autoplayStep(7900,200,8000,true),{advance:false,elapsed:7900});
  assert.deepEqual(autoplayStep(7900,200,8000,false),{advance:true,elapsed:100});
  assert.deepEqual(autoplayStep(2000,500,8000,false),{advance:false,elapsed:2500});
  assert.throws(()=>autoplayStep(0,1,0,false),RangeError);
});
test('execution timeline uses ordered actual observations, not fabricated uniform intervals', () => {
  const points=data.progress.points;
  assert.equal(data.progress.series_kind,'observed_processing_snapshots_not_business_events');
  const intervals=[];
  for(let i=1;i<points.length;i++) {
    intervals.push(Date.parse(points[i].at)-Date.parse(points[i-1].at));
    assert.ok(intervals.at(-1)>0);
    assert.ok(points[i].completed>=points[i-1].completed && points[i].completed<=data.progress.total);
  }
  assert.ok(new Set(intervals).size>1);
});
test('gallery mount targets exist and all nine slides have accessible navigation controls', () => {
  const path=require('node:path');
  const html=fs.readFileSync(path.join(__dirname,'../showcase/index.html'),'utf8');
  const js=fs.readFileSync(path.join(__dirname,'../showcase/gallery.js'),'utf8');
  const ids=new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]));
  for(const match of js.matchAll(/\$\('([a-z0-9-]+)'\)/g)) assert.ok(ids.has(match[1]),match[1]);
  assert.equal([...html.matchAll(/data-notebook="\d+"/g)].length,9);
  assert.equal([...html.matchAll(/data-gallery-page="\d+"/g)].length,9);
  assert.ok(html.includes('src="gallery.js"'));
  assert.ok(html.includes('aria-roledescription="轮播"'));
});
test('circular recentering keeps both neighbors at every wrap without cloning cards',()=>{
  for(const direction of [-1,1]){
    let order=[0,1,2,3,4,5,6],center=1;
    for(let i=0;i<35;i++){
      order=loopOrder(order,center).order;
      assert.equal(order[3],center);
      assert.equal(order[2],(center+6)%7);
      assert.equal(order[4],(center+1)%7);
      assert.deepEqual([...order].sort(),[0,1,2,3,4,5,6]);
      center=(center+direction+7)%7;
    }
  }
  assert.throws(()=>loopOrder([0,0,1],0),RangeError);
});


test('catalog totals, small categories and sampled links retain the true fixed input',()=>{
 const overview=require('../showcase/assets/source-overview.json');
 const {validate}=require('../showcase/source-overview.js');
 assert.equal(validate(overview),overview);
 assert.equal(overview.dataset_count,4710);
 assert.equal(overview.themes.reduce((n,t)=>n+t.count,0),4710);
 assert.equal(overview.themes.reduce((n,t)=>n+t.samples.length,0),192);
 assert.equal(overview.themes.find(t=>t.name==='生活安全').count,58);
 assert.equal(overview.themes.find(t=>t.name==='农业农村').count,103);
 assert.equal(overview.themes.find(t=>t.name==='消费购物').samples.length,5);
 assert.equal(overview.batch.known_logical_records,data.corpus.known_logical_records);
 assert.ok(overview.examples.every(e=>e.illustrative===true));
 const broken=structuredClone(overview);broken.themes[0].samples[0].url+='?token=example';assert.throws(()=>validate(broken));
});

test('the first six notebooks follow the requested narrative and remaining ones retain order',()=>{
 const html=fs.readFileSync(require('node:path').join(__dirname,'../showcase/index.html'),'utf8');
 const keys=[...html.matchAll(/data-card-key="([^"]+)"/g)].map(m=>m[1]);
 assert.deepEqual(keys,['sources','acquisition','events','hierarchy','methods','dedup','network','portrait','timeline']);
 const labels=[...html.matchAll(/class="cell-number">\[(\d+)\]/g)].map(m=>m[1]);
 assert.deepEqual(labels,Array.from({length:9},(_,i)=>String(i+1).padStart(2,'0')));
 assert.ok(!html.includes('id="gallery-sunburst"')); 
});


test('lineage conserves every routing branch and matches its exact source exports',()=>{
 const path=require('node:path'),crypto=require('node:crypto');
 const lineage=require('../showcase/assets/data-lineage.json'),model=require('../showcase/lineage.js');
 assert.equal(model.validate(lineage),lineage);
 assert.equal(lineage.hash_basis,'utf8_lf_newlines');
 for(const [name,digest] of Object.entries(lineage.source_sha256))assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(__dirname,'../showcase/assets',name),'utf8').replace(/\r\n/g,'\n')).digest('hex'),digest);
 const final=require('../showcase/assets/final-results.json');
 assert.equal(lineage.counts.known,final.input.known_logical_records);
 assert.equal(lineage.counts.retained,final.counts.record_ledger);
 assert.equal(lineage.counts.mapped,final.preparation.field_mapped_records);
 assert.equal(lineage.stages.length,9);
 assert.deepEqual(lineage.flow_points.map(p=>p.count),[43653625,15861277,1440619,388349,1440619,15861277,43653625]);
 assert.equal(lineage.outcomes.REVIEW,6179034);
 assert.ok(!/password|10\.126\.|\/opt\/|"cells"|"record_id"/.test(JSON.stringify(lineage)));
});

test('stage order and actual inference time remain distinct while both chart scales preserve quantities',()=>{
 const d=require('../showcase/assets/data-lineage.json'),m=require('../showcase/lineage.js');
 assert.ok(m.series(d,'flow').every(p=>p.at===undefined));
 assert.deepEqual(m.series(d,'time').map(p=>p.count),d.progress.points.map(p=>p.completed));
 for(const log of [true,false]){
  const p=m.positions(d,'flow',log).points;assert.equal(p[3].count,388349);assert.equal(p[4].count,1440619);
  assert.ok(p[3].y>p[4].y);assert.ok(p[0].y<p[1].y);assert.ok(p.every(n=>Number.isFinite(n.x)&&Number.isFinite(n.y)));
 }
 const p=m.positions(d,'time',false).points;
 assert.ok(p[1].x-p[0].x < p[6].x-p[5].x);
 assert.equal(p.at(-1).count,388349);
 const ticks=m.timeTickIndices(p);
 assert.equal(ticks[0],0);assert.equal(ticks.at(-1),p.length-1);
 const span=p.at(-1).x-p[0].x;
 assert.ok(p[ticks[1]].x-p[0].x>span*.25&&p.at(-1).x-p[ticks[1]].x>span*.25);
});

test('inconsistent lineage counts or fabricated stage timestamps cannot be presented as the batch',()=>{
 const d=require('../showcase/assets/data-lineage.json'),m=require('../showcase/lineage.js');
 for(const change of [c=>c.counts.retained++,c=>c.outcomes.REVIEW++,c=>c.flow_points[0].at='2026-11-07T00:00:00Z',c=>c.progress.points[1].at=c.progress.points[0].at]){
  const copy=structuredClone(d);change(copy);assert.throws(()=>m.validate(copy));
 }
 assert.throws(()=>m.series(d,'unknown'));
});
