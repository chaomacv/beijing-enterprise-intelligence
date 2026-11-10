/* D3 Category10, gray links and draggable nodes, with a true 3D force layout. */
(function(root){
 'use strict';
 if(typeof module==='object'&&module.exports){module.exports=require('./network-model.js');return;}
 const model=root.NetworkModel,d3=root.d3,doc=root.document,$=id=>doc.getElementById(id),host=$('enterprise-network');if(!host)return;
 const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),fmt=n=>n.toLocaleString('en-US');
 let data,nodes=[],edges=[],worker,serial=0,dimension=2,drag=null,selected='',camera={k:1,x:0,y:0,yaw:0,pitch:0};
 const expanded=()=>!!host.closest('#notebook-reader');
 const svg=d3.select(host).append('svg').attr('viewBox','0 0 720 440').attr('role','group').attr('aria-label','全量真实画像标签组合网络');
 const lines=svg.append('g').attr('class','network-edges').attr('stroke','#999').attr('stroke-opacity',.5),dots=svg.append('g').attr('class','network-nodes');
 const axis=svg.append('g').attr('class','network-axis').attr('transform','translate(667 391)').attr('aria-hidden','true');
 function describe(n){
  if(!n)return;selected=n.id;
  const tags=n.tags?n.tags.map(t=>data.categories.find(c=>c.id===t).label):[n.label];
  $('network-detail').hidden=false;
  $('network-detail').innerHTML=`<strong>${n.isTag?esc(n.label):fmt(n.profiles)+' 个真实主体画像'}</strong><span>${tags.length?(n.members?'分组共有标签：':'观察标签：')+tags.map(esc).join(' · '):'无可比较事件标签（未观察或仅待复核）'}</span><small>${n.members?'包含 '+n.members.length+' 种完整组合 · ':''}${n.isTag?'来源标签':fmt(n.provisional_profiles)+' 个临时身份'}；相似连线不表示业务联系。</small>`;draw();
 }
 function draw(){
  const positions=new Map(nodes.map(n=>[n.id,model.project(n,camera,dimension)]));
  lines.selectAll('line').attr('x1',e=>positions.get(e.source).x).attr('y1',e=>positions.get(e.source).y).attr('x2',e=>positions.get(e.target).x).attr('y2',e=>positions.get(e.target).y);
  dots.selectAll('g').sort((a,b)=>positions.get(b.id).z-positions.get(a.id).z)
   .attr('transform',n=>{const p=positions.get(n.id);return `translate(${p.x} ${p.y})`;})
   .attr('opacity',n=>dimension===3?Math.max(.45,Math.min(1,1-positions.get(n.id).z/600)):1)
   .select('circle').attr('r',n=>(n.isTag?6:n.id===selected?6.5:n.members?4.5:3.2)*Math.sqrt(positions.get(n.id).scale)).attr('stroke-width',n=>n.id===selected?2:1.2);
  dots.selectAll('text').attr('display',()=>$('network-labels').checked?null:'none');
  axis.selectAll('*').remove();
  if(dimension===3){for(const [name,end,color] of [['X',{x:24,y:0,z:0},'#d62728'],['Y',{x:0,y:24,z:0},'#2ca02c'],['Z',{x:0,y:0,z:24},'#1f77b4']]){
   const c={...camera,k:1,x:0,y:0},p=model.project(end,c,3),o=model.project({x:0,y:0,z:0},c,3);
   axis.append('line').attr('x2',p.x-o.x).attr('y2',p.y-o.y).attr('stroke',color);axis.append('text').attr('x',(p.x-o.x)*1.25).attr('y',(p.y-o.y)*1.25).attr('fill',color).text(name);
  }}
  $('network-zoom-value').textContent=Math.round(camera.k*100)+'%';host.dataset.camera=[camera.yaw,camera.pitch,camera.x,camera.y].join(',');
 }
 function rebuild(){
  if(!data)return;const scope=$('network-scope').value,visibleCategories=data.categories.filter((c,i)=>scope==='all'||i<10);
  let category=$('network-category').value;if(!visibleCategories.some(c=>c.id===category))category='';
  $('network-category').innerHTML='<option value="">全部类别</option>'+visibleCategories.map(c=>`<option value="${esc(c.id)}">${esc(c.label)}</option>`).join('');$('network-category').value=category;
  $('network-legend').innerHTML=visibleCategories.map(c=>`<span><i style="background:${c.color}"></i>${esc(c.label)}</span>`).join('');
  const groups=model.groups(data,scope,category),token=++serial,mode=$('network-mode').value,detail=$('network-detail-level').value;
  dimension=Number($('network-dimension').value);$('network-threshold').disabled=mode!=='similarity';
  $('network-threshold-value').value=Number($('network-threshold').value).toFixed(2);
  const profiles=groups.reduce((s,n)=>s+n.profiles,0);
  $('network-size').textContent=category?`当前 ${fmt(profiles)} / ${fmt(data.profiles)} 个画像`:`覆盖全部 ${fmt(profiles)} 个画像`;
  $('network-hint').textContent=dimension===3?'拖动空白旋转 · Shift拖动平移 · 滚轮缩放':'拖动节点或空白 · 滚轮缩放 · 悬停查看标签';
  $('network-detail').hidden=true;selected='';
  host.setAttribute('aria-busy','true');host.dataset.ready='loading';
  if(worker)worker.terminate();worker=new root.Worker('network-worker.js');
  worker.onmessage=event=>{
   if(token!==serial)return;if(event.data.error){$('network-detail').textContent='布局计算失败，请切换模式重试。';host.setAttribute('aria-busy','false');return;}
   nodes=event.data.nodes;edges=event.data.edges;
   lines.selectAll('line').data(edges).join('line').attr('stroke-width',.85);
   const items=dots.selectAll('g').data(nodes,n=>n.id).join(enter=>{
    const g=enter.append('g').attr('tabindex',0).attr('role','button');g.append('circle');g.append('title');g.append('text').attr('x',8).attr('y',3);return g;
   }).attr('data-network-node',n=>n.id).attr('aria-label',n=>n.isTag?n.label:fmt(n.profiles)+'个画像的真实标签组合')
    .on('focus',(e,n)=>describe(n)).on('click',(e,n)=>describe(n));
   items.select('circle').attr('fill',n=>n.color).attr('stroke','#fff');
   items.select('title').text(n=>n.isTag?n.label:fmt(n.profiles)+' 个画像\n'+(n.members?'分组共有标签：':'')+(n.tags.map(t=>data.categories.find(c=>c.id===t).label).join(' · ')||'无可比较事件标签')+(n.members?'\n包含 '+n.members.length+' 种完整标签组合':''));
   items.select('text').text(n=>n.isTag?n.label:n.tags.length+'类 · '+fmt(n.profiles));
   draw();host.dataset.ready='true';host.dataset.dimensions=dimension;host.dataset.detail=detail;host.dataset.profiles=profiles;host.setAttribute('aria-busy','false');
   $('network-edge-count').textContent=fmt(nodes.length)+(detail==='overview'?' 个概览分组':' 个完整组合')+' · '+fmt(edges.length)+' 条连接';
   $('network-view-note').textContent=detail==='overview'?'概览按固定类别顺序的前两项观察标签归组，全部画像保留；完整组合可在更多选项中查看。':'完整组合逐组展示，每组保留相同的全部观察标签；无标签画像也计入。';
  };
  worker.onerror=()=>{$('network-detail').textContent='网络布局暂不可用，请刷新后重试。';host.setAttribute('aria-busy','false');};
  worker.postMessage({groups,categories:visibleCategories,mode,dimensions:dimension,threshold:Number($('network-threshold').value),detail});
 }
 function zoom(factor,p={x:360,y:220}){const next=Math.max(.4,Math.min(8,camera.k*factor)),r=next/camera.k;camera={...camera,k:next,x:p.x-360-(p.x-360-camera.x)*r,y:p.y-220-(p.y-220-camera.y)*r};draw();}
 function point(e){const b=host.querySelector('svg').getBoundingClientRect();return {x:(e.clientX-b.left)/b.width*720,y:(e.clientY-b.top)/b.height*440};}
 host.addEventListener('wheel',e=>{if(!expanded())return;e.preventDefault();zoom(Math.exp(-e.deltaY*.001),point(e));},{passive:false});
 host.addEventListener('pointerdown',e=>{
  const el=e.target.closest('[data-network-node]'),node=el&&nodes.find(n=>n.id===el.dataset.networkNode);if(node)describe(node);if(!expanded())return;
  const p=point(e);drag={node,start:p,last:p,camera:{...camera},pan:e.shiftKey||e.button===2};host.setPointerCapture(e.pointerId);
 });
 host.addEventListener('pointermove',e=>{if(!drag)return;const p=point(e),dx=(p.x-drag.last.x)/camera.k,dy=(p.y-drag.last.y)/camera.k;
  if(drag.node){
   const n=drag.node,scale=model.project(n,camera,dimension).scale,xx=dx/scale,yy=dy/scale;
   if(dimension===3){n.x+=xx*Math.cos(camera.yaw)+yy*Math.sin(camera.pitch)*Math.sin(camera.yaw);n.y+=yy*Math.cos(camera.pitch);n.z+=xx*Math.sin(camera.yaw)-yy*Math.sin(camera.pitch)*Math.cos(camera.yaw);}else{n.x+=xx;n.y+=yy;}
  }else if(dimension===3&&!drag.pan){camera.yaw=drag.camera.yaw+(p.x-drag.start.x)*.008;camera.pitch=Math.max(-1.4,Math.min(1.4,drag.camera.pitch+(p.y-drag.start.y)*.008));}
  else{camera.x=drag.camera.x+p.x-drag.start.x;camera.y=drag.camera.y+p.y-drag.start.y;}
  drag.last=p;draw();
 });
 for(const event of ['pointerup','pointercancel','lostpointercapture'])host.addEventListener(event,()=>{drag=null;});
 host.addEventListener('contextmenu',e=>{if(expanded())e.preventDefault();});
 host.addEventListener('keydown',e=>{if(['+','=','-'].includes(e.key)){e.preventDefault();e.stopPropagation();zoom(e.key==='-'?.8:1.25);}if(dimension===3&&['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();e.stopPropagation();camera.yaw+=e.key==='ArrowLeft'?-.15:e.key==='ArrowRight'?.15:0;camera.pitch+=e.key==='ArrowUp'?-.15:e.key==='ArrowDown'?.15:0;draw();}});
 for(const id of ['network-category','network-mode','network-threshold','network-dimension','network-scope','network-detail-level'])$(id).addEventListener('change',rebuild);
 $('network-labels').addEventListener('change',draw);$('network-zoom-in').addEventListener('click',()=>zoom(1.25));$('network-zoom-out').addEventListener('click',()=>zoom(.8));
 $('network-reset').addEventListener('click',()=>{camera={k:1,x:0,y:0,yaw:0,pitch:0};rebuild();});
 root.fetch('assets/real-network.json').then(r=>{if(!r.ok)throw Error('Network unavailable');return r.json();}).then(value=>{
  if(value.kind!=='complete_real_profile_tag_census'||value.sampled!==false||value.groups.reduce((s,n)=>s+n.profiles,0)!==value.profiles)throw Error('Invalid real census');
  data=value;$('network-category').innerHTML='<option value="">全部类别</option>'+data.categories.map(c=>`<option value="${esc(c.id)}">${esc(c.label)}</option>`).join('');
  $('network-legend').innerHTML=data.categories.map(c=>`<span><i style="background:${c.color}"></i>${esc(c.label)}</span>`).join('');
  $('network-total').textContent='全量 · '+fmt(data.profiles)+' 个画像';rebuild();
 }).catch(()=>{$('network-detail').textContent='真实网络数据暂不可用，请刷新后重试。';});
})(typeof window==='object'?window:globalThis);
