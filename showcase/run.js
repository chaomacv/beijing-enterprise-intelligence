/* Public aggregate snapshot and the nine-stage source map. No business records. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const format = value => Number.isSafeInteger(value) ? value.toLocaleString('en-US') : '待验收';
  const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const definitions = [
    {title:'固定输入', input:'已下载附件与下载进度清单', method:'固定本批快照，核对内容哈希；容器成员保留原附件与原始路径关系。', output:'原件、来源台账与完整性核验', files:['01_inputs/input_ledger.json','01_inputs/snapshot_integrity.json','01_inputs/archive_members.json'], code:'bulk_inputs.py', metric:d=>[d.input.attachments,'份已接收附件']},
    {title:'解析与抽样', input:'表格、文档、压缩包、XML 与地理数据库', method:'按实际内容识别格式；读取原生文字，必要时 OCR；保留表头、位置、质量标记及首中尾样本。', output:'逻辑文件、文件卡片与解析复核项', files:['02_profiles/文件总表.csv','02_profiles/file_cards_native.jsonl','02_profiles/all_profiles_native.json'], code:'bulk_native.py', metric:d=>[d.input.scopes,'个逻辑表／文本作用域']},
    {title:'文件筛选', input:'文件名、表头、首中尾与固定种子样本', method:'本地 Qwen 判断保留、排除或复核。抽样用于文件理解，原件继续保留；漏采仍需独立抽查。', output:'逐表判断、依据与模型原回复', files:['03_screen/筛选总表.csv','03_screen/scopes/','03_screen/summary.json'], code:'bulk_screen.py', metric:d=>[d.input.scopes,'个作用域进入文件判断']},
    {title:'字段方案', input:'相关逻辑表、样本与九类事件定义', method:'模型选择主体、证据、条件及阶段，形成有限的声明式映射。程序执行映射，避免让模型反复转抄结构化原值。', output:'映射、基础信息、逐行理解、排除与复核方案', files:['04_plans/字段方案总表.csv','04_plans/scopes/','04_plans/config.json'], code:'bulk_plan.py', metric:d=>[d.plans.total,'份实际字段方案']},
    {title:'完整读取', input:'保留文件与已校验字段方案', method:'逐条保存完整单元格、稳定记录 ID 和上下文。结构化方案逐行应用，复杂内容另交模型理解。', output:'原始记录、语境、准备块与待推理任务', files:['05_records/<file_id>/rows.jsonl','05_records/<file_id>/contexts.json','05_records/<file_id>/chunks.jsonl'], code:'bulk_rows.py', metric:d=>[d.preparation.retained_records,'条保留记录有完整原值']},
    {title:'抽取与核验', input:'复杂内容代表及各自表头、语境与来源 ID', method:'完整内容精确分组后推理；按实际 tokenizer 预算拆组，再批量提交。核对主体、原文引用及记录归属，逐条回填重复来源；不确定项进入复核。', output:'逐条状态、来源引用、模型请求与原回复', files:['06_validation/内容去重总表.csv','06_validation/content_indices/','06_validation/<file_id>/record_results.jsonl'], code:'bulk_semantics.py', metric:d=>[d.semantic_work.representative_records,'个不同内容代表需语义处置']},
    {title:'身份关联', input:'已通过来源校验的主体提及', method:'优先校验信用代码，再用完整名称与非空地址保守关联。代码冲突阻止归并；近名只形成复核候选。', output:'主体、提及、匹配依据与近名候选', files:['07_entities/results.duckdb','07_entities/entity_mentions.parquet','07_entities/name_neighbors.parquet'], code:'bulk_aggregate.py', metric:d=>[d.final_counts?.entities,'个主体画像（含临时身份）']},
    {title:'结果导出', input:'主体归属、事件与全部来源提及', method:'将画像、事件与来源导出为 JSONL 和 Parquet；逐条台账使用 Parquet。保留事件阶段、原始金额日期与质量标记。', output:'画像、事件观察、来源与记录台账', files:['08_results/profiles.parquet','08_results/events.parquet','08_results/event_sources.parquet','08_results/record_ledger.parquet'], code:'bulk_aggregate.py', metric:d=>[d.final_counts?.events,'条事件观察（保守归并）']},
    {title:'复核与验收', input:'全部原附件、已知逻辑记录与最终导出', method:'核对每份原附件及每条已知记录的去向，分别列出排除、文件失败、结构问题和语义复核。覆盖对账与独立语义准确率分别评估。', output:'总对账、待复核明细及结构复核清单', files:['audit.json','09_review/file_review.json','09_review/record_review.parquet','09_review/表头及结构复核清单.csv'], code:'bulk_run.py', metric:d=>[d.input.known_logical_records,'条已知逻辑记录的去向需对账']}
  ];
  let snapshot, lineage, active = 5;
  const buttons = [...document.querySelectorAll('[data-run-step]')];
  function stageState(index) {
    if (snapshot.pipeline_status.startsWith('completed')) return 'complete';
    return index < 5 ? 'complete' : index === 5 ? 'running' : 'pending';
  }
  const states = {complete:'已完成',running:'进行中',pending:'尚未执行'};
  function selectStep(index, focus = false) {
    if (!snapshot) return;
    active = index; const step = definitions[index], state = stageState(index), [value,label] = step.metric(snapshot);
    buttons.forEach((button,i) => {
      button.setAttribute('aria-selected',String(i===index));button.tabIndex=i===index?0:-1;
      button.dataset.state=stageState(i);button.querySelector('.run-step-status').textContent=states[stageState(i)];
      if (i===index && focus) button.focus();
    });
    $('run-step-panel').setAttribute('aria-labelledby',buttons[index].id);
    $('run-detail-state').textContent=states[state];$('run-detail-state').dataset.state=state;
    $('run-detail-title').textContent=String(index+1).padStart(2,'0')+' / '+step.title;
    $('run-detail-number').textContent=format(value);
    $('run-detail-label').textContent=snapshot.pipeline_status.startsWith('completed')&&index===8?'条已知逻辑记录已完成去向对账':label;
    $('run-detail-input').textContent=lineage.stages[index].input;$('run-detail-method').textContent=step.method;$('run-detail-output').textContent=lineage.stages[index].output;
    $('run-detail-flow').innerHTML=lineage.stages[index].flow.map(value=>'<p>'+escape(value)+'</p>').join('');
    $('run-detail-files').innerHTML=lineage.stages[index].files.map(path=>'<code>'+escape(path)+'</code>').join('');
    const commit=/^[a-f0-9]{40}$/.test(snapshot.source_commit)?snapshot.source_commit:'main';
    $('run-detail-source').href='https://github.com/chaomacv/beijing-enterprise-intelligence/blob/'+commit+'/src/bank_data/'+step.code;
  }
  buttons.forEach((button,index)=>{
    button.addEventListener('click',()=>selectStep(index));
    button.addEventListener('keydown',event=>{
      const moves={ArrowRight:1,ArrowLeft:-1,ArrowDown:3,ArrowUp:-3};let next;
      if (event.key in moves) next=(index+moves[event.key]+9)%9;
      if (event.key==='Home') next=0;if(event.key==='End') next=8;
      if(next!==undefined){event.preventDefault();selectStep(next,true);}
    });
  });
  document.querySelectorAll('[data-html-view]').forEach(button=>button.addEventListener('click',()=>{
    const text=button.dataset.htmlView==='text';
    $('html-story-example').textContent=text?'合成HTML有限公司已处罚，罚款100元。':'<p class="notice">合成<span>HTML</span>有限公司已处罚，罚款100元。</p>';
    document.querySelectorAll('[data-html-view]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));
  }));
  Promise.all(['run-summary.json','data-lineage.json'].map(name=>fetch('assets/'+name).then(response=>{
    if(!response.ok)throw new Error('Aggregate snapshot unavailable');return response.json();
  }))).then(([data,flow])=>{
    lineage=window.BEILineage.validate(flow);
    if(lineage.counts.known!==data.input.known_logical_records||lineage.counts.retained!==data.preparation.retained_records)throw Error('Lineage snapshot mismatch');
    if(data.kind!=='aggregate_run_snapshot'||data.semantic_accuracy_evaluated!==false||!['running','completed','completed_with_review'].includes(data.pipeline_status))throw new Error('Unexpected snapshot provenance');
    if(data.pipeline_status.startsWith('completed')&&(!data.validation?.final_audit_passed||!data.final_counts))throw new Error('Final counts require completed audit');
    snapshot=data;const done=data.pipeline_status.startsWith('completed');
    $('run-overall-state').textContent=done?'本批流程已完成，含待复核结果':'本批全量抽取进行中';
    $('run-overall-state').dataset.state=done?'complete':'running';
    $('run-snapshot-date').textContent='固定输入 / '+data.snapshot_date+' · 汇总更新 / '+data.updated_at;
    $('dedup-source-count').textContent=format(data.preparation.pending_semantic_source_records);$('dedup-representative-count').textContent=format(data.semantic_work.representative_records);
    const ratio=data.semantic_work.exact_duplicate_source_records/data.preparation.pending_semantic_source_records*100;
    $('dedup-reuse-percent').textContent=ratio.toFixed(1)+'%';$('dedup-unique-bar').style.width=(100-ratio)+'%';
    $('dedup-reuse-bar').style.width=ratio+'%';$('dedup-reuse-count').textContent=format(data.semantic_work.exact_duplicate_source_records);
    $('dedup-unique-bar').parentElement.setAttribute('aria-label',(100-ratio).toFixed(1)+'% 不同内容代表，'+ratio.toFixed(1)+'% 可复用来源记录。');
    $('batch-before-value').textContent=data.benchmarks.batching.serial_seconds.toFixed(1)+' s';
    $('batch-after-value').textContent=data.benchmarks.batching.packed_seconds.toFixed(1)+' s';
    $('batch-after-bar').style.width=(data.benchmarks.batching.packed_seconds/data.benchmarks.batching.serial_seconds*100)+'%';
    $('run-lineage-table').innerHTML=lineage.stages.map((row,i)=>'<tr><td><button type="button" data-flow-step="'+i+'">'+String(i+1).padStart(2,'0')+' '+escape(row.title)+'</button></td><td>'+escape(row.input)+'</td><td>'+escape(row.output)+'<small><code>'+escape(row.files[0])+'</code></small></td></tr>').join('');
    $('run-lineage-table').dataset.ready='true';
    $('run-lineage-table').addEventListener('click',event=>{const button=event.target.closest('[data-flow-step]');if(button){selectStep(Number(button.dataset.flowStep));$('run-step-panel').scrollIntoView({block:'nearest',behavior:'auto'});}});
    selectStep(active);
  }).catch(()=>{$('run-overall-state').textContent='汇总暂不可用 · 可查看下方说明与源码';});
})();
