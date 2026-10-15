/* Bounded automatic source attempts. A source succeeds only after video advances. */
(function (root, factory) {
    'use strict';
    if (typeof module === 'object' && module.exports) { module.exports = factory(); }
    else { root.VizioAutoPlay = factory(); }
}(typeof window !== 'undefined' ? window : this, function () {
    'use strict';
    function create(adapter, options) {
        options = options || {};
        var clock = options.clock || {
            setTimeout: function (callback, delay) { return setTimeout(callback, delay); },
            clearTimeout: function (id) { clearTimeout(id); },
            now: function () { return new Date().getTime(); }
        };
        var prepareMs = options.prepareTimeout || 20000, startupMs = options.startupTimeout || 15000;
        var totalMs = options.totalTimeout || 180000, maximum = options.maxSources || 8;
        var queue = [], index = -1, active = false, serial = 0, session = '', media = null;
        var timer = null, poll = null, overall = null, began = 0, blockedAt = null;
        function clearAttempt() { clock.clearTimeout(timer); clock.clearTimeout(poll); timer = null; poll = null; }
        function clearAll() { clearAttempt(); clock.clearTimeout(overall); overall = null; }
        function emit(state, details) {
            adapter.state({state: state, index: index, count: queue.length, source: queue[index], details: details || {}});
        }
        function discard(id) { if (id && adapter.stop) { adapter.stop(id); } }
        function alive(value) { return active && serial === value; }
        function finish(message) {
            active = false; serial += 1; clearAll();
            adapter.stopVideo(); discard(session); session = '';
            emit('exhausted', {message: message || 'None of these sources started. Choose a source manually or search again.'});
        }
        function armOverall() {
            clock.clearTimeout(overall);
            overall = clock.setTimeout(function () { finish('Trying sources took too long. Choose a source manually or search again.'); }, Math.max(1, totalMs - (clock.now() - began)));
        }
        function next(reason) {
            if (!active) { return; }
            serial += 1; clearAttempt(); adapter.stopVideo(); discard(session); session = ''; media = null;
            index += 1;
            if (index >= queue.length || clock.now() - began >= totalMs) { finish(); return; }
            var current = serial;
            emit('preparing', {reason: reason || ''});
            timer = clock.setTimeout(function () { if (alive(current)) { next('This source was not ready in time.'); } }, prepareMs);
            adapter.request('POST', '/api/playback', {selection_id: queue[index].selection_id}, function (ok, data) {
                if (!alive(current)) { if (data && data.id) { discard(data.id); } return; }
                receive(current, ok, data);
            }, 45000);
        }
        function failed(current, data) {
            if (!alive(current)) { return; }
            var status = data && data.status;
            if (status === 401 || status === 403 || status === 429) {
                finish((data && data.detail) || 'Check your account or wait before trying again.');
            } else { next((data && data.detail) || 'This source could not start.'); }
        }
        function play(current) {
            if (!alive(current)) { return; }
            clearAttempt(); emit('starting');
            timer = clock.setTimeout(function () { if (alive(current)) { next('The video did not start in time.'); } }, startupMs);
            adapter.play(media, {
                started: function () {
                    if (!alive(current)) { return; }
                    active = false; clearAll(); emit('playing');
                },
                failed: function (message) { if (alive(current)) { next(message || 'This video could not play.'); } },
                blocked: function () {
                    if (!alive(current)) { return; }
                    clearAll(); blockedAt = clock.now(); emit('blocked', media);
                }
            });
        }
        function receive(current, ok, data) {
            if (!alive(current)) { return; }
            if (!ok || !data || !data.id) { failed(current, data); return; }
            session = data.id;
            if (data.state === 'ready') { media = data; play(current); return; }
            if (data.state === 'files') {
                if (data.recommended_file_id === null || data.recommended_file_id === undefined) { next('This source needs a manual file choice.'); return; }
                adapter.request('POST', '/api/playback/' + encodeURIComponent(session) + '/files', {file_id: data.recommended_file_id}, function (good, result) {
                    receive(current, good, result);
                }, 45000);
                return;
            }
            emit('preparing', data);
            poll = clock.setTimeout(function () {
                if (!alive(current)) { return; }
                adapter.request('GET', '/api/playback/' + encodeURIComponent(session), null, function (good, result) { receive(current, good, result); }, 15000);
            }, Math.max(3, data.retry_after || 3) * 1000);
        }
        return {
            start: function (items) {
                if (active) { this.cancel(); }
                var seen = {};
                queue = items.filter(function (item) {
                    var key = item.id || item.selection_id;
                    if (!item.selection_id || seen[key]) { return false; }
                    seen[key] = true; return true;
                }).slice(0, maximum);
                active = true; index = -1; began = clock.now(); blockedAt = null;
                armOverall(); next();
            },
            next: function () { next('Skipped by you.'); },
            resume: function () {
                if (!active || !media || blockedAt === null) { return; }
                began += clock.now() - blockedAt; blockedAt = null; armOverall(); play(serial);
            },
            cancel: function () {
                if (!active) { return; }
                active = false; serial += 1; clearAll(); adapter.stopVideo(); discard(session); session = '';
            },
            active: function () { return active; }
        };
    }
    return {create: create};
}));
