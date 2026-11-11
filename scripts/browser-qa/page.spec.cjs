const {test,expect}=require('@playwright/test');

test.beforeEach(async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');
  await expect(page.locator('#gallery-viewport')).toHaveAttribute('data-ready','true');
  await expect(page.locator('.method-pager')).toHaveAttribute('data-ready','true');
  expect(errors).toEqual([]);
});
async function measure(page){
  return page.locator('#gallery-viewport').evaluate(el=>{
    const box=el.getBoundingClientRect(),cards=[...el.querySelectorAll('[data-notebook]')].map(c=>c.getBoundingClientRect());
    const full=cards.filter(c=>c.left>=box.left-2&&c.right<=box.right+2).length;
    const partial=cards.filter(c=>c.right>box.left+2&&c.left<box.right-2&&!(c.left>=box.left-2&&c.right<=box.right+2)).length;
    return {full,partial,left:box.left,right:box.right,window:innerWidth,cardWidth:cards[0].width,pageWidth:document.documentElement.scrollWidth};
  });
}
test('bounded viewport shows three full desktop cards with clipped neighbors',async({page},info)=>{
  await page.locator('#explorations').scrollIntoViewIfNeeded();
  await expect.poll(async()=>(await measure(page)).full).toBe(page.viewportSize().width>1100?3:1);
  const m=await measure(page);expect(m.left).toBeGreaterThan(5);expect(m.right).toBeLessThan(m.window-5);
  const visibleStory=await page.locator('#gallery-viewport').evaluate(el=>{
    const b=el.getBoundingClientRect();return [...el.querySelectorAll('[data-card-key]')].filter(c=>{const r=c.getBoundingClientRect();return r.left>=b.left-2&&r.right<=b.right+2;}).map(c=>c.dataset.cardKey);
  });
  expect(visibleStory).toEqual(page.viewportSize().width>1100?['sources','acquisition','events']:['sources']);
  expect(m.pageWidth).toBeLessThanOrEqual(m.window+1);
  if(m.window>1100){expect(m.partial).toBe(2);expect(m.cardWidth).toBeLessThanOrEqual(558);}
  await page.screenshot({path:info.outputPath('bounded-gallery.png')});
});
test('hero actions move right on desktop and stack naturally on mobile',async({page},info)=>{
  await expect(page.locator('.hero .eyebrow')).toHaveText('从数千万条异构记录中，提取可信、可追溯的企业事实');
  await expect(page.locator('.hero-lead')).toContainText('以公共数据为实践场景，结合数据工程与大模型技术');
  const lead=await page.locator('.hero-lead').boundingBox(),cta=await page.locator('.hero-cta').boundingBox();
  if(page.viewportSize().width>900)expect(cta.x).toBeGreaterThan(lead.x+lead.width);
  else expect(cta.y).toBeGreaterThanOrEqual(lead.y+lead.height);
  if(page.viewportSize().width>1100)expect(await page.locator('.notebook-page').first().evaluate(el=>Math.round(el.getBoundingClientRect().height))).toBe(648);
  const title=page.locator('#hero-title');
  await expect(title).toHaveText('让公开数据，成为有据可查的企业情报。');
  expect(await title.locator('br').count()).toBe(0);
  expect(await title.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
  expect(await page.locator('.gallery-heading').count()).toBe(0);
  expect(await page.locator('#gallery-play').innerText()).toBe('');
  await expect(page.locator('#gallery-clock')).not.toBeVisible();
  expect(await page.locator('.hero-bottom').evaluate(el=>parseFloat(getComputedStyle(el).marginTop))).toBe(136);
  const size=await title.evaluate(el=>parseFloat(getComputedStyle(el).fontSize));
  if(page.viewportSize().width>1100)expect(size).toBeCloseTo(Math.min(72,page.viewportSize().width*.04933333),1);
  await page.screenshot({path:info.outputPath('hero-actions.png')});
});
test('square notebooks have protruding topic tabs and a separate corner expansion icon',async({page},info)=>{
  const card=page.locator('[data-notebook="2"]');
  await page.locator('[data-gallery-page="2"]').click();
  await page.locator('#explorations').scrollIntoViewIfNeeded();
  await expect(card.locator('.notebook-category')).toHaveText('事件分类');
  await expect(card.locator('.notebook-reader-open svg')).toHaveCount(1);
  expect(await card.locator('.notebook-reader-open').innerText()).toBe('');
  const geometry=await card.evaluate(el=>{
    const box=el.getBoundingClientRect(),button=el.querySelector('.notebook-reader-open').getBoundingClientRect();
    return {corner:getComputedStyle(el.querySelector('.notebook-page')).borderTopRightRadius,
      badge:getComputedStyle(el.querySelector('.notebook-category')).borderRadius,
      tabAbove:el.querySelector('.notebook-category').getBoundingClientRect().bottom<=box.top+2,
      right:box.right-button.right,top:button.top-box.top};
  });
  expect(geometry.tabAbove).toBe(true);expect(geometry.corner).toBe('0px');expect(geometry.badge).toBe('4px 4px 0px 0px');
  expect(geometry.right).toBeLessThan(20);expect(geometry.top).toBeLessThan(20);
  await page.screenshot({path:info.outputPath('card-controls.png')});
  await card.locator('.notebook-reader-open').click();
  await expect(page.locator('#notebook-reader')).toBeVisible();
  await expect(page.locator('#notebook-reader .notebook-reader-open')).not.toBeVisible();
});
test('crossing either end keeps circular neighbors and nine unique interactive cards',async({page})=>{
  const count=await page.locator('[data-gallery-page]').count(),last=count-1,mid=Math.floor(count/2);
  expect(count).toBe(9);
  for(const n of [last,0,last,0,1]){
    if(n===last){await page.locator('[data-gallery-page="0"]').click();await page.locator('#gallery-prev').click();}
    else if(n===0){await page.locator(`[data-gallery-page="${last}"]`).click();await page.locator('#gallery-next').click();}
    else await page.locator('#gallery-next').click();
    await expect(page.locator(`[data-gallery-page="${n}"]`)).toHaveAttribute('aria-pressed','true');
    await expect.poll(()=>page.locator('.carousel-track').evaluate(el=>Number(el.children[Math.floor(el.children.length/2)].dataset.notebook))).toBe(n);
    const order=await page.locator('.carousel-track').evaluate(el=>[...el.children].map(c=>Number(c.dataset.notebook)));
    expect(new Set(order).size).toBe(count);expect(order[mid-1]).toBe((n+count-1)%count);expect(order[mid+1]).toBe((n+1)%count);
  }
  const ids=await page.locator('[id]').evaluateAll(nodes=>nodes.map(n=>n.id));expect(ids.length).toBe(new Set(ids).size);
});

test('expanded notebook retains chart controls when restored',async({page},info)=>{
  await page.locator('[data-gallery-page="2"]').click();
  await page.locator('[data-notebook="2"] .notebook-reader-open').click();
  await expect(page.locator('#notebook-reader')).toBeVisible();
  await page.locator('#gallery-event-stage').selectOption('unknown');
  await expect(page.locator('#gallery-event-table')).toContainText('阶段未明');
  await page.locator('#notebook-reader-close').click();
  await expect(page.locator('#notebook-reader')).not.toBeVisible();
  await expect(page.locator('#gallery-event-stage')).toHaveValue('unknown');
  await expect(page.locator('.carousel-track [data-notebook]')).toHaveCount(9);
  await page.locator('[data-gallery-page="5"]').click();
  await page.locator('[data-notebook="5"] .notebook-reader-open').click();
  await page.locator('.dedup-example').scrollIntoViewIfNeeded();
  await page.screenshot({path:info.outputPath('dedup-reuse-example.png')});
});

test('classification chart shows all eighteen categories and keeps profile counts explicit',async({page},info)=>{
  await page.locator('[data-gallery-page="2"]').click();
  await page.locator('[data-notebook="2"] .notebook-reader-open').click();
  await expect(page.locator('#gallery-event-table tr')).toHaveCount(18);
  await expect(page.locator('#gallery-event-table')).toContainText('人员执业资格');
  await expect(page.locator('#gallery-event-table')).toContainText('申请办理');
  await expect(page.locator('#gallery-taxonomy-total')).toHaveText('5,968,620');
  await expect(page.locator('#gallery-taxonomy-categories')).toHaveText('18');
  await expect(page.locator('#gallery-event-scope')).toHaveCount(0);
  await expect(page.locator('#gallery-event-table')).toContainText('采购中标');
  await expect(page.locator('#gallery-event-table')).toContainText('行政处罚');
  await expect(page.locator('#gallery-event-table tr')).toHaveCount(18);
  await page.locator('#gallery-event-metric').selectOption('profiles');
  await expect(page.locator('#gallery-event-count-label')).toHaveText('关联画像数');
  await expect(page.locator('#gallery-event-insight')).toContainText('不能相加为企业总数');
  await page.locator('#gallery-event-stage').selectOption('unknown');
  await expect(page.locator('#gallery-event-table')).toContainText('阶段未明');
  await page.locator('#gallery-event-metric').selectOption('events');
  await page.locator('#gallery-event-stage').selectOption('all');
  await page.screenshot({path:info.outputPath('event-classification.png')});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width+1);
});
test('timed playback advances from the last notebook to the first',async({page})=>{
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.locator('[data-gallery-page="8"]').click();
  await page.locator('#gallery-play').click();
  await page.mouse.move(5,5);
  await expect(page.locator('[data-gallery-page="0"]')).toHaveAttribute('aria-pressed','true',{timeout:12000});
  await expect.poll(()=>page.locator('.carousel-track').evaluate(el=>Number(el.children[Math.floor(el.children.length/2)].dataset.notebook))).toBe(0);
});
test('method pages replace in place with useful content and keyboard controls',async({page},info)=>{
  await page.locator('#approach').scrollIntoViewIfNeeded();
  await page.locator('#method-tab-select').click();
  const before=await page.evaluate(()=>scrollY);
  await page.locator('#method-tab-extract').click();
  await expect(page.locator('#method-panel-extract')).toBeVisible();
  await expect(page.locator('#method-panel-select')).not.toBeVisible();
  expect(Math.abs((await page.evaluate(()=>scrollY))-before)).toBeLessThan(5);
  await page.locator('#method-tab-extract').press('ArrowRight');
  await expect(page.locator('#method-tab-resolve')).toBeFocused();
  await expect(page.locator('#method-panel-resolve')).toBeVisible();
  await page.locator('#method-tab-resolve').press('Home');
  await expect(page.locator('#method-panel-select')).toBeVisible();
  expect(await page.locator('#method-sample-preview .selected').count()).toBe(15);
  for(const id of ['select','extract','resolve']){
    await page.locator('#method-tab-'+id).click();
    await expect(page.locator('#method-panel-'+id+' .method-code')).toBeVisible();
    await expect(page.locator('#method-panel-'+id+' .method-result')).toBeVisible();
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width+1);
  await page.screenshot({path:info.outputPath('method-pager.png')});
});

