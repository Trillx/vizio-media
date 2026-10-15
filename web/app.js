/* Deliberately ES5 + XMLHttpRequest for an unverified embedded browser. */
(function () {
    'use strict';
    var byId = function (id) { return document.getElementById(id); };
    var video = byId('video');
    var session = 'tv-' + new Date().getTime() + '-' + Math.floor(Math.random() * 1000000);
    var mode = 'home', row = 1, col = 0, focused = null;
    var homeRows = [['nav-home', 'nav-watchlist', 'nav-search', 'nav-accounts', 'nav-profile', 'nav-remote', 'nav-checks'], ['genre-all','genre-comedy','genre-horror','genre-science-fiction','genre-animation'], ['hero-details']];
    var rows = homeRows, previousFocus = 'hero-details';
    var playerButton = 'toggle-play';
    var saved = { position: 0, duration: 0 }, resumeAt = 0, progressTicket = 0;
    var pendingProgress = null, savingProgress = false;
    var streamMedia = null, streamReturn = null, streamSaved = null;
    var streamHooks = null, streamStarted = false, streamPlaying = false, streamProofPosition = 0, mediaSerial = 0;
    var progressQueue = [];
    var refreshAfterSave = false;
    var lastSave = 0, hudTimer = null, toastTimer = null;
    var lastRemote = 'No button received yet', remoteLog = [], videoState = 'Not started';
    var checks = { navigation: 'Not tested', picture: 'Not tested', audio: 'Not tested', resume: 'Not tested' };
    var checkLabels = { navigation: 'D-pad, OK, and Back', picture: 'Video plays and seeks', audio: 'Music and effects are audible', resume: 'Playback resumes after returning' };
    var titles = {
        bunny: { name: 'Big Buck Bunny', description: 'A large rabbit takes on three troublesome woodland neighbors. This 33-second trailer is the playable hardware test.', meta: '2008 / Blender Foundation / Animation', available: true },
        sintel: { name: 'Sintel', description: 'A young traveler searches for a dragon. This sample card tests navigation and film details. No video is included for this title.', meta: '2010 / Blender Foundation / Fantasy', available: false },
        dream: { name: 'Elephants Dream', description: 'Two characters explore a strange mechanical world. This sample card tests navigation and film details. No video is included for this title.', meta: '2006 / Blender Foundation / Animation', available: false }
    };

    function text(node, value) { node.textContent = String(value); }
    function visible(node, show) {
        if (show) { node.removeAttribute('hidden'); } else { node.setAttribute('hidden', 'hidden'); }
    }
    function escapeHtml(value) {
        return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function request(method, path, payload, callback, timeout) {
        var xhr = new XMLHttpRequest();
        xhr.open(method, path, true);
        xhr.timeout = timeout || 20000;
        if (payload !== null) {
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('X-Vizio-Media', '1');
        }
        function complete() {
            if (!callback) { return; }
            var result = null;
            try { result = JSON.parse(xhr.responseText); } catch (ignored) { /* Report failed request below. */ }
            if (xhr.status < 200 || xhr.status >= 300) { result = result || {}; result.status = xhr.status; }
            callback(xhr.status >= 200 && xhr.status < 300, result);
            callback = null;
        }
        xhr.onload = complete;
        xhr.onerror = complete;
        xhr.ontimeout = complete;
        xhr.send(payload === null ? null : JSON.stringify(payload));
    }
    function log(kind, payload) {
        request('POST', '/api/diagnostics', { session_id: session, kind: kind, payload: payload }, null);
    }
    function toast(message) {
        text(byId('toast'), message);
        visible(byId('toast'), true);
        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () { visible(byId('toast'), false); }, 6000);
    }
    function time(seconds) {
        seconds = isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0;
        return Math.floor(seconds / 60) + ':' + (seconds % 60 < 10 ? '0' : '') + (seconds % 60);
    }
    function scale() {
        var width = window.innerWidth || document.documentElement.clientWidth || 1920;
        var height = window.innerHeight || document.documentElement.clientHeight || 1080;
        var ratio = Math.min(width / 1920, height / 1080);
        var stage = byId('stage');
        stage.style.transform = 'scale(' + ratio + ')';
        stage.style.webkitTransform = 'scale(' + ratio + ')';
        stage.style.left = Math.round((width - 1920 * ratio) / 2) + 'px';
        stage.style.top = Math.round((height - 1080 * ratio) / 2) + 'px';
    }
    function focusAt(nextRow, nextCol) {
        row = nextRow; col = nextCol;
        if (focused) { focused.className = focused.className.replace(/\s*focused/g, ''); }
        focused = byId(rows[row][col]);
        if (focused) { focused.className += ' focused'; focused.focus(); }
        if (mode === 'home' && focused && window.VizioHome) { window.VizioHome.focused(focused); }
        if (mode === 'player' && focused) {
            if (focused.id !== 'timeline') { playerButton = focused.id; }
            var backHint = streamMedia ? 'Sources' : 'Library';
            byId('player-help').innerHTML = focused.id === 'timeline' ?
                '<span class="hint"><span class="keycap">Left / Right</span>Seek 10s</span><span class="hint"><span class="keycap">Down</span>Buttons</span><span class="hint"><span class="keycap">OK</span>Play / pause</span><span class="hint"><span class="keycap">Back</span>' + backHint + '</span>' :
                '<span class="hint"><span class="keycap">Left / Right</span>Choose button</span><span class="hint"><span class="keycap">OK</span>Select</span><span class="hint"><span class="keycap">Up</span>Timeline</span><span class="hint"><span class="keycap">Back</span>' + backHint + '</span>';
            hud();
        }
    }
    function focusId(id) {
        var r, c;
        for (r = 0; r < rows.length; r += 1) {
            for (c = 0; c < rows[r].length; c += 1) {
                if (rows[r][c] === id) { focusAt(r, c); return; }
            }
        }
        focusAt(0, 0);
    }
    function setMode(nextMode, nextRows, id) {
        mode = nextMode; rows = nextRows; focusId(id);
    }
    function canResume() { return saved.position > 1 && saved.position < saved.duration - 2; }
    function updateProgress(notifyHome) {
        text(byId('play-label'), canResume() ? 'Resume test clip' : 'Play test clip');
        text(byId('resume-note'), canResume() ? 'Saved at ' + time(saved.position) + '. Film details lets you restart.' : 'Picture, sound, and remote. Start here.');
        byId('card-progress-fill').style.width = (saved.duration ? Math.min(100, saved.position / saved.duration * 100) : 0) + '%';
        if (notifyHome !== false && window.VizioHome) { window.VizioHome.progress(saved); }
    }
    function dialog(kind) {
        if (kind !== 'extra' && window.VizioExtras) { window.VizioExtras.dismiss(); }
        if (mode === 'home' && focused) { previousFocus = focused.id; }
        visible(byId('dialog'), true);
        if (kind === 'remote') { renderRemote(); }
        if (kind === 'checks') { renderChecks(); }
    }
    function closeDialog() {
        if (window.VizioExtras) { window.VizioExtras.dismiss(); }
        visible(byId('dialog'), false);
        setMode('home', homeRows, previousFocus);
    }
    function details(id) {
        var title = titles[id] || titles.bunny;
        dialog('details');
        text(byId('dialog-title'), title.name);
        var actions = '<button id="detail-remote" class="button secondary" data-action="remote">Remote check</button>';
        var ids = ['detail-remote'];
        if (title.available) {
            actions = '<button id="detail-start" class="button primary" data-action="play-start">Play from start</button>' + actions;
            ids.unshift('detail-start');
            if (canResume()) {
                actions = '<button id="detail-resume" class="button primary" data-action="play">Resume at ' + time(saved.position) + '</button>' + actions;
                ids.unshift('detail-resume');
            }
        }
        var posterClass = id === 'sintel' ? 'sintel' : (id === 'dream' ? 'dream' : 'bunny');
        byId('dialog-content').innerHTML = '<div class="film-details"><div class="detail-poster ' + posterClass + '" aria-hidden="true"><span>' + escapeHtml(title.name) + '</span></div><div class="detail-copy"><p class="detail-meta">' + escapeHtml(title.meta) + '</p><p>' + escapeHtml(title.description) + '</p>' +
            (title.available ? '<p class="availability">H.264 video and AAC stereo. Volume stays on your TV remote.</p>' : '<p class="availability">Choose Big Buck Bunny in the library to test playback.</p>') +
            '<div class="dialog-actions">' + actions + '</div>' +
            '<p class="attribution">(c) copyright 2008, Blender Foundation / www.bigbuckbunny.org<br>Trailer used under Creative Commons Attribution 3.0. Sample-card illustrations are original.</p></div></div>';
        setMode('details', [['dialog-close'], ids], ids[0]);
    }
    function capabilities() {
        var probe = document.createElement('video');
        var codec = probe.canPlayType ? probe.canPlayType('video/mp4; codecs="avc1.42E01E, mp4a.40.2"') : '';
        return { user_agent: navigator.userAgent.slice(0, 512), viewport: (window.innerWidth || 0) + ' x ' + (window.innerHeight || 0), h264_aac: codec || 'No support reported', session: session };
    }
    function renderRemote() {
        var info = capabilities();
        text(byId('dialog-title'), 'Check your remote');
        byId('dialog-content').innerHTML = '<p>Press the D-pad, OK, Back, or media buttons. The readout records what this browser actually receives. Volume may stay with the TV.</p>' +
            '<div class="diagnostic-grid"><div><div class="readout">Last input</div><div id="remote-last">' + escapeHtml(lastRemote) + '</div><div id="remote-log" class="event-log"></div></div>' +
            '<div class="readout"><strong>Browser</strong><span class="browser-agent">' + escapeHtml(info.user_agent) + '</span><strong>Viewport</strong> ' + escapeHtml(info.viewport) + '<br><strong>H.264 / AAC report</strong> ' + escapeHtml(info.h264_aac) + '<br><strong>Video state</strong> ' + escapeHtml(videoState) + '</div></div>' +
            '<div class="dialog-actions"><button id="remote-test" class="button primary" data-action="play-start">Play test clip</button><button id="remote-checks" class="button secondary" data-action="checks">Record results</button></div>';
        updateRemote();
        setMode('remote', [['dialog-close'], ['remote-test', 'remote-checks']], 'remote-test');
    }
    function updateRemote() {
        if (byId('remote-last')) { text(byId('remote-last'), lastRemote); }
        if (byId('remote-log')) { byId('remote-log').innerHTML = remoteLog.map(escapeHtml).join('<br>'); }
    }
    function renderChecks() {
        text(byId('dialog-title'), 'What works on this TV?');
        var content = '<p>Select each row to cycle through Not tested, Pass, and Fail. Record sound by listening on the TV. A browser cannot confirm audible output.</p>';
        var checkRows = [['dialog-close']], key;
        for (key in checkLabels) {
            if (Object.prototype.hasOwnProperty.call(checkLabels, key)) {
                content += '<button id="check-' + key + '" class="check-row" data-action="check" data-check="' + key + '" data-result="' + checks[key] + '">' + checkLabels[key] + '<span>' + checks[key] + '</span></button>';
                checkRows.push(['check-' + key]);
            }
        }
        content += '<p class="attribution">Results and button events are saved locally. Reloading this page starts a fresh checklist. Recent results remain in /api/diagnostics.</p>';
        byId('dialog-content').innerHTML = content;
        setMode('checks', checkRows, 'check-navigation');
    }
    function cycleCheck(key) {
        var options = ['Not tested', 'Pass', 'Fail'];
        checks[key] = options[(options.indexOf(checks[key]) + 1) % 3];
        byId('check-' + key).setAttribute('data-result', checks[key]);
        text(byId('check-' + key).getElementsByTagName('span')[0], checks[key]);
        request('POST', '/api/diagnostics', { session_id: session, kind: 'check', payload: { test: key, result: checks[key] } }, function (ok) {
            if (!ok) { toast('Result was not saved. Check the server connection.'); }
        });
    }
    function flushProgress() {
        if (pendingProgress !== null) {
            var entry = pendingProgress, i;
            pendingProgress = null;
            for (i = progressQueue.length - 1; i >= 0; i -= 1) {
                if (progressQueue[i].path === entry.path) { progressQueue.splice(i, 1); }
            }
            progressQueue.push(entry);
        }
        if (savingProgress || !progressQueue.length) { return; }
        var snapshot = progressQueue.shift();
        savingProgress = true;
        request('PUT', snapshot.path, snapshot.body, function (ok) {
            savingProgress = false;
            if (!ok) { toast('Playback position was not saved. Check the server connection.'); }
            flushProgress();
            if (!savingProgress && !progressQueue.length && refreshAfterSave && window.VizioHome) {
                refreshAfterSave = false; window.VizioHome.refreshPersonal();
            }
        });
    }
    function saveProgress(force) {
        if (streamHooks && !streamStarted) { return; }
        if (!isFinite(video.duration) || video.duration <= 0 || !isFinite(video.currentTime)) { return; }
        var now = new Date().getTime();
        if (!force && now - lastSave < 5000) { return; }
        lastSave = now;
        var position = { position: Math.min(video.currentTime, video.duration), duration: video.duration };
        if (streamMedia) { streamSaved = position; }
        else { saved = position; updateProgress(); }
        // Serialize writes so a slow earlier request cannot overwrite a later seek.
        pendingProgress = {path: streamMedia ? '/api/playback/' + streamMedia.id + '/progress' : '/api/progress/big-buck-bunny', body: position};
        flushProgress();
    }
    function hud() {
        byId('player-hud').className = 'player-hud';
        clearTimeout(hudTimer);
        // Leave the timeline visible while the user is choosing a position.
        if (!video.paused && !video.ended && (!focused || focused.id !== 'timeline')) {
            hudTimer = setTimeout(function () { byId('player-hud').className = 'player-hud quiet'; }, 6500);
        }
    }
    function playerStatus(message) { videoState = message; text(byId('player-status'), message); }
    function playButton(label) {
        text(byId('toggle-label'), label);
        byId('toggle-play').setAttribute('data-state', label === 'Pause' ? 'pause' : 'play');
    }
    function play() {
        // Legacy browsers return undefined; modern browsers return a Promise.
        var current = mediaSerial;
        var result = video.play();
        if (result && result['catch']) {
            result['catch'](function (error) {
                if (current !== mediaSerial || mode !== 'player' || error.name === 'AbortError') { return; }
                if (streamHooks && !streamStarted) {
                    if (error.name === 'NotAllowedError') { streamHooks.blocked(); }
                    else { streamHooks.failed('This video could not start.'); }
                    return;
                }
                playerStatus('Playback did not start. Press OK to retry. ' + error.name);
                log('error', { message: 'play rejected', name: error.name });
                hud();
            });
        }
    }
    function startVideo(fromBeginning) {
        mediaSerial += 1; streamHooks = null; streamStarted = false;
        streamMedia = null; streamReturn = null; streamSaved = null;
        byId('close-player').lastChild.nodeValue = 'Library';
        if (mode === 'home' && focused) { previousFocus = focused.id; }
        visible(byId('dialog'), false);
        visible(byId('player'), true);
        setMode('player', [['timeline'], ['seek-back', 'toggle-play', 'seek-forward', 'close-player']], 'toggle-play');
        resumeAt = !fromBeginning && canResume() ? saved.position : 0;
        playerStatus('Loading the local trailer...');
        text(byId('player-title'), 'Big Buck Bunny');
        text(byId('player-attribution'), 'Blender Foundation / CC BY 3.0');
        video.setAttribute('aria-label', 'Big Buck Bunny trailer');
        video.src = '/media/sample.mp4';
        video.load();
        play();
        hud();
    }
    function closePlayer() {
        if (mode !== 'player') { return; }
        refreshAfterSave = true;
        saveProgress(true);
        mediaSerial += 1; streamHooks = null;
        video.pause();
        clearTimeout(hudTimer);
        visible(byId('player'), false);
        video.removeAttribute('src');
        video.load();
        setMode('home', homeRows, previousFocus);
        var returning = streamReturn;
        streamMedia = null; streamReturn = null; streamSaved = null;
        if (!savingProgress && !progressQueue.length && window.VizioHome) { refreshAfterSave = false; window.VizioHome.refreshPersonal(); }
        if (returning) { returning(); }
    }
    function stopStreamAttempt() {
        mediaSerial += 1; streamHooks = null; streamStarted = false; streamPlaying = false;
        streamMedia = null; streamReturn = null; streamSaved = null;
        video.pause(); clearTimeout(hudTimer);
        visible(byId('player'), false); video.removeAttribute('src'); video.load();
        if (mode === 'player') { setMode('home', homeRows, previousFocus); }
    }
    function togglePlay() { if (video.paused || video.ended) { play(); } else { video.pause(); } hud(); }
    function updateTimeline() {
        var duration = isFinite(video.duration) && video.duration > 0 ? video.duration : 0;
        var position = isFinite(video.currentTime) ? video.currentTime : 0;
        var percent = duration ? Math.max(0, Math.min(100, position / duration * 100)) : 0;
        byId('timeline-fill').style.width = percent + '%';
        byId('timeline-thumb').style.left = percent + '%';
        byId('timeline').setAttribute('aria-valuemax', String(duration));
        byId('timeline').setAttribute('aria-valuenow', String(Math.round(position * 10) / 10));
        byId('timeline').setAttribute('aria-valuetext', time(position) + ' of ' + time(duration));
        text(byId('elapsed'), time(position));
        text(byId('duration'), time(duration));
    }
    function seekTo(position) {
        if (isFinite(video.duration) && video.duration > 0) {
            video.currentTime = Math.max(0, Math.min(video.duration - 0.1, position));
            updateTimeline();
        }
        hud();
    }
    function seek(offset) { seekTo(video.currentTime + offset); }
    function activate(button) {
        var action = button.getAttribute('data-action');
        if (action === 'play') { startVideo(false); }
        if (action === 'play-start') { startVideo(true); }
        if (action === 'details') { details(button.getAttribute('data-title')); }
        if (action === 'remote' || action === 'checks') { dialog(action); }
        if (action === 'home') { if (window.VizioHome) { window.VizioHome.reset(); } else { setMode('home', homeRows, 'hero-details'); } }
        if (action === 'close-dialog') { closeDialog(); }
        if (action === 'close-player') { closePlayer(); }
        if (action === 'toggle-play') { togglePlay(); }
        if (action === 'seek-position') { togglePlay(); }
        if (action === 'seek-back') { seek(-10); }
        if (action === 'seek-forward') { seek(10); }
        if (action === 'check') { cycleCheck(button.getAttribute('data-check')); }
        if (window.VizioExtras) { window.VizioExtras.activate(action, button); }
        if (window.VizioHome) { window.VizioHome.activate(action, button); }
    }
    function onKey(event) {
        var action = window.VizioRemote.action(event);
        // Input text and PINs must never enter the remote diagnostic log.
        if (window.VizioExtras && window.VizioExtras.key(event, action)) { return; }
        var code = event.keyCode || event.which || 0;
        if (mode !== 'extra') {
            lastRemote = (event.key || 'unnamed') + ' / code ' + code + ' / ' + (action || 'unmapped');
            text(byId('last-key'), lastRemote);
            remoteLog.unshift(lastRemote); remoteLog = remoteLog.slice(0, 5); updateRemote();
            if (!event.repeat) { log('key', { key: String(event.key || '').slice(0, 64), code: code, action: action, mode: mode }); }
        }
        if (!action) { return; }
        event.preventDefault();
        event.stopPropagation();
        if (event.repeat && (action === 'select' || action === 'back' || action === 'toggle')) { return; }
        if (action === 'back') {
            if (mode === 'player') { closePlayer(); }
            else if (window.VizioExtras && window.VizioExtras.back()) { return; }
            else if (mode !== 'home') { closeDialog(); }
            else if (window.VizioHome && window.VizioHome.back()) { return; }
            else { focusId('hero-details'); toast('You are in the library. Use the Vizio Home button to leave.'); }
            return;
        }
        if (mode === 'player') {
            var wasQuiet = byId('player-hud').className.indexOf('quiet') !== -1;
            hud();
            // The first navigation press reveals hidden controls without activating one.
            if (wasQuiet && (action === 'left' || action === 'right' || action === 'up' || action === 'down' || action === 'select')) { return; }
            if (action === 'rewind') { seek(-10); return; }
            if (action === 'forward') { seek(10); return; }
            if (focused.id === 'timeline' && action === 'left') { seek(-10); return; }
            if (focused.id === 'timeline' && action === 'right') { seek(10); return; }
            if (action === 'up') { focusId('timeline'); return; }
            if (action === 'down') { focusId(playerButton); return; }
            if (action === 'toggle') { togglePlay(); return; }
            if (action === 'play') { play(); return; }
            if (action === 'pause') { video.pause(); return; }
            if (action === 'stop') { closePlayer(); return; }
        }
        if (action === 'select' && focused) { activate(focused); return; }
        if (action === 'left' || action === 'right' || action === 'up' || action === 'down') {
            var next = window.VizioRemote.move(rows, row, col, action);
            focusAt(next.row, next.col);
        }
    }
    document.addEventListener('keydown', onKey, true);
    function actionTarget(target) {
        while (target && target !== document) {
            if (target.getAttribute && target.getAttribute('data-action')) { return target; }
            target = target.parentNode;
        }
        return null;
    }
    document.addEventListener('click', function (event) {
        var target = actionTarget(event.target);
        if (mode === 'player') { hud(); }
        if (!target) { return; }
        focusId(target.id);
        if (target.id === 'timeline') {
            var bounds = byId('timeline-track').getBoundingClientRect();
            if (bounds.width > 0) { seekTo((event.clientX - bounds.left) / bounds.width * video.duration); }
        } else { activate(target); }
    }, false);
    document.addEventListener('mousemove', function () { if (mode === 'player') { hud(); } }, false);
    document.addEventListener('mouseover', function (event) {
        if (mode !== 'player') { return; }
        var target = actionTarget(event.target);
        if (target && target !== focused) { focusId(target.id); }
    }, false);
    // Keep Tab within the same explicit focus model used by the remote.
    document.addEventListener('keydown', function (event) {
        if ((event.keyCode || event.which) === 9) {
            event.preventDefault();
            if (mode === 'player') { hud(); }
            if (event.shiftKey) {
                if (col > 0) { focusAt(row, col - 1); }
                else { var prev = (row + rows.length - 1) % rows.length; focusAt(prev, rows[prev].length - 1); }
            } else if (col + 1 < rows[row].length) { focusAt(row, col + 1); }
            else { focusAt((row + 1) % rows.length, 0); }
        }
    }, false);
    video.addEventListener('loadedmetadata', function () {
        if (resumeAt > 0) { video.currentTime = Math.min(resumeAt, video.duration - 0.1); resumeAt = 0; }
        streamProofPosition = video.currentTime;
        updateTimeline();
        log('video', { event: 'loadedmetadata', duration: video.duration, width: video.videoWidth, height: video.videoHeight });
    }, false);
    video.addEventListener('timeupdate', function () {
        updateTimeline();
        if (mode === 'player' && streamHooks && !streamStarted && streamPlaying && !video.paused && !video.seeking &&
                video.readyState >= 2 && video.videoWidth > 0 && video.currentTime > streamProofPosition + 0.25) {
            streamStarted = true; streamHooks.started();
        }
        if (mode === 'player') { saveProgress(false); }
    }, false);
    video.addEventListener('playing', function () {
        streamPlaying = true;
        playerStatus(streamMedia ? 'Playing through Real-Debrid.' : 'Playing locally. Listen for music and effects.');
        playButton('Pause'); hud();
        log('video', { event: 'playing', position: video.currentTime });
    }, false);
    video.addEventListener('pause', function () {
        playButton('Play');
        if (mode === 'player') { playerStatus('Paused'); saveProgress(true); hud(); }
    }, false);
    video.addEventListener('seeked', function () { if (mode === 'player') { saveProgress(true); } }, false);
    video.addEventListener('waiting', function () { if (mode === 'player') { playerStatus(streamMedia ? 'Buffering video...' : 'Buffering the local file...'); hud(); } }, false);
    video.addEventListener('ended', function () {
        if (mode !== 'player') { return; }
        saveProgress(true); playerStatus(streamMedia ? 'Finished. Back returns to sources.' : 'Trailer finished. Back returns to the library.');
        playButton('Replay'); hud();
        log('video', { event: 'ended', position: video.currentTime });
    }, false);
    video.addEventListener('error', function () {
        if (mode !== 'player') { return; }
        var code = video.error ? video.error.code : 0;
        if (streamHooks && !streamStarted) { streamHooks.failed('This video format or connection did not work.'); return; }
        var messages = { 1: 'Playback was interrupted.', 2: 'The video could not be downloaded. Check the server and Wi-Fi. Go back and retry the source.', 3: 'The TV could not decode this video or audio. Go back and try an H.264/AAC source.', 4: 'The TV rejected this video format. Go back and choose another source.' };
        playerStatus((messages[code] || 'Unknown video error.') + ' Error code ' + code);
        log('error', { message: 'video error', code: code, ready_state: video.readyState, network_state: video.networkState }); hud();
    }, false);
    window.addEventListener('resize', scale, false);
    window.addEventListener('pagehide', function () { if (mode === 'player') { saveProgress(true); } }, false);
    document.addEventListener('visibilitychange', function () {
        if (document.hidden && mode === 'player') { saveProgress(true); video.pause(); }
    }, false);
    window.addEventListener('error', function (event) {
        log('error', { message: String(event.message || 'script error').slice(0, 512), line: event.lineno || 0 });
    }, false);
    window.VizioApp = {
        request: request, escape: escapeHtml, text: text, toast: toast, focus: focusId,
        open: function (title, html, nextRows, id) {
            dialog('extra'); text(byId('dialog-title'), title); byId('dialog-content').innerHTML = html;
            setMode('extra', [['dialog-close']].concat(nextRows), id || 'dialog-close');
        },
        close: closeDialog,
        homeRows: function (nextRows, preferred) {
            homeRows = nextRows;
            if (mode === 'home') { rows = homeRows; focusId(preferred || (focused && focused.id) || 'hero-details'); }
        },
        play: function () { if (window.VizioExtras) { window.VizioExtras.dismiss(); } startVideo(true); },
        stopStreamAttempt: stopStreamAttempt,
        playStream: function (media, fromBeginning, returning, hooks) {
            stopStreamAttempt();
            streamMedia = media; streamReturn = returning; streamSaved = media.progress || {position: 0, duration: 0};
            streamHooks = hooks || null; streamStarted = !hooks; streamPlaying = false;
            byId('close-player').lastChild.nodeValue = 'Sources';
            resumeAt = !fromBeginning && streamSaved.position > 1 && streamSaved.position < streamSaved.duration - 2 ? streamSaved.position : 0;
            if (mode === 'home' && focused) { previousFocus = focused.id; }
            visible(byId('dialog'), false); visible(byId('player'), true);
            text(byId('player-title'), media.title); text(byId('player-attribution'), 'Real-Debrid');
            video.setAttribute('aria-label', media.title);
            setMode('player', [['timeline'], ['seek-back', 'toggle-play', 'seek-forward', 'close-player']], 'toggle-play');
            playerStatus('Loading video...'); lastSave = 0;
            video.src = media.stream; video.load(); play(); hud();
        },
        reloadProgress: function () {
            var current = ++progressTicket;
            pendingProgress = null;
            progressQueue = [];
            saved = {position: 0, duration: 0}; updateProgress(false);
            request('GET', '/api/progress/big-buck-bunny', null, function (ok, data) {
                if (ok && current === progressTicket) { saved = {position: data.position, duration: data.duration}; updateProgress(); }
            });
        }
    };
    scale(); focusId('hero-details');
    request('GET', '/api/health', null, function (ok, data) {
        text(byId('connection'), ok ? (data.media_ready ? 'Local server ready' : 'Test clip missing') : 'Server unreachable');
        if (ok) { byId('connection').className += ' connected'; }
        if (ok && !data.media_ready) { toast('Download the test clip on the computer before starting playback.'); }
    });
    window.VizioApp.reloadProgress();
    log('capabilities', capabilities());
}());
