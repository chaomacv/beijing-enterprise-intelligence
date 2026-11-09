(function(root,factory){
 const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;
 if(root.document)api.mount(root).catch(()=>{const el=root.document.getElementById('network-detail');if(el)el.textContent='网络示例暂不可用。';});
})(typeof window==='object'?window:globalThis,function(){
 'use strict';
 const palette=['#4269d0','#efb118','#ff725c','#6cc5b0','#a463f2','#ff8ab7','#97bbf5','#b59a6b','#60a8a4','#b5c456'];
 const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function jaccard(a,b){
  const x=new Set(a.filter(t=>t!=='qualification_review')),y=new Set(b.filter(t=>t!=='qualification_review'));
  const intersection=[...x].filter(t=>y.has(t)).length,union=new Set([...x,...y]).size;
  return union?intersection/union:0;
 }
 function links(companies,threshold){
  const result=[];for(let i=0;i<companies.length;i++)for(let j=i+1;j<companies.length;j++){
   const similarity=jaccard(companies[i].tags,companies[j].tags);
   if(similarity>0&&similarity>=threshold)result.push({source:companies[i].id,target:companies[j].id,similarity,distance:160-100*similarity});
  }return result;
 }
 function step(nodes,edges,alpha=1){
  const byId=new Map(nodes.map(n=>[n.id,n]));
  for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){
   const a=nodes[i],b=nodes[j];let dx=b.x-a.x,dy=b.y-a.y,d=Math.max(8,Math.hypot(dx,dy));
   if(!dx&&!dy){dx=.2;dy=.1;}
   const force=(1800/(d*d)+Math.max(0,23-d)*.12)*alpha;
   a.vx-=dx/d*force;a.vy-=dy/d*force;b.vx+=dx/d*force;b.vy+=dy/d*force;
  }
  for(const e of edges){const a=byId.get(e.source),b=byId.get(e.target);if(!a||!b)continue;
   const dx=b.x-a.x,dy=b.y-a.y,d=Math.max(1,Math.hypot(dx,dy)),force=(d-e.distance)*.018*alpha;
   a.vx+=dx/d*force;a.vy+=dy/d*force;b.vx-=dx/d*force;b.vy-=dy/d*force;
  }
  for(const n of nodes){n.vx=(n.vx+(360-n.x)*.0015*alpha)*.8;n.vy=(n.vy+(215-n.y)*.0015*alpha)*.8;
   if(n.fixed){n.vx=n.vy=0;}else{n.x=Math.max(28,Math.min(692,n.x+n.vx));n.y=Math.max(28,Math.min(402,n.y+n.vy));}
  }
 }
 async function mount(win){
  const doc=win.document,$=id=>doc.getElementById(id),host=$('enterprise-network');if(!host)return;
  const response=await win.fetch('assets/network-demo.json');if(!response.ok)throw Error('Network unavailable');
  const data=await response.json();if(data.kind!=='synthetic_enterprise_network')throw Error('Network provenance mismatch');
  const cats=new Map(data.categories.map((c,i)=>[c.id,{...c,color:palette[i]}]));
  $('network-category').innerHTML='<option value="">全部类别</option>'+data.categories.map(c=>`<option value="${c.id}">${esc(c.label)}</option>`).join('');
  let nodes=[],edges=[],frame=0,iteration=0,selected='',camera={k:1,x:0,y:0},drag=null,mode='similarity';
  const expanded=()=>!!host.closest('#notebook-reader');
  function describe(n){
   selected=n.id;const labels=n.tags?n.tags.map(t=>cats.get(t).label):[n.label];
   $('network-detail').innerHTML=`<strong>${esc(n.name||n.label)}</strong><span>${labels.map(esc).join(' · ')}</span><small>${n.tags?'合成企业的示意标签；不代表实际持证或业务关系。':'类别节点表示合成示例中的关联记录类型。'}</small>`;
  }
  function draw(){
   const byId=new Map(nodes.map(n=>[n.id,n]));
   const body=edges.map(e=>{const a=byId.get(e.source),b=byId.get(e.target);return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="${mode==='similarity'?'#a9b5ca':'#d1d8e4'}" stroke-opacity=".65" stroke-width="${mode==='similarity'?.5+e.similarity*2:1}"><title>${mode==='similarity'?'标签相似度 '+e.similarity.toFixed(3):'合成企业—类别关联'}</title></line>`;}).join('')+
    nodes.map(n=>`<g data-network-node="${n.id}" tabindex="0" role="button" aria-label="${esc(n.name||n.label)}" transform="translate(${n.x} ${n.y})">${n.tags?`<circle r="${selected===n.id?9:7}" fill="${n.color}" stroke="white" stroke-width="1.5"/>`:`<path d="M0 -9L9 0 0 9 -9 0Z" fill="${n.color}" stroke="white"/>`}<title>${esc(n.name||n.label)}</title><text x="11" y="4" font-size="10" fill="#5a6880" pointer-events="none">${esc(n.tags?n.id.slice(-2):n.label)}</text></g>`).join('');
   host.innerHTML=`<svg viewBox="0 0 720 430" role="group" aria-label="合成企业标签画像网络，可展开操作"><g transform="translate(${camera.x} ${camera.y}) scale(${camera.k})">${body}</g></svg>`;
   $('network-zoom-value').textContent=Math.round(camera.k*100)+'%';
  }
  function settle(){
   win.cancelAnimationFrame(frame);for(let i=0;i<100;i++)step(nodes,edges,1-i/160);draw();
   iteration=0;
   function animate(){if(!expanded()||doc.hidden||win.matchMedia('(prefers-reduced-motion: reduce)').matches)return;
    step(nodes,edges,Math.max(.06,1-iteration/140));draw();if(++iteration<140)frame=win.requestAnimationFrame(animate);
   }if(expanded())frame=win.requestAnimationFrame(animate);
  }
  function rebuild(){
   const category=$('network-category').value,companies=data.companies.filter(c=>!category||c.tags.includes(category));mode=$('network-mode').value;
   nodes=companies.map((c,i)=>({...c,color:cats.get(c.tags.find(t=>t!=='qualification_review')||c.tags[0]).color,
     x:360+Math.cos(i*2.4)*130,y:215+Math.sin(i*2.4)*120,vx:0,vy:0}));
   if(mode==='similarity')edges=links(companies,Number($('network-threshold').value));
   else{const used=new Set(companies.flatMap(c=>c.tags));
    data.categories.filter(c=>used.has(c.id)).forEach((c,i)=>nodes.push({...c,color:cats.get(c.id).color,x:360+Math.cos(i*.8)*170,y:215+Math.sin(i*.8)*150,vx:0,vy:0}));
    edges=companies.flatMap(c=>c.tags.map(t=>({source:c.id,target:t,distance:90,similarity:1})));
   }
   $('network-threshold-value').value=Number($('network-threshold').value).toFixed(2);
   $('network-threshold').disabled=mode!=='similarity';
   $('network-size').textContent=`${companies.length} 个合成企业 · ${mode==='similarity'?edges.length+' 条相似边':nodes.length-companies.length+' 类标签'}`;
   settle();
  }
  function zoom(factor,point={x:360,y:215}){
   const next=Math.max(.45,Math.min(3.5,camera.k*factor)),ratio=next/camera.k;
   camera={k:next,x:point.x-(point.x-camera.x)*ratio,y:point.y-(point.y-camera.y)*ratio};draw();
  }
  function point(event){const rect=host.querySelector('svg').getBoundingClientRect();return {x:(event.clientX-rect.left)/rect.width*720,y:(event.clientY-rect.top)/rect.height*430};}
  for(const id of ['network-category','network-mode','network-threshold'])$(id).addEventListener('input',rebuild);
  $('network-zoom-in').addEventListener('click',()=>zoom(1.25));$('network-zoom-out').addEventListener('click',()=>zoom(.8));
  $('network-reset').addEventListener('click',()=>{camera={k:1,x:0,y:0};rebuild();});
  host.addEventListener('wheel',e=>{if(!expanded())return;e.preventDefault();zoom(Math.exp(-e.deltaY*.001),point(e));},{passive:false});
  host.addEventListener('pointerdown',e=>{
   const target=e.target.closest('[data-network-node]'),node=target&&nodes.find(n=>n.id===target.dataset.networkNode);
   if(node)describe(node);if(!expanded())return;
   win.cancelAnimationFrame(frame);const p=point(e);drag={node,start:p,x:camera.x,y:camera.y};
   if(node)node.fixed=true;host.setPointerCapture(e.pointerId);
  });
  host.addEventListener('pointermove',e=>{if(!drag)return;const p=point(e);
   if(drag.node){drag.node.x=(p.x-camera.x)/camera.k;drag.node.y=(p.y-camera.y)/camera.k;}
   else{camera.x=drag.x+p.x-drag.start.x;camera.y=drag.y+p.y-drag.start.y;}draw();
  });
  for(const type of ['pointerup','pointercancel','lostpointercapture'])host.addEventListener(type,()=>{if(drag?.node)drag.node.fixed=false;drag=null;});
  host.addEventListener('focusin',e=>{const node=e.target.closest('[data-network-node]');if(node)describe(nodes.find(n=>n.id===node.dataset.networkNode));});
  host.addEventListener('keydown',e=>{if(e.key==='+'||e.key==='='){e.preventDefault();e.stopPropagation();zoom(1.25);}if(e.key==='-'){e.preventDefault();e.stopPropagation();zoom(.8);}});
  if(win.ResizeObserver)new win.ResizeObserver(()=>{if(!drag)draw();}).observe(host);
  doc.addEventListener('visibilitychange',()=>{if(doc.hidden)win.cancelAnimationFrame(frame);});
  rebuild();host.dataset.ready='true';
 }
 return {jaccard,links,step,mount};
});
