const test = require('node:test');
const assert = require('node:assert/strict');
const {create} = require('../web/source-playback.js');

function fixture(options = {}) {
    let now = 0, next = 0;
    const timers = new Map(), requests = [], states = [], plays = [], stopped = [];
    const clock = {
        now: () => now,
        setTimeout(fn, delay) { const id = ++next; timers.set(id, {at:now + delay, fn}); return id; },
        clearTimeout(id) { timers.delete(id); },
        advance(ms) {
            const end = now + ms;
            while (true) {
                const due = [...timers].filter(([,t]) => t.at <= end).sort((a,b) => a[1].at - b[1].at)[0];
                if (!due) { break; }
                now = due[1].at; timers.delete(due[0]); due[1].fn();
            }
            now = end;
        }
    };
    const controller = create({
        request(method, url, body, callback) { requests.push({method,url,body,callback}); },
        state(state) { states.push(state); },
        play(media, hooks) { plays.push({media,hooks}); },
        stopVideo() {}, stop(id) { stopped.push(id); }
    }, {...options, clock});
    const items = Array.from({length:10}, (_,i) => ({id:String(i),selection_id:'choice-'+i}));
    function reply(index, data, ok = true) { requests[index].callback(ok, data); }
    return {controller, clock, requests, states, plays, stopped, items, reply};
}

test('tries the next source after an API failure and stops only when video advances', () => {
    const f = fixture(); f.controller.start(f.items);
    f.reply(0, {status:409, detail:'Dead source'}, false);
    assert.equal(f.requests[1].body.selection_id, 'choice-1');
    f.reply(1, {id:'second',state:'ready',stream:'/second'});
    assert.equal(f.controller.active(), true);
    f.plays[0].hooks.started(); f.clock.advance(200000);
    assert.equal(f.requests.length, 2); assert.equal(f.controller.active(), false);
    assert.equal(f.states.at(-1).state, 'playing'); assert.deepEqual(f.stopped, []);
});

test('preparation and video startup have independent deadlines and clean up late sessions', () => {
    const f = fixture(); f.controller.start(f.items);
    f.clock.advance(20000);
    f.reply(0, {id:'late',state:'ready'});
    assert.deepEqual(f.stopped, ['late']); assert.equal(f.plays.length, 0);
    f.reply(1, {id:'slow-video',state:'ready'});
    f.clock.advance(15000);
    assert.equal(f.requests[2].body.selection_id, 'choice-2');
    assert.deepEqual(f.stopped, ['late','slow-video']);
    f.plays[0].hooks.started(); // A stale event must not accept the old source.
    assert.equal(f.controller.active(), true);
});

test('a decoding failure skips the source, but account and rate-limit failures end the run', () => {
    for (const status of [401,403,429]) {
        const f = fixture(); f.controller.start(f.items);
        f.reply(0, {id:'bad',state:'ready'}); f.plays[0].hooks.failed('Cannot decode');
        assert.equal(f.requests.length, 2); assert.deepEqual(f.stopped, ['bad']);
        f.reply(1, {status,detail:'Account needs attention'}, false);
        assert.equal(f.states.at(-1).state, 'exhausted');
        assert.equal(f.states.at(-1).details.message, 'Account needs attention');
        f.clock.advance(200000); assert.equal(f.requests.length, 2);
    }
});

test('cancellation prevents late preparation from starting playback or another attempt', () => {
    const f = fixture(); f.controller.start(f.items); f.controller.cancel();
    f.reply(0, {id:'late',state:'ready'}); f.clock.advance(200000);
    assert.equal(f.plays.length, 0); assert.equal(f.requests.length, 1);
    assert.deepEqual(f.stopped, ['late']);
});

test('automatic file selection requires a server recommendation and polls no faster than three seconds', () => {
    const f = fixture(); f.controller.start(f.items);
    f.reply(0, {id:'pack',state:'files',recommended_file_id:null});
    assert.equal(f.requests[1].body.selection_id, 'choice-1');
    f.reply(1, {id:'matching-pack',state:'files',recommended_file_id:20});
    assert.deepEqual(f.requests[2].body, {file_id:20});
    f.reply(2, {id:'matching-pack',state:'preparing',retry_after:1});
    f.clock.advance(2999); assert.equal(f.requests.length, 3);
    f.clock.advance(1); assert.equal(f.requests[3].method, 'GET');
    f.reply(3, {id:'matching-pack',state:'ready'}); f.plays[0].hooks.started();
});

test('gesture blocking pauses the deadline and resumes on the same source', () => {
    const f = fixture(); f.controller.start(f.items);
    f.reply(0, {id:'needs-gesture',state:'ready'}); f.plays[0].hooks.blocked();
    f.clock.advance(240000); assert.equal(f.requests.length, 1);
    f.controller.resume(); assert.equal(f.plays.length, 2);
    f.plays[1].hooks.started(); f.clock.advance(240000);
    assert.equal(f.requests.length, 1); assert.equal(f.states.at(-1).state,'playing');
});

test('attempts are deduplicated, capped at eight, and bounded by the total deadline', () => {
    const f = fixture(); f.controller.start([f.items[0], ...f.items]);
    for (let i=0; i<8; i++) { f.reply(i, {status:409}, false); }
    assert.equal(f.requests.length, 8); assert.equal(f.states.at(-1).state,'exhausted');
    const limited = fixture({prepareTimeout:20000,totalTimeout:25000});
    limited.controller.start(limited.items); limited.clock.advance(25000);
    assert.equal(limited.requests.length, 2); assert.equal(limited.states.at(-1).state,'exhausted');
});