test('three real sunburst modes retain full totals and support true two-level zoom',async({page},info)=>{
 await page.locator('[data-gallery-page="3"]').click();
 await expect(page.locator('#event-sunburst-chart')).toHaveAttribute('data-ready','true');
 async function wholeChartFits(){
  const bounds=await page.locator('#event-sunburst-chart').evaluate(el=>{
   const chart=el.getBoundingClientRect(),frame=el.closest('.notebook-page').getBoundingClientRect();
   return {top:chart.top,bottom:chart.bottom,left:chart.left,right:chart.right,width:chart.width,height:chart.height,frameTop:frame.top,frameBottom:frame.bottom,frameLeft:frame.left,frameRight:frame.right,scroll:el.closest('.notebook-page').scrollTop,screen:innerHeight};
  });
  expect(bounds.width).toBeGreaterThan(page.viewportSize().width>1100?250:180);
  expect(bounds.height/bounds.width).toBeCloseTo(1,1);
  expect(bounds.top).toBeGreaterThanOrEqual(bounds.frameTop);
  expect(bounds.bottom).toBeLessThanOrEqual(Math.min(bounds.frameBottom,bounds.screen)+1);
  expect(bounds.left).toBeGreaterThanOrEqual(bounds.frameLeft);
  expect(bounds.right).toBeLessThanOrEqual(bounds.frameRight+1);
  expect(bounds.scroll).toBe(0);
 }
 await wholeChartFits();
 await page.screenshot({path:info.outputPath('whole-sunburst-card.png')});
 await page.locator('[data-notebook="3"] .notebook-reader-open').click();
 await wholeChartFits();
 for(const [mode,total] of [['attachments','5200'],['logical','11701'],['records','43653625']]){
  await page.locator(`[data-sun-mode="${mode}"]`).click();
  const chart=page.locator('#event-sunburst-chart');await expect(chart).toHaveAttribute('data-mode',mode);
  await expect(chart).toHaveAttribute('data-focus-count',total);
  await expect(page.locator('#event-sunburst-breadcrumb button')).toHaveCount(1);
  await page.locator('#event-sunburst-table button').first().click();
  await expect(page.locator('#event-sunburst-breadcrumb button')).toHaveCount(2);
  expect(Number(await chart.getAttribute('data-focus-count'))).toBeLessThan(Number(total));
  await page.locator('#event-sunburst-table button').first().click();
  await expect(page.locator('#event-sunburst-breadcrumb button')).toHaveCount(3);
  await wholeChartFits();
  await expect(page.locator('#event-sunburst-detail')).toContainText('占父级');
  await page.locator('[data-sun-up]').click();await expect(page.locator('#event-sunburst-breadcrumb button')).toHaveCount(2);
  await page.locator('#event-sunburst-breadcrumb button').first().click();
  await expect(chart).toHaveAttribute('data-focus-count',total);
  await wholeChartFits();
 }
 await page.screenshot({path:info.outputPath('three-mode-sunburst.png')});
 await page.locator('[data-sun-mode="attachments"]').click();await expect(page.locator('#event-sunburst-chart')).toHaveAttribute('data-mode','attachments');
 await page.screenshot({path:info.outputPath('attachment-sunburst.png')});
});

