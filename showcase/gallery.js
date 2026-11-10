(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root.document) api.mount(root).catch(error => {
    const message = root.document.getElementById('gallery-announcement');
    if (message) message.textContent = '图表汇总暂时无法读取，可通过汇总 JSON 查看数据。';
    root.console.warn('Notebook gallery unavailable:', error.name);
  });
})(typeof window === 'object' ? window : globalThis, function () {
  'use strict';
  const colors = ['#4269d0', '#efb118', '#ff725c', '#6cc5b0', '#a463f2', '#ff8ab7', '#97bbf5', '#b59a6b', '#60a8a4', '#b5c456', '#9194a5'];
  const eventStates = {confirmed: '来源标为 confirmed', proposed: '拟议', unknown: '阶段未明', removed: '已移出', revoked: '已撤销'};
  const number = n => n.toLocaleString('en-US');
  const percent = (part, total) => (part / total * 100).toFixed(1) + '%';
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const text = (x,y,s,attrs='') => `<text x="${x}" y="${y}" ${attrs}>${esc(s)}</text>`;
  const svg = (body, label, width=720, height=340) => `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(label)}"><title>${esc(label)}</title>${body}</svg>`;

  function eventGroups(rows, state='all') {
    const groups = new Map();
    for (const r of rows) {
      if (!groups.has(r.type)) groups.set(r.type, {type:r.type, label:r.label, count:0});
      if (state === 'all' || r.status === state) groups.get(r.type).count += r.count;
    }
    return [...groups.values()].sort((a,b) => b.count - a.count || a.type.localeCompare(b.type));
  }
  function eventView(data, state='all', scope='refined', metric='events') {
    const categories=new Set(data.taxonomy.refined_types);
    const groups=eventGroups(data.events,state).filter(r=>scope==='all' || categories.has(r.type));
    if(metric==='profiles') {
      const counts=new Map(state==='all' ? data.taxonomy.category_profiles.map(r=>[r.type,r.count]) :
        data.events.filter(r=>r.status===state).map(r=>[r.type,r.associated_profiles]));
      groups.forEach(r=>{r.count=counts.get(r.type)||0;});
    }
    return groups.sort((a,b)=>b.count-a.count||a.type.localeCompare(b.type));
  }
  function autoplayStep(elapsed, delta, duration, paused) {
    if (duration <= 0 || delta < 0 || elapsed < 0) throw new RangeError('Invalid timer');
    const next = elapsed + (paused ? 0 : delta);
    return {advance:next>=duration, elapsed:next>=duration ? next%duration : next};
  }
  function loopOrder(order, target) {
    const position=order.indexOf(target);
    if(position<0 || new Set(order).size!==order.length)throw new RangeError('Invalid circular order');
    const shift=position-Math.floor(order.length/2), pivot=(shift+order.length)%order.length;
    return {shift, order:order.slice(pivot).concat(order.slice(0,pivot))};
  }
  async function mount(win) {
    const doc=win.document, $=id=>doc.getElementById(id);
    const response=await win.fetch('assets/gallery-data.json');
    if (!response.ok) throw new Error('AggregateFetchFailed');
    const data=await response.json();
    if (data.kind!=='aggregate_notebook_gallery' || data.final_pipeline_complete!==true || data.subset.partial_only!==false) throw new Error('AggregateScopeMismatch');
    doc.querySelectorAll('.gallery-code code').forEach(block=>{
      block.innerHTML=block.textContent.split('\n').map(line=>line.trimStart().startsWith('#')?`<span class="syntax-comment">${esc(line)}</span>`:esc(line).replace(/\b(SELECT|FROM|GROUP BY|AS|if|elif|else|for|in)\b/g,'<span class="syntax-keyword">$1</span>')).join('\n');
    });

    function renderEvents() {
      const state=$('gallery-event-stage').value, log=$('gallery-event-log').checked;
      const scope=$('gallery-event-scope').value, metric=$('gallery-event-metric').value;
      const rows=eventView(data,state,scope,metric), total=rows.reduce((n,r)=>n+r.count,0), max=Math.max(1,...rows.map(r=>r.count));
      const height=Math.max(340,rows.length*29+65), floor=height-48;
      const width=Math.max(420,Math.min(720,$('gallery-event-chart').clientWidth)), left=120, plot=width-left-94, ticks=width<500?2:4;
      let body='';const scale=n=>(log?Math.log10(1+n)/Math.log10(1+max):n/max)*plot;
      for(let i=0;i<=ticks;i++) {
        const value=log?Math.round(Math.pow(1+max,i/ticks)-1):Math.round(max*i/ticks), x=left+i/ticks*plot;
        const label=width<500&&value>=10000?(value/10000).toFixed(1)+'万':number(value);
        body+=`<path d="M${x} 20V${floor}" stroke="#eceff3"/>`+text(x,floor+22,label,'text-anchor="middle" class="svg-tick"');
      }
      rows.forEach((row,i)=>{
        const y=27+i*29;
        body+=text(left-13,y+14,row.label,'text-anchor="end" class="svg-label"')+`<rect x="${left}" y="${y}" width="${scale(row.count)}" height="19" fill="${colors[i%colors.length]}"><title>${esc(row.label)}：${number(row.count)}</title></rect>`+text(left+plot+12,y+14,number(row.count),'class="svg-tick"');
      });
      $('gallery-event-chart').innerHTML=svg(body,`${scope==='refined'?'原许可相关记录细分':'全部细分事件'}，${metric==='profiles'?'关联画像数':'事件观察数'}，${state==='all'?'全部阶段':eventStates[state]}，横轴${log?'为 log10(1+数量)':'为实际数量'}`,width,height);
      $('gallery-event-table').innerHTML=rows.map(r=>`<tr><td>${esc(r.label)}</td><td>${number(r.count)}</td><td>${esc(state==='all'?'全部':eventStates[state])}</td></tr>`).join('');
      $('gallery-event-count-label').textContent=metric==='profiles'?'关联画像数':'事件观察数';
      $('gallery-event-insight').textContent=metric==='profiles'?'各类别、阶段的关联画像可能重叠，不能相加为企业总数；画像仍包含临时身份。':
        total?`${rows[0].label}占当前选择的 ${percent(rows[0].count,total)} · 共 ${number(total)} 条事件观察。记录数不能解释为独立证照数。`:'这一阶段没有观察条目。';
    }
    for(const id of ['gallery-event-stage','gallery-event-log','gallery-event-scope','gallery-event-metric'])$(id).addEventListener('change',renderEvents);
    $('gallery-taxonomy-total').textContent=number(data.taxonomy.legacy_qualification_events);
    $('gallery-taxonomy-downgraded').textContent=number(data.taxonomy.downgraded_confirmed);
    renderEvents();

    const dedup=data.dedup, ratio=dedup.representative_records/dedup.source_records;
    const uniqueHeight=200*ratio, duplicateHeight=200-uniqueHeight;
    $('gallery-dedup-chart').innerHTML=svg(
      text(40,28,'待语义记录','class="svg-muted"')+text(40,66,number(dedup.source_records),'class="svg-stat"')+
      `<path d="M60 100C280 100 390 60 590 60L590 ${60+uniqueHeight}C390 ${60+uniqueHeight} 280 ${100+uniqueHeight} 60 ${100+uniqueHeight}Z" fill="#4269d0" opacity=".78"/>`+
      `<path d="M60 ${100+uniqueHeight}C280 ${100+uniqueHeight} 390 160 590 160L590 ${160+duplicateHeight}C390 ${160+duplicateHeight} 280 300 60 300Z" fill="#bdd0f5"/>`+
      `<rect x="40" y="100" width="20" height="200" fill="#18233a"/><rect x="590" y="60" width="13" height="${uniqueHeight}" fill="#4269d0"/><rect x="590" y="160" width="13" height="${duplicateHeight}" fill="#a4bbe9"/>`+
      text(350,47,number(dedup.representative_records),'class="svg-stat"')+text(350,127,'不同内容代表 · '+percent(ratio,1),'class="svg-muted"')+
      text(350,284,number(dedup.exact_duplicate_source_records),'class="svg-stat"')+text(350,329,'重复来源 · 保留全部原始位置','class="svg-muted"'),
      '来源记录精确分组：不同内容代表与重复来源，端点高度按记录比例绘制');

    // A real clock drives the pager. Reading, hidden tabs and reduced motion pause it.
    const viewport=$('gallery-viewport'), track=viewport.querySelector('.carousel-track');
    const cards=[...doc.querySelectorAll('[data-notebook]')], pages=[...doc.querySelectorAll('[data-gallery-page]')];
    const reduced=win.matchMedia('(prefers-reduced-motion: reduce)');
    const reader=$('notebook-reader');
    const initialIndex=win.matchMedia('(min-width: 1101px)').matches?1:0;
    let index=initialIndex, playing=!reduced.matches, hover=false, focused=false, dragging=false, visible=true, elapsed=0, last=0, settle, reading=null;
    function updateControls(manual=false) {
      pages.forEach((b,i)=>b.setAttribute('aria-pressed',String(i===index)));
      cards.forEach((c,i)=>c.dataset.active=String(i===index));
      $('gallery-play').innerHTML=playing?'<svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"><path d="M7 5v10M13 5v10" stroke="currentColor" stroke-width="2"/></svg>':'<svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"><path d="M6 4l10 6-10 6Z" fill="currentColor"/></svg>';$('gallery-play').setAttribute('aria-pressed',String(playing));
      $('gallery-play').setAttribute('aria-label',playing?'暂停自动轮播':'播放自动轮播');
      if(manual)$('gallery-announcement').textContent=`第 ${index+1} / ${cards.length} 个笔记本：${cards[index].querySelector('h3').textContent}`;
    }
    function recenter() {
      if(reading)return;
      const order=[...track.children].map(c=>Number(c.dataset.notebook)), plan=loopOrder(order,index);
      if(!plan.shift)return;
      const before=cards[index].offsetLeft, scroll=viewport.scrollLeft;
      viewport.style.scrollSnapType='none';
      if(plan.shift>0)for(let i=0;i<plan.shift;i++)track.append(track.firstElementChild);
      if(plan.shift<0)for(let i=0;i>plan.shift;i--)track.prepend(track.lastElementChild);
      viewport.scrollTo({left:scroll+cards[index].offsetLeft-before,behavior:'auto'});
      win.requestAnimationFrame(()=>{viewport.style.scrollSnapType='';});
    }
    function select(next,manual=true,smooth=true) {
      if(reading)return;
      const previous=index;index=(next+cards.length)%cards.length;elapsed=0;updateControls(manual);
      const distance=(index-previous+cards.length)%cards.length;
      const adjacent=distance===1 || distance===cards.length-1;
      if(!smooth || !adjacent || reduced.matches)recenter();
      const left=cards[index].offsetLeft-(viewport.clientWidth-cards[index].offsetWidth)/2;
      viewport.scrollTo({left,behavior:smooth&&adjacent&&!reduced.matches?'smooth':'auto'});
    }
    cards.forEach((card,i)=>{
      const button=doc.createElement('button');button.type='button';button.className='notebook-reader-open';
      button.innerHTML='<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false"><path d="M15 4h5v5M9 20H4v-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';button.setAttribute('aria-label','展开阅读：'+card.querySelector('h3').textContent);
      card.append(button);
      button.addEventListener('click',()=>{
        select(i,false,false);
        const slot=doc.createElement('div');slot.className='notebook-slot';slot.setAttribute('aria-hidden','true');
        card.replaceWith(slot);reading={card,slot,button};$('notebook-reader-body').append(card);
        $('notebook-reader-title').textContent=card.querySelector('h3').textContent;
        reader.showModal();
        if(card.dataset.cardKey==='hierarchy')card.querySelector('.notebook-page').scrollTop=0;
        renderEvents();$('notebook-reader-close').focus();
      });
    });
    $('notebook-reader-close').addEventListener('click',()=>reader.close());
    reader.addEventListener('close',()=>{
      if(!reading)return;
      const current=reading;current.slot.replaceWith(current.card);reading=null;
      select(index,false,false);renderEvents();current.button.focus({preventScroll:true});
    });
    $('gallery-prev').addEventListener('click',()=>select(index-1));$('gallery-next').addEventListener('click',()=>select(index+1));
    pages.forEach((button,i)=>button.addEventListener('click',()=>select(i)));
    $('gallery-play').addEventListener('click',()=>{playing=!playing;last=0;updateControls();});
    viewport.addEventListener('pointerenter',e=>{if(e.pointerType==='mouse')hover=true;});viewport.addEventListener('pointerleave',()=>{hover=false;});
    viewport.addEventListener('pointerdown',()=>{dragging=true;});
    for(const type of ['pointerup','pointercancel'])win.addEventListener(type,()=>{if(dragging){dragging=false;elapsed=0;}});
    viewport.addEventListener('focusin',()=>{focused=true;});viewport.addEventListener('focusout',()=>{focused=viewport.contains(doc.activeElement);});
    viewport.addEventListener('keydown',event=>{
      if(event.target.closest('input,select,button,a'))return;
      if(event.key==='ArrowRight'){event.preventDefault();select(index+1);}
      if(event.key==='ArrowLeft'){event.preventDefault();select(index-1);}
      if(event.key==='Home'){event.preventDefault();select(0);}
      if(event.key==='End'){event.preventDefault();select(cards.length-1);}
    });
    viewport.addEventListener('scroll',()=>{if(reading)return;win.clearTimeout(settle);settle=win.setTimeout(()=>{
      if(reading)return;
      const center=viewport.scrollLeft+viewport.clientWidth/2;
      const nearest=cards.reduce((best,c,i)=>Math.abs(c.offsetLeft+c.offsetWidth/2-center)<Math.abs(cards[best].offsetLeft+cards[best].offsetWidth/2-center)?i:best,0);
      if(nearest!==index){index=nearest;elapsed=0;updateControls(false);}
      recenter();
    },180);},{passive:true});
    if(win.IntersectionObserver)new win.IntersectionObserver(entries=>{visible=entries[0].intersectionRatio>=.2;},{threshold:.2}).observe(viewport);
    reduced.addEventListener('change',e=>{if(e.matches){playing=false;updateControls();}});
    doc.addEventListener('visibilitychange',()=>{last=0;});
    let resizeTimer;win.addEventListener('resize',()=>{win.clearTimeout(resizeTimer);resizeTimer=win.setTimeout(()=>{select(index,false,false);renderEvents();},120);});
    function tick(now) {
      const paused=!playing||hover||focused||dragging||reading||!visible||doc.hidden, dt=last?Math.min(250,now-last):0;last=now;
      const state=autoplayStep(elapsed,dt,8000,paused);elapsed=state.elapsed;
      if(state.advance)select(index+1,false,true);
      $('gallery-clock').textContent='';
      doc.querySelector('.gallery-pagination').style.setProperty('--play-progress',elapsed/8000);
      win.requestAnimationFrame(tick);
    }
    select(initialIndex,false,false);viewport.dataset.ready='true';win.requestAnimationFrame(tick);
  }
  return {eventGroups,eventView,autoplayStep,loopOrder,mount};
});
