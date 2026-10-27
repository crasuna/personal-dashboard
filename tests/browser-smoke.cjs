const {chromium}=require(process.env.DASHBOARD_TEST_PLAYWRIGHT || 'playwright');
const assert=require('node:assert/strict');
const {startTestServer}=require('./browser-server.cjs');
(async()=>{
 const fixture=await startTestServer();
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']}).catch(async error=>{await fixture.close();throw error;});
 try{
  const context=await browser.newContext({viewport:{width:1380,height:950}});const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(fixture.url);await page.waitForFunction(()=>typeof syncClient!=='undefined'&&syncClient?.ready);
  const before=await page.evaluate(()=>({todos:state.db.todos.length,transactions:state.db.transactions.length,subjects:state.db.subjects.length}));
  assert.equal(before.todos,0);assert.equal(before.transactions,0);assert.equal(before.subjects,0);
  await page.locator('.hero [data-modal="todo"]').click();await page.locator('#todoTitle').fill('同步测试-早餐');await page.locator('#todoStartH').fill('7');await page.locator('#todoStartM').fill('30');await page.locator('#todoEndH').fill('8');await page.locator('#todoEndM').fill('00');await page.locator('#todoForm [type=submit]').click();
  await page.waitForFunction(()=>state.db.todos.some(t=>t.title==='同步测试-早餐')&&syncClient.localWrites===0&&!syncClient.localRunning);
  await page.reload();await page.waitForFunction(()=>syncClient?.ready&&state.db.todos.some(t=>t.title==='同步测试-早餐'));
  await page.locator('#syncBadge').click();await page.locator('#syncEmail').waitFor({state:'visible'});assert(await page.locator('#syncFolder').inputValue()==='personal-dashboard-v1');await page.locator('#modalClose').click();
  const tab=await context.newPage();await tab.goto(fixture.url);await tab.waitForFunction(()=>syncClient?.ready);
  await Promise.all([page.evaluate(async()=>{state.db.transactions.push({id:'browser-a',type:'expense',date:todayISO(),amount:11,category:'餐饮',note:'并发 A'});await save();}),tab.evaluate(async()=>{state.db.todos.push({id:'browser-b',title:'并发 B',date:todayISO(),start:'09:00',done:false});await save();})]);
  // flushDesktop deliberately skips an already-running flush. Wait for each
  // background save before requesting another pass, then test convergence.
  for(const p of [page,tab,page]){
   await p.waitForFunction(()=>!syncClient.localRunning&&syncClient.localWrites===0);
   await p.evaluate(()=>syncClient.flushDesktop());
  }
  assert(await page.evaluate(()=>DashboardSyncCore.materialize(syncClient.doc).transactions.some(t=>t.id==='browser-a')&&DashboardSyncCore.materialize(syncClient.doc).todos.some(t=>t.id==='browser-b')));
  const saved=await(await page.request.get(fixture.url+'/api/data')).json();
  assert(saved.transactions.some(t=>t.id==='browser-a')&&saved.todos.some(t=>t.id==='browser-b'));
  await tab.close();
  await page.route('**/api/**',r=>r.abort());
  await page.evaluate(async()=>{state.db.transactions.push({id:'offline-test',type:'expense',date:todayISO(),amount:12,category:'餐饮',note:'离线保存'});await save();});
  await page.reload();await page.waitForFunction(()=>syncClient?.ready&&state.db.transactions.some(t=>t.id==='offline-test'));
  await page.unroute('**/api/**');await page.evaluate(()=>syncClient.flushDesktop());
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:require('node:path').join(fixture.dir,'home.png'),fullPage:true});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);assert.equal(overflow,false);
  for(const view of ['schedule','course','finance','deadline','review']){await page.locator(`#bottomNav [data-view="${view}"]`).click();await page.waitForTimeout(80);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'overflow in '+view);}
  await page.locator('#syncBadge').click();await page.screenshot({path:require('node:path').join(fixture.dir,'sync.png'),fullPage:true});
  assert.deepEqual(errors,[]);console.log('PASS fresh empty desktop, UI create/reload, multitab, offline reload, 390px all six modules, sync settings; no JS errors');
  await context.close();
 }finally{await browser.close();await fixture.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