test('sunburst animation remains correct after interrupted zoom and mode switches',async({page})=>{
 await page.emulateMedia({reducedMotion:'no-preference'});
 await page.locator('[data-gallery-page="3"]').click();await page.locator('[data-notebook="3"] .notebook-reader-open').click();
 await page.locator('#event-sunburst-table button').first().click();
 await page.locator('[data-sun-up]').click();
 await page.locator('[data-sun-mode="logical"]').click();await page.locator('[data-sun-mode="records"]').click();
 await expect(page.locator('#event-sunburst-chart')).toHaveAttribute('data-mode','records');
 await expect(page.locator('#event-sunburst-chart')).toHaveAttribute('data-focus-count','43653625');
 await expect(page.locator('#event-sunburst-chart svg')).toHaveCount(1);
});

test('five-question notebook explains each method in place',async({page},info)=>{
 await page.locator('[data-gallery-page="4"]').click();
 await page.locator('[data-notebook="4"] .notebook-reader-open').click();
 await expect(page.locator('#story-questions button')).toHaveCount(5);
 await page.locator('[data-story="3"]').click();
 await expect(page.locator('#story-method')).toContainText('独立标注评测');
 await expect(page.locator('#story-code')).toContainText('schema_valid');
 await page.locator('[data-story="4"]').click();
 await expect(page.locator('#story-code')).toContainText('J(a, b)');
 await page.screenshot({path:info.outputPath('story-notebook.png')});
});

