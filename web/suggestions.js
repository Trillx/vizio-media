/* Debounced title suggestions with stale-response suppression. */
(function (root, factory) {
    'use strict';
    if (typeof module === 'object' && module.exports) { module.exports = factory(); }
    else { root.VizioSuggestions = factory(); }
}(typeof window !== 'undefined' ? window : this, function () {
    'use strict';
    function create(request, changed, options) {
        options = options || {};
        var clock = options.clock || {
            setTimeout: function (callback, delay) { return setTimeout(callback, delay); },
            clearTimeout: function (id) { clearTimeout(id); }
        };
        var timer = null, serial = 0;
        function clear() {
            serial += 1; clock.clearTimeout(timer); timer = null;
            changed({state: 'idle', items: []});
        }
        return {
            clear: clear,
            search: function (text, kind) {
                clear();
                var query = String(text).trim().slice(0, 120), current = serial;
                if (query.length < 2 || kind === 'watchlist') { return; }
                changed({state: 'loading', items: []});
                timer = clock.setTimeout(function () {
                    timer = null;
                    request('GET', '/api/catalog/search?q=' + encodeURIComponent(query) + '&kind=' + kind + '&page=1', null, function (ok, data) {
                        if (current !== serial) { return; }
                        changed({state: ok && data && Array.isArray(data.items) ? 'ready' : 'error',
                            items: ok && data && Array.isArray(data.items) ? data.items.slice(0, 3) : []});
                    }, 12000);
                }, options.delay || 350);
            }
        };
    }
    return {create: create};
}));
