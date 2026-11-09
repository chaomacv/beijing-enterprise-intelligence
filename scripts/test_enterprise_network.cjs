const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {jaccard,links,step}=require('../showcase/enterprise-network.js');
const data=JSON.parse(fs.readFileSync(path.join(__dirname,'../showcase/assets/network-demo.json'),'utf8'));
test('network is explicitly synthetic with ten real category definitions and no real enterprise identifiers',()=>{
 assert.equal(data.kind,'synthetic_enterprise_network');assert.equal(data.real_entity_overlap_available,false);
 assert.equal(data.companies.length,24);assert.equal(data.categories.length,10);
 const ids=new Set(data.categories.map(c=>c.id));
 assert.equal(new Set(data.companies.map(c=>c.id)).size,24);
 for(const c of data.companies){assert.match(c.name,/^合成企业/);assert.ok(c.tags.every(t=>ids.has(t)));}
 assert.ok(!/credit_code|record_id|file_id|\/opt\/|password|address/.test(JSON.stringify(data)));
});
test('Jaccard scores ignore duplicate tags and quality-review flags and never infer business relationships',()=>{
 assert.equal(jaccard(['a','a','b'],['a','b']),1);
 assert.equal(jaccard(['a','b'],['b','c']),1/3);
 assert.equal(jaccard(['qualification_review'],['qualification_review']),0);
 assert.equal(jaccard(['a','qualification_review'],['a']),1);
 assert.equal(jaccard([],[]),0);
 const low=links(data.companies,.3),high=links(data.companies,.8);
 assert.ok(low.length>high.length&&high.length>0);
 assert.ok(low.every(e=>e.source!==e.target&&e.similarity>=.3&&e.distance>=60&&e.distance<=160));
 for(const edge of high)assert.ok(low.some(e=>e.source===edge.source&&e.target===edge.target));
});
test('force layout stays finite and bounded including isolated and coincident nodes',()=>{
 const nodes=data.companies.map(c=>({...c,x:360,y:215,vx:0,vy:0})),edges=links(nodes,.3);
 for(let i=0;i<300;i++)step(nodes,edges,.6);
 for(const n of nodes){assert.ok([n.x,n.y,n.vx,n.vy].every(Number.isFinite));assert.ok(n.x>=28&&n.x<=692&&n.y>=28&&n.y<=402);}
});
test('requested notebooks replace removed views and preserve data provenance boundaries',()=>{
 const html=fs.readFileSync(path.join(__dirname,'../showcase/index.html'),'utf8');
 for(const title of ['每条记录，都有明确的去向。','把异构文件放进一个三维空间。','像同一家，不等于就是同一家。'])assert.ok(!html.includes('<h3>'+title+'</h3>'));
 for(const label of ['方法说明','画像网络','企业画像'])assert.ok(html.includes('notebook-category">'+label));
 assert.ok(html.includes('24个合成企业'));assert.ok(html.includes('合成企业示例'));
 const module=fs.readFileSync(path.join(__dirname,'../showcase/story-portrait.js'),'utf8');
 for(const phrase of ['数据如何被读取？','如何找到有价值的信息？','如何让处理更高效？','如何保证结果可信？','如何将事实变成业务价值？'])assert.ok(module.includes(phrase));
});