test('100 real companies support similarity distances, peripheral tag anchors, dragging and 3D',async({page},info)=>{
 await page.locator('[data-gallery-page="6"]').click();await page.locator('[data-notebook="6"] .notebook-reader-open').click();
 const host=page.locator('#enterprise-network');await expect(host).toHaveAttribute('data-ready','true',{timeout:30000});
 await expect(page.locator('#network-total')).toContainText('100 家真实企业样本');
 await expect(page.locator('[data-node-kind="company"]')).toHaveCount(100);
 await expect(page.locator('[data-node-kind="tag"]')).toHaveCount(0);
 await expect(page.locator('#network-options')).not.toHaveAttribute('open','');
 await expect(page.locator('#network-category')).not.toBeVisible();
 await expect(page.locator('#network-mode')).toBeVisible();
 await expect(page.locator('.network-nodes text:visible')).toHaveCount(0);
 expect(await page.locator('.network-edges line').count()).toBeLessThanOrEqual(300);
 await expect(host).toHaveAttribute('data-company-count','100');
 await page.locator('#network-zoom-in').click();await expect(page.locator('#network-zoom-value')).toHaveText('125%');
 await page.locator('#network-reset').click();await expect(host).toHaveAttribute('data-ready','true',{timeout:30000});
 const first=page.locator('[data-network-node]').first();await first.focus();await expect(page.locator('#network-detail')).toContainText('一家真实企业');
 if(page.viewportSize().width>1100){
  const circle=first.locator('circle'),box=await circle.boundingBox(),before=await first.getAttribute('transform');
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();
  await page.mouse.move(box.x+box.width/2+30,box.y+box.height/2+18,{steps:6});await page.mouse.up();
  expect(await first.getAttribute('transform')).not.toBe(before);
 }
 await page.screenshot({path:info.outputPath('real-network-2d.png')});
 await page.locator('#network-dimension').selectOption('3');await expect(host).toHaveAttribute('data-ready','true',{timeout:30000});
 await expect(host).toHaveAttribute('data-dimensions','3');
 const camera=await host.getAttribute('data-camera');
 if(page.viewportSize().width>1100){
  const box=await host.locator('svg').boundingBox();await page.mouse.move(box.x+7,box.y+7);await page.mouse.down();
  await page.mouse.move(box.x+70,box.y+38,{steps:6});await page.mouse.up();
 }else{await host.focus();await host.press('ArrowRight');}
 expect(await host.getAttribute('data-camera')).not.toBe(camera);
 await page.screenshot({path:info.outputPath('simple-network-3d.png')});
 await page.locator('#network-options summary').click();
 await page.locator('#network-mode').selectOption('bipartite');await expect(host).toHaveAttribute('data-ready','true',{timeout:30000});
 await expect(page.locator('.network-axis text')).toHaveCount(3);
 await expect(page.locator('[data-node-kind="company"]')).toHaveCount(100);
 await expect(page.locator('[data-node-kind="tag"]')).toHaveCount(18);
 expect(await page.locator('[data-node-kind="tag"] text:visible').count()).toBe(18);
 const endpoints=await page.locator('.network-edges line').evaluateAll(els=>els.map(el=>({source:el.__data__.source,target:el.__data__.target})));
 expect(endpoints.every(e=>e.source.startsWith('enterprise-')&&e.target.startsWith('tag-'))).toBe(true);
 await page.screenshot({path:info.outputPath('real-network-3d.png')});
 await page.locator('#network-dimension').selectOption('2');await expect(host).toHaveAttribute('data-ready','true',{timeout:30000});
 const positions=await page.locator('[data-node-kind="tag"]').evaluateAll(els=>els.map(el=>({x:el.__data__.x,y:el.__data__.y,fx:el.__data__.fx,fy:el.__data__.fy})));
 expect(positions.every(p=>Math.abs(p.x-p.fx)<1e-6&&Math.abs(p.y-p.fy)<1e-6)).toBe(true);
 const companies=await page.locator('[data-node-kind="company"]').evaluateAll(els=>els.map(el=>({x:el.__data__.x,y:el.__data__.y})));
 expect(companies.every(p=>(p.x/200)**2+(p.y/120)**2<1.000001)).toBe(true);
 await page.locator('#network-options summary').click();
 await page.locator('#enterprise-network').scrollIntoViewIfNeeded();
 await page.screenshot({path:info.outputPath('company-tag-network.png')});
 await page.locator('#network-options summary').click();
 await page.locator('#network-category').selectOption('product_registration');await expect(host).toHaveAttribute('data-ready','true',{timeout:30000});
 expect(await page.locator('[data-network-node]').count()).toBeLessThan(118);
 await page.locator('#network-category').selectOption('');
 await expect(page.locator('#network-category option')).toHaveCount(19);
 await expect(page.locator('#network-scope')).toHaveCount(0);
 await expect(host).toHaveAttribute('data-ready','true',{timeout:30000});await expect(host).toHaveAttribute('data-company-count','100');
 await page.locator('#network-mode').selectOption('similarity');await expect(host).toHaveAttribute('data-ready','true',{timeout:30000});
 await expect(page.locator('[data-node-kind="company"]')).toHaveCount(100);
 await expect(host).toHaveAttribute('data-company-count','100');
});

