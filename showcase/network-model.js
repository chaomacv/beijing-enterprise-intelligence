/* Complete tag-signature census: aggregate membership, then construct real edges. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.NetworkModel=api;})(typeof self==='object'?self:globalThis,function(){
 'use strict';
 const palette=['#1f77b4','#ff7f0e','#2ca02c','#d62728','#9467bd','#8c564b','#e377c2','#7f7f7f','#bcbd22','#17becf'];
 function jaccard(a,b){const x=new Set(a.filter(t=>t!=='qualification_review')),y=new Set(b.filter(t=>t!=='qualification_review'));const shared=[...x].filter(t=>y.has(t)).length,total=new Set([...x,...y]).size;return total?shared/total:0;}
 function groups(data,scope='all',category=''){
  const allowed=new Set(data.categories.filter((c,i)=>scope==='all'||i<10).map(c=>c.id)),bins=new Map();
  for(const g of data.groups){const tags=g.tags.filter(t=>allowed.has(t)).sort();if(category&&!tags.includes(category))continue;
   const key=tags.join('|');if(!bins.has(key))bins.set(key,{id:'signature-'+(key||'empty'),tags,profiles:0,provisional_profiles:0});
   const n=bins.get(key);n.profiles+=g.profiles;n.provisional_profiles+=g.provisional_profiles;
  }
  return [...bins.values()].sort((a,b)=>b.profiles-a.profiles||a.id.localeCompare(b.id));
 }
 function popcount(n){n-=n>>>1&0x55555555;n=(n&0x33333333)+(n>>>2&0x33333333);return ((n+(n>>>4)&0x0f0f0f0f)*0x01010101)>>>24;}
 function overview(nodes,categories){
  const order=new Map(categories.map((c,i)=>[c.id,i])),bins=new Map();
  for(const n of nodes){
   const tags=n.tags.filter(t=>t!=='qualification_review').sort((a,b)=>order.get(a)-order.get(b)).slice(0,2),key=tags.join('|');
   if(!bins.has(key))bins.set(key,{id:'overview-'+(key||'empty'),tags,profiles:0,provisional_profiles:0,members:[]});
   const g=bins.get(key);g.profiles+=n.profiles;g.provisional_profiles+=n.provisional_profiles;g.members.push(n);
  }
  return [...bins.values()].sort((a,b)=>b.profiles-a.profiles||a.id.localeCompare(b.id));
 }
 function links(nodes,threshold=.6,neighbors=6){
  const members=nodes.map(n=>n.members||[n]),tags=[...new Set(members.flatMap(list=>list.flatMap(n=>n.tags)))].filter(t=>t!=='qualification_review');if(tags.length>30)throw Error('Too many mask dimensions');
  const vectors=members.map(list=>list.map(n=>({mask:n.tags.reduce((m,t)=>t==='qualification_review'?m:m|(1<<tags.indexOf(t)),0),count:n.profiles||1})));
  const totals=vectors.map(list=>list.reduce((sum,v)=>sum+v.count,0));
  const candidates=nodes.map(()=>[]);
  for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){
   let similarity=0;
   if(vectors[i].length===1&&vectors[j].length===1){const a=vectors[i][0],b=vectors[j][0],union=popcount(a.mask|b.mask);similarity=union?popcount(a.mask&b.mask)/union:0;}
   else{let weighted=0;for(const a of vectors[i])for(const b of vectors[j]){const union=popcount(a.mask|b.mask);if(union)weighted+=popcount(a.mask&b.mask)/union*a.count*b.count;}similarity=weighted/totals[i]/totals[j];}
   if(similarity>0&&similarity>=threshold){
    for(const index of [i,j]){const list=candidates[index];
     if(list.length<neighbors||similarity>list.at(-1).similarity){list.push({i,j,similarity});list.sort((a,b)=>b.similarity-a.similarity||a.i-b.i||a.j-b.j);if(list.length>neighbors)list.pop();}
    }
   }
  }
  const result=new Map();for(const list of candidates){list.sort((a,b)=>b.similarity-a.similarity||a.i-b.i||a.j-b.j);for(const e of list.slice(0,neighbors))result.set(e.i+':'+e.j,e);}
  return [...result.values()].map(e=>({source:nodes[e.i].id,target:nodes[e.j].id,similarity:e.similarity,distance:160-100*e.similarity}));
 }
 function project(n,camera,dimensions){
  let x=n.x,y=n.y,z=dimensions===3?n.z:0;
  if(dimensions===3){const xx=x*Math.cos(camera.yaw)+z*Math.sin(camera.yaw),zz=-x*Math.sin(camera.yaw)+z*Math.cos(camera.yaw);x=xx;z=zz;
   const yy=y*Math.cos(camera.pitch)-z*Math.sin(camera.pitch);z=y*Math.sin(camera.pitch)+z*Math.cos(camera.pitch);y=yy;}
  const perspective=dimensions===3?700/(700+z):1;
  return {x:360+camera.x+x*camera.k*perspective,y:220+camera.y+y*camera.k*perspective,z,scale:perspective};
 }
 return {palette,jaccard,groups,overview,popcount,links,project};
});
