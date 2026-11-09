(function(root,factory){
  const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;
  if(root.document)api.mount(root).catch(()=>{root.document.getElementById('event-sunburst-detail').textContent='层级汇总读取失败，请查看数据接口。';});
})(typeof window==='object'?window:globalThis,function(){
  'use strict';
  const palette=['#a997cf','#84bfba','#e8b5c8','#91b4d7','#edc88d','#a6c999','#d5b092','#a8afce','#d8c78e','#b1cdd6'];
  const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function hierarchy(data){
    const ids=new Set(),nodes=[];
    function visit(d,parent=null){
      if(!d||typeof d.id!=='string'||!d.id||ids.has(d.id)||typeof d.name!=='string')throw Error('Invalid hierarchy node');
      ids.add(d.id);const n={id:d.id,name:d.name,parent,depth:parent?parent.depth+1:0,children:[]};n.path=parent?[...parent.path,n.name]:[n.name];nodes.push(n);
      if(d.children!==undefined&&!Array.isArray(d.children))throw Error('Invalid children');
      n.children=(d.children||[]).map(c=>visit(c,n));
      n.value=n.children.length?n.children.reduce((s,c)=>s+c.value,0):d.value;
      if(!Number.isSafeInteger(n.value)||n.value<0||(d.value!==undefined&&d.value!==n.value))throw Error('Counts do not reconcile');
      n.path=parent?[...parent.path,n.name]:[n.name];
      return n;
    }
    const tree=visit(data);if(tree.value<=0)throw Error('Empty hierarchy');
    tree.children.forEach((n,i)=>{function color(c){c.color=palette[i%palette.length];c.children.forEach(color);}color(n);});
    function angles(n,start,end){n.x0=start;n.x1=end;let a=start;for(const c of n.children){const b=a+(end-start)*c.value/n.value;angles(c,a,b);a=b;}}
    angles(tree,0,Math.PI*2);return {tree,nodes};
  }
  function layout(nodes,focus){
    const descendants=nodes.filter(n=>n.depth>focus.depth&&n.depth<=focus.depth+2&&n.x0>=focus.x0-1e-10&&n.x1<=focus.x1+1e-10&&n.value>0);
    const levels=Math.max(1,...descendants.map(n=>n.depth-focus.depth));
    return descendants.map(n=>{const level=n.depth-focus.depth;return {id:n.id,
      a:(n.x0-focus.x0)/(focus.x1-focus.x0)*Math.PI*2,b:(n.x1-focus.x0)/(focus.x1-focus.x0)*Math.PI*2,
      inner:Math.sqrt(80**2+(250**2-80**2)*(level-1)/levels),outer:Math.sqrt(80**2+(250**2-80**2)*level/levels),opacity:1};});
  }
  function arc(s){
    const pt=(r,a)=>[270+r*Math.sin(a),270-r*Math.cos(a)],a=s.a,b=Math.min(s.b,a+Math.PI*2-1e-7);
    const p=pt(s.outer,a),q=pt(s.outer,b),r=pt(s.inner,b),t=pt(s.inner,a),large=+(b-a>Math.PI);
    return `M${p}A${s.outer},${s.outer} 0 ${large} 1 ${q}L${r}A${s.inner},${s.inner} 0 ${large} 0 ${t}Z`;
  }
  async function mount(win){
    const doc=win.document,$=id=>doc.getElementById(id),host=$('event-sunburst-chart');if(!host)return;
    const response=await win.fetch('assets/event-hierarchy.json');if(!response.ok)throw Error('Hierarchy unavailable');
    const data=await response.json(),{tree,nodes}=hierarchy(data.tree),lookup=new Map(nodes.map(n=>[n.id,n]));
    let focus=tree,filter='',frame=0,current=new Map();const fmt=n=>n.toLocaleString('en-US');
    $('event-sunburst-filter').innerHTML='<option value="">全部十类</option>'+tree.children.map(n=>`<option value="${esc(n.id)}">${esc(n.name)}</option>`).join('');
    function details(n){
      const parent=n.parent||n;
      $('event-sunburst-detail').textContent=`${n.name} · ${fmt(n.value)} 条 · 占父级 ${(n.value/parent.value*100).toFixed(2)}% · ${n.path.join(' → ')}${!n.children.length?' · 暂无已核实下级，未开放下钻':''}`;
    }
    function paint(shapes){
      current=new Map(shapes.map(s=>[s.id,s]));let body='';
      for(const s of shapes){
        const n=lookup.get(s.id),major=n.path[1],selected=!filter||lookup.get(filter).name===major;
        const tip=`${n.name}\n记录数量：${fmt(n.value)}\n占父级：${(n.value/n.parent.value*100).toFixed(2)}%\n${n.path.join(' → ')}`;
        body+=`<path d="${arc(s)}" fill="${n.color}" fill-opacity="${s.opacity*(selected?Math.max(.55,1-(n.depth-1)*.12):.13)}" stroke="white" stroke-width=".6" data-sun-node="${esc(n.id)}" tabindex="0" role="${n.children.length?'button':'img'}" aria-label="${esc(tip)}${n.children.length?'，点击展开':'，下级尚未开放'}"><title>${esc(tip)}</title></path>`;
        if(selected&&s.b-s.a>.13&&s.opacity>.6){const angle=(s.a+s.b)/2,r=(s.inner+s.outer)/2,x=270+r*Math.sin(angle),y=270-r*Math.cos(angle),rotation=angle*180/Math.PI-90+(angle>Math.PI?180:0);
          body+=`<text x="${x}" y="${y}" transform="rotate(${rotation} ${x} ${y})" text-anchor="middle" dominant-baseline="middle" font-size="13" fill="#354052" pointer-events="none">${esc(n.name)}</text>`;}
      }
      body+=`<g data-sun-up="true" role="button" tabindex="0" aria-label="${focus.parent?'返回上一级':'当前为根级'}"><circle cx="270" cy="270" r="79" fill="#fafbfe"/><text x="270" y="263" text-anchor="middle" font-size="23" fill="#354052">${fmt(focus.value)}</text><text x="270" y="286" text-anchor="middle" font-size="12" fill="#718096">${focus.parent?'返回上一级':'当前范围事件观察'}</text></g>`;
      host.innerHTML=`<svg viewBox="0 0 540 540" role="group" aria-label="按真实事件观察数分区的旭日图">${body}</svg>`;
    }
    function render(animate=true){
      win.cancelAnimationFrame(frame);const target=layout(nodes,focus),previous=current;
      $('event-sunburst-breadcrumb').innerHTML=focus.path.map((name,i)=>{let n=focus;while(n.depth>i)n=n.parent;return `<button type="button" data-sun-crumb="${esc(n.id)}">${esc(name)}</button>`;}).join('<span aria-hidden="true">›</span>');
      $('event-sunburst-table').innerHTML=nodes.filter(n=>n.parent===focus&&(!filter||n.path[1]===lookup.get(filter).name)).map(n=>`<tr><td>${esc(n.name)}</td><td>${fmt(n.value)}</td><td>${(n.value/focus.value*100).toFixed(2)}%</td></tr>`).join('');
      const start=win.performance.now(),duration=animate&&!win.matchMedia('(prefers-reduced-motion: reduce)').matches?550:0;
      function tick(now){const t=duration?Math.min(1,(now-start)/duration):1,e=1-(1-t)**3;
        paint(target.map(s=>{const old=previous.get(s.id)||{...s,b:s.a,opacity:0};return Object.fromEntries(Object.entries(s).map(([k,v])=>[k,typeof v==='number'?old[k]+(v-old[k])*e:v]));}));
        if(t<1)frame=win.requestAnimationFrame(tick);
      }tick(start);details(focus);
    }
    function activate(event){
      const up=event.target.closest('[data-sun-up]'),crumb=event.target.closest('[data-sun-crumb]'),sector=event.target.closest('[data-sun-node]');
      if(up){focus=focus.parent||tree;render();}
      else if(crumb){focus=lookup.get(crumb.dataset.sunCrumb);render();}
      else if(sector){const n=lookup.get(sector.dataset.sunNode);if(n.children.length){focus=n;render();}else details(n);}
    }
    host.addEventListener('click',activate);host.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate(e);}});
    for(const type of ['pointerover','focusin'])host.addEventListener(type,e=>{const p=e.target.closest('[data-sun-node]');if(p)details(lookup.get(p.dataset.sunNode));});
    $('event-sunburst-breadcrumb').addEventListener('click',activate);
    $('event-sunburst-filter').addEventListener('change',e=>{filter=e.target.value;focus=tree;render(false);});
    render(false);host.dataset.ready='true';
  }
  return {hierarchy,layout,arc,mount};
});
