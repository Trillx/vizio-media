/* Exercise real UI, RD preparation and byte-range video with controlled services. */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
    const base = process.env.VIZIO_PLAYBACK_TEST_URL || 'http://127.0.0.1:8768';
    const output = path.resolve('artifacts/playback');
    fs.mkdirSync(output, {recursive: true});
    const browser = await chromium.launch({channel: process.env.VIZIO_BROWSER_CHANNEL || 'msedge', headless: true});
    const context = await browser.newContext({viewport: {width:1920, height:1080}});
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(String(error)));
    async function shot(name) { await page.screenshot({path:path.join(output,name+'.png')}); }
    try {
        await page.goto(base);
        await page.waitForFunction(() => window.VizioExtras && window.VizioExtras.currentProfile());
        await page.locator('#hero-details').click();
        await page.locator('#catalog-files').click();
        await page.locator('#source-1').waitFor();
        await shot('sources-1080');
        await page.locator('.source-choice').filter({hasText:'CocoScrapers'}).click();
        await page.locator('#playback-play').waitFor({timeout:20000});
        await shot('ready-1080');
        await page.locator('#playback-play').click();
        await page.waitForFunction(() => document.getElementById('video').currentTime > 1);
        assert.equal(await page.locator('#player-title').textContent(),'A Test Film');
        const stream = await page.locator('#video').getAttribute('src');
        assert.match(stream,/^\/api\/playback\/[A-Za-z0-9_-]+\/stream$/);
        await page.locator('#seek-forward').click();
        await page.waitForFunction(() => document.getElementById('video').currentTime > 10);
        await page.keyboard.press('ArrowUp');
        assert.equal(await page.evaluate(() => document.activeElement.id),'timeline');
        await page.keyboard.press('ArrowRight');
        await page.keyboard.press('Enter');
        await page.waitForFunction(() => document.getElementById('video').paused);
        const savedAt = await page.locator('#video').evaluate(video => video.currentTime);
        assert.ok(savedAt > 18);
        await shot('player-1080');
        await page.keyboard.press('Escape');
        await page.locator('.source-choice').filter({hasText:'CocoScrapers'}).waitFor();
        await page.locator('.source-choice').filter({hasText:'CocoScrapers'}).click();
        await page.locator('#playback-play').filter({hasText:'Resume at'}).waitFor();
        await page.locator('#playback-play').click();
        await page.waitForFunction(position => document.getElementById('video').currentTime >= position - 1, savedAt);
        await page.keyboard.press('Escape');
        await page.keyboard.press('Escape');
        await page.keyboard.press('Escape');
        await page.locator('#continue-0').waitFor();
        assert.match(await page.locator('#continue-0').textContent(),/A Test Film/);
        await page.reload();
        await page.locator('#continue-0').filter({hasText:'A Test Film'}).waitFor();
        await page.locator('#continue-0').click();
        await page.locator('#catalog-files').click();
        await page.locator('.source-choice').filter({hasText:'CocoScrapers'}).click();
        await page.locator('#playback-play').filter({hasText:'Resume at'}).waitFor();
        await page.setViewportSize({width:1280,height:720});
        await shot('resume-720');
        await page.locator('#playback-restart').click();
        await page.waitForFunction(() => document.getElementById('video').currentTime > 0 && document.getElementById('video').currentTime < 5);
        await page.keyboard.press('Escape');
        await shot('sources-720');
        const rendered = await page.content();
        for (const secret of ['PRIVATE-SIGNED-LINK','PRIVATE-RD-API-TOKEN','TMDB-READ-SECRET']) assert.ok(!rendered.includes(secret));
        const diagnostics = JSON.stringify(await (await context.request.get(base+'/api/diagnostics')).json());
        assert.ok(!diagnostics.includes('PRIVATE-SIGNED-LINK'));
        assert.deepEqual(errors,[]);
        console.log(JSON.stringify({result:'PASS',checks:['Coco source selection','Real-Debrid preparation','range-stream playback','D-pad seek and pause','return to sources','resume after reload','continue watching','restart','1080p and 720p layouts','no credentials in DOM or diagnostics'],screenshots:output},null,2));
    } catch (error) {
        await shot('failure');
        throw error;
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
