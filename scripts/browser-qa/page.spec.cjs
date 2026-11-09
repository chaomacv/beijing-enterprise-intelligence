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
  expect(m.pageWidth).toBeLessThanOrEqual(m.window+1);
  if(m.window>1100){expect(m.partial).toBe(2);expect(m.cardWidth).toBeLessThan(500);}
  await page.screenshot({path:info.outputPath('bounded-gallery.png')});
});
test('crossing either end keeps circular neighbors and unique interactive cards',async({page})=>{
  for(const n of [6,0,6,0,1]){
    if(n===6){await page.locator('[data-gallery-page="0"]').click();await page.locator('#gallery-prev').click();}
    else if(n===0){await page.locator('[data-gallery-page="6"]').click();await page.locator('#gallery-next').click();}
    else await page.locator('#gallery-next').click();
    await expect(page.locator(`[data-gallery-page="${n}"]`)).toHaveAttribute('aria-pressed','true');
    await expect.poll(()=>page.locator('.carousel-track').evaluate(el=>Number(el.children[3].dataset.notebook))).toBe(n);
    const order=await page.locator('.carousel-track').evaluate(el=>[...el.children].map(c=>Number(c.dataset.notebook)));
    expect(new Set(order).size).toBe(7);expect(order[2]).toBe((n+6)%7);expect(order[4]).toBe((n+1)%7);
  }
  const ids=await page.locator('[id]').evaluateAll(nodes=>nodes.map(n=>n.id));expect(ids.length).toBe(new Set(ids).size);
});
test('expanded notebook retains chart controls when restored',async({page})=>{
  await page.locator('[data-notebook="1"] .notebook-reader-open').click();
  await expect(page.locator('#notebook-reader')).toBeVisible();
  await page.locator('#gallery-event-stage').selectOption('unknown');
  await expect(page.locator('#gallery-event-table')).toContainText('阶段未明');
  await page.locator('#notebook-reader-close').click();
  await expect(page.locator('#notebook-reader')).not.toBeVisible();
  await expect(page.locator('#gallery-event-stage')).toHaveValue('unknown');
  await expect(page.locator('.carousel-track [data-notebook]')).toHaveCount(7);
});
test('timed playback advances from the last notebook to the first',async({page})=>{
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.locator('[data-gallery-page="6"]').click();
  await page.locator('#gallery-play').click();
  await page.mouse.move(5,5);
  await expect(page.locator('[data-gallery-page="0"]')).toHaveAttribute('aria-pressed','true',{timeout:12000});
  await expect.poll(()=>page.locator('.carousel-track').evaluate(el=>Number(el.children[3].dataset.notebook))).toBe(0);
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
