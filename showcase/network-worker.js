/* Real company sample, with separate company-company and company-tag layouts. */
importScripts('vendor/d3.v7.min.js','vendor/d3-binarytree.min.js','vendor/d3-octree.min.js','vendor/d3-force-3d.min.js','network-model.js');
self.onmessage=function(event){
 try{
  const {companies,categories,mode,dimensions,threshold,normalizers}=event.data;
  const colors=new Map(categories.map(c=>[c.id,c.color]));
  const nodes=companies.map((c,i)=>{const dominant=c.tags.slice().sort((a,b)=>c.event_counts[b]-c.event_counts[a]||a.localeCompare(b))[0];
   return {...c,color:colors.get(dominant)||'#bcc3cd',x:Math.cos(i*2.4)*Math.sqrt(i+1)*8,y:Math.sin(i*2.4)*Math.sqrt(i+1)*8,z:dimensions===3?Math.sin(i*1.8)*60:0};});
  let edges,forces;
  if(mode==='similarity'){const result=NetworkModel.connections(nodes,threshold,3,normalizers);edges=result.edges;forces=result.forces;}
  else{edges=NetworkModel.tagEdges(nodes);forces=edges;nodes.push(...NetworkModel.tagPositions(categories,dimensions));}
  const simulation=d3.forceSimulation(nodes,dimensions).stop()
   .force('link',d3.forceLink(forces).id(d=>d.id).distance(d=>d.distance).strength(d=>mode==='similarity'?.04+.3*d.similarity:.16+.04*Math.log1p(d.event_count)))
   .force('charge',d3.forceManyBody().strength(-65).distanceMax(300)).force('collision',d3.forceCollide(d=>d.isTag?13:6.5));
  if(mode==='similarity')simulation.force('center',d3.forceCenter(0,0,0));
  else simulation.force('inner-x',d3.forceX(0).strength(d=>d.isTag?0:.02)).force('inner-y',d3.forceY(0).strength(d=>d.isTag?0:.02));
  simulation.tick(220);
  if(mode==='similarity'){
   const factor=Math.min(270/Math.max(1,...nodes.map(n=>Math.abs(n.x))),175/Math.max(1,...nodes.map(n=>Math.abs(n.y))),dimensions===3?190/Math.max(1,...nodes.map(n=>Math.abs(n.z))):Infinity);
   for(const n of nodes){n.x*=factor;n.y*=factor;n.z=dimensions===3?n.z*factor:0;}
  }
  else for(const n of nodes.filter(n=>!n.isTag)){
   const r=Math.sqrt((n.x/200)**2+(n.y/120)**2+(dimensions===3?(n.z/95)**2:0));
   if(r>1){n.x/=r;n.y/=r;n.z/=r;}
  }
  self.postMessage({nodes,edges:edges.map(e=>({...e,source:e.source.id,target:e.target.id})),dimensions,mode});
 }catch(error){self.postMessage({error:error.message});}
};
