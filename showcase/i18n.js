/* Local, reversible UI localization. Never changes data, identifiers or event handlers. */
(function(root,factory){
  const catalog=typeof module==='object'&&module.exports?require('./locale-en.js'):root.BEIEnglish;
  const api=factory(catalog);if(typeof module==='object'&&module.exports)module.exports=api;
  if(root.document)api.mount(root);
})(typeof window==='object'?window:globalThis,function(catalog){
  'use strict';
  const quote=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const keys=Object.keys(catalog).filter(s=>s.length>1).sort((a,b)=>b.length-a.length);
  const phrases=new RegExp(keys.map(quote).join('|'),'g');
  const reverse=new Map(Object.entries(catalog).map(([zh,en])=>[en,zh]));
  function translate(value){
    const source=String(value),trimmed=source.trim();
    if(catalog[trimmed])return source.replace(trimmed,catalog[trimmed]);
    const event=trimmed.match(/^(.+)占当前选择的 ([\d.]+%) · 共 ([\d,]+) 条事件观察。记录数不能解释为独立证照数。$/);
    if(event)return `${translate(event[1])}: ${event[2]} of this selection · ${event[3]} event observations. Counts are not distinct licenses.`;
    return source.replace(phrases,key=>catalog[key])
      .replace(/([\d,.]+)\s*万/g,(_,n)=>new Intl.NumberFormat('en',{notation:'compact',maximumFractionDigits:2}).format(Number(n.replace(/,/g,''))*10000))
      .replace(/(\d[\d,.]*)\s*(?:条|个|份)(?=\s|[A-Za-z])/g,'$1 ');
  }
  function mount(win){
    const doc=win.document,texts=new WeakMap(),attributes=new WeakMap(),pending=new Set();
    const skip='script,style,pre,code,[data-i18n-original],.language-switch,.source-links a,.source-examples tbody td:nth-child(-n+2),.source-preview';
    let lang='zh',scheduled=false,observer;
    const attrs=['aria-label','aria-valuetext','title','placeholder','alt','content'];
    function localizeText(node){
      if(!node.parentElement||node.parentElement.closest(skip))return;
      const value=node.nodeValue;if(!value.trim())return;
      const old=texts.get(node);
      const source=old&&value===old.last?old.source:reverse.get(value.trim())||value;
      // Filenames are evidence labels. Keep their exact spelling in either language.
      const original=/\.(?:csv|xlsx?|docx?|pdf|zip|rar|rdf|jsonl?|parquet)(?:$|[\s)）])/i.test(source.trim());
      const result=lang==='en'&&!original?translate(source):source;
      if(value!==result)node.nodeValue=result;
      texts.set(node,{source,last:result});
    }
    function localizeElement(el){
      if(el.closest(skip))return;
      let known=attributes.get(el);if(!known){known=new Map();attributes.set(el,known);}
      for(const attr of attrs){
        if(attr==='content'&&el.tagName!=='META')continue;
        const value=el.getAttribute(attr);if(!value)continue;
        const old=known.get(attr),source=old&&value===old.last?old.source:reverse.get(value.trim())||value;
        const result=lang==='en'?translate(source):source;
        if(value!==result)el.setAttribute(attr,result);
        known.set(attr,{source,last:result});
      }
    }
    function walk(node){
      if(node.nodeType===3){localizeText(node);return;}
      if(node.nodeType!==1||node.matches(skip))return;
      localizeElement(node);
      const iterator=doc.createTreeWalker(node,win.NodeFilter.SHOW_ELEMENT|win.NodeFilter.SHOW_TEXT,{acceptNode:n=>n.nodeType===1&&n.matches(skip)?win.NodeFilter.FILTER_REJECT:win.NodeFilter.FILTER_ACCEPT});
      let current;while((current=iterator.nextNode())){if(current.nodeType===3)localizeText(current);else localizeElement(current);}
    }
    function observe(){observer.observe(doc.documentElement,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:attrs});}
    function flush(){
      observer.disconnect();for(const node of pending)if(node.isConnected)walk(node);
      pending.clear();scheduled=false;observe();
    }
    observer=new win.MutationObserver(changes=>{
      for(const change of changes){if(change.type==='childList')for(const node of change.addedNodes)pending.add(node);else pending.add(change.target);}
      if(pending.size&&!scheduled){scheduled=true;win.queueMicrotask(flush);}
    });
    function setLanguage(next,persist=true){
      if(next!=='zh'&&next!=='en')return;
      lang=next;observer.disconnect();pending.clear();
      doc.documentElement.lang=lang==='en'?'en':'zh-CN';
      walk(doc.documentElement);
      doc.querySelectorAll('[data-language]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.language===lang)));
      if(persist){
        try{win.localStorage.setItem('bei-language',lang);}catch{}
        const url=new URL(win.location.href);url.searchParams.set('lang',lang);win.history.replaceState(null,'',url);
      }
      doc.documentElement.dataset.localeReady=lang;
      observe();win.dispatchEvent(new win.CustomEvent('bei:languagechange',{detail:{language:lang}}));
    }
    doc.querySelectorAll('[data-language]').forEach(button=>button.addEventListener('click',()=>setLanguage(button.dataset.language)));
    let saved='zh';try{saved=win.localStorage.getItem('bei-language')||'zh';}catch{}
    const requested=new URL(win.location.href).searchParams.get('lang');
    setLanguage(['zh','en'].includes(requested)?requested:['zh','en'].includes(saved)?saved:'zh',false);
    win.BEILocale={setLanguage,get language(){return lang;},translate};
  }
  return {translate,mount};
});
