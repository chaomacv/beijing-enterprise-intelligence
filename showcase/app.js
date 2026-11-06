(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
  const model = window.BEIModel;
  let demo, activeEntity, eventFilter = 'all';

  function setLab(name, focus = false) {
    document.querySelectorAll('[data-lab]').forEach(button => {
      const active = button.dataset.lab === name;
      button.setAttribute('aria-selected', String(active));
      button.tabIndex = active ? 0 : -1;
      $(`panel-${button.dataset.lab}`).hidden = !active;
      if (active && focus) button.focus();
    });
  }
  const tabs = [...document.querySelectorAll('[data-lab]')];
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => setLab(tab.dataset.lab));
    tab.addEventListener('keydown', event => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      if (next !== undefined) { event.preventDefault(); setLab(tabs[next].dataset.lab, true); }
    });
  });
  document.querySelectorAll('[data-open-lab]').forEach(link => link.addEventListener('click', () => setLab(link.dataset.openLab)));

  function renderSamples() {
    const count = Number($('sample-count').value);
    const selected = model.sampleRows(120, count, $('random-sample').checked);
    $('sample-count-value').value = count;
    $('sample-selected').textContent = selected.size;
    const percent = (selected.size / 120 * 100).toFixed(1) + '%';
    $('sample-percent').textContent = percent;
    $('sample-meter').style.width = percent;
    $('sample-grid').setAttribute('aria-label', `120 条原始记录中，${selected.size} 条进入样本，占 ${percent}。`);
    const fragment = document.createDocumentFragment();
    for (let i = 0; i < 120; i++) {
      const cell = document.createElement('span');
      const kind = selected.get(i);
      cell.className = 'sample-cell' + (kind ? ' ' + kind : '');
      cell.title = `记录 ${String(i + 1).padStart(3, '0')} · ${kind === 'stratified' ? '首中尾样本' : kind === 'random' ? '随机补样' : '原始记录保留，未进入本轮样本'}`;
      fragment.append(cell);
    }
    $('sample-grid').replaceChildren(fragment);
  }
  $('sample-count').addEventListener('input', renderSamples);
  $('random-sample').addEventListener('change', renderSamples);
  renderSamples();

  const chunkRecords = Array.from({length: 12}, (_, index) => ({
    id: 'R-' + String(index + 1).padStart(3, '0'),
    name: `合成示例${index % 2 ? '乙' : '甲'}科技`,
    amount: ((index + 1) * 7.5).toFixed(1),
    status: index % 3 ? '已备案' : '拟支持'
  }));
  let activeChunk = 0;
  function renderChunks(reset = false) {
    const size = Number($('chunk-size').value);
    const chunks = model.chunkRows(chunkRecords, size);
    if (reset) activeChunk = 0;
    activeChunk = Math.min(activeChunk, chunks.length - 1);
    $('chunk-size-value').value = size;
    $('chunk-summary').textContent = `${chunks.length} 块 × 完整记录 + 公共表头`;
    $('chunk-buttons').innerHTML = chunks.map((_, index) => `<button type="button" data-chunk="${index}" aria-pressed="${index === activeChunk}">CHUNK ${String(index + 1).padStart(2, '0')}</button>`).join('');
    $('chunk-rows').innerHTML = chunks[activeChunk].map(row => `<tr><td>${row.id}</td><td>${row.name}</td><td>${row.amount}</td><td>${row.status}</td></tr>`).join('');
    $('chunk-coverage').textContent = `${chunks.flat().length} / ${chunkRecords.length} 个记录编号都有去向`;
  }
  $('chunk-size').addEventListener('input', () => renderChunks(true));
  $('chunk-buttons').addEventListener('click', event => {
    const button = event.target.closest('[data-chunk]');
    if (button) { activeChunk = Number(button.dataset.chunk); renderChunks(); }
  });
  renderChunks();

  const matchCases = {
    same: [
      {name: '合成示例甲科技有限公司', code: '', address: '北京市测试区示例路 1 号'},
      {name: '合成示例甲科技有限公司', code: '', address: '北京市测试区示例路 1 号'}
    ],
    conflict: [
      {name: '合成示例甲科技有限公司', code: '示意标识 A', address: '北京市测试区示例路 1 号'},
      {name: '合成示例甲科技有限公司', code: '示意标识 B', address: '北京市测试区示例路 1 号'}
    ],
    uncertain: [
      {name: '合成示例甲科技有限公司', code: '', address: ''},
      {name: '合成示例乙科技有限公司', code: '', address: ''}
    ]
  };
  const verdictCopy = {
    same: ['可以关联 · 暂定身份', '本例名称和地址完全一致，支持关联到同一暂定主体；它仍不等同于权威工商身份核验。'],
    conflict: ['保留独立主体 · 标识冲突', '本例假设两份标识均可靠。即使名称与地址相同，标识冲突也阻止自动合并。'],
    uncertain: ['进入候选复核 · 证据不足', '字面相似可以生成候选；缺少身份与地址证据，无法据此确认是同一企业。']
  };
  function renderMatch(name) {
    const pair = matchCases[name];
    const verdict = model.classifyIdentity(...pair);
    ['match-left', 'match-right'].forEach((id, index) => {
      const row = pair[index];
      $(id).innerHTML = `<small>RECORD ${index ? 'B' : 'A'}</small><h4>${escape(row.name)}</h4><dl><dt>身份标识</dt><dd>${escape(row.code || '未提供')}</dd><dt>地址</dt><dd>${escape(row.address || '未提供')}</dd></dl>`;
    });
    $('match-verdict').className = 'match-verdict ' + verdict;
    $('match-verdict').innerHTML = `<strong>${verdictCopy[verdict][0]}</strong><p>${verdictCopy[verdict][1]}</p>`;
    document.querySelectorAll('[data-match]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.match === name)));
  }
  document.querySelectorAll('[data-match]').forEach(button => button.addEventListener('click', () => renderMatch(button.dataset.match)));
  renderMatch('same');

  const eventTypes = {innovation: '科技认定记录', administrative_penalty: '行政处罚记录'};
  function renderEntity() {
    const profile = demo.profiles.find(row => row.entity_id === activeEntity);
    $('entity-name').textContent = profile.names[0];
    $('entity-address').textContent = profile.addresses[0] || '来源未提供地址';
    document.querySelectorAll('[data-entity]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.entity === activeEntity)));
    document.querySelectorAll('[data-filter]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.filter === eventFilter)));
    const events = demo.events.filter(row => row.entity_id === activeEntity && (eventFilter === 'all' || row.event_type === eventFilter))
      .sort((a, b) => (a.date?.value || '').localeCompare(b.date?.value || ''));
    $('event-timeline').innerHTML = events.length ? events.map(event => {
      const proposed = event.status === 'proposed';
      const source = demo.records.find(row => row.record_id === event.sources[0].record_id);
      return `<div class="event-row"><time class="event-date">${escape(event.date?.value || '日期未知')}</time><i class="event-dot ${event.event_type === 'administrative_penalty' ? 'penalty' : ''}" aria-hidden="true"></i><div class="event-body"><strong>${escape(eventTypes[event.event_type] || event.event_type)}</strong><span class="event-status ${proposed ? 'proposed' : ''}">${proposed ? '拟议 / proposed' : '已记录 / confirmed'}</span><p>${escape(source?.filename.replace('合成示例_', '') || '示例来源')}</p></div><button type="button" class="source-button" data-event="${escape(event.event_id)}">查看证据 ↗</button></div>`;
    }).join('') : '<p class="empty-events">当前样例在此筛选下没有事件。来源覆盖未知，不能据此判断没有相关事实。</p>';
  }
  function renderDemo() {
    demo.profiles.sort((a, b) => a.names[0].includes('甲') ? -1 : b.names[0].includes('甲') ? 1 : a.entity_id.localeCompare(b.entity_id));
    activeEntity = demo.profiles[0].entity_id;
    $('entity-buttons').innerHTML = demo.profiles.map(profile => `<button class="entity-button" type="button" data-entity="${escape(profile.entity_id)}" aria-pressed="false">${escape(profile.names[0])}<span>${profile.event_ids.length} 条事件 · 暂定归属</span></button>`).join('');
    const s = demo.summary;
    $('demo-totals').innerHTML = `${demo.files.length} 份合成文件 / ${s.records} 条记录<br>${s.entities} 个暂定主体 / ${s.events} 条事件<br>${s.excluded_records} 条排除记录 / ${s.records} 条状态留存`;
    renderEntity();
  }
  $('entity-buttons').addEventListener('click', event => {
    const button = event.target.closest('[data-entity]');
    if (button) { activeEntity = button.dataset.entity; renderEntity(); }
  });
  document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
    eventFilter = button.dataset.filter;
    if (demo) renderEntity();
  }));

  function openSource(id) {
    const event = demo.events.find(row => row.event_id === id);
    const source = event.sources[0];
    const record = demo.records.find(row => row.record_id === source.record_id);
    const evidence = new Set(event.evidence.map(item => item.field));
    $('source-title').textContent = eventTypes[event.event_type] || event.event_type;
    const metadata = [['文件', record.filename], ['工作表', source.sheet], ['原始行', String(source.row) + '（含表头）'], ['记录 ID', source.record_id], ['文件 ID', source.file_id], ['处理方式', demo.provenance.backend]];
    $('source-content').innerHTML = `<dl class="source-meta">${metadata.map(([key, value]) => `<dt>${escape(key)}</dt><dd>${escape(value)}</dd>`).join('')}</dl><blockquote class="source-quote">${event.evidence.map(item => escape(item.value)).join('；')}</blockquote><div class="source-cells">${Object.entries(record.cells).map(([key, value]) => `<div class="source-cell ${evidence.has(key) ? 'highlight' : ''}"><span>${escape(key)}</span><strong>${escape(value === '' ? '（原文为空）' : value)}</strong></div>`).join('')}</div><p class="dialog-note">完整保留原始值；空值保持为空。以上企业、地址、文书与事件均为合成示例。</p>`;
    $('source-dialog').showModal();
  }
  $('event-timeline').addEventListener('click', event => {
    const button = event.target.closest('[data-event]');
    if (button) openSource(button.dataset.event);
  });
  $('close-source').addEventListener('click', () => $('source-dialog').close());
  document.querySelector('.dialog-close').addEventListener('click', () => $('source-dialog').close());
  $('source-dialog').addEventListener('click', event => {
    if (event.target === $('source-dialog')) {
      const bounds = event.target.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) event.target.close();
    }
  });
  $('copy-command').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText($('quickstart-code').textContent.trim());
      $('copy-status').textContent = '命令已复制。Demo 生成合成数据；正式数据处理需另行配置。';
      $('copy-command').textContent = '已复制 ✓';
    } catch (_) {
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents($('quickstart-code'));
      selection.removeAllRanges(); selection.addRange(range);
      $('copy-status').textContent = '当前浏览器限制剪贴板访问，命令已选中，请手动复制。';
    }
  });

  fetch('assets/demo.json').then(response => {
    if (!response.ok) throw new Error('Cannot load public fixture');
    return response.json();
  }).then(value => {
    if (value.provenance?.kind !== 'synthetic' || !value.summary?.rule_baseline) throw new Error('Invalid demo provenance');
    demo = value;
    renderDemo();
  }).catch(() => {
    $('demo-totals').textContent = '示例未能载入';
    $('entity-address').textContent = '请通过 HTTP 预览页面，或下载上方的示例 JSON 查看。';
    $('event-timeline').innerHTML = '<p class="empty-events">示例暂不可用。方法实验和源码链接仍可使用。</p>';
  });
})();