test('portrait separates real scale from synthetic company facts and can trace evidence',async({page},info)=>{
 await expect(page.locator('#portrait-summary')).toHaveAttribute('data-ready','true');
 await page.locator('[data-gallery-page="7"]').click();
 await page.locator('[data-notebook="7"] .notebook-reader-open').click();
 await expect(page.locator('#portrait-summary')).toContainText('5,202,714');
 await expect(page.locator('#portrait-summary')).toContainText('837,993');
 await expect(page.locator('#portrait-name')).toContainText('合成示例');
 await page.locator('[data-portrait-evidence="0"]').click();
 await expect(page.locator('#portrait-source-0')).toBeVisible();
 await expect(page.locator('#portrait-source-0')).toContainText('原始行');
 await page.locator('#portrait-company').selectOption('1');
 await expect(page.locator('#portrait-timeline')).toContainText('拟议');
 await page.screenshot({path:info.outputPath('enterprise-portrait.png')});
});


test('catalog background shows true counts and at most ten real source links per theme',async({page},info)=>{
 await page.locator('[data-gallery-page="0"]').click();await page.locator('[data-notebook="0"] .notebook-reader-open').click();
 await expect(page.locator('#source-chart')).toHaveAttribute('data-ready','true');
 await expect(page.locator('#source-count')).toHaveText('4,710');
 await expect(page.locator('[data-source-bar]')).toHaveCount(20);
 if(page.viewportSize().width<600){expect(await page.locator('.source-chart-scroll').evaluate(el=>el.scrollWidth>el.clientWidth)).toBe(true);}
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width+1);
 await page.locator('#source-theme-select').selectOption('5');
 await expect(page.locator('#source-links a')).toHaveCount(7);
 await expect(page.locator('#source-status')).toContainText('全部显示');
 await page.locator('#source-theme-select').selectOption('16');
 await expect(page.locator('#source-links a')).toHaveCount(10);
 await expect(page.locator('#source-status')).toContainText('1,207');
 const links=await page.locator('#source-links a').evaluateAll(els=>els.map(el=>el.href));
 expect(links.every(link=>link.startsWith('https://data.beijing.gov.cn/zyml/')&&!link.includes('?'))).toBe(true);
 if(page.viewportSize().width>1100){await page.locator('[data-source-bar="0"]').hover();await expect(page.locator('#source-status')).toContainText('经济建设');}
 await page.locator('[data-source-bar="0"]').focus();await page.locator('[data-source-bar="0"]').press('ArrowRight');
 await expect(page.locator('#source-status')).toContainText('信用服务');
 await expect(page.locator('#source-examples tr')).toHaveCount(5);
 await expect(page.locator('[data-notebook="0"]')).toContainText('结构示意');
 await page.locator('#source-theme-select').selectOption('0');
 await page.screenshot({path:info.outputPath('source-catalog-notebook.png')});
 await page.locator('#source-examples').scrollIntoViewIfNeeded();
 await page.screenshot({path:info.outputPath('heterogeneous-file-examples.png')});
});

