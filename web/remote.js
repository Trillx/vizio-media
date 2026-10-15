/* ES5 only. Key codes are candidates until observed on the user's firmware. */
(function (root) {
    'use strict';
    var names = {
        ArrowLeft: 'left', Left: 'left', ArrowRight: 'right', Right: 'right',
        ArrowUp: 'up', Up: 'up', ArrowDown: 'down', Down: 'down',
        Enter: 'select', Accept: 'select', Select: 'select',
        Escape: 'back', Esc: 'back', Backspace: 'back', BrowserBack: 'back', GoBack: 'back',
        MediaPlayPause: 'toggle', MediaPlay: 'play', MediaPause: 'pause',
        MediaStop: 'stop', MediaRewind: 'rewind', MediaFastForward: 'forward',
        ' ': 'toggle', Spacebar: 'toggle'
    };
    var codes = {
        37: 'left', 38: 'up', 39: 'right', 40: 'down', 13: 'select',
        8: 'back', 27: 'back', 461: 'back', 10009: 'back',
        32: 'toggle', 179: 'toggle', 415: 'play', 19: 'pause',
        413: 'stop', 412: 'rewind', 417: 'forward'
    };
    var remote = {
        action: function (event) { return names[event.key] || codes[event.keyCode || event.which] || ''; },
        move: function (rows, row, col, action) {
            var nextRow = row, nextCol = col;
            if (action === 'left') { nextCol = Math.max(0, col - 1); }
            if (action === 'right') { nextCol = Math.min(rows[row].length - 1, col + 1); }
            if (action === 'up') { nextRow = Math.max(0, row - 1); }
            if (action === 'down') { nextRow = Math.min(rows.length - 1, row + 1); }
            if (nextRow !== row) { nextCol = Math.min(col, rows[nextRow].length - 1); }
            return { row: nextRow, col: nextCol };
        }
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = remote; }
    root.VizioRemote = remote;
}(this));
