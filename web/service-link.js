/* Device approval coordinator shared by the TV and local account manager. ES5. */
(function () {
    'use strict';
    window.VizioLink = function (request, paths, change) {
        var timer = null, flow = null, generation = 0;
        function stop() { generation += 1; clearTimeout(timer); timer = null; }
        function schedule(ticket, seconds) {
            clearTimeout(timer);
            timer = setTimeout(function () {
                if (ticket !== generation || !flow) { return; }
                request('POST', paths.flow(flow.id) + '/poll', {}, function (ok, data) {
                    if (ticket !== generation) { return; }
                    if (!ok) {
                        change(flow, (data && data.detail) || 'Connection lost. Retrying shortly.');
                        if (ticket !== generation || !flow) { return; }
                        if (Date.now() / 1000 < flow.expires_at) { schedule(ticket, (data && data.retry_after) || 30); }
                        else { flow.state = 'expired'; change(flow); }
                        return;
                    }
                    flow = data; change(flow);
                    if (ticket === generation && flow && flow.state === 'pending') { schedule(ticket, Math.max(flow.interval, flow.retry_after || 0, 1)); }
                });
            }, Math.max(1, seconds) * 1000);
        }
        return {
            start: function (service) {
                stop(); var ticket = generation;
                change(null, 'Requesting a sign-in code...');
                request('POST', paths.start(service), {}, function (ok, data) {
                    if (ticket !== generation) {
                        if (ok && data.state === 'pending') { request('DELETE', paths.flow(data.id), {}, function () {}); }
                        return;
                    }
                    if (!ok) { change(null, (data && data.detail) || 'Could not request a code. Try again.'); return; }
                    flow = data; change(flow);
                    if (ticket === generation && flow && flow.state === 'pending') { schedule(ticket, Math.max(flow.interval, flow.retry_after || 0, 1)); }
                });
            },
            cancel: function (callback) {
                stop(); var previous = flow; flow = null;
                if (previous && previous.state === 'pending') { request('DELETE', paths.flow(previous.id), {}, callback || function () {}); }
                else if (callback) { callback(true, {}); }
            },
            stop: stop
        };
    };
}());
