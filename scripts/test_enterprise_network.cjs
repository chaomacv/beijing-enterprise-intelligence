const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {palette,companies,normalizers,similarity,connections,tagPositions,tagEdges,project}=require('../showcase/network-model.js');
const data=JSON.parse(fs.readFileSync(path.join(__dirname,'../showcase/assets/company-network.json'),'utf8'));
const company=(id,event_counts)=>{const tags=Object.keys(event_counts).filter(t=>t!=='qualification_review');return {id,event_counts,tags,tag_count:tags.length,event_count:tags.reduce((s,t)=>s+event_counts[t],0)};};
test('sample contains exactly 100 real company aliases with reconciled event and stage counts',()=>{
 assert.equal(data.kind,'real_enterprise_sample');assert.equal(data.sample_size,100);assert.equal(data.one_node_per_company,true);
 assert.equal(data.companies.length,100);assert.equal(new Set(data.companies.map(n=>n.id)).size,100);
 assert.deepEqual(data.categories.slice(0,10).map(c=>c.color),palette);
 assert.ok(!/"(?:entity_id|valid_code|credit_code|address|names|file_id|record_id)"|\/opt\//.test(JSON.stringify(data)));
 for(const c of data.companies){
  assert.match(c.id,/^enterprise-\d{3}$/);assert.match(c.label,/^企业\d{3}$/);
  const keys=Object.keys(c.event_counts).filter(t=>t!=='qualification_review');
  assert.equal(c.tag_count,keys.length);assert.equal(c.event_count,keys.reduce((s,t)=>s+c.event_counts[t],0));
  for(const [tag,count] of Object.entries(c.event_counts)){assert.ok(Number.isSafeInteger(count)&&count>0);assert.equal(Object.values(c.stage_counts[tag]).reduce((a,b)=>a+b,0),count);}
 }
 assert.equal(companies(data).length,100);assert.equal(companies(data,'refined').length,100);
});
test('more shared event kinds or more corresponding events shorten target distance',()=>{
 const scale={tag_count:7,event_count:100};
 const a=company('a',{permit:10,equipment:10}),few=company('b',{permit:2}),moreKinds=company('c',{permit:2,equipment:2}),moreEvents=company('d',{permit:8});
 assert.ok(similarity(a,moreKinds,scale).distance<similarity(a,few,scale).distance);
 assert.ok(similarity(a,moreEvents,scale).distance<similarity(a,few,scale).distance);
 const overlap=similarity(a,moreKinds,scale);assert.equal(overlap.shared_types,2);assert.equal(overlap.shared_events,4);
 assert.equal(similarity(a,company('x',{innovation:100}),scale).similarity,0);
 assert.equal(similarity(company('r',{qualification_review:10}),company('s',{qualification_review:20}),scale).similarity,0);
});
test('similarity edges only connect distinct real sample companies and retain sparse nearest neighbors',()=>{
 const nodes=companies(data),scale=normalizers(nodes),byId=new Map(nodes.map(n=>[n.id,n]));
 const {edges,forces}=connections(nodes,.1,3,scale);assert.ok(edges.length>0&&edges.length<=300);assert.ok(forces.length>=edges.length);
 for(const e of edges){assert.ok(e.source!==e.target&&byId.has(e.source)&&byId.has(e.target));assert.deepEqual(similarity(byId.get(e.source),byId.get(e.target),scale),{shared_types:e.shared_types,shared_events:e.shared_events,similarity:e.similarity,distance:e.distance});}
});
test('tag network places category anchors around the perimeter and links actual company observations',()=>{
 const nodes=companies(data),anchors=tagPositions(data.categories,2),edges=tagEdges(nodes),byId=new Map(nodes.map(n=>[n.id,n]));
 assert.equal(anchors.length,18);for(const t of anchors){assert.ok(t.isTag);assert.equal(t.fx,t.x);assert.equal(t.fy,t.y);assert.ok(Math.abs((t.x/235)**2+(t.y/155)**2-1)<1e-10);}
 assert.equal(edges.length,nodes.reduce((s,n)=>s+Object.keys(n.event_counts).length,0));
 for(const e of edges){assert.ok(byId.has(e.source));assert.ok(e.target.startsWith('tag-'));assert.equal(e.event_count,byId.get(e.source).event_counts[e.target.slice(4)]);}
});
test('3D projection responds to depth and rotation while 2D ignores depth',()=>{
 const camera={k:1,x:0,y:0,yaw:0,pitch:0},n={x:70,y:30,z:100};
 assert.notDeepEqual(project(n,camera,3),project(n,{...camera,yaw:.5},3));assert.deepEqual(project(n,camera,2),project({...n,z:-100},camera,2));
});
test('UI declares the 100-company sample and no longer treats grouped profiles as companies',()=>{
 const html=fs.readFileSync(path.join(__dirname,'../showcase/index.html'),'utf8'),module=fs.readFileSync(path.join(__dirname,'../showcase/enterprise-network.js'),'utf8');
 assert.ok(html.includes('一点一家'));assert.ok(html.includes('assets/company-network.json'));assert.ok(!html.includes('id="network-detail-level"'));
 assert.ok(module.includes("assets/company-network.json"));assert.ok(!module.includes('model.overview')&&!module.includes('model.groups'));
});
