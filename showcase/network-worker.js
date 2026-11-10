/* Layout runs off the UI thread; every tag-signature group remains represented. */
importScripts('vendor/d3.v7.min.js','vendor/d3-binarytree.min.js','vendor/d3-octree.min.js','vendor/d3-force-3d.min.js','network-model.js');
self.onmessage=function(event){
 try{
  const {groups,categories,mode,dimensions,threshold}=event.data;
  const colors=new Map(categories.map(c=>[c.id,c.color]));
  const nodes=groups.map((g,i)=>({...g,color:colors.get(g.tags.find(t=>t!=='qualification_review')||g.tags[0])||'#bcc3cd',
   x:Math.cos(i*2.4)*Math.sqrt(i+1)*7,y:Math.sin(i*2.4)*Math.sqrt(i+1)*7,z:dimensions===3?Math.sin(i*1.8)*80:0}));
  let edges;
  if(mode==='similarity')edges=NetworkModel.links(nodes,threshold,6);
  else{
   const used=new Set(groups.flatMap(g=>g.tags));
   for(const c of categories.filter(c=>used.has(c.id)))nodes.push({...c,id:'tag-'+c.id,label:c.label,isTag:true,x:0,y:0,z:0});
   edges=groups.flatMap(g=>g.tags.map(t=>({source:g.id,target:'tag-'+t,similarity:1,distance:95})));
  }
  const simulation=d3.forceSimulation(nodes,dimensions).stop()
   .force('link',d3.forceLink(edges).id(d=>d.id).distance(d=>d.distance).strength(.35))
   .force('charge',d3.forceManyBody().strength(-24).distanceMax(260))
   .force('center',d3.forceCenter(0,0,0)).force('collision',d3.forceCollide(4.7));
  simulation.tick(140);
  const bound=Math.max(1,...nodes.map(n=>Math.hypot(n.x,n.y,dimensions===3?n.z:0)));
  for(const n of nodes){n.x=n.x/bound*285;n.y=n.y/bound*185;n.z=dimensions===3?n.z/bound*230:0;}
  self.postMessage({nodes,edges:edges.map(e=>({...e,source:e.source.id,target:e.target.id})),dimensions});
 }catch(error){self.postMessage({error:error.message});}
};
