/* Zoom interaction: Mike Bostock / D3 Zoomable Sunburst, ISC.
 * https://observablehq.com/@d3/zoomable-sunburst — see vendor/D3-LICENSE.txt.
 */
(function(root,factory){
 const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;
 if(root.document)api.mount(root).catch(()=>{const e=root.document.getElementById('event-sunburst-detail');if(e)e.textContent='层级汇总暂时无法读取，请刷新后重试。';});
})(typeof window==='object'?window:globalThis,function(){
 'use strict';
 const TAU=Math.PI*2,INNER=90,OUTER=282,fmt=n=>n.toLocaleString('en-US');
 const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
 function hierarchy(data){
  const ids=new Set(),nodes=[];
  function visit(d,parent=null){
   if(!d||typeof d.id!=='string'||!d.id||ids.has(d.id)||typeof d.name!=='string')throw Error('Invalid hierarchy node');
   ids.add(d.id);const n={id:d.id,name:d.name,parent,depth:parent?parent.depth+1:0,children:[]};
   n.path=parent?[...parent.path,n.name]:[n.name];nodes.push(n);
   if(d.children!==undefined&&!Array.isArray(d.children))throw Error('Invalid children');
   n.children=(d.children||[]).map(c=>visit(c,n));n.value=n.children.length?n.children.reduce((s,c)=>s+c.value,0):d.value;
   if(!Number.isSafeInteger(n.value)||n.value<=0||(d.value!==undefined&&d.value!==n.value))throw Error('Counts do not reconcile');return n;
  }
  const tree=visit(data);
  function angles(n,a,b){n.x0=a;n.x1=b;let at=a;for(const c of n.children){const end=at+(b-a)*c.value/n.value;angles(c,at,end);at=end;}}
  angles(tree,0,TAU);return {tree,nodes};
 }
 function project(n,focus){const span=focus.x1-focus.x0;return {
  x0:clamp((n.x0-focus.x0)/span,0,1)*TAU,x1:clamp((n.x1-focus.x0)/span,0,1)*TAU,
  y0:Math.max(0,n.y0-focus.depth),y1:Math.max(0,n.y1-focus.depth)};}
 function radius(y){return Math.sqrt(INNER**2+(OUTER**2-INNER**2)*(clamp(y,1,3)-1)/2);}
 function visible(d){return d.y0>=1&&d.y1<=3&&d.x1-d.x0>1e-9;}
 function layout(nodes,focus){return nodes.filter(n=>n!==focus).map(n=>({n,p:project({...n,y0:n.depth,y1:n.depth+1},focus)})).filter(({p})=>visible(p)).map(({n,p})=>({id:n.id,a:p.x0,b:p.x1,inner:radius(p.y0),outer:radius(p.y1)}));}
 async function mount(win){
  const doc=win.document,$=id=>doc.getElementById(id),host=$('event-sunburst-chart');if(!host)return;
  const d3=win.d3;if(!d3)throw Error('D3 unavailable');
  async function json(file){const r=await win.fetch('assets/'+file);if(!r.ok)throw Error('Hierarchy unavailable');return r.json();}
  const manifest=await json('event-hierarchy.json');if(manifest.schema_version!==2||!Array.isArray(manifest.modes))throw Error('Invalid manifest');
  const cache=new Map();let sequence=0,mode,root,nodes=[],focus,filter='',svg,lookup;
  const modes=$('event-sunburst-modes');modes.innerHTML=manifest.modes.map(m=>`<button type="button" data-sun-mode="${esc(m.id)}" aria-pressed="false"><span>${esc(m.label)}</span><b>${fmt(m.total)}</b></button>`).join('');
  const tooltip=doc.createElement('div');tooltip.className='sunburst-tooltip';tooltip.hidden=true;
  const ancestors=n=>n.ancestors().reverse();
  function details(n,event){
   const share=n.parent?n.value/n.parent.value*100:100,path=ancestors(n).map(d=>d.data.name).join(' → ');
   $('event-sunburst-detail').textContent=`${n.data.name} · ${fmt(n.value)} ${mode.unit} · 占父级 ${share.toFixed(2)}% · ${path}`;
   if(event?.type==='pointerenter'&&event.pointerType!=='touch'){
    tooltip.innerHTML=`<strong>${esc(n.data.name)}</strong><b>${fmt(n.value)} <small>${esc(mode.unit)}</small></b><span>占父级 ${share.toFixed(2)}%</span><p>${esc(path)}</p>`;tooltip.hidden=false;positionTooltip(event);
   }
  }
  function positionTooltip(event){const b=host.getBoundingClientRect();tooltip.style.left=clamp(event.clientX-b.left+12,4,Math.max(4,b.width-232))+'px';tooltip.style.top=clamp(event.clientY-b.top+15,4,Math.max(4,b.height-145))+'px';}
  function major(n){while(n.parent&&n.parent!==root)n=n.parent;return n;}
  function selected(n){return !filter||major(n).data.id===filter;}
  function labelVisible(d){return visible(d)&&d.x1-d.x0>.095;}
  function labelTransform(d){const a=(d.x0+d.x1)/2*180/Math.PI,r=(radius(d.y0)+radius(d.y1))/2;return `rotate(${a-90}) translate(${r},0) rotate(${a<180?0:180})`;}
  function navigation(){
   $('event-sunburst-breadcrumb').innerHTML=ancestors(focus).map(n=>`<button type="button" data-sun-crumb="${esc(n.data.id)}">${esc(n.data.name)}</button>`).join('<span aria-hidden="true">›</span>');
   $('event-sunburst-table').innerHTML=(focus.children||[]).filter(selected).map(n=>`<tr><td><button type="button" data-sun-table="${esc(n.data.id)}">${esc(n.data.name)}${n.children?' ↗':''}</button></td><td>${fmt(n.value)}</td><td>${(n.value/focus.value*100).toFixed(2)}%</td></tr>`).join('');
   const center=svg.select('[data-sun-up]');center.attr('aria-label',focus.parent?'返回上一级':'总览，点击扇区探索');
   center.select('.sunburst-center-name').text(focus.data.name.length>9?focus.data.name.slice(0,8)+'…':focus.data.name);
   center.select('.sunburst-center-count').text(fmt(focus.value));center.select('.sunburst-center-hint').text(focus.parent?'点击中心返回':mode.unit+' · 点击扇区探索');
   center.select('title').text(focus.data.name+'：'+fmt(focus.value)+' '+mode.unit);host.dataset.focus=focus.data.id;host.dataset.focusCount=focus.value;details(focus);
  }
  function zoom(n,animate=true){
   if(!n.children){details(n);return;}
   host.closest('.notebook-page').scrollTop=0;
   svg.interrupt('zoom');focus=n;tooltip.hidden=true;for(const d of nodes)d.target=project(d,focus);
   const shown=nodes.filter(d=>d!==root&&(visible(d.current)||visible(d.target)));
   const activate=(e,d)=>{if(e.type==='keydown'&&!['Enter',' '].includes(e.key))return;if(e.type==='keydown')e.preventDefault();zoom(d);};
   const paths=svg.select('.sunburst-sectors').selectAll('path').data(shown,d=>d.data.id).join('path')
    .attr('data-sun-node',d=>d.data.id).attr('role','button').attr('aria-label',d=>`${d.data.name}，${fmt(d.value)}${mode.unit}，${d.children?'点击展开下级':'末层分类'}`)
    .attr('fill',d=>d.color).on('click',activate).on('keydown',activate).on('pointerenter',(e,d)=>details(d,e)).on('pointermove',positionTooltip).on('pointerleave',()=>{tooltip.hidden=true;}).on('focus',(e,d)=>details(d));
   paths.selectAll('title').data(d=>[d]).join('title').text(d=>ancestors(d).map(n=>n.data.name).join(' → ')+'\n'+fmt(d.value)+' '+mode.unit+'\n占父级 '+(d.value/d.parent.value*100).toFixed(2)+'%');
   const labels=svg.select('.sunburst-labels').selectAll('text').data(shown,d=>d.data.id).join('text').attr('dy','.35em').text(d=>d.data.name.length>11?d.data.name.slice(0,10)+'…':d.data.name);
   const arc=d3.arc().startAngle(d=>d.x0).endAngle(d=>d.x1).padAngle(d=>Math.min((d.x1-d.x0)/2,.004)).padRadius(180).innerRadius(d=>radius(d.y0)).outerRadius(d=>radius(d.y1));
   function paint(){paths.attr('d',d=>arc(d.current)).attr('fill-opacity',d=>visible(d.current)?(selected(d)?1:.14):0)
    .attr('pointer-events',d=>visible(d.target)?'auto':'none').attr('tabindex',d=>visible(d.target)?0:-1).attr('aria-hidden',d=>visible(d.target)?null:'true').style('cursor',d=>d.children?'pointer':'default');
    labels.attr('transform',d=>labelTransform(d.current)).attr('fill-opacity',d=>labelVisible(d.current)&&selected(d)?1:0);}
   navigation();const duration=animate&&!win.matchMedia('(prefers-reduced-motion: reduce)').matches?750:0;
   if(duration){const pairs=shown.map(d=>[d,d3.interpolate(d.current,d.target)]);svg.transition('zoom').duration(duration).tween('partition',()=>t=>{for(const [d,i] of pairs)d.current=i(t);paint();});}
   else{for(const d of nodes)d.current={...d.target};paint();}
  }
  async function setMode(id){
   const next=manifest.modes.find(m=>m.id===id);if(!next)throw Error('Unknown mode');const token=++sequence;host.setAttribute('aria-busy','true');tooltip.hidden=true;
   try{
    if(!cache.has(id))cache.set(id,await json(next.file));if(token!==sequence)return;
    const data=cache.get(id);hierarchy(data.tree);root=d3.hierarchy(data.tree).sum(d=>d.children?0:d.value).sort((a,b)=>b.value-a.value);
    if(root.value!==next.total)throw Error('Mode count mismatch');d3.partition().size([TAU,root.height+1])(root);nodes=root.descendants();mode=next;focus=root;filter='';lookup=new Map(nodes.map(d=>[d.data.id,d]));
    const colors=d3.quantize(t=>d3.interpolateRgb(d3.interpolateRainbow(t),'#fff')(.44),root.children.length+1);
    root.children.forEach((n,i)=>{for(const d of n.descendants())d.color=d3.interpolateRgb(colors[i],'#fff')(Math.min(.28,(d.depth-1)*.1));});
    for(const d of nodes)d.current={x0:d.x0,x1:d.x1,y0:d.y0,y1:d.y1};if(svg)svg.interrupt('zoom');host.replaceChildren();
    svg=d3.select(host).append('svg').attr('viewBox',[-300,-300,600,600]).attr('role','group').attr('aria-label',mode.label+'多层级旭日图');
    svg.append('g').attr('class','sunburst-sectors');svg.append('g').attr('class','sunburst-labels').attr('pointer-events','none').attr('text-anchor','middle');
    const center=svg.append('g').attr('data-sun-up','true').attr('role','button').attr('tabindex',0).on('click',()=>zoom(focus.parent||root)).on('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();zoom(focus.parent||root);}});
    center.append('circle').attr('r',INNER-1).attr('fill','#fff');center.append('title');
    center.append('text').attr('class','sunburst-center-name').attr('text-anchor','middle').attr('y',-17);
    center.append('text').attr('class','sunburst-center-count').attr('text-anchor','middle').attr('y',14);
    center.append('text').attr('class','sunburst-center-hint').attr('text-anchor','middle').attr('y',37);host.appendChild(tooltip);
    for(const b of modes.querySelectorAll('button'))b.setAttribute('aria-pressed',String(b.dataset.sunMode===id));
    $('event-sunburst-filter').innerHTML='<option value="">全部'+esc(mode.levels[0])+'</option>'+root.children.map(n=>`<option value="${esc(n.data.id)}">${esc(n.data.name)}</option>`).join('');
    $('event-sunburst-levels').textContent=mode.levels.join(' → ');$('event-sunburst-note').textContent=mode.note;$('event-sunburst-unit').textContent=mode.unit==='条'?'记录数':'文件数';
    zoom(root,false);host.dataset.mode=id;host.dataset.ready='true';
   }catch(e){if(token===sequence)$('event-sunburst-detail').textContent='该模式读取失败，请重新选择模式重试。';throw e;}
   finally{if(token===sequence)host.setAttribute('aria-busy','false');}
  }
  modes.addEventListener('click',e=>{const b=e.target.closest('[data-sun-mode]');if(b)setMode(b.dataset.sunMode).catch(()=>{});});
  $('event-sunburst-breadcrumb').addEventListener('click',e=>{const b=e.target.closest('[data-sun-crumb]');if(b)zoom(lookup.get(b.dataset.sunCrumb));});
  $('event-sunburst-table').addEventListener('click',e=>{const b=e.target.closest('[data-sun-table]');if(b)zoom(lookup.get(b.dataset.sunTable));});
  $('event-sunburst-filter').addEventListener('change',e=>{filter=e.target.value;zoom(root,false);});await setMode(manifest.default_mode);
 }
 return {hierarchy,layout,project,radius,visible,mount};
});
