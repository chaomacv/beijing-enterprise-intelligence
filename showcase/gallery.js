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
  const statusLabels = {PROFILED: '已解析', CONVERTED: '已转换', REVIEW: '待复核', CONTAINER: '容器', EMPTY: '空文件', COMPONENT: '配套组件'};
  const eventStates = {confirmed: '来源标为 confirmed', proposed: '拟议', unknown: '阶段未明', removed: '已移出', revoked: '已撤销'};
  const recordColors = {EXTRACTED: '#39a98b', NO_EVENT: '#4269d0', REVIEW: '#ed9950'};
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
  function allocateSlots(rows, slots) {
    const total = rows.reduce((s,r) => s+r.count,0);
    if (!(total > 0) || !Number.isInteger(slots) || slots < 1) throw new RangeError('Invalid allocation');
    const exact = rows.map(r => r.count / total * slots), counts = exact.map(Math.floor);
    const order = exact.map((v,i) => ({i,remainder:v-counts[i]})).sort((a,b) => b.remainder-a.remainder || a.i-b.i);
    for (let i=0, remaining=slots-counts.reduce((a,b)=>a+b,0); i<remaining; i++) counts[order[i].i]++;
    return counts;
  }
  function autoplayStep(elapsed, delta, duration, paused) {
    if (duration <= 0 || delta < 0 || elapsed < 0) throw new RangeError('Invalid timer');
    const next = elapsed + (paused ? 0 : delta);
    return {advance:next>=duration, elapsed:next>=duration ? next%duration : next};
  }
  function project(x,y,z,yaw,pitch) {
    const a = x*Math.cos(yaw)-z*Math.sin(yaw), b = x*Math.sin(yaw)+z*Math.cos(yaw);
    const up = y*Math.cos(pitch)-b*Math.sin(pitch), depth = y*Math.sin(pitch)+b*Math.cos(pitch);
    return {x:360+a*150, y:186-up*116, depth};
  }
  function loopOrder(order, target) {
    const position=order.indexOf(target);
    if(position<0 || new Set(order).size!==order.length)throw new RangeError('Invalid circular order');
    const shift=position-Math.floor(order.length/2), pivot=(shift+order.length)%order.length;
    return {shift, order:order.slice(pivot).concat(order.slice(0,pivot))};
  }
  function sector(cx,cy,inner,outer,start,end) {
    const point=(r,a)=>[cx+r*Math.cos(a),cy+r*Math.sin(a)];
    const a=point(outer,start), b=point(outer,end), c=point(inner,end), d=point(inner,start), large=end-start>Math.PI?1:0;
    return `M${a}A${outer},${outer} 0 ${large} 1 ${b}L${c}A${inner},${inner} 0 ${large} 0 ${d}Z`;
  }
  async function mount(win) {
    const doc=win.document, $=id=>doc.getElementById(id);
    const response=await win.fetch('assets/gallery-data.json');
    if (!response.ok) throw new Error('AggregateFetchFailed');
    const data=await response.json();
    if (data.kind!=='aggregate_notebook_gallery' || data.final_pipeline_complete!==false) throw new Error('AggregateScopeMismatch');
    doc.querySelectorAll('.gallery-code code').forEach(block=>{
      block.innerHTML=block.textContent.split('\n').map(line=>line.trimStart().startsWith('#')?`<span class="syntax-comment">${esc(line)}</span>`:esc(line).replace(/\b(SELECT|FROM|GROUP BY|AS|if|elif|else|for|in)\b/g,'<span class="syntax-keyword">$1</span>')).join('\n');
    });

    // Hierarchy: format totals and their parser-status children share one denominator.
    const formats=new Map();
    for(const row of data.formats) {
      if(!formats.has(row.format)) formats.set(row.format,{name:row.format,count:0,children:[]});
      const f=formats.get(row.format);f.count+=row.files;f.children.push(row);
    }
    const groups=[...formats.values()].sort((a,b)=>b.count-a.count), totalFiles=groups.reduce((n,g)=>n+g.count,0);
    let angle=-Math.PI/2, rings='';
    groups.forEach((group,index)=>{
      const end=angle+group.count/totalFiles*Math.PI*2, color=colors[index%colors.length];
      rings+=`<path d="${sector(240,205,59,130,angle,end)}" fill="${color}" stroke="white" stroke-width="1.2"><title>${esc(group.name)}：${number(group.count)} 个逻辑文件</title></path>`;
      let childAngle=angle;
      group.children.forEach((child,j)=>{
        const childEnd=childAngle+child.files/totalFiles*Math.PI*2;
        rings+=`<path d="${sector(240,205,132,190,childAngle,childEnd)}" fill="${color}" opacity="${.5+j*.08}" stroke="white" stroke-width="1"><title>${esc(group.name+' / '+statusLabels[child.status])}：${number(child.files)}</title></path>`;
        childAngle=childEnd;
      });angle=end;
    });
    rings+=text(240,202,number(totalFiles),'text-anchor="middle" class="svg-big"')+text(240,225,'逻辑文件','text-anchor="middle" class="svg-muted"');
    $('gallery-sunburst').innerHTML=svg(rings,'全批逻辑文件按格式与解析状态分组的层级图',480,410);
    $('gallery-file-total').textContent=number(totalFiles);
    $('gallery-format-legend').innerHTML=groups.map((g,i)=>`<span><i style="background:${colors[i%colors.length]}"></i>${esc(g.name)}<b>${number(g.count)}</b></span>`).join('');
    $('gallery-format-detail').textContent=`${groups[0].name} 占逻辑文件的 ${percent(groups[0].count,totalFiles)}；JSONL 包含派生结果，各格式不等同于原附件数量。`;

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

    const spaceFormats=[...new Set(data.file_space.bins.map(r=>r.format))], spaceStates=[...new Set(data.file_space.bins.map(r=>r.status))];
    let yaw=-Math.PI/6, pitch=.4;
    function renderSpace() {
      let body='';const p=(x,y,z)=>project(x,y,z,yaw,pitch);
      for(const z of [-1,1])for(const x of [-1,1]) {
        const a=p(x,-1,z),b=p(x,1,z);body+=`<path d="M${a.x} ${a.y}L${b.x} ${b.y}" stroke="#dce1e9"/>`;
      }
      for(const y of [-1,1])for(const fixed of [-1,1]) {
        let a=p(-1,y,fixed),b=p(1,y,fixed);body+=`<path d="M${a.x} ${a.y}L${b.x} ${b.y}" stroke="#dce1e9"/>`;
        a=p(fixed,y,-1);b=p(fixed,y,1);body+=`<path d="M${a.x} ${a.y}L${b.x} ${b.y}" stroke="#dce1e9"/>`;
      }
      const dots=data.file_space.bins.map(row=>({...row,...p(spaceFormats.indexOf(row.format)/(spaceFormats.length-1)*2-1,row.bucket/(data.file_space.buckets.length-1)*2-1,spaceStates.indexOf(row.status)/(spaceStates.length-1)*2-1)})).sort((a,b)=>a.depth-b.depth);
      dots.forEach(row=>{
        const label=`${row.format} / ${data.file_space.buckets[row.bucket]} 条 / ${statusLabels[row.status]}：${number(row.files)} 个文件`;
        body+=`<circle cx="${row.x}" cy="${row.y}" r="${Math.min(19,3+Math.sqrt(row.files)*.45)}" fill="${colors[spaceFormats.indexOf(row.format)%colors.length]}" fill-opacity=".85" stroke="white" stroke-width="1.2"><title>${esc(label)}</title></circle>`;
      });
      body+=text(20,362,'X 格式分组   /   Y 已知记录规模   /   Z 解析状态','class="svg-muted"');
      $('gallery-file-space').innerHTML=svg(body,'三维文件分箱，点大小表示文件数；可用下方滑块旋转',720,380);
      $('gallery-space-angle-value').value=Math.round(yaw*180/Math.PI)+'°';
    }
    $('gallery-space-angle').addEventListener('input',e=>{yaw=Number(e.target.value)*Math.PI/180;renderSpace();});
    let drag=null;const space=$('gallery-file-space');
    space.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,yaw,pitch};space.setPointerCapture(e.pointerId);});
    space.addEventListener('pointermove',e=>{if(!drag)return;yaw=drag.yaw+(e.clientX-drag.x)*.008;pitch=Math.max(-1,Math.min(1,drag.pitch+(e.clientY-drag.y)*.006));$('gallery-space-angle').value=Math.max(-180,Math.min(180,yaw*180/Math.PI));renderSpace();});
    for(const event of ['pointerup','pointercancel','lostpointercapture'])space.addEventListener(event,()=>{drag=null;});
    renderSpace();

    const states=data.record_statuses, slots=allocateSlots(states,200), qualityTotal=states.reduce((n,r)=>n+r.count,0);
    $('gallery-review-share').textContent=percent(states.find(r=>r.status==='REVIEW').count,qualityTotal);
    $('gallery-quality-waffle').innerHTML=states.map((r,i)=>Array.from({length:slots[i]},()=>`<span style="background:${recordColors[r.status]}" title="${r.status}"></span>`).join('')).join('');
    $('gallery-quality-waffle').setAttribute('aria-label',states.map(r=>`${r.status} ${number(r.count)} 条，占 ${percent(r.count,qualityTotal)}`).join('；'));
    $('gallery-quality-legend').innerHTML=states.map(r=>`<div><i style="background:${recordColors[r.status]}"></i><span>${r.status}</span><strong>${number(r.count)}</strong><small>${percent(r.count,qualityTotal)}</small></div>`).join('');

    const ids=data.identities, identityTotal=ids.reduce((n,r)=>n+r.count,0), provisional=ids.find(r=>r.status==='provisional').count;
    let a=-Math.PI/2, donut='';
    ids.forEach((r,i)=>{const b=a+r.count/identityTotal*Math.PI*2;donut+=`<path d="${sector(130,120,67,108,a,b)}" fill="${i?'#ffb86a':'#4269d0'}" stroke="white" stroke-width="3"><title>${r.status}：${number(r.count)}</title></path>`;a=b;});
    donut+=text(130,121,number(identityTotal),'text-anchor="middle" class="svg-big"')+text(130,143,'主体画像','text-anchor="middle" class="svg-muted"');
    $('gallery-identity-chart').innerHTML=svg(donut,'主体画像身份状态：临时身份与只做代码校验位检查的身份',260,245);
    $('gallery-provisional-share').textContent=percent(provisional,identityTotal);
    $('gallery-identity-counts').innerHTML=`<span><i style="background:#4269d0"></i>临时身份 <b>${number(provisional)}</b></span><span><i style="background:#ffb86a"></i>代码校验位通过 <b>${number(identityTotal-provisional)}</b></span>`;

    const points=data.progress.points, start=Date.parse(points[0].at), span=Date.parse(points.at(-1).at)-start;
    const timeFormatter=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
    const x=p=>55+(Date.parse(p.at)-start)/span*620, y=p=>267-p.completed/data.progress.total*235;
    function renderTimeline() {
      const index=Number($('gallery-time-scrub').value), point=points[index];let body='';
      for(let i=0;i<=4;i++) {const value=data.progress.total*i/4, yy=267-i/4*235;body+=`<path d="M55 ${yy}H680" stroke="#e9edf3"/>`+text(43,yy+4,Math.round(value/1000)+'k','text-anchor="end" class="svg-tick"');}
      body+=`<path d="${points.map((p,i)=>(i?'L':'M')+x(p)+' '+y(p)).join(' ')}" stroke="#d9e0ec" stroke-width="2" fill="none"/>`;
      body+=`<path d="${points.slice(0,index+1).map((p,i)=>(i?'L':'M')+x(p)+' '+y(p)).join(' ')}" stroke="#4269d0" stroke-width="3" fill="none"/>`;
      points.forEach((p,i)=>{body+=`<circle cx="${x(p)}" cy="${y(p)}" r="${i===index?6:3.5}" fill="${i<=index?'#4269d0':'#d9e0ec'}"><title>${esc(timeFormatter.format(new Date(p.at)))}：${number(p.completed)}</title></circle>`;});
      for(const i of [0,Math.floor((points.length-1)/2),points.length-1])body+=text(x(points[i]),300,timeFormatter.format(new Date(points[i].at)),`text-anchor="${i===0?'start':i===points.length-1?'end':'middle'}" class="svg-tick"`);
      $('gallery-timeline-chart').innerHTML=svg(body,'实际模型内容代表处理进度，横轴为北京时间，按真实时间间隔绘制',720,325);
      $('gallery-time-count').textContent=number(point.completed);$('gallery-time-percent').textContent=percent(point.completed,data.progress.total)+' 个内容代表已处理';
      $('gallery-time-at').textContent=timeFormatter.format(new Date(point.at))+'（北京时间）';$('gallery-time-at').dateTime=point.at;$('gallery-time-index').value=`${index+1} / ${points.length}`;
    }
    $('gallery-time-scrub').max=points.length-1;$('gallery-time-scrub').value=points.length-1;$('gallery-time-scrub').addEventListener('input',renderTimeline);renderTimeline();

    // A real clock drives the pager. Reading, hidden tabs and reduced motion pause it.
    const viewport=$('gallery-viewport'), track=viewport.querySelector('.carousel-track');
    const cards=[...doc.querySelectorAll('[data-notebook]')], pages=[...doc.querySelectorAll('[data-gallery-page]')];
    const reduced=win.matchMedia('(prefers-reduced-motion: reduce)');
    const reader=$('notebook-reader');
    let index=1, playing=!reduced.matches, hover=false, focused=false, dragging=false, visible=true, elapsed=0, last=0, settle, reading=null;
    function updateControls(manual=false) {
      pages.forEach((b,i)=>b.setAttribute('aria-pressed',String(i===index)));
      cards.forEach((c,i)=>c.dataset.active=String(i===index));
      $('gallery-play').textContent=playing?'暂停':'播放';$('gallery-play').setAttribute('aria-pressed',String(playing));
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
        reader.showModal();renderEvents();$('notebook-reader-close').focus();
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
      $('gallery-clock').textContent=!playing?'已暂停':paused?'阅读时暂停':Math.ceil((8000-elapsed)/1000)+'s / 每张';
      doc.querySelector('.gallery-pagination').style.setProperty('--play-progress',elapsed/8000);
      win.requestAnimationFrame(tick);
    }
    select(1,false,false);viewport.dataset.ready='true';win.requestAnimationFrame(tick);
  }
  return {eventGroups,eventView,allocateSlots,autoplayStep,project,loopOrder,mount};
});
