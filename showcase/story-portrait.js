(function(){
 'use strict';
 const $=id=>document.getElementById(id),fmt=n=>n.toLocaleString('en-US');
 const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const stories=[
  {question:'数据如何被读取？',topic:'异构文件解析与统一表示',input:'CSV、Excel、文档与压缩成员',method:'按实际格式读取，保存完整单元格和表头语境。转换结果仍关联原附件；无法可靠解析的内容保留复核。',output:'文件卡片、完整逻辑记录与来源索引',code:'source → detect_format() → parse_records()\nrecord = {cells, sheet, row, context, source}\n# 转换和 OCR 不等于人工核验'},
  {question:'如何找到有价值的信息？',topic:'分层筛选、字段理解与事件提取',input:'文件名、表头及首中尾样本',method:'先判断文件主题，再由本地模型理解字段和条件；结构化数据复制原值，复杂记录保留全文按预算分块理解。',output:'相关文件、字段方案与有证据的事件候选',code:'card = sample(head, middle, tail, seeded_random)\nplan = local_model.map_fields(card)\nevents = apply_plan_to_complete_records(plan)'},
  {question:'如何让处理更高效？',topic:'内容去重、推理复用与批次优化',input:'完整记录与所属逻辑表语境',method:'同表内容和语境完全一致才复用推理；按实际 tokenizer 预算组成独立请求批次，保留每条原始位置。',output:'内容代表、复用关系与逐条回填结果',code:'key = hash(file, scope, complete_cells, context)\nresults = infer(unique_content, token_budget)\nrestore_every_source_position(results)'},
  {question:'如何保证结果可信？',topic:'输出约束、语义核验、质量分流与来源追溯',input:'模型候选、原始字段与稳定记录编号',method:'检查输出结构、引用是否存在、主体和阶段是否矛盾；不确定项分流复核。语义准确率仍需独立标注评测，来源可追溯并不等于理解一定正确。',output:'通过来源校验的候选、复核队列与审计信息',code:'assert schema_valid(candidate)\nassert evidence_exists_in_source(candidate)\nroute(EXTRACTED, NO_EVENT, REVIEW)\n# 独立语义评测仍待完成'},
  {question:'如何将事实变成业务价值？',topic:'企业实体关联、标签画像与相似企业分析',input:'带来源的主体提及与分类事件',method:'结合信用代码、名称和非空地址保守关联，再聚合事件标签。共享标签可用于相似画像候选；它不证明业务联系，也不自动生成信用评分。',output:'可追溯画像、相似候选与后续业务分析入口',code:'profile = resolve_identity(evidence) + event_tags\nJ(a, b) = |tags(a) ∩ tags(b)| / |tags(a) ∪ tags(b)|\n# 相似性分析示意，不是授信模型'}
 ];
 function mountStory(){
  const nav=$('story-questions');if(!nav)return;
  nav.innerHTML=stories.map((s,i)=>`<button type="button" data-story="${i}" aria-pressed="${!i}"><span>0${i+1}</span><strong>${s.question}</strong><small>${s.topic}</small></button>`).join('');
  function select(i){const s=stories[i];nav.querySelectorAll('button').forEach((b,j)=>b.setAttribute('aria-pressed',String(i===j)));
   $('story-method').innerHTML=`<p>${s.method}</p><dl><dt>输入</dt><dd>${s.input}</dd><dt>输出</dt><dd>${s.output}</dd></dl>`;
   $('story-code').textContent=s.code;
  }
  nav.addEventListener('click',e=>{const button=e.target.closest('[data-story]');if(button)select(Number(button.dataset.story));});select(0);
 }
 async function mountPortrait(){
  const host=$('portrait-summary');if(!host)return;
  const responses=await Promise.all([fetch('assets/gallery-data.json'),fetch('assets/demo.json')]);
  if(responses.some(r=>!r.ok))throw Error('Portrait sources unavailable');
  const [data,demo]=await Promise.all(responses.map(r=>r.json()));
  if(demo.provenance.kind!=='synthetic')throw Error('Synthetic provenance required');
  const provisional=data.identities.find(r=>r.status==='provisional').count,code=data.subset.profiles-provisional;
  host.innerHTML=`<div class="portrait-total"><span>真实阶段子集 · 关联画像数</span><strong>${fmt(data.subset.profiles)}</strong><small>画像包含临时身份，不能解释为独立登记企业数量</small></div><div class="portrait-metrics"><div><strong>${fmt(code)}</strong><span>代码校验位通过</span></div><div><strong>${fmt(provisional)}</strong><span>临时身份</span></div></div><div class="portrait-identity-bar" role="img" aria-label="代码校验位通过${fmt(code)}，临时身份${fmt(provisional)}"><i style="width:${code/data.subset.profiles*100}%"></i></div>`;
  const profiles=[...demo.profiles].sort((a,b)=>a.names[0].localeCompare(b.names[0],'zh-CN'));
  $('portrait-company').innerHTML=profiles.map((p,i)=>`<option value="${i}">${esc(p.names[0])}</option>`).join('');
  function render(){const p=profiles[Number($('portrait-company').value)],events=demo.events.filter(e=>e.entity_id===p.entity_id).sort((a,b)=>(a.date?.value||'').localeCompare(b.date?.value||''));
   $('portrait-name').textContent=p.names[0];$('portrait-address').textContent=p.addresses[0]||'示例未提供地址';
   $('portrait-tags').innerHTML=[...new Set(events.map(e=>e.event_type))].map(type=>`<span>${type==='innovation'?'科技认定记录':'行政处罚记录'}</span>`).join('');
   $('portrait-timeline').innerHTML=events.map((e,i)=>`<div class="portrait-event"><time>${esc(e.date?.value||'日期未知')}</time><i class="${e.event_type==='innovation'?'innovation':'penalty'}"></i><div><strong>${e.event_type==='innovation'?'科技认定记录':'行政处罚记录'}</strong><small>${e.status==='proposed'?'拟议 · proposed':'已记录 · confirmed'}</small></div><button type="button" data-portrait-evidence="${i}" aria-expanded="false">证据 ↗</button></div><div class="portrait-source" id="portrait-source-${i}" hidden></div>`).join('');
   $('portrait-timeline').querySelectorAll('button').forEach(button=>button.addEventListener('click',()=>{
    const i=Number(button.dataset.portraitEvidence),e=events[i],source=e.sources[0],record=demo.records.find(r=>r.record_id===source.record_id),panel=$('portrait-source-'+i),open=panel.hidden;
    panel.innerHTML=`<strong>${esc(record.filename)}</strong><span>工作表 ${esc(source.sheet)} · 原始行 ${source.row}</span><p>${e.evidence.map(x=>esc(x.value)).join('；')}</p><small>完整证据来自仓库合成规则示例；不代表真实企业或本地模型准确率。</small>`;panel.hidden=!open;button.setAttribute('aria-expanded',String(open));
   }));
  }
  $('portrait-company').addEventListener('change',render);render();host.dataset.ready='true';
 }
 mountStory();mountPortrait().catch(()=>{const el=$('portrait-summary');if(el)el.textContent='画像汇总暂不可用。';});
})();
