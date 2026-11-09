(function(root,factory){
  'use strict';
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root.document)api.mount(root);
})(typeof window==='object'?window:globalThis,function(){
  'use strict';
  const labels=['文件筛选','结构抽取','主体关联'];
  function pageIndex(index,total=3){return ((index%total)+total)%total;}
  function keyboardPage(index,key,total=3){
    if(key==='ArrowRight')return pageIndex(index+1,total);
    if(key==='ArrowLeft')return pageIndex(index-1,total);
    if(key==='Home')return 0;
    if(key==='End')return total-1;
    return null;
  }
  function mount(win){
    const doc=win.document,tabs=[...doc.querySelectorAll('[data-method-tab]')];
    if(!tabs.length)return;
    const panels=tabs.map(tab=>doc.getElementById(tab.getAttribute('aria-controls')));let active=0;
    function select(index,focus=false){
      active=pageIndex(index,tabs.length);
      tabs.forEach((tab,i)=>{tab.setAttribute('aria-selected',String(i===active));tab.tabIndex=i===active?0:-1;panels[i].hidden=i!==active;});
      doc.getElementById('method-page-position').textContent=`0${active+1} / 03 · ${labels[active]}`;
      if(focus)tabs[active].focus();
    }
    tabs.forEach((tab,i)=>{
      tab.addEventListener('click',()=>select(i));
      tab.addEventListener('keydown',event=>{const next=keyboardPage(active,event.key,tabs.length);if(next!==null){event.preventDefault();select(next,true);}});
    });
    doc.getElementById('method-prev').addEventListener('click',()=>select(active-1));
    doc.getElementById('method-next').addEventListener('click',()=>select(active+1));
    const sample=doc.getElementById('method-sample-preview'),selected=win.BEIModel.sampleRows(120,3,true);
    const fragment=doc.createDocumentFragment();
    for(let i=0;i<120;i++){
      const cell=doc.createElement('span');cell.className=selected.has(i)?'selected '+selected.get(i):'';
      cell.title=`合成记录 ${i+1} · ${selected.has(i)?'进入文件卡片':'原始记录继续保留'}`;fragment.append(cell);
    }
    sample.replaceChildren(fragment);select(0);doc.querySelector('.method-pager').dataset.ready='true';
  }
  return {pageIndex,keyboardPage,mount};
});
