const assert = require('node:assert/strict');
const test = require('node:test');
const remote = require('../web/remote.js');

test('standard and legacy remote events map to the same actions', () => {
  assert.equal(remote.action({key: 'ArrowLeft', keyCode: 0}), 'left');
  assert.equal(remote.action({keyCode: 39}), 'right');
  assert.equal(remote.action({which: 13}), 'select');
  for (const keyCode of [8, 27, 461, 10009]) {
    assert.equal(remote.action({keyCode}), 'back');
  }
  assert.equal(remote.action({key: 'MediaPlayPause'}), 'toggle');
  assert.equal(remote.action({keyCode: 415}), 'play');
  assert.equal(remote.action({key: 'AudioVolumeUp', keyCode: 175}), '');
});

test('navigation handles different row lengths and stays inside the screen', () => {
  const rows = [['a','b','c'], ['d'], ['e','f']];
  assert.deepEqual(remote.move(rows, 0, 2, 'down'), {row: 1, col: 0});
  assert.deepEqual(remote.move(rows, 0, 0, 'up'), {row: 0, col: 0});
  assert.deepEqual(remote.move(rows, 0, 0, 'left'), {row: 0, col: 0});
  assert.deepEqual(remote.move(rows, 2, 1, 'right'), {row: 2, col: 1});
  assert.deepEqual(remote.move(rows, 1, 0, 'down'), {row: 2, col: 0});
});