test('acquisition notebook explains actual scheduling, retries and privacy boundaries',async({page},info)=>{
 await page.locator('[data-gallery-page="1"]').click();await page.locator('[data-notebook="1"] .notebook-reader-open').click();
 await expect(page.locator('.acquisition-flow')).toContainText('解析附件');
 await expect(page.locator('.acquisition-equations')).toContainText('SHA256');
 await expect(page.locator('.acquisition-retry')).toContainText('最多 3 次总尝试');
 await expect(page.locator('.acquisition-practices')).toContainText('私有环境');
 await page.screenshot({path:info.outputPath('acquisition-safety-notebook.png')});
});

test('sunburst pointer focus has no rectangular outline and keyboard focus remains shaped',async({page},info)=>{
 await page.locator('[data-gallery-page="3"]').click();await page.locator('[data-notebook="3"] .notebook-reader-open').click();
 await expect(page.locator('#event-sunburst-chart')).toHaveAttribute('data-ready','true');
 const sector=page.locator('.sunburst-sectors path[tabindex="0"]').first();
 await sector.dispatchEvent('click');await sector.focus();
 expect(await sector.evaluate(el=>getComputedStyle(el).outlineStyle)).toBe('none');
 const center=page.locator('[data-sun-up]');await center.focus();
 expect(await center.evaluate(el=>getComputedStyle(el).outlineStyle)).toBe('none');
 await center.press('Enter');await expect(page.locator('#event-sunburst-breadcrumb button')).toHaveCount(1);
 await page.screenshot({path:info.outputPath('sunburst-without-black-outline.png')});
});


