/* Catalog, profiles, and account linking. Compatible with the TV's ES5 baseline. */
(function () {
    'use strict';
    var A = window.VizioApp, esc = A.escape, req = A.request;
    var $ = function (id) { return document.getElementById(id); };
    var view = '', ticket = 0, meTicket = 0, me = null, profileList = [], pinProfile = null;
    var query = '', kind = 'all', page = 1, offset = 0, results = null, keyboard = false, searchError = '';
    var title = null, season = null, episode = null, listOffset = 0, sourceResult = null, sourceOffset = 0, detailOrigin = 'search';
    var flowService = '', flowTick = null, activeFlow = null;
    var names = {trakt: 'Trakt', real_debrid: 'Real-Debrid'};
    function button(id, label, action, value, classes) {
        return '<button id="' + id + '" class="button ' + (classes || 'secondary') + '" data-action="' + action + '"' +
            (value === undefined ? '' : ' data-value="' + esc(value) + '"') + '>' + esc(label) + '</button>';
    }
    function open(next, heading, html, rows, focus) {
        view = next; $('dialog').setAttribute('data-extra', next); A.open(heading, html, rows, focus);
    }
    function fail(data) { return esc((data && data.detail) || 'The server could not complete this request. Try again.'); }
    function load(next, heading, path, callback) {
        var current = ++ticket;
        open(next, heading, '<p role="status">Loading...</p>', [], 'dialog-close');
        req('GET', path, null, function (ok, data) {
            if (current !== ticket || view !== next) { return; }
            if (!ok) {
                open(next, heading, '<p class="error-message" role="alert">' + fail(data) + '</p>' + button('extra-back', 'Go back', 'extra-back'), [['extra-back']], 'extra-back');
                return;
            }
            callback(data);
        });
    }
    function refreshMe(callback) {
        var current = ++meTicket;
        req('GET', '/api/me', null, function (ok, data) {
            if (current !== meTicket) { return; }
            if (ok) { me = data; A.text($('profile-name'), data.profile ? data.profile.name : 'Choose profile'); if (window.VizioHome) { window.VizioHome.profile(data.profile); } }
            if (callback) { callback(ok); }
        });
    }
    function search(start) {
        if ($('catalog-query')) { query = $('catalog-query').value.slice(0, 120); }
        keyboard = false;
        if (start) { page = 1; offset = 0; }
        results = null; searchError = ''; renderSearch();
        var current = ++ticket;
        var path = kind === 'watchlist' ? '/api/catalog/watchlist' : '/api/catalog/search?q=' + encodeURIComponent(query) + '&kind=' + kind + '&page=' + page;
        req('GET', path, null, function (ok, data) {
            if (ticket !== current || view !== 'search') { return; }
            results = ok ? data : null; searchError = ok ? '' : fail(data); renderSearch();
        });
    }
    function renderSearch(focus) {
        var html = '<div class="search-line"><input id="catalog-query" class="tv-input" type="text" maxlength="120" autocomplete="off" aria-label="Search movies and series" placeholder="Title or year" value="' + esc(query) + '">' +
            button('catalog-submit', 'Search', 'catalog-search', undefined, 'primary') + button('catalog-keyboard', keyboard ? 'Hide keyboard' : 'Keyboard', 'catalog-keyboard') + '</div>';
        var rows = [['catalog-query', 'catalog-submit', 'catalog-keyboard']], filters = ['all', 'movie', 'tv', 'watchlist'];
        var labels = ['All titles', 'Movies', 'Series', 'Trakt watchlist'], ids = [], i, r;
        html += '<div class="filter-line">';
        for (i = 0; i < filters.length; i += 1) {
            ids.push('filter-' + filters[i]);
            html += button(ids[i], labels[i], 'catalog-filter', filters[i], kind === filters[i] ? 'selected' : 'secondary');
        }
        html += '</div>'; rows.push(ids);
        if (keyboard) {
            html += '<div class="tv-keyboard" aria-label="On-screen keyboard">';
            var letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
            for (r = 0; r < 6; r += 1) {
                ids = []; html += '<div class="keyboard-row">';
                for (i = r * 6; i < r * 6 + 6; i += 1) {
                    ids.push('key-' + i); html += '<button id="key-' + i + '" class="keyboard-key" data-action="catalog-type" data-value="' + letters.charAt(i) + '">' + letters.charAt(i) + '</button>';
                }
                rows.push(ids); html += '</div>';
            }
            html += '<div class="keyboard-row">' + button('key-space', 'Space', 'catalog-type', ' ', 'keyboard-key wide') + button('key-delete', 'Delete', 'catalog-delete', undefined, 'keyboard-key wide') + button('key-clear', 'Clear', 'catalog-clear', undefined, 'keyboard-key wide') + '</div></div>';
            rows.push(['key-space', 'key-delete', 'key-clear']);
        } else {
            var items = results ? results.items : [], shown = items.slice(offset, offset + 6);
            html += '<p class="catalog-note" role="status">' + (searchError || (!results ? 'Searching...' : results.notice ? esc(results.notice) :
                (kind === 'watchlist' ? 'Your Trakt watchlist' : (query ? 'Results for "' + esc(query) + '"' : 'Explore this week')) + ' / ' + esc(results.source.toUpperCase()) + (results.stale ? ' / Saved results, service unavailable' : ''))) + '</p>';
            html += '<div class="catalog-grid">';
            ids = [];
            for (i = 0; i < shown.length; i += 1) {
                var item = shown[i], id = 'result-' + i;
                ids.push(id);
                html += '<button id="' + id + '" class="catalog-card" data-action="catalog-detail" data-value="' + esc(item.id) + '">' +
                    (item.poster ? '<img src="' + esc(item.poster) + '" alt="">' : '<span class="catalog-placeholder" aria-hidden="true">' + esc(item.title.charAt(0)) + '</span>') +
                    '<span class="catalog-card-copy"><strong>' + esc(item.title) + '</strong><small>' + esc(item.year || 'Year unknown') + ' / ' + (item.kind === 'tv' ? 'Series' : 'Movie') + (item.sample ? ' / Sample' : '') + '</small></span></button>';
                if (ids.length === 3) { rows.push(ids); ids = []; }
            }
            if (ids.length) { rows.push(ids); }
            html += '</div>';
            if (results && !items.length) { html += '<p>No titles found. Try another title or change the filter.</p>'; }
            ids = []; html += '<div class="catalog-pages"><div>';
            if (offset > 0 || page > 1) { html += button('catalog-prev', 'Previous', 'catalog-prev', undefined, 'secondary compact'); ids.push('catalog-prev'); }
            if (results && (offset + 6 < items.length || page < results.total_pages)) { html += button('catalog-next', 'Next', 'catalog-next', undefined, 'secondary compact'); ids.push('catalog-next'); }
            html += '</div><span>' + (results && items.length ? (offset + 1) + '-' + Math.min(offset + 6, items.length) + ' / Page ' + page + ' of ' + results.total_pages : '') + '</span></div>';
            if (ids.length) { rows.push(ids); }
        }
        open('search', 'Find your next watch', html, rows, focus || (keyboard ? 'key-0' : 'catalog-submit'));
    }
    function details(id, origin) {
        detailOrigin = origin || 'search';
        episode = null; season = null; listOffset = 0;
        load('detail', 'Title details', '/api/catalog/' + encodeURIComponent(id), function (data) { title = data; renderDetail(); });
    }
    function renderDetail() {
        var ids = ['catalog-files'], actions = button('catalog-files', 'Find in my Real-Debrid files', 'catalog-sources');
        if (title.kind === 'tv') { ids.unshift('catalog-seasons'); actions = button('catalog-seasons', 'Seasons and episodes', 'catalog-seasons', undefined, 'primary') + actions; }
        if (title.playable) { ids.unshift('catalog-play'); actions = button('catalog-play', 'Play local trailer', 'catalog-play', undefined, 'primary') + actions; }
        var html = '<div class="film-details">' + (title.poster ? '<img class="detail-poster" src="' + esc(title.poster) + '" alt="">' : '') + '<div class="detail-copy"><p class="detail-meta">' + esc(title.year || 'Year unknown') + ' / ' + (title.kind === 'tv' ? 'Series' : 'Movie') + (title.runtime ? ' / ' + esc(title.runtime) + ' min' : '') + '</p>' +
            '<p id="catalog-overview" class="catalog-overview" tabindex="0">' + esc(title.overview) + '</p><p class="catalog-note">' + esc((title.genres || []).join(' / ')) + '</p><div class="dialog-actions">' + actions + '</div><p class="attribution">' + (title.playable ? 'Licensed local test clip.' : 'Catalog metadata does not indicate playback availability. File search checks your linked account.') + '</p></div></div>';
        open('detail', title.title, html, [['catalog-overview'], ids], ids[0]);
    }
    function pagedList(nextView, heading, entries, action, label) {
        var rows = [], html = '', i, visible = entries.slice(listOffset, listOffset + 6);
        for (i = 0; i < visible.length; i += 1) {
            var entry = visible[i], id = 'list-' + i;
            html += button(id, label(entry), action, listOffset + i, 'secondary list-entry'); rows.push([id]);
        }
        if (!entries.length) { html = '<p>No entries available. Season browsing requires TMDB metadata.</p>'; }
        var ids = []; html += '<div class="catalog-pages"><div>';
        if (listOffset > 0) { html += button('list-prev', 'Previous', 'list-prev', undefined, 'secondary compact'); ids.push('list-prev'); }
        if (listOffset + 6 < entries.length) { html += button('list-next', 'Next', 'list-next', undefined, 'secondary compact'); ids.push('list-next'); }
        html += '</div><span>' + entries.length + ' entries</span></div>';
        if (ids.length) { rows.push(ids); }
        open(nextView, heading, html, rows, visible.length ? 'list-0' : 'dialog-close');
    }
    function renderSeasons() { pagedList('seasons', title.title, title.seasons || [], 'catalog-season', function (s) { return s.name + ' / ' + s.episode_count + ' episodes'; }); }
    function renderEpisodes() { pagedList('episodes', season.name, season.episodes, 'catalog-episode', function (e) { return e.number + '. ' + e.name; }); }
    function renderEpisode() {
        open('episode', episode.number + '. ' + episode.name, '<p class="detail-meta">' + esc(title.title) + ' / Season ' + season.number + '</p><p class="catalog-overview">' + esc(episode.overview) + '</p>' + button('episode-files', 'Find episode in my files', 'catalog-sources', undefined, 'primary'), [['episode-files']], 'episode-files');
    }
    function sources() {
        var suffix = episode ? '?season=' + season.number + '&episode=' + episode.number : '';
        sourceOffset = 0;
        load('sources', 'Your Real-Debrid files', '/api/catalog/' + encodeURIComponent(title.id) + '/sources' + suffix, function (data) { sourceResult = data; renderSources(); });
    }
    function renderSources() {
        var items = sourceResult.items.slice(sourceOffset, sourceOffset + 4), html = '<p class="catalog-note">' + esc(sourceResult.notice) + '</p>', i;
        for (i = 0; i < items.length; i += 1) {
            html += '<div class="source-item"><span title="' + esc(items[i].filename) + '">' + esc(items[i].filename) + '</span><small>' + esc(items[i].status) + ' / ' + (items[i].size / 1073741824).toFixed(2) + ' GB / Filename match ' + Math.round(items[i].match_score * 100) + '%</small></div>';
        }
        if (!items.length) { html += '<p>No matching filenames in the first 100 downloads and 100 torrents. Check the title and linked account.</p>'; }
        var ids = ['source-back']; html += '<div class="dialog-actions">' + button('source-back', 'Back to title', 'extra-back');
        if (sourceOffset > 0) { html += button('sources-prev', 'Previous', 'sources-prev'); ids.push('sources-prev'); }
        if (sourceOffset + 4 < sourceResult.items.length) { html += button('sources-next', 'Next', 'sources-next'); ids.push('sources-next'); }
        html += '</div>'; open('sources', 'Your Real-Debrid files', html, [ids], ids[0]);
    }
    function accounts() {
        load('accounts', 'Your accounts', '/api/me', function (data) {
            me = data;
            if (window.VizioHome) { window.VizioHome.profile(data.profile); window.VizioHome.refreshPersonal(); }
            if (!me.profile) { profiles(); return; }
            var html = '<p>Connected services for ' + esc(me.profile.name) + '. Each profile keeps its own accounts.</p><div class="account-columns">', rows = [], i;
            var services = ['trakt', 'real_debrid'];
            for (i = 0; i < services.length; i += 1) {
                var service = services[i], state = me.accounts[service], connected = state.state === 'connected';
                html += '<section class="account-service"><h3>' + names[service] + '</h3><span class="account-state ' + (connected ? '' : 'disconnected') + '">' + (connected ? 'Connected / ' + esc(state.display_name) : state.state === 'reconnect_required' ? 'Reconnect required' : 'Disconnected') + '</span><p>' + (service === 'trakt' ? 'Bring your watchlist to the catalog.' : 'Search filenames in your account library.') + '</p>';
                if (connected || state.state === 'reconnect_required') { html += button('unlink-' + service, 'Disconnect', 'account-unlink', service); rows.push('unlink-' + service); }
                else if (state.configured) { html += button('link-' + service, 'Connect ' + names[service], 'account-link', service, 'primary'); rows.push('link-' + service); }
                else { html += '<p class="catalog-note">Finish service setup in Account manager on this PC.</p>'; }
                html += '</section>';
            }
            html += '</div><p class="catalog-note">Use Account manager on the server, or its SSH tunnel, to add application settings, manage profiles, or enter a Real-Debrid personal token.</p><div class="dialog-actions">' + button('account-profiles', 'Change profile', 'profiles') + button('account-credits', 'Credits', 'credits') + '</div>';
            open('accounts', 'Your accounts', html, (rows.length ? [rows] : []).concat([['account-profiles', 'account-credits']]), rows[0] || 'account-profiles');
        });
    }
    var linker = window.VizioLink(req, {start: function (s) { return '/api/accounts/' + s + '/start'; }, flow: function (id) { return '/api/flows/' + id; }}, function (flow, error) {
        if (view !== 'link') { return; }
        activeFlow = flow;
        if (flow && flow.state === 'connected') { clearInterval(flowTick); A.toast(names[flowService] + ' connected.'); accounts(); return; }
        renderFlow(flow, error);
    });
    function renderFlow(flow, error) {
        var pending = flow && flow.state === 'pending';
        var html = pending ? '<p>On your phone or computer, open</p><div class="device-address">' + esc(flow.verification_url) + '</div><div class="device-code">' + esc(flow.user_code) + '</div><p>Enter this code and approve the connection for ' + esc(me.profile.name) + '.</p><p id="flow-countdown" class="catalog-note"></p>' : '';
        html += '<p class="flow-status" role="status">' + (error ? esc(error) : pending ? 'Waiting for approval. This screen checks automatically.' : 'Sign-in ' + esc(flow ? flow.state : 'could not start') + '. Return to Accounts and try again.') + '</p>' + button('flow-cancel', pending ? 'Cancel sign-in' : 'Back to accounts', 'account-cancel');
        open('link', 'Connect ' + names[flowService], html, [['flow-cancel']], 'flow-cancel');
        updateCountdown();
    }
    function updateCountdown() {
        if ($('flow-countdown') && activeFlow) { var seconds = Math.max(0, Math.ceil(activeFlow.expires_at - Date.now() / 1000)); A.text($('flow-countdown'), 'Code expires in ' + Math.floor(seconds / 60) + ':' + (seconds % 60 < 10 ? '0' : '') + seconds % 60); }
    }
    function profiles() {
        load('profiles', 'Who is watching?', '/api/profiles', function (data) {
            profileList = data.profiles;
            var html = '<p>Choose a household profile. Manage names, PINs, and accounts on the server computer.</p><div class="profile-grid">', rows = [], ids = [], i;
            for (i = 0; i < profileList.length; i += 1) {
                ids.push('profile-' + i);
                html += '<button id="profile-' + i + '" class="button secondary profile-choice" data-action="profile-choose" data-value="' + i + '">' + esc(profileList[i].name) + '<small>' + (profileList[i].requires_pin ? 'PIN required' : 'Select profile') + '</small></button>';
                if (ids.length === 4) { rows.push(ids); ids = []; }
            }
            if (ids.length) { rows.push(ids); }
            html += '</div>';
            if (me && me.profile) { html += button('profile-lock', 'Lock current profile', 'profile-lock'); rows.push(['profile-lock']); }
            open('profiles', 'Who is watching?', html, rows, 'profile-0');
        });
    }
    function renderPin(error) {
        var html = '<p>Enter the PIN for ' + esc(pinProfile.name) + '.</p><input id="profile-pin" class="tv-input pin-entry" type="password" inputmode="numeric" pattern="[0-9]*" maxlength="8" autocomplete="off" aria-label="Profile PIN"><div class="pin-pad">', rows = [['profile-pin']], r, c;
        for (r = 0; r < 3; r += 1) {
            var ids = []; html += '<div class="keyboard-row">';
            for (c = 1; c < 4; c += 1) { var n = r * 3 + c; ids.push('pin-' + n); html += '<button id="pin-' + n + '" class="keyboard-key" data-action="pin-digit" data-value="' + n + '">' + n + '</button>'; }
            html += '</div>'; rows.push(ids);
        }
        html += '<div class="keyboard-row">' + button('pin-delete', 'Delete', 'pin-delete', undefined, 'keyboard-key') + button('pin-0', '0', 'pin-digit', 0, 'keyboard-key') + button('pin-unlock', 'Unlock', 'pin-unlock', undefined, 'keyboard-key') + '</div></div><p class="error-message" role="alert">' + (error || '') + '</p>';
        rows.push(['pin-delete', 'pin-0', 'pin-unlock']); open('pin', 'Unlock profile', html, rows, 'pin-1');
    }
    function selectProfile(p, pin) {
        req('POST', '/api/profiles/select', {id: p.id, pin: pin || ''}, function (ok, data) {
            if (!ok) { if (p.requires_pin) { renderPin(fail(data)); } else { A.toast((data && data.detail) || 'Profile could not be selected.'); } return; }
            if (window.VizioHome) { window.VizioHome.profile(data); }
            A.text($('profile-name'), data.name);
            A.reloadProgress(); refreshMe(); A.close(); A.toast('Watching as ' + data.name);
        });
    }
    function credits() {
        open('credits', 'Credits', '<div class="credits-copy"><img class="tmdb-logo" src="/static/art/tmdb.svg" alt="TMDB"><p>This product uses the TMDB API but is not endorsed or certified by TMDB.</p><p>Trakt supplies catalog metadata and your watchlist. Real-Debrid supplies account file listings when connected.</p><p>FenLight+ is a reference for browsing and provider design. This is an independent implementation.</p><p class="attribution">Big Buck Bunny trailer: &copy; 2008 Blender Foundation / www.bigbuckbunny.org, Creative Commons Attribution 3.0. Sample-card illustrations are original. Vizio Media is an independent home project.</p></div>' + button('credits-back', 'Back to accounts', 'accounts'), [['credits-back']], 'credits-back');
    }
    function back() {
        ticket += 1;
        if (view === 'detail') { if (detailOrigin === 'home') { A.close(); } else { renderSearch('result-0'); } return true; }
        if (view === 'seasons') { renderDetail(); return true; }
        if (view === 'episodes') { listOffset = 0; renderSeasons(); return true; }
        if (view === 'episode') { renderEpisodes(); return true; }
        if (view === 'sources') { if (episode) { renderEpisode(); } else { renderDetail(); } return true; }
        if (view === 'pin') { profiles(); return true; }
        if (view === 'link') { linker.cancel(); clearInterval(flowTick); accounts(); return true; }
        if (view === 'credits' || view === 'confirm') { accounts(); return true; }
        if (view === 'search' && keyboard) { keyboard = false; renderSearch(); return true; }
        return false;
    }
    window.VizioExtras = {
        currentProfile: function () { return me && me.profile; },
        openTitle: function (id) { details(id, 'home'); },
        dismiss: function () { ticket += 1; view = ''; $('dialog').removeAttribute('data-extra'); linker.cancel(); clearInterval(flowTick); activeFlow = null; },
        back: back,
        key: function (event, action) {
            var input = document.activeElement;
            if (input && input.id === 'catalog-overview' && (action === 'up' || action === 'down')) {
                var direction = action === 'down' ? 1 : -1, before = input.scrollTop;
                input.scrollTop += direction * 100;
                if (input.scrollTop !== before) { event.preventDefault(); event.stopPropagation(); return true; }
            }
            if (!input || input.tagName !== 'INPUT') { return false; }
            var code = event.keyCode || event.which;
            if (action === 'up' || action === 'down' || code === 9 || code === 27 || code === 461 || code === 10009) { return false; }
            if (code === 13) { event.preventDefault(); if (input.id === 'catalog-query') { search(true); } else if (input.id === 'profile-pin') { var pin = input.value; input.value = ''; selectProfile(pinProfile, pin); } }
            // Let the browser edit input text, suppressing app actions and diagnostics.
            event.stopPropagation(); return true;
        },
        activate: function (action, node) {
            var value = node.getAttribute('data-value'), input;
            if (action === 'catalog') { query = ''; kind = 'all'; page = 1; offset = 0; search(false); }
            if (action === 'catalog-search') { search(true); }
            if (action === 'catalog-filter') { kind = value; search(true); }
            if (action === 'catalog-keyboard') { query = $('catalog-query').value; keyboard = !keyboard; renderSearch(); }
            if (action === 'catalog-type' || action === 'catalog-delete' || action === 'catalog-clear') {
                input = $('catalog-query'); query = input.value;
                query = action === 'catalog-type' ? (query + value).slice(0, 120) : action === 'catalog-delete' ? query.slice(0, -1) : '';
                input.value = query;
            }
            if (action === 'catalog-next') { if (offset + 6 < results.items.length) { offset += 6; renderSearch('result-0'); } else { page += 1; offset = 0; search(false); } }
            if (action === 'catalog-prev') { if (offset > 0) { offset = Math.max(0, offset - 6); renderSearch('result-0'); } else { page = Math.max(1, page - 1); offset = 0; search(false); } }
            if (action === 'catalog-detail') { details(value); }
            if (action === 'catalog-play') { A.play(); }
            if (action === 'catalog-seasons') { listOffset = 0; renderSeasons(); }
            if (action === 'catalog-season') { var number = title.seasons[Number(value)].number; listOffset = 0; load('episodes', 'Episodes', '/api/catalog/' + title.id + '/seasons/' + number, function (data) { season = data; renderEpisodes(); }); }
            if (action === 'catalog-episode') { episode = season.episodes[Number(value)]; renderEpisode(); }
            if (action === 'list-prev' || action === 'list-next') { listOffset = Math.max(0, listOffset + (action === 'list-next' ? 6 : -6)); if (view === 'seasons') { renderSeasons(); } else { renderEpisodes(); } }
            if (action === 'catalog-sources') { sources(); }
            if (action === 'sources-prev' || action === 'sources-next') { sourceOffset = Math.max(0, sourceOffset + (action === 'sources-next' ? 4 : -4)); renderSources(); }
            if (action === 'accounts') { accounts(); }
            if (action === 'account-link') { flowService = value; view = 'link'; activeFlow = null; clearInterval(flowTick); flowTick = setInterval(updateCountdown, 1000); linker.start(value); }
            if (action === 'account-cancel') { linker.cancel(); clearInterval(flowTick); accounts(); }
            if (action === 'account-unlink') { open('confirm', 'Disconnect ' + names[value] + '?', '<p>Remove this account from ' + esc(me.profile.name) + '? You can connect it again later.</p>' + button('unlink-confirm', 'Disconnect', 'account-confirm', value, 'primary') + button('unlink-cancel', 'Keep account', 'accounts'), [['unlink-confirm', 'unlink-cancel']], 'unlink-cancel'); }
            if (action === 'account-confirm') { req('DELETE', '/api/accounts/' + value, {}, function (ok, data) { if (ok) { A.toast(data.message); accounts(); } else { A.toast((data && data.detail) || 'Could not disconnect.'); } }); }
            if (action === 'profiles') { profiles(); }
            if (action === 'profile-choose') { pinProfile = profileList[Number(value)]; if (pinProfile.requires_pin) { renderPin(); } else { selectProfile(pinProfile); } }
            if (action === 'pin-digit') { input = $('profile-pin'); input.value = (input.value + value).slice(0, 8); }
            if (action === 'pin-delete') { input = $('profile-pin'); input.value = input.value.slice(0, -1); }
            if (action === 'pin-unlock') { input = $('profile-pin'); var pin = input.value; input.value = ''; selectProfile(pinProfile, pin); }
            if (action === 'profile-lock') { req('POST', '/api/profiles/lock', {}, function (ok) { if (ok) { if (window.VizioHome) { window.VizioHome.profile(null); } A.reloadProgress(); refreshMe(); profiles(); } }); }
            if (action === 'credits') { credits(); }
            if (action === 'extra-back') { if (!back()) { A.close(); } }
        }
    };
    document.addEventListener('click', function (event) { if (event.target.tagName === 'INPUT') { A.focus(event.target.id); } }, false);
    window.addEventListener('pagehide', function () { linker.stop(); clearInterval(flowTick); }, false);
    refreshMe(function (ok) {
        if (!ok || me.profile) { return; }
        req('GET', '/api/profiles', null, function (good, data) {
            if (good && data.profiles.length === 1 && !data.profiles[0].requires_pin) {
                req('POST', '/api/profiles/select', {id: data.profiles[0].id}, function (selected) { if (selected) { refreshMe(); A.reloadProgress(); } });
            }
        });
    });
}());
