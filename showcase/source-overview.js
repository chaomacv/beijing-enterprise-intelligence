(function(root,factory){
 const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;
 if(root.document)api.mount(root).catch(()=>{const host=root.document.getElementById('source-status');if(host)host.textContent='来源目录暂时无法读取，请刷新或查看目录汇总。';});
})(typeof window==='object'?window:globalThis,function(){
 'use strict';
 const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const fmt=n=>n.toLocaleString('en-US');
 function validate(data){
  if(data.kind!=='public_catalog_overview'||data.sample_limit!==10||data.themes.length!==20)throw Error('Invalid catalog');
  const names=new Set();let total=0;
  for(const theme of data.themes){
   if(names.has(theme.name)||!Number.isSafeInteger(theme.count)||theme.count<1||theme.samples.length!==Math.min(10,theme.count))throw Error('Invalid theme');
   names.add(theme.name);total+=theme.count;
   if(new Set(theme.samples.map(s=>s.url)).size!==theme.samples.length)throw Error('Duplicate sample');
   for(const source of theme.samples){const url=new URL(source.url);if(url.origin!=='https://data.beijing.gov.cn'||!url.pathname.startsWith('/zyml/')||url.search||url.hash)throw Error('Invalid source page');}
  }
  if(total!==data.dataset_count)throw Error('Catalog total mismatch');return data;
 }
 async function mount(win){
  const doc=win.document,$=id=>doc.getElementById(id),host=$('source-chart');if(!host)return;
  const response=await win.fetch('assets/source-overview.json');if(!response.ok)throw Error('Catalog unavailable');
  const data=validate(await response.json()),top=26,bottom=263,left=43,width=662,step=width/data.themes.length,max=1400;
  let body='<text x="3" y="12" class="source-axis-label">↑ 数据集数</text>';
  for(let value=0;value<=max;value+=350){const y=bottom-value/max*(bottom-top);body+=`<path d="M${left} ${y}H710" stroke="#edf0f4"/><text x="${left-8}" y="${y+4}" text-anchor="end" class="source-tick">${fmt(value)}</text>`;}
  data.themes.forEach((theme,index)=>{
   const x=left+index*step+3,h=theme.count/max*(bottom-top),y=bottom-h;
   body+=`<g data-source-bar="${index}" role="button" tabindex="0" aria-label="${esc(theme.name)}，${fmt(theme.count)}个数据集，查看${theme.samples.length}个来源下载页"><rect class="source-column" x="${x}" y="${y}" width="${step-6}" height="${h}"/><rect x="${left+index*step}" y="${top}" width="${step}" height="${bottom-top}" fill="transparent"/><text x="${x+(step-6)/2}" y="${y-6}" text-anchor="middle" class="source-count">${theme.count}</text><text x="${x+8}" y="281" transform="rotate(55 ${x+8} 281)" class="source-category-label">${esc(theme.name)}</text><title>${esc(theme.name)}：${fmt(theme.count)}个数据集</title></g>`;
  });
  host.innerHTML=`<svg viewBox="0 0 720 390" role="group" aria-label="20个官网主题的来源数据集数量；悬停、点击或键盘选择查看来源">${body}</svg>`;
  $('source-count').textContent=fmt(data.dataset_count);$('source-attachments').textContent=fmt(data.batch.attachments);$('source-records').textContent=(data.batch.known_logical_records/10000).toFixed(0)+'万';
  $('source-theme-select').innerHTML=data.themes.map((t,i)=>`<option value="${i}">${esc(t.name)} (${fmt(t.count)})</option>`).join('');
  let current=-1;
  function select(index){
   if(index===current)return;current=index;const theme=data.themes[index];
   $('source-theme-select').value=String(index);
   host.querySelectorAll('[data-source-bar]').forEach((g,i)=>g.setAttribute('aria-pressed',String(i===index)));
   $('source-status').textContent=`${theme.name} · ${fmt(theme.count)} 个来源 · ${theme.count<=10?'全部显示':'显示 10 个目录样本'}`;
   $('source-links').innerHTML=theme.samples.map((s,i)=>`<li><span>${String(i+1).padStart(2,'0')}</span><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer"><b>${esc(s.name)}</b><small>${esc(s.url)}</small></a></li>`).join('');
  }
  for(const g of host.querySelectorAll('[data-source-bar]')){
   const index=Number(g.dataset.sourceBar);
   g.addEventListener('pointerenter',()=>select(index));g.addEventListener('focus',()=>select(index));g.addEventListener('click',()=>select(index));
   g.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();select(index);}else if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();const next=(index+(e.key==='ArrowRight'?1:-1)+data.themes.length)%data.themes.length;host.querySelector(`[data-source-bar="${next}"]`).focus();}});
  }
  $('source-theme-select').addEventListener('change',e=>select(Number(e.target.value)));
  $('source-examples').innerHTML=data.examples.map(e=>`<tr><td><a href="${esc(e.source.url)}" target="_blank" rel="noopener noreferrer" title="官网来源：${esc(e.source.name)}">${esc(e.filename)} ↗</a></td><td>${esc(e.fields)}</td><td><span class="relevance ${e.relevance==='高相关'?'high':'low'}">${esc(e.relevance)}</span></td></tr>`).join('');
  select(0);host.dataset.ready='true';
 }
 return {validate,mount};
});