test('lineage routing returns to original sources while observed time remains a separate view',async({page},info)=>{
 await page.locator('[data-gallery-page="8"]').click();await page.locator('[data-notebook="8"] .notebook-reader-open').click();
 const chart=page.locator('#gallery-timeline-chart');await expect(chart).toHaveAttribute('data-ready','true');
 await expect(chart).toHaveAttribute('data-mode','flow');await expect(page.locator('[data-lineage-point]')).toHaveCount(7);
 await page.locator('[data-lineage-point="3"]').focus();
 await expect(chart).toHaveAttribute('data-selected-count','388349');
 await expect(page.locator('#lineage-info')).toContainText('1,052,270');
 const representative=page.locator('[data-lineage-point="3"]');
 if(page.viewportSize().width>1100){await representative.hover();await expect(page.locator('.lineage-tooltip')).toBeVisible();await expect(page.locator('.lineage-tooltip')).toContainText('388,349');}
 await page.locator('[data-lineage-point="4"]').click();await expect(chart).toHaveAttribute('data-selected-count','1440619');
 await expect(page.locator('#lineage-info')).toContainText('回填');
 await page.locator('[data-lineage-point="4"]').focus();await page.locator('[data-lineage-point="4"]').press('ArrowRight');
 await expect(chart).toHaveAttribute('data-selected-count','15861277');
 await page.locator('#lineage-scale').selectOption('linear');await expect(chart).toHaveAttribute('data-selected-count','15861277');
 await page.locator('#lineage-scale').selectOption('log');await representative.click();
 await page.screenshot({path:info.outputPath('lineage-stage-flow.png')});
 await page.locator('[data-lineage-mode="time"]').click();await expect(chart).toHaveAttribute('data-mode','time');
 await expect(page.locator('[data-lineage-point]')).toHaveCount(9);await expect(page.locator('#lineage-count')).toHaveText('388,349');
 await expect(page.locator('#lineage-at')).toContainText('实际观测');await expect(page.locator('#lineage-info')).toContainText('最终验收');
 await expect(page.locator('#lineage-scale')).not.toBeVisible();
 await page.locator('#lineage-scrub').focus();await page.locator('#lineage-scrub').press('Home');
 await expect(chart).toHaveAttribute('data-selected-count','42540');
 await page.locator('#lineage-scrub').press('End');
 await page.screenshot({path:info.outputPath('lineage-observed-progress.png')});
 await page.locator('[data-lineage-mode="flow"]').click();await expect(chart).toHaveAttribute('data-selected-count','388349');
});

test('nine-step lineage table and selected details expose the same conserved record quantities',async({page},info)=>{
 await page.locator('#pipeline').scrollIntoViewIfNeeded();await expect(page.locator('#run-lineage-table')).toHaveAttribute('data-ready','true');
 const disclosure=page.locator('#run-lineage-overview'),summary=page.locator('#run-lineage-title');
 await expect(disclosure).not.toHaveAttribute('open','');
 await expect(page.locator('#run-lineage-table')).not.toBeVisible();
 await expect(page.locator('#run-step-panel')).toBeVisible();
 await expect(page.locator('#approach-title')).toHaveText('针对具体难点，给出相应的方法设计。');
 await expect(page.locator('#lab-title')).toHaveText('方法举例演示');
 await expect(page.locator('#pipeline-title')).toHaveText('每一步的数据量和去向');
 await expect(page.locator('#field-notes-title')).toHaveText('工程处理设计');
 await expect(page.locator('#validation, #release')).toHaveCount(0);
 await page.screenshot({path:info.outputPath('pipeline-lineage-collapsed.png')});
 await summary.focus();await summary.press('Enter');
 await expect(disclosure).toHaveAttribute('open','');
 await expect(page.locator('#run-lineage-table')).toBeVisible();
 await expect(page.locator('#run-lineage-table tr')).toHaveCount(9);
 await expect(page.locator('#run-lineage-table tr').nth(4)).toContainText('27,792,348');
 await expect(page.locator('#run-lineage-table tr').nth(4)).toContainText('14,420,658');
 await expect(page.locator('#run-lineage-table tr').nth(5)).toContainText('388,349');
 await expect(page.locator('#run-lineage-table tr').nth(5)).toContainText('1,440,619');
 await page.locator('.run-lineage-overview').scrollIntoViewIfNeeded();
 await page.screenshot({path:info.outputPath('pipeline-lineage-table.png')});
 await page.locator('[data-flow-step="5"]').click();await expect(page.locator('#run-detail-flow')).toContainText('1,052,270');
 await expect(page.locator('#run-detail-output')).toContainText('15,861,277');
 await summary.focus();await summary.press('Space');
 await expect(disclosure).not.toHaveAttribute('open','');
 await expect(page.locator('#run-lineage-table')).not.toBeVisible();
 await expect(page.locator('#run-detail-flow')).toContainText('1,052,270');
 await page.locator('#run-step-panel').scrollIntoViewIfNeeded();
 await page.screenshot({path:info.outputPath('pipeline-lineage-detail.png')});
 await page.locator('[data-run-step="8"]').click();await expect(page.locator('#run-detail-output')).toContainText('43,653,625');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width+1);
});

