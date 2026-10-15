/* Local-only owner UI. No diagnostic logging, browser storage, or secret readback. */
(function () {
    'use strict';
    var $ = function (id) { return document.getElementById(id); };
    var setup = false, profiles = [], selected = '', config = {}, activeTab = 'profiles';
    var linker = null, flow = null, flowTimer = null, flowService = '';
    var labels = {trakt: 'Trakt', real_debrid: 'Real-Debrid', tmdb: 'TMDB'};
    function esc(value) { return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
    function show(id, visible) { $(id).hidden = !visible; }
    function message(text, error) { $('message').textContent = text; $('message').className = 'message' + (error ? ' error' : ''); show('message', true); }
    function request(method, path, payload, callback) {
        var xhr = new XMLHttpRequest(); xhr.open(method, path, true); xhr.timeout = 25000;
        if (payload !== null) { xhr.setRequestHeader('X-Vizio-Media', '1'); xhr.setRequestHeader('Content-Type', 'application/json'); }
        function done() {
            var data; try { data = JSON.parse(xhr.responseText); } catch (ignored) { data = {detail: 'The server could not be reached. Check that Vizio Media is running.'}; }
            if (!callback) { return; } var fn = callback; callback = null; fn(xhr.status >= 200 && xhr.status < 300, data);
        }
        xhr.onload = done; xhr.onerror = done; xhr.ontimeout = done; xhr.send(payload === null ? null : JSON.stringify(payload));
    }
    function error(data) { message((data && data.detail) || 'Request failed. Try again.', true); }
    function action(label, name, value, classes) { return '<button type="button" data-action="' + name + '" data-value="' + esc(value || '') + '"' + (classes ? ' class="' + classes + '"' : '') + '>' + esc(label) + '</button>'; }
    function cancelFlow() { if (linker) { linker.cancel(); } linker = null; flow = null; clearInterval(flowTimer); show('device-panel', false); }
    function status() {
        request('GET', '/api/admin/status', null, function (ok, data) {
            if (!ok) { error(data); return; }
            setup = data.setup_required;
            show('auth', !data.signed_in); show('dashboard', data.signed_in); show('sign-out', data.signed_in);
            $('auth-title').textContent = setup ? 'Set up your household' : 'Welcome back';
            $('auth-copy').textContent = setup ? 'Create an owner password of at least twelve characters. You will use it to manage profiles and service credentials on this PC.' : 'Sign in to manage profiles and connected services.';
            $('owner-password').minLength = setup ? 12 : 1;
            $('owner-password').autocomplete = setup ? 'new-password' : 'current-password';
            $('auth-submit').textContent = setup ? 'Create account manager' : 'Sign in';
            show('auth-form', !data.signed_in);
            if (data.signed_in) { dashboard(); }
        });
    }
    function dashboard() {
        request('GET', '/api/admin/config', null, function (ok, data) {
            if (!ok) { error(data); return; } config = data;
            ['tmdb', 'trakt', 'real_debrid'].forEach(function (service) {
                $('config-' + service).textContent = config[service].configured ? 'Application configured' : 'Application setup needed';
                $('config-' + service).className = 'state' + (config[service].configured ? '' : ' off');
            });
        });
        request('GET', '/api/admin/profiles', null, function (ok, data) {
            if (!ok) { error(data); return; }
            profiles = data.profiles;
            if (!profiles.some(function (p) { return p.id === selected; })) { selected = profiles[0].id; }
            renderProfiles();
        });
    }
    function profile() { return profiles.filter(function (p) { return p.id === selected; })[0]; }
    function renderProfiles() {
        var html = '', p = profile();
        profiles.forEach(function (entry) { html += '<button class="profile-option' + (entry.id === selected ? ' current' : '') + '" data-action="select-profile" data-value="' + esc(entry.id) + '"' + (entry.id === selected ? ' aria-current="true"' : '') + '>' + esc(entry.name) + '<small>' + (entry.requires_pin ? 'PIN protected' : 'No PIN') + '</small></button>'; });
        $('profile-list').innerHTML = html;
        html = '<div class="profile-title"><h2>' + esc(p.name) + '</h2><div class="form-actions">' + action('Refresh connections', 'refresh-profiles') + (p.id !== 'household' ? action('Delete profile', 'delete-profile', p.id) : '') + '</div></div><p>These connections belong to this profile.</p>';
        ['trakt', 'real_debrid'].forEach(function (service) {
            var account = p.accounts[service], linked = account.state === 'connected', exists = account.state !== 'disconnected';
            html += '<section class="service-row"><h3>' + labels[service] + '</h3><div class="state' + (linked ? '' : ' off') + '">' + (linked ? 'Connected as ' + esc(account.display_name) : exists ? 'Reconnect required' : 'Disconnected') + '</div><div class="service-actions">';
            if (exists) { html += action('Check connection', 'check-account', service) + action('Disconnect', 'disconnect', service); }
            else if (account.configured) { html += action('Connect with device code', 'connect', service, 'primary'); }
            else { html += action('Set up application', 'settings', service); }
            html += '</div>';
            if (service === 'real_debrid') {
                html += '<details class="personal-token"><summary>Use a personal token on this private installation</summary><p>Get your token from <a href="https://real-debrid.com/apitoken" target="_blank" rel="noopener noreferrer">Real-Debrid</a> while signed in. Enter it here to connect ' + esc(p.name) + '. It is encrypted on this PC.</p><form id="personal-token" class="stack-form"><label for="personal-rd-token">Real-Debrid personal token</label><input id="personal-rd-token" type="password" required autocomplete="off" maxlength="2048"><button type="submit">' + (exists ? 'Replace connected account' : 'Connect Real-Debrid') + '</button></form></details>';
            }
            html += '</section>';
        });
        html += '<details class="profile-edit"><summary>Edit name or PIN</summary><form id="edit-profile" class="stack-form"><label for="edit-name">Profile name</label><input id="edit-name" value="' + esc(p.name) + '" maxlength="32" required><label for="edit-pin">New PIN, optional</label><input id="edit-pin" type="password" inputmode="numeric" pattern="[0-9]{4,8}" minlength="4" maxlength="8" autocomplete="new-password"><small>Leave blank to keep the current PIN. Saving changes locks this profile on all devices.</small><label class="inline-check"><input id="clear-pin" type="checkbox">Remove the current PIN</label><button type="submit">Save profile</button></form></details>';
        $('profile-detail').innerHTML = html;
    }
    function tab(name) {
        if (name !== activeTab) { cancelFlow(); }
        activeTab = name;
        ['profiles', 'settings', 'credits'].forEach(function (entry) {
            show('panel-' + entry, entry === name);
            if (entry === name) { $('tab-' + entry).setAttribute('aria-current', 'page'); } else { $('tab-' + entry).removeAttribute('aria-current'); }
        });
    }
    function renderFlow(data, problem) {
        var wasHidden = $('device-panel').hidden;
        flow = data; show('device-panel', true);
        var pending = flow && flow.state === 'pending';
        var html = '<h3>Connect ' + labels[flowService] + '</h3>';
        if (pending) {
            html += '<p>Open <a href="' + esc(flow.verification_url) + '" target="_blank" rel="noopener noreferrer">' + esc(flow.verification_url) + '</a> and enter this code.</p><div class="device-code">' + esc(flow.user_code) + '</div><p id="device-countdown"></p>';
        }
        html += '<p>' + esc(problem || (pending ? 'Waiting for approval. This page checks automatically.' : flow ? 'Sign-in ' + flow.state + '.' : 'Requesting a code...')) + '</p>' + action(pending ? 'Cancel sign-in' : 'Close', 'cancel-flow');
        $('device-panel').innerHTML = html; countdown();
        if (wasHidden) { $('device-panel').scrollIntoView({block: 'nearest'}); }
        if (flow && flow.state === 'connected') { cancelFlow(); message(labels[flowService] + ' connected for ' + profile().name + '.'); dashboard(); }
    }
    function countdown() {
        if ($('device-countdown') && flow) { var s = Math.max(0, Math.ceil(flow.expires_at - Date.now() / 1000)); $('device-countdown').textContent = 'Code expires in ' + Math.floor(s / 60) + ':' + (s % 60 < 10 ? '0' : '') + s % 60; }
    }
    function connect(service) {
        cancelFlow(); flowService = service;
        var prefix = '/api/admin/profiles/' + selected;
        linker = window.VizioLink(request, {start: function (s) { return prefix + '/' + s + '/start'; }, flow: function (id) { return prefix + '/flows/' + id; }}, renderFlow);
        linker.start(service); flowTimer = setInterval(countdown, 1000);
    }
    document.addEventListener('click', function (event) {
        var node = event.target;
        while (node && node !== document && !node.getAttribute('data-action')) { node = node.parentNode; }
        if (!node || node === document) { return; }
        var name = node.getAttribute('data-action'), value = node.getAttribute('data-value');
        if (name === 'tab') { tab(value); }
        if (name === 'settings') { tab('settings'); $('setup-' + value).querySelector('input').focus(); }
        if (name === 'logout') { cancelFlow(); request('POST', '/api/admin/logout', {}, function (ok, data) { if (ok) { profiles = []; selected = ''; $('profile-detail').innerHTML = ''; document.querySelectorAll('input').forEach(function (input) { input.value = ''; }); show('message', false); status(); } else { error(data); } }); }
        if (name === 'select-profile') { cancelFlow(); selected = value; renderProfiles(); }
        if (name === 'refresh-profiles') { dashboard(); }
        if (name === 'connect') { connect(value); }
        if (name === 'cancel-flow') { cancelFlow(); }
        if (name === 'check-account') { request('POST', '/api/admin/profiles/' + selected + '/accounts/' + value + '/refresh', {}, function (ok, data) { if (ok) { message(data.state === 'connected' ? 'Connection checked.' : 'This account needs to be connected again.', data.state !== 'connected'); dashboard(); } else { error(data); } }); }
        if (name === 'disconnect' && window.confirm('Disconnect ' + labels[value] + ' from ' + profile().name + '?')) {
            cancelFlow(); request('DELETE', '/api/admin/profiles/' + selected + '/accounts/' + value, {}, function (ok, data) { if (ok) { message(data.message); dashboard(); } else { error(data); } });
        }
        if (name === 'delete-profile' && window.confirm('Delete ' + profile().name + ' and its saved progress? Disconnect service accounts first.')) {
            request('DELETE', '/api/admin/profiles/' + value, {}, function (ok, data) { if (ok) { cancelFlow(); message('Profile deleted.'); dashboard(); } else { error(data); } });
        }
        if (name === 'remove-config' && window.confirm('Remove ' + labels[value] + ' application setup? Linked accounts must be disconnected first.')) {
            request('DELETE', '/api/admin/config/' + value, {}, function (ok, data) { if (ok) { message(labels[value] + ' setup removed.'); dashboard(); } else { error(data); } });
        }
    }, false);
    document.addEventListener('submit', function (event) {
        event.preventDefault(); var form = event.target, id = form.id, payload = {}, method = 'POST', path = '', complete;
        if (id === 'auth-form') { payload.password = $('owner-password').value; $('owner-password').value = ''; path = '/api/admin/' + (setup ? 'setup' : 'login'); complete = function () { show('message', false); status(); }; }
        if (id === 'create-profile') { payload = {name: $('new-name').value, pin: $('new-pin').value || null}; $('new-pin').value = ''; path = '/api/admin/profiles'; complete = function (data) { selected = data.id; form.reset(); message('Profile added.'); dashboard(); }; }
        if (id === 'edit-profile') { payload = {name: $('edit-name').value, pin: $('edit-pin').value || null, clear_pin: $('clear-pin').checked}; $('edit-pin').value = ''; method = 'PUT'; path = '/api/admin/profiles/' + selected; complete = function () { message('Profile saved. Choose it again on the TV.'); dashboard(); }; }
        if (id === 'personal-token') {
            if (profile().accounts.real_debrid.state !== 'disconnected' && !window.confirm('Replace the current Real-Debrid account for ' + profile().name + '?')) { return; }
            payload.token = $('personal-rd-token').value.trim(); $('personal-rd-token').value = ''; path = '/api/admin/profiles/' + selected + '/real_debrid/token'; complete = function () { cancelFlow(); message('Real-Debrid connected.'); dashboard(); };
        }
        if (id.indexOf('setup-') === 0) {
            var service = id.slice(6); method = 'PUT'; path = '/api/admin/config/' + service;
            Array.prototype.forEach.call(form.querySelectorAll('input'), function (input) { if (input.value.trim()) { payload[input.name] = input.value.trim(); } input.value = ''; });
            complete = function () { message(labels[service] + ' application setup saved.'); dashboard(); };
        }
        if (!path) { return; }
        var submit = form.querySelector('button[type="submit"]'); submit.disabled = true;
        request(method, path, payload, function (ok, data) { submit.disabled = false; if (ok) { complete(data); } else { error(data); } });
    }, false);
    window.addEventListener('pagehide', function () { if (linker) { linker.stop(); } clearInterval(flowTimer); }, false);
    status();
}());
