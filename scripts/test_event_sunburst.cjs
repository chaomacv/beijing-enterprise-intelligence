const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {hierarchy,layout}=require('../showcase/event-sunburst.js');
const data=JSON.parse(fs.readFileSync(path.join(__dirname,'../showcase/assets/event-hierarchy.json'),'utf8'));
test('published hierarchy conserves real ten-category counts and invents no descendants',()=>{
 const {tree,nodes}=hierarchy(data.tree);
 assert.equal(tree.value,5031890);assert.equal(nodes.length,11);assert.equal(tree.children.length,10);
 assert.ok(tree.children.every(n=>!n.children.length));
 assert.equal(tree.value+data.excluded_other_event_observations,5961231);
 assert.deepEqual(data.pending_levels,['business_subcategory','event_label']);
 assert.ok(!/record_id|file_id|\/opt\/|cells|password/.test(JSON.stringify(data)));
});
test('every same-depth sector has area proportional to its actual count',()=>{
 // Synthetic hierarchy is test-only; it is never included in public counts.
 const {tree,nodes}=hierarchy({id:'r',name:'test',value:100,children:[
  {id:'a',name:'A',value:75,children:[{id:'aa',name:'AA',value:50},{id:'ab',name:'AB',value:25}]},
  {id:'b',name:'B',value:25,children:[{id:'ba',name:'BA',value:25}]}]});
 for(const focus of [tree,tree.children[0]]){
  const shapes=layout(nodes,focus);
  const areas=shapes.map(s=>({n:nodes.find(n=>n.id===s.id),area:(s.b-s.a)*(s.outer**2-s.inner**2)/2}));
  const scale=areas[0].area/areas[0].n.value;
  for(const x of areas)assert.ok(Math.abs(x.area/x.n.value-scale)<1e-8);
  assert.ok(shapes.every(s=>s.a>=-1e-8&&s.b<=Math.PI*2+1e-8));
 }
 assert.throws(()=>hierarchy({id:'x',name:'bad',value:10,children:[{id:'y',name:'bad',value:9}]}));
 assert.throws(()=>hierarchy({id:'x',name:'bad',children:[{id:'x',name:'duplicate',value:9}]}));
});
