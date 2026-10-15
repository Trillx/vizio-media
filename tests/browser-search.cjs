/* Run against a fresh tests/serve_search_mock.py fixture. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');

(async()=>{
    const base=process.env.VIZIO_SEARCH_TEST_URL || 'http://localhost:8770';
    const output=path.resolve('artifacts/search'); fs.mkdirSync(output,{recursive:true});
    const browser=await chromium.launch({channel:process.env.VIZIO_BROWSER_CHANNEL || 'msedge',headless:true});
    const context=await browser.newContext({viewport:{width:1280,height:720}});
    const page=await context.newPage(),errors=[];
    page.on('pageerror',error=>errors.push(String(error)));
    const input=page.locator('#catalog-query'), suggestions=page.locator('#catalog-suggestions');
    try {
        await page.goto(base+'/manage');
        await page.locator('#owner-password').fill('search-fixture-owner-password');
        await page.locator('#auth-submit').click(); await page.locator('#tab-settings').click();
        await page.locator('#provider-options').getByText('Provider list temporarily unavailable in this test. Retry.',{exact:true}).waitFor();
        assert.equal(await page.locator('#source-providers button[type=submit]').isEnabled(),false);
        await page.locator('#provider-options').getByRole('button',{name:'Retry',exact:true}).click();
        await page.locator('#provider-torrentio').waitFor();
        assert.equal(await page.locator('#provider-options input').count(),8);
        assert.equal(await page.locator('#source-providers button[type=submit]').isEnabled(),true);
        await page.goto(base);
        await page.waitForFunction(()=>window.VizioExtras && window.VizioExtras.currentProfile());
        await page.locator('#nav-search').click(); await input.fill('Test');
        await suggestions.locator('#suggestion-0').waitFor();
        assert.equal(await input.evaluate(element=>document.activeElement===element),true);
        assert.equal(await page.locator('#catalog-results').isVisible(),false);
        await input.press('ArrowDown'); assert.equal(await page.locator(':focus').getAttribute('id'),'suggestion-0');
        await page.locator(':focus').press('Enter');
        await page.locator('#catalog-files').waitFor(); await page.keyboard.press('Escape');
        await page.locator('#catalog-keyboard').click();
        assert.equal(await page.locator(':focus').getAttribute('id'),'key-Q');
        const rows=await page.locator('.tv-keyboard .keyboard-row').evaluateAll(elements=>elements.map(element=>Array.from(element.querySelectorAll('button')).map(button=>button.textContent).join('')));
        assert.deepEqual(rows.slice(0,4),['1234567890','QWERTYUIOP','ASDFGHJKL','ZXCVBNM']);
        await page.locator('#key-clear').click(); await page.locator('#key-T').click(); await page.locator('#key-E').click();
        await suggestions.locator('#suggestion-0').waitFor(); assert.equal(await input.inputValue(),'TE');
        assert.equal(await page.locator(':focus').getAttribute('id'),'key-E');
        await page.screenshot({path:path.join(output,'qwerty-suggestions-720.png')});
        const slow=page.waitForRequest(request=>request.url().includes('q=Slow'));
        const slowDone=page.waitForResponse(response=>response.url().includes('q=Slow'));
        await input.fill('Slow'); await slow; await input.fill('Fast');
        await suggestions.getByText('New fast response',{exact:true}).waitFor(); await slowDone;
        assert.match(await suggestions.textContent(),/New fast response/);
        assert.doesNotMatch(await suggestions.textContent(),/Old slow response/);
        await input.fill('Outage'); await suggestions.getByText('Suggestions unavailable. Press Search to try again.',{exact:true}).waitFor();
        await input.fill('Nomatch'); await suggestions.getByText('No matching suggestions. Try another title.',{exact:true}).waitFor();
        await input.fill('T'); assert.equal(await suggestions.isVisible(),false);
        await page.setViewportSize({width:1920,height:1080}); await input.fill('Test');
        await suggestions.locator('#suggestion-0').waitFor();
        const bounds=await page.locator('.dialog-panel').boundingBox(); assert.ok(bounds.y>=0 && bounds.y+bounds.height<=1080);
        await page.screenshot({path:path.join(output,'qwerty-suggestions-1080.png')});
        assert.deepEqual(errors,[]);
        console.log(JSON.stringify({result:'PASS',checks:['provider failure and retry','autocomplete and D-pad selection','QWERTY and virtual-key suggestions','typing focus retained','late responses ignored','unavailable and empty suggestions','1080p and 720p layouts'],screenshots:output},null,2));
    } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
