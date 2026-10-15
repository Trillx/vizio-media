/* Live discovery, with explicit focus rows for the TV remote. ES5 only. */
(function () {
    'use strict';
    var A = window.VizioApp, esc = A.escape, req = A.request;
    var $ = function (id) { return document.getElementById(id); };
    var genre = 'all', listView = false, catalog = null, related = null, personal = null, profile = null;
    var publicTicket = 0, privateTicket = 0, privateError = '', publicError = '', localProgress = null;
    var header = ['nav-home','nav-watchlist','nav-search','nav-accounts','nav-profile','nav-remote','nav-checks'];
    var genres = ['all','comedy','horror','science-fiction','animation'];
    var focusRows = [];

    function show(node, yes) { if (yes) { node.removeAttribute('hidden'); } else { node.setAttribute('hidden', 'hidden'); } }
    function button(id, label, action, value) {
        return '<button id="' + id + '" class="button secondary" data-action="' + action + '"' +
            (value === undefined ? '' : ' data-value="' + esc(value) + '"') + '>' + esc(label) + '</button>';
    }
    function minutes(seconds) { return seconds < 60 ? Math.max(1, Math.ceil(seconds)) + ' sec left' : Math.ceil(seconds / 60) + ' min left'; }
    function excerpt(copy) { return copy.length > 115 ? copy.slice(0, 112).replace(/\s+\S*$/, '') + '...' : copy; }
    function card(item, id, continuing) {
        var image = item.backdrop || item.poster, progress = item.progress;
        var html = '<button id="' + id + '" class="home-film" data-action="' + (continuing ? 'play' : 'home-title') + '" data-value="' + esc(item.id) + '">';
        html += '<span class="home-film-art">' + (image ? '<img loading="lazy" src="' + esc(image) + '" alt="">' : '<span class="home-film-initial" aria-hidden="true">' + esc(item.title.charAt(0)) + '</span>');
        if (progress) { html += '<span class="home-progress"><i style="width:' + Math.min(100, Math.max(0, progress.position / progress.duration * 100)) + '%"></i></span>'; }
        html += '</span><span class="home-film-name">' + esc(item.title) + '</span><span class="home-film-meta">' + esc(progress ? minutes(progress.duration - progress.position) : (item.year || 'Year unknown') + ' / ' + (item.kind === 'tv' ? 'Series' : 'Movie') + (item.sample ? ' / Sample' : '')) + '</span></button>';
        return html;
    }
    function shelf(data, prefix, continuing) {
        var html = '<section class="home-shelf" aria-labelledby="heading-' + prefix + '"><div class="home-heading"><h2 id="heading-' + prefix + '">' + esc(data.title) + '</h2><span>' + esc(data.notice || '') + '</span></div>', ids = [], i;
        if (data.error) {
            html += '<div class="home-empty"><p>' + esc(data.error) + '</p>' + button(prefix + '-retry', 'Try again', 'home-page', data.id + ':1') + '</div>';
            focusRows.push([prefix + '-retry']);
        } else if (!data.items.length) {
            html += '<p class="home-notice">No titles available in this collection yet.</p>';
        } else {
            html += '<div class="home-track">';
            for (i = 0; i < data.items.length; i += 1) {
                ids.push(prefix + '-' + i); html += card(data.items[i], prefix + '-' + i, continuing);
            }
            focusRows.push(ids); html += '</div>';
        }
        if (data.total_pages > 1) {
            ids = []; html += '<div class="home-pages">';
            if (data.page > 1) { ids.push(prefix + '-prev'); html += button(prefix + '-prev', 'Previous', 'home-page', data.id + ':' + (data.page - 1)); }
            if (data.page < data.total_pages) { ids.push(prefix + '-next'); html += button(prefix + '-next', 'Next titles', 'home-page', data.id + ':' + (data.page + 1)); }
            html += '<span>Page ' + data.page + ' of ' + data.total_pages + '</span></div>';
            if (ids.length) { focusRows.push(ids); }
        }
        return html + '</section>';
    }
    function emptyList(message, action, label) {
        focusRows.push(['home-list-action']);
        return '<section class="home-empty"><h2>My list</h2><p>' + esc(message) + '</p>' + button('home-list-action', label, action) + '</section>';
    }
    function renderPersonal() {
        var html = '', watchlist;
        if (!profile) { return listView ? emptyList('Choose a profile to see its Trakt watchlist.', 'profiles', 'Choose profile') : ''; }
        if (privateError) { return emptyList(privateError, 'home-personal-retry', 'Try again'); }
        if (!personal) { return listView ? '<p class="home-notice" role="status">Loading your list...</p>' : ''; }
        if (!listView && personal.continue_watching.length) {
            html += shelf({title:'Continue watching', notice:profile.name, items:personal.continue_watching}, 'continue', true);
        }
        watchlist = personal.watchlist;
        if (watchlist.state === 'connected' && watchlist.items.length) {
            html += shelf({title:'My list', notice:watchlist.notice || profile.name + ' / Trakt', items:watchlist.items}, 'watchlist', false);
        } else if (listView) {
            html += emptyList(watchlist.notice || 'Your Trakt watchlist is empty. Save titles on Trakt and refresh your list here.', watchlist.state === 'connected' || watchlist.state === 'unavailable' ? 'home-personal-retry' : 'accounts', watchlist.state === 'connected' || watchlist.state === 'unavailable' ? 'Refresh list' : 'Open Accounts');
        }
        return html;
    }
    function render(preferred) {
        var active = document.activeElement, keep = preferred || (active && active.id), i, html = '', hero = catalog && catalog.hero;
        focusRows = [header, ['genre-all','genre-comedy','genre-horror','genre-science-fiction','genre-animation']];
        show($('home-feature'), !listView); show($('home-samples'), !listView);
        for (i = 0; i < genres.length; i += 1) {
            $('genre-' + genres[i]).className = 'home-genre' + (!listView && genre === genres[i] ? ' selected' : '');
            $('genre-' + genres[i]).setAttribute('aria-pressed', String(!listView && genre === genres[i]));
        }
        $('nav-home').className = 'nav' + (!listView ? ' active' : '');
        $('nav-watchlist').className = 'nav' + (listView ? ' active' : '');
        if (listView) { $('nav-watchlist').setAttribute('aria-current', 'page'); $('nav-home').removeAttribute('aria-current'); }
        else { $('nav-home').setAttribute('aria-current', 'page'); $('nav-watchlist').removeAttribute('aria-current'); }
        if (!listView) {
            focusRows.push(['hero-details']);
            if (hero) {
                A.text($('home-title'), hero.title); A.text($('home-meta'), (hero.year || 'Year unknown') + ' / ' + (hero.kind === 'tv' ? 'Series' : 'Movie') + (hero.sample ? ' / Sample title' : ''));
                A.text($('home-overview'), excerpt(hero.overview)); A.text($('home-kicker'), genre === 'all' ? 'IN THE SPOTLIGHT' : $('genre-' + genre).textContent.toUpperCase() + ' / IN THE SPOTLIGHT');
                A.text($('hero-details'), 'Explore title'); $('hero-details').setAttribute('data-action', 'home-title'); $('hero-details').setAttribute('data-value', hero.id);
                var image = hero.backdrop || hero.poster;
                // Artwork is always a same-origin URL emitted by our catalog normalizer.
                $('home-image').style.backgroundImage = image ? 'url("' + image.replace(/"/g, '%22') + '")' : 'none';
            } else {
                A.text($('home-title'), 'Find your next watch.'); A.text($('home-kicker'), 'YOUR NEXT MOVIE NIGHT');
                A.text($('home-meta'), 'Movies, series, and a little inspiration.');
                A.text($('home-overview'), publicError || 'Loading your catalog...'); A.text($('hero-details'), publicError ? 'Try again' : 'Loading titles...');
                $('hero-details').setAttribute('data-action', 'home-retry'); $('home-image').style.backgroundImage = 'none';
            }
        }
        A.text($('home-notice'), publicError || (catalog && catalog.notice) || '');
        show($('home-notice'), !listView && !!(publicError || (catalog && catalog.notice)));
        $('home-lead').innerHTML = !listView && catalog && catalog.shelves.length ? shelf(catalog.shelves[0], 'shelf-' + catalog.shelves[0].id, false) : '';
        $('home-personal').innerHTML = renderPersonal();
        if (!listView && catalog) {
            for (i = 1; i < catalog.shelves.length; i += 1) { html += shelf(catalog.shelves[i], 'shelf-' + catalog.shelves[i].id, false); }
            if (related && related.items.length) { html += shelf(related, 'related', false); }
        }
        $('home-shelves').innerHTML = html;
        if (!listView) { focusRows.push(['card-bunny','card-sintel','card-dream']); focusRows.push(['play-feature','details-feature']); }
        focusRows.push(['home-credits']);
        // Reuse stable IDs when asynchronous content arrives, including during a dialog.
        if (!keep || !$(keep) || $(keep).offsetParent === null) { keep = listView ? 'nav-watchlist' : 'hero-details'; }
        A.homeRows(focusRows, keep);
    }
    function loadHome(preferred) {
        var current = ++publicTicket;
        publicError = ''; catalog = null; related = null; render(preferred);
        req('GET', '/api/home?genre=' + encodeURIComponent(genre), null, function (ok, data) {
            if (current !== publicTicket) { return; }
            if (!ok) { publicError = (data && data.detail) || 'The catalog could not load. Check the server connection and try again.'; render(); return; }
            catalog = data; render();
            req('GET', '/api/home/related/' + encodeURIComponent(data.hero.id), null, function (good, result) {
                if (current !== publicTicket || !good) { return; }
                related = result; related.title = 'More like ' + data.hero.title; render();
            }, 35000);
        }, 35000);
    }
    function applyProgress(progress) {
        if (!personal) { return; }
        personal.continue_watching = progress.position > 1 && progress.position < progress.duration - 2 ? [{id:'sample-bunny',title:'Big Buck Bunny',year:'2008',kind:'movie',poster:'/static/art/hero.jpg',sample:true,progress:progress}] : [];
    }
    function refreshPersonal() {
        var current = ++privateTicket, expected = profile && profile.id;
        if (!expected) { return; }
        privateError = '';
        req('GET', '/api/home/personal', null, function (ok, data) {
            if (current !== privateTicket || !profile || expected !== profile.id) { return; }
            if (!ok || data.profile.id !== expected) { personal = null; privateError = (data && data.detail) || 'Your list could not load. Try again or choose your profile again.'; }
            else { personal = data; if (localProgress) { applyProgress(localProgress); } }
            render();
        }, 35000);
    }
    function page(value) {
        var values = value.split(':'), key = values[0], number = Number(values[1]), current = publicTicket, i;
        A.toast('Loading titles...');
        req('GET', '/api/home/shelf?genre=' + encodeURIComponent(key) + '&page=' + number, null, function (ok, data) {
            if (current !== publicTicket || !catalog) { return; }
            if (!ok) { A.toast((data && data.detail) || 'This collection could not load. Try again.'); return; }
            for (i = 0; i < catalog.shelves.length; i += 1) { if (catalog.shelves[i].id === key) { catalog.shelves[i] = data; } }
            render(data.items.length ? 'shelf-' + key + '-0' : 'genre-' + key);
        }, 35000);
    }
    function reset() {
        listView = false; $('home-content').scrollTop = 0;
        if (genre !== 'all' || !catalog) { genre = 'all'; loadHome('hero-details'); }
        else { render('hero-details'); }
    }
    window.VizioHome = {
        reset: reset,
        back: function () { if (listView || genre !== 'all') { reset(); return true; } return false; },
        profile: function (next) {
            if ((profile && profile.id) === (next && next.id)) { return; }
            privateTicket += 1; profile = next; personal = null; localProgress = null; privateError = '';
            render(); if (profile) { refreshPersonal(); }
        },
        refreshPersonal: refreshPersonal,
        progress: function (progress) {
            if (!profile) { return; }
            var hadContinue = personal && personal.continue_watching.length, node;
            localProgress = {position:progress.position,duration:progress.duration};
            applyProgress(localProgress);
            if (!personal || listView) { return; }
            node = $('continue-0');
            if (node && personal.continue_watching.length) {
                node.querySelector('.home-progress i').style.width = Math.min(100, progress.position / progress.duration * 100) + '%';
                A.text(node.querySelector('.home-film-meta'), minutes(progress.duration - progress.position));
            } else if (hadContinue || personal.continue_watching.length) { render(); }
        },
        focused: function (node) {
            if (!$('home-content').contains(node)) { return; }
            // Use scaled geometry rather than newer scrollIntoView options on the TV.
            var content = $('home-content'), track = node.parentNode, bounds, box;
            var ratio = $('stage').getBoundingClientRect().width / 1920, inset = 10 * ratio;
            if (track.className.indexOf('home-track') !== -1) {
                bounds = track.getBoundingClientRect(); box = node.getBoundingClientRect();
                if (box.left < bounds.left + inset) { track.scrollLeft -= (bounds.left + inset - box.left) / ratio; }
                else if (box.right > bounds.right - inset) { track.scrollLeft += (box.right - bounds.right + inset) / ratio; }
            }
            bounds = content.getBoundingClientRect(); box = node.getBoundingClientRect();
            if (box.top < bounds.top + inset) { content.scrollTop -= (bounds.top + inset - box.top) / ratio; }
            else if (box.bottom > bounds.bottom - inset) { content.scrollTop += (box.bottom - bounds.bottom + inset) / ratio; }
        },
        activate: function (action, node) {
            var value = node.getAttribute('data-value');
            if (action === 'home-title') { window.VizioExtras.openTitle(value); }
            if (action === 'home-genre') { genre = value; listView = false; $('home-content').scrollTop = 0; loadHome('genre-' + genre); }
            if (action === 'home-watchlist') { listView = true; $('home-content').scrollTop = 0; render('nav-watchlist'); refreshPersonal(); }
            if (action === 'home-retry') { loadHome('hero-details'); }
            if (action === 'home-personal-retry') { privateError = ''; personal = null; render(); refreshPersonal(); }
            if (action === 'home-page') { page(value); }
        }
    };
    loadHome('hero-details');
    // The shared profile controller also reports automatic household selection.
    window.VizioHome.profile(window.VizioExtras.currentProfile());
}());
