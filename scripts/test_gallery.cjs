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
test('refinement conserves legacy observations without summing nonadditive profile counts',()=>{
  const selected=eventView(data);
  assert.equal(sum(selected,'count'),5032506);
  assert.equal(selected.length,10);
  assert.equal(data.taxonomy.legacy_qualification_events,5032506);
  assert.equal(data.taxonomy.downgraded_confirmed,540486);
  assert.ok(!data.events.some(r=>r.type==='qualification'));
  assert.equal(data.taxonomy.unique_licences,null);
  assert.equal(data.taxonomy.unique_registered_enterprises,null);
  const profiles=eventView(data,'all','refined','profiles');
  for(const row of profiles)assert.equal(row.count,data.taxonomy.category_profiles.find(p=>p.type===row.type).count);
  const original=data.events.map(r=>({...r}));
  const multi={...data,events:[
    {type:'business_permit',label:'企业经营许可',status:'confirmed',count:7,associated_profiles:3},
    {type:'business_permit',label:'企业经营许可',status:'unknown',count:9,associated_profiles:4}],
    taxonomy:{...data.taxonomy,category_profiles:[{type:'business_permit',count:5}]}};
  assert.equal(eventView(multi,'all','refined','profiles')[0].count,5);
  assert.equal(eventView(multi,'unknown','refined','profiles')[0].count,4);
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
test('gallery mount targets exist and all eight slides have accessible navigation controls', () => {
  const path=require('node:path');
  const html=fs.readFileSync(path.join(__dirname,'../showcase/index.html'),'utf8');
  const js=fs.readFileSync(path.join(__dirname,'../showcase/gallery.js'),'utf8');
  const ids=new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]));
  for(const match of js.matchAll(/\$\('([a-z0-9-]+)'\)/g)) assert.ok(ids.has(match[1]),match[1]);
  assert.equal([...html.matchAll(/data-notebook="\d+"/g)].length,8);
  assert.equal([...html.matchAll(/data-gallery-page="\d+"/g)].length,8);
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