test('language controls preserve notebook interaction, translate new content and persist the preference',async({page},info)=>{
 await expect(page.locator('html')).toHaveAttribute('data-locale-ready','zh');
 await page.locator('[data-gallery-page="2"]').click();
 await page.locator('[data-notebook="2"] .notebook-reader-open').click();
 await page.locator('#gallery-event-stage').selectOption('unknown');
 await page.locator('#notebook-reader-close').click();
 await page.locator('[data-language="en"]').click();
 await page.locator('[data-notebook="2"] .notebook-reader-open').click();
 await expect(page.locator('html')).toHaveAttribute('lang','en');
 await expect(page.locator('#notebook-reader h3')).toHaveText('Company event categories');
 await expect(page.locator('#gallery-event-stage')).toHaveValue('unknown');
 await expect(page.locator('#gallery-event-table tr')).toHaveCount(18);
 await expect(page.locator('#gallery-taxonomy-total')).toHaveText('5,968,620');
 await page.locator('#gallery-event-stage').selectOption('all');
 await expect(page.locator('#gallery-event-table')).toContainText('Business permits');
 await page.screenshot({path:info.outputPath('english-event-notebook.png')});
 await page.locator('#notebook-reader-close').click();
 await page.locator('[data-gallery-page="6"]').click();
 await page.locator('[data-notebook="6"] .notebook-reader-open').click();
 await page.locator('#network-mode').selectOption('bipartite');
 await expect(page.locator('#enterprise-network')).toHaveAttribute('data-ready','true');
 await expect(page.locator('[data-node-kind="tag"]')).toHaveCount(18);
 await expect.poll(()=>page.locator('[data-node-kind="tag"] text').allTextContents()).toContain('Personnelcredentials');
 await page.screenshot({path:info.outputPath('english-company-network.png')});
 await page.locator('#notebook-reader-close').click();
 await page.locator('[data-gallery-page="2"]').click();
 await page.locator('[data-language="zh"]').click();
 await expect(page.locator('#approach-title')).toHaveText('针对具体难点，给出相应的方法设计。');
 await expect(page.locator('[data-gallery-page="2"]')).toHaveAttribute('aria-pressed','true');
 await page.locator('[data-language="en"]').click();
 await expect(page.locator('#approach-title')).toHaveText('Methods designed for specific challenges.');
 await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
 await page.screenshot({path:info.outputPath('english-typography-hero.png')});
 await page.reload();await expect(page.locator('html')).toHaveAttribute('data-locale-ready','en');
 await expect(page.locator('#pipeline-title')).toHaveText('Record counts and destinations at every step');
 await page.locator('#pipeline').scrollIntoViewIfNeeded();
 await page.locator('#run-lineage-title').click();
 await expect(page.locator('#run-lineage-table')).toContainText('15,861,277');
 await expect(page.locator('#run-lineage-table')).toContainText('provisional identities');
 await page.screenshot({path:info.outputPath('english-pipeline-table.png')});
 await page.locator('[data-language="zh"]').click();
 await expect(page.locator('#pipeline-title')).toHaveText('每一步的数据量和去向');
 await expect(page.locator('#run-lineage-table')).toContainText('临时身份');
 await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
 await page.screenshot({path:info.outputPath('chinese-typography-hero.png')});
 await page.goto('/?lang=en#approach');await expect(page.locator('#approach-title')).toHaveText('Methods designed for specific challenges.');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width+1);
});
