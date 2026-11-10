const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {palette,jaccard,groups,links,project}=require('../showcase/network-model.js');
const data=JSON.parse(fs.readFileSync(path.join(__dirname,'../showcase/assets/real-network.json'),'utf8'));
test('real network is a complete, additive census of corrected tag signatures, not a sample',()=>{
 assert.equal(data.kind,'complete_real_profile_tag_census');assert.equal(data.sampled,false);assert.equal(data.groups.length,1753);
 assert.equal(data.groups.reduce((s,n)=>s+n.profiles,0),5202714);assert.equal(data.groups.reduce((s,n)=>s+n.provisional_profiles,0),4364721);
 assert.equal(data.groups.filter(n=>!n.tags.length).reduce((s,n)=>s+n.profiles,0),1665951);
 assert.deepEqual(data.categories.slice(0,10).map(c=>c.color),palette);
 for(const c of data.categories)assert.equal(data.groups.filter(n=>n.tags.includes(c.id)).reduce((s,n)=>s+n.profiles,0),c.profiles);
 for(const scope of ['all','refined'])assert.equal(groups(data,scope).reduce((s,n)=>s+n.profiles,0),5202714);
 assert.ok(!/"(?:entity_id|record_id|file_id|credit_code|address|name)"|\/opt\/|password/.test(JSON.stringify(data)));
});
test('Jaccard ignores review flags; every nearest-neighbor edge meets its actual threshold',()=>{
 assert.equal(jaccard(['a','a','b'],['a','b']),1);assert.equal(jaccard(['a','b'],['b','c']),1/3);
 assert.equal(jaccard(['qualification_review'],['qualification_review']),0);assert.equal(jaccard([],[]),0);
 const nodes=groups(data,'refined'),map=new Map(nodes.map(n=>[n.id,n]));
 const edges=links(nodes,.6,6);assert.ok(edges.length>0&&edges.length<=nodes.length*6);
 const seen=new Set();for(const e of edges){assert.ok(e.similarity>=.6);assert.equal(e.similarity,jaccard(map.get(e.source).tags,map.get(e.target).tags));assert.ok(!seen.has([e.source,e.target].sort().join(',')));seen.add([e.source,e.target].sort().join(','));}
});
test('3D projection responds to real depth and rotation, while 2D keeps depth absent',()=>{
 const camera={k:1,x:0,y:0,yaw:0,pitch:0},n={x:70,y:30,z:100};
 assert.notDeepEqual(project(n,camera,3),project(n,{...camera,yaw:.5},3));
 assert.deepEqual(project(n,camera,2),project({...n,z:-100},camera,2));
 assert.ok(Object.values(project(n,{...camera,yaw:1,pitch:.8},3)).every(Number.isFinite));
});
test('real network UI replaces synthetic data and exposes scope, dimension and complete census',()=>{
 const html=fs.readFileSync(path.join(__dirname,'../showcase/index.html'),'utf8'),module=fs.readFileSync(path.join(__dirname,'../showcase/enterprise-network.js'),'utf8');
 assert.ok(!html.includes('24个合成企业'));assert.ok(html.includes('id="network-dimension"'));assert.ok(html.includes('id="network-scope"'));
 assert.ok(module.includes('assets/real-network.json'));assert.ok(!module.includes('network-demo.json'));
 assert.ok(html.includes('合成企业示例')); // Separate evidence tutorial retains its honest synthetic provenance.
});
