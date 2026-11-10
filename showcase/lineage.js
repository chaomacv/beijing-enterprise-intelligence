(function(root,factory){
 const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;
 if(root.document){root.BEILineage=api;api.mount(root).catch(()=>{const e=root.document.getElementById('lineage-info');if(e)e.textContent='数据去向暂时不可用，可查看下方固定汇总及来源文件。';});}
})(typeof window==='object'?window:globalThis,function(){
 'use strict';
 const fmt=n=>n.toLocaleString('en-US'),esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function validate(data){
  if(data.kind!=='completed_batch_lineage'||data.stages.length!==9||data.flow_points.length!==7||data.flow_axis!=='processing_stage_order_not_elapsed_time'||data.progress.series_kind!=='observed_processing_snapshots_not_business_events')throw Error('Invalid lineage');
  for(const value of Object.values(data.counts))if(!Number.isSafeInteger(value)||value<0)throw Error('Invalid count');
  for(const e of data.equations)if(data.counts[e.total]!==e.parts.reduce((n,k)=>n+data.counts[k],0))throw Error('Conservation failed');
  if(Object.values(data.outcomes).reduce((a,b)=>a+b,0)!==data.counts.retained)throw Error('Outcome mismatch');
  if(data.progress.total!==data.counts.representatives)throw Error('Progress denominator mismatch');
  for(const p of data.flow_points)if(p.count<=0||p.count!==data.counts[p.count_key]||p.step<0||p.step>8||p.at!==undefined)throw Error('Point mismatch');
  let at=-Infinity,completed=-1;
  for(const p of data.progress.points){const time=Date.parse(p.at);if(!Number.isFinite(time)||time<=at||!Number.isSafeInteger(p.completed)||p.completed<completed||p.completed>data.progress.total)throw Error('Invalid observation');at=time;completed=p.completed;}
  if(completed!==data.progress.total)throw Error('Incomplete progress');return data;
 }
 function series(data,mode){
  if(mode==='flow')return data.flow_points;
  if(mode!=='time')throw Error('Invalid view');
  return data.progress.points.map((p,i)=>({id:'observed-'+i,name:'内容代表推理进度',count:p.completed,at:p.at,unit:'个已完成内容代表',step:5,details:[
   `观测时已完成 ${fmt(p.completed)} / ${fmt(data.progress.total)} 个代表，剩余 ${fmt(data.progress.total-p.completed)} 个。`,
   i===data.progress.points.length-1?'本点来自最终验收汇总，说明当时已全部完成，不是精确推理结束时刻。':'这里只计内容代表的处理进度；其后仍需逐来源回填与覆盖对账。'
  ]}));
 }
 function positions(data,mode,log){
  const points=series(data,mode),left=66,right=695,top=26,bottom=251;
  const start=mode==='time'?Date.parse(points[0].at):0,end=mode==='time'?Date.parse(points.at(-1).at):points.length-1;
  const max=mode==='time'?400000:50000000;
  const y=n=>log&&mode==='flow'?bottom-(Math.log10(n)-5)/3*(bottom-top):bottom-n/max*(bottom-top);
  return {points:points.map((p,i)=>({...p,x:left+((mode==='time'?Date.parse(p.at):i)-start)/(end-start)*(right-left),y:y(p.count)})),y};
 }
 async function mount(win){
  const doc=win.document,$=id=>doc.getElementById(id),host=$('gallery-timeline-chart');if(!host)return;
  const response=await win.fetch('assets/data-lineage.json');if(!response.ok)throw Error('Lineage unavailable');const data=validate(await response.json());
  const date=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
  const compact=n=>n>=100000000?'1亿':n>=10000?(n/10000).toFixed(n%10000?1:0)+'万':fmt(n);
  const tooltip=doc.createElement('div');tooltip.className='lineage-tooltip';tooltip.hidden=true;
  let mode='flow',index=3,points=[];
  function tooltipPosition(e){const box=host.getBoundingClientRect();tooltip.style.left=Math.max(4,Math.min(e.clientX-box.left+12,box.width-tooltip.offsetWidth-4))+'px';tooltip.style.top=Math.max(4,Math.min(e.clientY-box.top+12,box.height-tooltip.offsetHeight-4))+'px';}
  function inspect(next,event){
   index=next;const p=points[index];$('lineage-count').textContent=fmt(p.count);$('lineage-unit').textContent=p.name+' · '+p.unit;
   $('lineage-at').textContent=mode==='time'?date.format(new Date(p.at))+'（北京时间 · 实际观测）':`处理阶段 ${index+1} / ${points.length} · ${String(p.step+1).padStart(2,'0')} ${data.stages[p.step].title}`;
   $('lineage-info').innerHTML=p.details.map(s=>'<p>'+esc(s)+'</p>').join('');
   $('lineage-scrub').value=index;$('lineage-index').value=`${index+1} / ${points.length}`;
   host.dataset.selectedCount=p.count;host.dataset.selectedId=p.id;
   host.querySelectorAll('[data-lineage-point]').forEach((g,i)=>{g.setAttribute('aria-pressed',String(i===index));g.querySelector('.lineage-dot').setAttribute('r',i===index?6:4);});
   if(event?.type==='pointerenter'&&event.pointerType!=='touch'){
    tooltip.innerHTML=`<strong>${esc(p.name)}</strong><b>${fmt(p.count)} <small>${esc(p.unit)}</small></b>${p.at?'<time>'+esc(date.format(new Date(p.at)))+'（北京时间）</time>':''}<p>${esc(p.details.join(' '))}</p>`;tooltip.hidden=false;tooltipPosition(event);
   }
  }
  function render(){
   const log=$('lineage-scale').value==='log',layout=positions(data,mode,log);points=layout.points;tooltip.hidden=true;let body='';
   const ticks=mode==='time'?[0,100000,200000,300000,400000]:log?[100000,1000000,10000000,100000000]:[0,10000000,20000000,30000000,40000000,50000000];
   body+=`<text x="6" y="12" class="svg-tick">${mode==='time'?'已完成代表（个）':log?'节点数量（对数刻度）':'节点数量（线性刻度）'}</text>`;
   for(const tick of ticks){const yy=layout.y(tick);body+=`<path d="M66 ${yy}H695" stroke="#e9edf3"/><text x="56" y="${yy+4}" text-anchor="end" class="svg-tick">${compact(tick)}</text>`;}
   body+=`<path d="${points.map((p,i)=>(i?'L':'M')+p.x+' '+p.y).join(' ')}" stroke="#4269d0" stroke-width="2.3" fill="none"/>`;
   points.forEach((p,i)=>{
    body+=`<g class="lineage-point" data-lineage-point="${i}" tabindex="0" role="button" aria-label="${esc(p.name+'，'+fmt(p.count)+p.unit)}"><circle cx="${p.x}" cy="${p.y}" r="13" fill="transparent"/><circle class="lineage-dot" cx="${p.x}" cy="${p.y}" r="4" fill="#4269d0" stroke="#fff" stroke-width="1.5"/><title>${esc(p.name+'：'+fmt(p.count)+p.unit+'。'+p.details.join(' '))}</title></g>`;
    if(mode==='flow')body+=`<text x="${p.x}" y="${p.y-13}" text-anchor="${i===0?'start':i===points.length-1?'end':'middle'}" class="svg-tick">${compact(p.count)}</text><text x="${p.x}" y="276" text-anchor="${i===0?'start':i===points.length-1?'end':'middle'}" class="svg-tick">${i+1} ${esc(p.name)}</text>`;
   });
   if(mode==='time')for(const i of [0,Math.floor(points.length/2),points.length-1])body+=`<text x="${points[i].x}" y="276" text-anchor="${i===0?'start':i===points.length-1?'end':'middle'}" class="svg-tick">${esc(date.format(new Date(points[i].at)))}</text>`;
   host.innerHTML=`<svg viewBox="0 0 720 305" role="group" aria-label="${mode==='flow'?'按处理阶段展示记录分流、内容代表、回填和最终覆盖对账':'按实际时间展示内容代表处理进度'}">${body}</svg>`;host.append(tooltip);
   host.querySelectorAll('[data-lineage-point]').forEach((g,i)=>{
    g.addEventListener('pointerenter',e=>inspect(i,e));g.addEventListener('pointermove',e=>{if(!tooltip.hidden)tooltipPosition(e);});g.addEventListener('pointerleave',()=>{tooltip.hidden=true;});
    g.addEventListener('click',()=>inspect(i));g.addEventListener('focus',()=>inspect(i));
    g.addEventListener('keydown',e=>{let next;if(e.key==='ArrowRight')next=(i+1)%points.length;if(e.key==='ArrowLeft')next=(i+points.length-1)%points.length;if(e.key==='Home')next=0;if(e.key==='End')next=points.length-1;if(next!==undefined){e.preventDefault();e.stopPropagation();host.querySelector(`[data-lineage-point="${next}"]`).focus();}});
   });
   $('lineage-scrub').max=points.length-1;$('lineage-scale-label').hidden=mode==='time';
   $('lineage-axis-note').textContent=mode==='flow'?'横轴为处理阶段顺序；各点是当前通道的工作量，回填与合并后恢复来源粒度。':'横轴为真实观测时间；折线连接观测点，不补造中间测量。末点来自最终验收汇总。';
   doc.querySelectorAll('[data-lineage-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.lineageMode===mode)));
   host.dataset.mode=mode;host.dataset.pointCount=points.length;inspect(Math.min(index,points.length-1));host.dataset.ready='true';
  }
  doc.querySelectorAll('[data-lineage-mode]').forEach(b=>b.addEventListener('click',()=>{mode=b.dataset.lineageMode;index=mode==='flow'?3:data.progress.points.length-1;render();}));
  $('lineage-scale').addEventListener('change',render);$('lineage-scrub').addEventListener('input',e=>inspect(Number(e.target.value)));
  $('lineage-equations').innerHTML=data.equations.map(e=>`<div><b>${esc(e.total==='known'?'全批去向':e.total==='retained'?'处理分流':'精确复用')}</b><span>${fmt(data.counts[e.total])} = ${e.parts.map(k=>fmt(data.counts[k])).join(' + ')}</span></div>`).join('');
  render();
 }
 return {validate,series,positions,mount};
});
