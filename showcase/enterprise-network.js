/* D3 Category10, gray links and draggable nodes, with a true 3D force layout. */
(function(root){
 'use strict';
 if(typeof module==='object'&&module.exports){module.exports=require('./network-model.js');return;}
 const model=root.NetworkModel,d3=root.d3,doc=root.document,$=id=>doc.getElementById(id),host=$('enterprise-network');if(!host)return;
 const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),fmt=n=>n.toLocaleString('en-US');
 let data,nodes=[],edges=[],worker,serial=0,dimension=2,drag=null,selected='',camera={k:1,x:0,y:0,yaw:0,pitch:0};
 const expanded=()=>!!host.closest('#notebook-reader');
 const svg=d3.select(host).append('svg').attr('viewBox','0 0 720 440').attr('role','group').attr('aria-label','100家真实企业样本网络，每个圆点对应一家企业');
 const lines=svg.append('g').attr('class','network-edges').attr('stroke','#999').attr('stroke-opacity',.5),dots=svg.append('g').attr('class','network-nodes');
 const axis=svg.append('g').attr('class','network-axis').attr('transform','translate(667 391)').attr('aria-hidden','true');
 function describe(n){
  if(!n)return;selected=n.id;
  $('network-detail').hidden=false;
  if(n.isTag){const matched=nodes.filter(c=>!c.isTag&&c.event_counts[n.category]>0);$('network-detail').innerHTML=`<strong>${esc(n.label)}</strong><span>${matched.length} 家样本企业出现此标签 · ${fmt(matched.reduce((s,c)=>s+c.event_counts[n.category],0))} 条事件观察</span>`;}
  else{
   const counts=Object.entries(n.event_counts).map(([tag,count])=>`${data.categories.find(c=>c.id===tag).label} ${fmt(count)}条`);
   $('network-detail').innerHTML=`<strong>${esc(n.label)} · 一家真实企业的匿名编号</strong><span>${n.tag_count} 类可比较标签 · ${fmt(n.event_count)} 条事件观察</span><p>${counts.map(esc).join(' · ')}</p><small>含来源中拟议或阶段未明的观察；待分类复核不参与相似度。代码仅通过校验位检查。</small>`;
  }draw();
 }
 function draw(){
  const positions=new Map(nodes.map(n=>[n.id,model.project(n,camera,dimension)]));
  lines.selectAll('line').attr('x1',e=>positions.get(e.source).x).attr('y1',e=>positions.get(e.source).y).attr('x2',e=>positions.get(e.target).x).attr('y2',e=>positions.get(e.target).y);
  dots.selectAll('g').sort((a,b)=>positions.get(b.id).z-positions.get(a.id).z)
   .attr('transform',n=>{const p=positions.get(n.id);return `translate(${p.x} ${p.y})`;})
   .attr('opacity',n=>dimension===3?Math.max(.45,Math.min(1,1-positions.get(n.id).z/600)):1)
   .select('circle').attr('r',n=>(n.id===selected?6.5:5)*Math.sqrt(positions.get(n.id).scale)).attr('stroke-width',n=>n.id===selected?2:1.2);
  dots.selectAll('text').attr('display',n=>n.isTag||n.id===selected||$('network-labels').checked?null:'none');
  dots.selectAll('g').each(function(n){const p=positions.get(n.id),t=d3.select(this).select('text');
   if(n.isTag){const center=Math.abs(p.x-(360+camera.x))<35,x=center?0:p.x>360+camera.x?10:-10;
    t.attr('text-anchor',center?'middle':x>0?'start':'end').attr('x',x).attr('y',center?(p.y>220+camera.y?16:-12):3);t.selectAll('tspan').attr('x',x);
   }else t.attr('x',9).attr('y',3).attr('text-anchor','start');
  });
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
  const companies=model.companies(data,scope,category),normalizers=model.normalizers(model.companies(data,scope)),token=++serial,mode=$('network-mode').value;
  dimension=Number($('network-dimension').value);$('network-threshold').disabled=mode!=='similarity';
  $('network-threshold-value').value=Number($('network-threshold').value).toFixed(2);
  $('network-size').textContent=`显示 ${companies.length} / ${data.sample_size} 家样本企业`;
  $('network-hint').textContent=dimension===3?'拖动空白旋转 · Shift拖动平移 · 滚轮缩放':'拖动节点或空白 · 滚轮缩放 · 悬停查看标签';
  $('network-detail').hidden=true;selected='';
  host.setAttribute('aria-busy','true');host.dataset.ready='loading';
  if(worker)worker.terminate();worker=new root.Worker('network-worker.js');
  worker.onmessage=event=>{
   if(token!==serial)return;if(event.data.error){$('network-detail').hidden=false;$('network-detail').textContent='布局计算失败，请切换模式重试。';host.setAttribute('aria-busy','false');return;}
   nodes=event.data.nodes;edges=event.data.edges;
   lines.selectAll('line').data(edges).join('line').attr('stroke-width',e=>mode==='similarity'?.6+1.6*e.similarity:.5+Math.log1p(e.event_count)/Math.log1p(normalizers.event_count))
    .selectAll('title').data(e=>[e]).join('title').text(e=>mode==='similarity'?`共同 ${e.shared_types} 类标签 · ${e.shared_events} 条可对应事件\n相似度 ${e.similarity.toFixed(3)}，目标距离 ${e.distance.toFixed(1)}`:`此企业的 ${e.event_count} 条标签事件观察`);
   const items=dots.selectAll('g').data(nodes,n=>n.id).join(enter=>{
    const g=enter.append('g').attr('tabindex',0).attr('role','button');g.append('circle');g.append('rect').attr('x',-3).attr('y',-3).attr('width',6).attr('height',6).attr('transform','rotate(45)');g.append('title');g.append('text').attr('x',8).attr('y',3);return g;
   }).attr('data-network-node',n=>n.id).attr('data-node-kind',n=>n.isTag?'tag':'company').attr('aria-label',n=>n.isTag?n.label:`${n.label}，${n.tag_count}类标签，${n.event_count}条事件观察`)
    .on('focus',(e,n)=>describe(n)).on('click',(e,n)=>describe(n));
   items.select('circle').attr('fill',n=>n.color).attr('stroke','#fff').attr('display',n=>n.isTag?'none':null);
   items.select('rect').attr('fill',n=>n.color).attr('display',n=>n.isTag?null:'none');
   items.select('title').text(n=>n.isTag?n.label:`${n.label}\n${n.tag_count} 类标签 · ${n.event_count} 条事件观察\n`+n.tags.map(t=>data.categories.find(c=>c.id===t).label).join(' · '));
   items.select('text').each(function(n){const t=d3.select(this);t.selectAll('*').remove();t.text('');
    if(n.isTag){for(const [i,part] of (n.label.match(/.{1,6}/gu)||[]).entries())t.append('tspan').attr('dy',i?11:0).text(part);}
    else t.text(n.label);
   });
   draw();host.dataset.ready='true';host.dataset.dimensions=dimension;host.dataset.companyCount=companies.length;host.setAttribute('aria-busy','false');
   $('network-edge-count').textContent=companies.length+' 家企业 · '+(mode==='similarity'?edges.length+' 条相似连线':visibleCategories.length+' 类外围标签');
   $('network-view-note').textContent=mode==='similarity'?'共同标签种类、共同事件数量越多，目标距离越短；几何位置是力布局的近似结果。':'圆点是企业，外围菱形是标签；连线只表示该企业具备此来源观察标签。';
  };
  worker.onerror=()=>{$('network-detail').hidden=false;$('network-detail').textContent='网络布局暂不可用，请刷新后重试。';host.setAttribute('aria-busy','false');};
  worker.postMessage({companies,categories:visibleCategories,mode,dimensions:dimension,threshold:Number($('network-threshold').value),normalizers});
 }
 function zoom(factor,p={x:360,y:220}){const next=Math.max(.4,Math.min(8,camera.k*factor)),r=next/camera.k;camera={...camera,k:next,x:p.x-360-(p.x-360-camera.x)*r,y:p.y-220-(p.y-220-camera.y)*r};draw();}
 function point(e){const b=host.querySelector('svg').getBoundingClientRect();return {x:(e.clientX-b.left)/b.width*720,y:(e.clientY-b.top)/b.height*440};}
 host.addEventListener('wheel',e=>{if(!expanded())return;e.preventDefault();zoom(Math.exp(-e.deltaY*.001),point(e));},{passive:false});
 host.addEventListener('pointerdown',e=>{
  const el=e.target.closest('[data-network-node]'),node=el&&nodes.find(n=>n.id===el.dataset.networkNode);if(node)describe(node);if(!expanded()||node?.isTag)return;
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
 for(const id of ['network-category','network-mode','network-threshold','network-dimension','network-scope'])$(id).addEventListener('change',rebuild);
 $('network-labels').addEventListener('change',draw);$('network-zoom-in').addEventListener('click',()=>zoom(1.25));$('network-zoom-out').addEventListener('click',()=>zoom(.8));
 $('network-reset').addEventListener('click',()=>{camera={k:1,x:0,y:0,yaw:0,pitch:0};rebuild();});
 root.fetch('assets/company-network.json').then(r=>{if(!r.ok)throw Error('Network unavailable');return r.json();}).then(value=>{
  if(value.kind!=='real_enterprise_sample'||value.one_node_per_company!==true||value.companies.length!==100||new Set(value.companies.map(c=>c.id)).size!==100)throw Error('Invalid company sample');
  data=value;$('network-category').innerHTML='<option value="">全部类别</option>'+data.categories.map(c=>`<option value="${esc(c.id)}">${esc(c.label)}</option>`).join('');
  $('network-legend').innerHTML=data.categories.map(c=>`<span><i style="background:${c.color}"></i>${esc(c.label)}</span>`).join('');
  $('network-total').textContent='100 家真实企业样本 · 已匿名';rebuild();
 }).catch(()=>{$('network-detail').hidden=false;$('network-detail').textContent='真实企业样本暂不可用，请刷新后重试。';});
})(typeof window==='object'?window:globalThis);
