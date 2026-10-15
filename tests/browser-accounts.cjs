/* Real UI + FastAPI with deterministic third-party HTTP fixtures. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({headless:true, channel:'msedge'});
  const context = await browser.newContext({viewport:{width:1440,height:1000}});
  const owner = await context.newPage(), tv = await context.newPage();
  const base=process.env.VIZIO_TEST_URL || 'http://127.0.0.1:8767', headers={'X-Vizio-Media':'1'};
  const errors=[], output=path.resolve(__dirname,'../artifacts');
  fs.mkdirSync(output,{recursive:true});
  [owner,tv].forEach(page=>page.on('pageerror',e=>errors.push(e.stack || e.message)));
  const shot=async(page,name)=>page.screenshot({path:path.join(output,name+'.png'),fullPage:true});
  async function textVisible(page,text) { await page.getByText(text,{exact:true}).waitFor(); }
  async function saveSetup(service, fields) {
    for(const [id,value] of Object.entries(fields)) await owner.locator('#'+id).fill(value);
    await owner.locator('#setup-'+service+' button[type=submit]').click();
    await textVisible(owner,({tmdb:'TMDB',trakt:'Trakt',real_debrid:'Real-Debrid'})[service]+' application setup saved.');
    for(const id of Object.keys(fields)) assert.equal(await owner.locator('#'+id).inputValue(),'');
  }
  async function approve(service) {
    const result=await owner.request.post(base+'/__test__/approve/'+service,{headers,data:{}});
    assert.equal(result.status(),200);
  }
  try {
    await tv.setViewportSize({width:1920,height:1080});
    await tv.goto(base,{waitUntil:'networkidle'});
    await textVisible(tv,'Household');
    await tv.locator('#nav-search').click();
    await tv.locator('#result-0').waitFor();
    await tv.locator('#catalog-keyboard').click();
    assert.equal(await tv.locator(':focus').getAttribute('id'),'key-Q');
    // Remote focus chooses B, then typing continues with clickable keyboard keys.
    await tv.keyboard.press('ArrowRight'); await tv.keyboard.press('Enter');
    for(const letter of ['U','N','N','Y']) await tv.locator('[data-action=catalog-type][data-value="'+letter+'"]').click();
    assert.equal(await tv.locator('#catalog-query').inputValue(),'BUNNY');
    await tv.locator('#catalog-submit').click();
    await tv.locator('#result-0').waitFor();
    assert.equal(await tv.locator('.catalog-card').count(),1);
    await tv.locator('#result-0').click(); await tv.locator('#catalog-play').waitFor();
    await tv.keyboard.press('Escape'); await tv.locator('#catalog-query').waitFor();
    await tv.keyboard.press('Escape');

    await owner.goto(base+'/manage',{waitUntil:'networkidle'});
    await textVisible(owner,'Set up your household');
    await shot(owner,'manager-setup');
    await owner.locator('#owner-password').fill('browser-fixture-owner-password');
    await owner.locator('#auth-submit').click();
    await textVisible(owner,'Your household');
    await owner.locator('#new-name').fill('Alice'); await owner.locator('#new-pin').fill('1234');
    await owner.locator('#create-profile button').click();
    await textVisible(owner,'Profile added.');
    await owner.locator('#profile-detail h2').filter({hasText:'Alice'}).waitFor();
    await owner.locator('#tab-settings').click();
    await saveSetup('tmdb',{'tmdb-token':'TMDB-READ-SECRET'});
    await saveSetup('trakt',{'trakt-id':'TRAKT-CLIENT-SECRET'});
    await saveSetup('real_debrid',{'rd-id':'REGISTERED-RD-APP'});
    await shot(owner,'manager-services-desktop');
    await owner.setViewportSize({width:390,height:844});
    await shot(owner,'manager-services-mobile');
    assert.ok(await owner.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
    await owner.setViewportSize({width:1440,height:1000});
    await owner.locator('#tab-profiles').click();
    await shot(owner,'manager-profile');

    await tv.locator('#nav-profile').click();
    await tv.locator('[data-action=profile-choose]').filter({hasText:'Alice'}).click();
    await tv.locator('#pin-1').waitFor();
    await shot(tv,'profile-pin-1080');
    for(const n of [1,2,3,4]) await tv.locator('#pin-'+n).click();
    await tv.locator('#pin-unlock').click(); await textVisible(tv,'Alice');
    const me=await (await tv.request.get(base+'/api/me')).json();
    assert.equal(me.profile.name,'Alice');
    await tv.locator('#nav-accounts').click();
    await tv.locator('#link-trakt').click();
    await tv.locator('.device-code').waitFor(); await textVisible(tv,'ABCD-1234');
    await shot(tv,'account-code-1080');
    await approve('trakt'); await tv.locator('#unlink-trakt').waitFor();
    await textVisible(tv,'Connected / Linked Trakt user');
    await tv.locator('#link-real_debrid').click();
    await tv.locator('.device-code').waitFor();
    await tv.locator('#flow-cancel').click(); await tv.locator('#link-real_debrid').waitFor();
    await tv.locator('#link-real_debrid').click(); await tv.locator('.device-code').waitFor();
    await approve('real_debrid'); await tv.locator('#unlink-real_debrid').waitFor();
    await shot(tv,'accounts-linked-1080');
    await tv.keyboard.press('Escape');
    await require('./browser-home.cjs')(tv,base,shot);
    await tv.locator('#nav-search').click(); await tv.locator('#result-0').waitFor();
    await tv.locator('#catalog-query').click(); await tv.keyboard.type('Test');
    await tv.keyboard.press('Enter'); await tv.locator('#result-1').waitFor();
    await shot(tv,'catalog-1080');
    await tv.setViewportSize({width:1280,height:720}); await shot(tv,'catalog-720');
    await tv.setViewportSize({width:1920,height:1080});
    await tv.locator('#catalog-keyboard').click(); await shot(tv,'catalog-keyboard-1080');
    await tv.keyboard.press('Escape');
    await tv.locator('#result-1').click(); await tv.locator('#catalog-seasons').click();
    await tv.locator('#list-0').click(); await tv.locator('#list-0').waitFor();
    await textVisible(tv,'1. First episode');
    await tv.locator('#list-0').click(); await tv.locator('#episode-files').waitFor();
    await tv.keyboard.press('Escape'); await textVisible(tv,'1. First episode');
    await tv.keyboard.press('Escape'); await textVisible(tv,'Season 1 / 2 episodes');
      await tv.keyboard.press('Escape'); await tv.locator('#catalog-seasons').waitFor();
    await tv.keyboard.press('Escape'); await tv.locator('#catalog-query').waitFor();
    await tv.locator('#catalog-query').fill('Many'); await tv.locator('#catalog-submit').click();
    await tv.getByText('A longer catalog title for result 1',{exact:true}).waitFor();
    assert.equal(await tv.locator('.catalog-card').count(),6);
    assert.ok(await tv.locator('#dialog-content').evaluate(node=>node.getBoundingClientRect().bottom<=node.parentNode.getBoundingClientRect().bottom-35));
    await tv.locator('#catalog-next').click(); await tv.getByText('A longer catalog title for result 7',{exact:true}).waitFor();
    await tv.locator('#catalog-prev').click(); await tv.getByText('A longer catalog title for result 1',{exact:true}).waitFor();
    await tv.locator('#filter-watchlist').click(); await tv.locator('#result-0').waitFor();
    await tv.locator('#result-0').click(); await tv.locator('#catalog-files').click();
    await tv.locator('.source-item').filter({hasText:'A.Test.Film.2020.1080p.mp4'}).waitFor();
    await shot(tv,'account-file-search-1080');
    const source=await tv.locator('#dialog-content').textContent();
      assert.ok(source.includes('Choose a source to prepare it in Real-Debrid'));
    const diagnostics=JSON.stringify(await (await tv.request.get(base+'/api/diagnostics')).json());
    for(const secret of ['TMDB-READ-SECRET','TRAKT-CLIENT-SECRET','1234','PRIVATE-DEVICE-CODE']) assert.ok(!diagnostics.includes(secret),secret+' leaked');
    const ownerHtml=await owner.content();
    assert.ok(!ownerHtml.includes('TMDB-READ-SECRET'));
    // Profile isolation survives separate browser sessions.
    const other=await browser.newContext();
    await other.request.post(base+'/api/profiles/select',{headers,data:{id:'household'}});
    const accounts=await (await other.request.get(base+'/api/accounts')).json();
    assert.equal(accounts.trakt.state,'disconnected'); await other.close();
    // The PC manager supports personal tokens and its own device-approval view.
    await owner.locator('[data-action=refresh-profiles]').click();
    await textVisible(owner,'Connected as Linked RD user');
    await owner.locator('.personal-token summary').click();
    await owner.locator('#personal-rd-token').fill('PRIVATE-RD-API-TOKEN');
    owner.once('dialog',dialog=>dialog.accept());
    await owner.locator('#personal-token button').click(); await textVisible(owner,'Real-Debrid connected.');
    owner.once('dialog',dialog=>dialog.accept());
    await owner.locator('[data-action=disconnect][data-value=real_debrid]').click();
    await owner.locator('[data-action=connect][data-value=real_debrid]').waitFor();
    await owner.locator('[data-action=connect][data-value=real_debrid]').click();
    await owner.locator('#device-panel .device-code').waitFor();
    await owner.locator('#device-panel').waitFor({state:'hidden'});
    await owner.locator('.profile-edit summary').click();
    await owner.locator('#edit-name').fill('Alice renamed'); await owner.locator('#edit-profile button').click();
    await textVisible(owner,'Profile saved. Choose it again on the TV.');
    assert.equal((await tv.request.get(base+'/api/accounts')).status(),401);
    // Logout protects all owner API operations.
    await owner.locator('#sign-out').click(); await owner.locator('#auth-submit').waitFor();
    assert.equal((await owner.request.get(base+'/api/admin/config')).status(),401);
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({result:'PASS',checks:['live home and genre shelves','home pagination and horizontal D-pad scrolling','home focus restoration and retry','profile-scoped My list and continue watching','sample and live catalog search','D-pad on-screen keyboard','owner onboarding and logout','service configuration without credential readback','profile PIN and isolation','Trakt device approval','Real-Debrid cancellation and approval','series/season/episode navigation','Trakt watchlist','account filename search','input diagnostic privacy','desktop/mobile manager and 1080p/720p TV layouts','no script errors'],screenshots:output},null,2));
  } catch(error) {
    await shot(tv,'accounts-test-failure-tv'); await shot(owner,'accounts-test-failure-manager');
    throw error;
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
