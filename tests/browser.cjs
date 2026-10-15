/* Optional desktop integration test. Requires Playwright + its Chromium runtime. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const base = process.env.VIZIO_TEST_URL || 'http://127.0.0.1:8767';
  const browser = await chromium.launch({ headless: true, channel: process.env.VIZIO_BROWSER_CHANNEL || 'msedge' });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  const errors = [], ranges = [];
  const output = path.resolve(__dirname, '../artifacts');
  fs.mkdirSync(output, {recursive: true});
  page.on('pageerror', error => errors.push(error.message));
  page.on('response', response => {
    if (response.url().endsWith('/media/sample.mp4')) ranges.push(response.status());
  });
  const position = () => page.locator('#video').evaluate(v => v.currentTime);
  async function nearPosition(expected) {
    await page.waitForFunction(value => Math.abs(document.getElementById('video').currentTime - value) < 0.6, expected);
  }
  async function clickTimeline(fraction) {
    const track = await page.locator('#timeline-track').boundingBox();
    await page.mouse.click(track.x + track.width * fraction, track.y + track.height / 2);
    await nearPosition(33.023333 * fraction);
  }
  let previous;
  try {
    previous = await (await page.request.get(base + '/api/progress/big-buck-bunny')).json();
    await page.request.put(base + '/api/progress/big-buck-bunny', {headers: {'X-Vizio-Media': '1'}, data: {position: 0, duration: 33.023333}});
    await page.goto(base, {waitUntil: 'networkidle'});
    assert.equal(await page.locator('#connection').textContent(), 'Local server ready');
    assert.equal(await page.locator(':focus').getAttribute('id'), 'hero-details');
    await page.screenshot({path: path.join(output, 'home-1080.png')});
    await page.locator('#details-feature').click();
    assert.equal(await page.locator('#detail-start').isVisible(), true);
    await page.screenshot({path: path.join(output, 'film-1080.png')});
    await page.setViewportSize({width:1280,height:720});
    await page.screenshot({path: path.join(output, 'film-720.png')});
    await page.setViewportSize({width:1920,height:1080});
    await page.keyboard.press('Escape');
    await page.locator('#nav-home').click();

    await page.evaluate(() => window.VizioApp.focus('card-bunny'));
    assert.equal(await page.locator(':focus').getAttribute('id'), 'card-bunny');
    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#dialog-title').textContent(), 'Sintel');
    assert.equal(await page.locator('#detail-start').count(), 0);
    await page.screenshot({path: path.join(output, 'sample-1080.png')});
    await page.keyboard.press('Escape');
    assert.equal(await page.locator(':focus').getAttribute('id'), 'card-sintel');
    // Legacy numeric Back is handled too, and focus stays in the modal.
    await page.locator('#nav-remote').click();
    await page.keyboard.press('ArrowUp');
    await page.keyboard.press('ArrowRight');
    assert.equal(await page.locator(':focus').getAttribute('id'), 'dialog-close');
    await page.screenshot({path: path.join(output, 'remote-1080.png')});
    await page.setViewportSize({width:1280,height:720});
    await page.screenshot({path: path.join(output, 'remote-720.png')});
    await page.setViewportSize({width:1920,height:1080});
    await page.evaluate(() => document.dispatchEvent(new KeyboardEvent('keydown', {keyCode:461, bubbles:true, cancelable:true})));
    assert.equal(await page.locator('#dialog').isVisible(), false);

    await page.locator('#nav-checks').click();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#check-navigation span').textContent(), 'Pass');
    assert.equal(await page.locator('#check-navigation').getAttribute('data-result'), 'Pass');
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Enter');
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#check-picture span').textContent(), 'Fail');
    await page.screenshot({path: path.join(output, 'results-1080.png')});
    await page.setViewportSize({width:1280,height:720});
    await page.screenshot({path: path.join(output, 'results-720.png')});
    await page.setViewportSize({width:1920,height:1080});
    await page.keyboard.press('Escape');
    await page.evaluate(() => window.VizioApp.focus('play-feature'));
    await page.mouse.move(0,0);
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.getElementById('video').currentTime > 1);
    assert.equal(await page.locator('#video').evaluate(v => v.videoWidth), 480);
    // Left/Right chooses a button without changing playback until OK is pressed.
    await page.keyboard.press('ArrowRight');
    assert.equal(await page.locator(':focus').getAttribute('id'), 'seek-forward');
    assert.ok(await position() < 5);
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.getElementById('video').currentTime >= 10);
    const afterSkip = await position();
    await page.locator('#seek-back').click();
    await nearPosition(afterSkip - 10);
    const afterBack = await position();
    await page.locator('#seek-forward').click();
    await nearPosition(afterBack + 10);
    await page.keyboard.press('Space');
    await page.waitForFunction(() => document.getElementById('video').paused);
    await page.waitForFunction(() => document.getElementById('toggle-label').textContent === 'Play');
    assert.equal(await page.locator('#toggle-label').textContent(), 'Play');
    assert.equal(await page.locator('#toggle-play .icon').isVisible(), true);
    await page.screenshot({path:path.join(output,'player-buttons-1080.png')});
    // Up focuses the slider. Its arrows seek, and Down restores the last button.
    await page.keyboard.press('ArrowUp');
    assert.equal(await page.locator(':focus').getAttribute('id'), 'timeline');
    const beforeTimeline = await position();
    await page.keyboard.press('ArrowLeft');
    await nearPosition(beforeTimeline - 10);
    await page.keyboard.press('ArrowRight');
    await nearPosition(beforeTimeline);
    await page.keyboard.press('ArrowDown');
    assert.equal(await page.locator(':focus').getAttribute('id'), 'seek-forward');
    await page.keyboard.press('ArrowLeft');
    assert.equal(await page.locator(':focus').getAttribute('id'), 'toggle-play');
    assert.ok(Math.abs(await position() - beforeTimeline) < 0.1);
    // Pointer clicks seek to an absolute point and keep the slider accessible.
    await clickTimeline(0.75);
    assert.equal(await page.locator(':focus').getAttribute('id'), 'timeline');
    assert.ok(Math.abs(Number(await page.locator('#timeline').getAttribute('aria-valuenow')) - await position()) < 0.2);
    await page.keyboard.press('ArrowRight');
    await nearPosition(33.023333 - 0.1);
    await clickTimeline(0.05);
    await page.keyboard.press('ArrowLeft');
    await nearPosition(0);
    await clickTimeline(0.35);
    await page.screenshot({path: path.join(output, 'player-1080.png')});
    const expectedSavedPosition = await position();
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => document.getElementById('play-label').textContent.indexOf('Resume') === 0);
    // Seeking and pause can queue multiple serialized writes. Verify the final value,
    // rather than treating an earlier in-flight PUT response as the final save.
    await page.waitForFunction(async expected => {
      const data = await (await fetch('/api/progress/big-buck-bunny')).json();
      return Math.abs(data.position - expected) < 0.6;
    }, expectedSavedPosition);
    const progress = await (await page.request.get(base + '/api/progress/big-buck-bunny')).json();
    assert.ok(progress.position >= 10 && progress.position < 20, JSON.stringify(progress));
    await page.reload({waitUntil:'networkidle'});
    assert.equal(await page.locator('#play-label').textContent(), 'Resume test clip');
    await page.evaluate(() => window.VizioApp.focus('play-feature'));
    await page.mouse.move(0,0);
    await page.keyboard.press('Enter');
    await page.waitForFunction(position => document.getElementById('video').currentTime >= position, progress.position);
    // Hidden controls wake on the first navigation press without an invisible action.
    await page.waitForFunction(() => document.getElementById('player-hud').className.includes('quiet'), null, {timeout:10000});
    await page.keyboard.press('ArrowRight');
    assert.equal(await page.locator(':focus').getAttribute('id'), 'toggle-play');
    assert.equal(await page.locator('#player-hud').getAttribute('class'), 'player-hud');
    await page.keyboard.press('ArrowRight');
    assert.equal(await page.locator(':focus').getAttribute('id'), 'seek-forward');
    await page.keyboard.press('Space');
    await page.keyboard.press('ArrowUp');
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => !document.getElementById('video').paused);
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.getElementById('video').paused);
    // Absolute pointer seeking also uses the displayed geometry on the scaled TV layout.
    await page.setViewportSize({width:1280,height:720});
    await page.waitForFunction(() => document.getElementById('stage').getBoundingClientRect().width < 1281);
    await clickTimeline(0.5);
    await page.screenshot({path:path.join(output,'player-720.png')});
    await page.keyboard.press('Escape');

    await page.setViewportSize({width:1280,height:720});
    await page.screenshot({path:path.join(output,'home-720.png')});
    const bounds = await page.locator('#stage').boundingBox();
    assert.ok(Math.abs(bounds.width-1280)<1 && Math.abs(bounds.height-720)<1);
    await page.setViewportSize({width:390,height:844});
    await page.waitForFunction(() => document.getElementById('stage').getBoundingClientRect().width <= 391);
    await page.screenshot({path:path.join(output,'home-small.png')});
    const mobile = await page.locator('#stage').boundingBox();
    assert.ok(mobile.x >= 0 && mobile.width <= 391 && mobile.y >= 0);
    assert.ok(ranges.includes(206), 'Expected real media byte range response');
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({result:'PASS', tests:['remote focus','modal Back','checklist','H264 playback','D-pad button selection and OK activation','clickable 10-second skip buttons during playback','D-pad timeline seeking and focus restoration','click-to-seek at 1080p and 720p','seek boundaries and slider accessibility','hidden control wake-up','pause','SQLite resume after reload','1080p/720p/small viewport','no browser script errors'],mediaResponses:ranges,progress,screenshots:output},null,2));
  } finally {
    if (previous) {
      await page.request.put(base + '/api/progress/big-buck-bunny', {headers:{'X-Vizio-Media':'1'}, data:{position:previous.position,duration:previous.duration || 33.023333}}).catch(() => {});
    }
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
