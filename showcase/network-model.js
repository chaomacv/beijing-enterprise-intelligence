/* One company per node. Similarity uses shared category and event counts. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.NetworkModel=api;})(typeof self==='object'?self:globalThis,function(){
 'use strict';
 const palette=['#1f77b4','#ff7f0e','#2ca02c','#d62728','#9467bd','#8c564b','#e377c2','#7f7f7f','#bcbd22','#17becf'];
 function companies(data,scope='all',category=''){
  const allowed=new Set(data.categories.filter((c,i)=>scope==='all'||i<10).map(c=>c.id));
  return data.companies.map(c=>{
   const event_counts=Object.fromEntries(Object.entries(c.event_counts).filter(([t,n])=>allowed.has(t)&&n>0));
   const tags=Object.keys(event_counts).filter(t=>t!=='qualification_review');
   return {...c,event_counts,tags,tag_count:tags.length,event_count:tags.reduce((s,t)=>s+event_counts[t],0)};
  }).filter(c=>!category||c.event_counts[category]>0);
 }
 function normalizers(nodes){return {tag_count:Math.max(1,...nodes.map(n=>n.tag_count)),event_count:Math.max(1,...nodes.map(n=>n.event_count))};}
 function similarity(a,b,scale){
  const shared=a.tags.filter(t=>b.tags.includes(t));
  const shared_events=shared.reduce((s,t)=>s+Math.min(a.event_counts[t],b.event_counts[t]),0);
  const score=shared.length?.65*shared.length/scale.tag_count+.35*Math.log1p(shared_events)/Math.log1p(scale.event_count):0;
  return {shared_types:shared.length,shared_events,similarity:Math.min(1,score),distance:220-160*Math.min(1,score)};
 }
 function connections(nodes,threshold=.1,neighbors=3,scale=normalizers(nodes)){
  const pairs=[],candidates=nodes.map(()=>[]);
  for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){
   const metrics=similarity(nodes[i],nodes[j],scale);if(!metrics.shared_types)continue;
   const edge={source:nodes[i].id,target:nodes[j].id,...metrics};pairs.push(edge);
   if(metrics.similarity>=threshold){candidates[i].push(edge);candidates[j].push(edge);}
  }
  const visible=new Map();for(const list of candidates){list.sort((a,b)=>b.similarity-a.similarity||a.source.localeCompare(b.source)||a.target.localeCompare(b.target));
   for(const e of list.slice(0,neighbors))visible.set(e.source+'|'+e.target,e);}
  return {edges:[...visible.values()],forces:pairs};
 }
 function tagPositions(categories,dimensions){
  return categories.map((c,i)=>{const a=i/categories.length*Math.PI*2-Math.PI/2;
   const x=Math.cos(a)*235,y=Math.sin(a)*155,z=dimensions===3?Math.sin(a*2)*70:0;
   return {...c,id:'tag-'+c.id,category:c.id,isTag:true,x,y,z,fx:x,fy:y,fz:z};
  });
 }
 function tagEdges(nodes){return nodes.flatMap(n=>Object.entries(n.event_counts).map(([tag,count])=>({source:n.id,target:'tag-'+tag,event_count:count,distance:100,similarity:1})));}
 function project(n,camera,dimensions){
  let x=n.x,y=n.y,z=dimensions===3?n.z:0;
  if(dimensions===3){const xx=x*Math.cos(camera.yaw)+z*Math.sin(camera.yaw),zz=-x*Math.sin(camera.yaw)+z*Math.cos(camera.yaw);x=xx;z=zz;
   const yy=y*Math.cos(camera.pitch)-z*Math.sin(camera.pitch);z=y*Math.sin(camera.pitch)+z*Math.cos(camera.pitch);y=yy;}
  const perspective=dimensions===3?700/(700+z):1;
  return {x:360+camera.x+x*camera.k*perspective,y:220+camera.y+y*camera.k*perspective,z,scale:perspective};
 }
 return {palette,companies,normalizers,similarity,connections,tagPositions,tagEdges,project};
});
