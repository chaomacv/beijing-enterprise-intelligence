const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pageIndex,keyboardPage}=require('../showcase/methods.js');
test('method paging wraps through all three pages in either direction',()=>{
  assert.equal(pageIndex(-1),2);assert.equal(pageIndex(3),0);assert.equal(pageIndex(7),1);
  assert.equal(keyboardPage(2,'ArrowRight'),0);assert.equal(keyboardPage(0,'ArrowLeft'),2);
  assert.equal(keyboardPage(1,'Home'),0);assert.equal(keyboardPage(1,'End'),2);
  assert.equal(keyboardPage(1,'Tab'),null);
});
test('each method page has input/output, substantive examples and matching tab references',()=>{
  const html=fs.readFileSync(path.join(__dirname,'../showcase/index.html'),'utf8');
  for(const name of ['select','extract','resolve']){
    const panel=html.match(new RegExp('<article id="method-panel-'+name+'"[\\s\\S]*?</article>'))?.[0];
    assert.ok(panel,name);assert.ok(panel.includes('<dt>输入</dt>'));assert.ok(panel.includes('<dt>输出</dt>'));
    assert.ok(panel.includes('method-steps'));assert.ok(panel.includes('method-code'));assert.ok(panel.includes('method-result'));
    assert.ok(panel.includes('合成方法示意'));
    assert.ok(html.includes('aria-controls="method-panel-'+name+'"'));
  }
});
