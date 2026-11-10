const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {hierarchy,layout}=require('../showcase/event-sunburst.js');
const assets=path.join(__dirname,'../showcase/assets'),manifest=JSON.parse(fs.readFileSync(path.join(assets,'event-hierarchy.json'),'utf8'));
test('all three real exploration modes reconcile their unit and every parent, without private fields',()=>{
 assert.equal(manifest.kind,'verified_exploration_manifest');assert.deepEqual(manifest.modes.map(m=>m.total),[5200,11701,43653625]);
 assert.equal(manifest.checks.unmatched_catalog_attachments,0);
 for(const mode of manifest.modes){
  const raw=fs.readFileSync(path.join(assets,mode.file)),data=JSON.parse(raw);assert.equal(crypto.createHash('sha256').update(raw).digest('hex'),mode.sha256);
  const {tree,nodes}=hierarchy(data.tree);assert.equal(tree.value,mode.total);assert.equal(Math.max(...nodes.map(n=>n.depth)),3);
  assert.ok(!/"(?:record_id|file_id|entity_id|cells|path|address|credit_code)"|\/opt\/|password/.test(raw.toString()));
  if(mode.id==='logical'){const leaves=nodes.filter(n=>!n.children.length);assert.equal(leaves.length,11701);assert.ok(leaves.every(n=>n.value===1&&/^逻辑文件 \d{5}$/.test(n.name)));}
  if(mode.id==='records')assert.equal(nodes.filter(n=>n.depth===2&&n.name==='已筛选排除').reduce((s,n)=>s+n.value,0),27792348);
 }
});
test('zoom shows two descendant levels with area proportional to counts and no sibling leakage',()=>{
 const {tree,nodes}=hierarchy({id:'r',name:'test',value:100,children:[{id:'a',name:'A',value:75,children:[{id:'aa',name:'AA',value:50},{id:'ab',name:'AB',value:25}]},{id:'b',name:'B',value:25,children:[{id:'ba',name:'BA',value:25}]}]});
 for(const focus of [tree,tree.children[0]]){
  const areas=layout(nodes,focus).map(s=>({n:nodes.find(n=>n.id===s.id),area:(s.b-s.a)*(s.outer**2-s.inner**2)/2}));
  const scale=areas[0].area/areas[0].n.value;for(const x of areas)assert.ok(Math.abs(x.area/x.n.value-scale)<1e-8);
  if(focus!==tree)assert.deepEqual(areas.map(a=>a.n.id).sort(),['aa','ab']);
 }
 assert.throws(()=>hierarchy({id:'x',name:'bad',value:10,children:[{id:'y',name:'bad',value:9}]}));
 assert.throws(()=>hierarchy({id:'x',name:'bad',children:[{id:'x',name:'duplicate',value:9}]}));
});
