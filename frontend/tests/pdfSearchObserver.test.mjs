import test from 'node:test';
import assert from 'node:assert/strict';
import { observeSearchText } from '../src/pdfSearchObserver.mjs';

test('owned search writes cannot schedule another frame; external text still refreshes', () => {
  let connected = false;
  let callback;
  const frames = new Map();
  let next = 0;
  let renders = 0;
  let clears = 0;
  const stop = observeSearchText({}, {
    createObserver(fn) {
      callback = fn;
      return { observe() { connected = true; }, disconnect() { connected = false; } };
    },
    requestFrame(fn) { frames.set(++next, fn); return next; },
    cancelFrame(id) { frames.delete(id); },
    render() { renders++; if (connected) callback(); },
    clear() { clears++; assert.equal(connected, false); },
  });
  assert.equal(renders, 1);
  assert.equal(frames.size, 0);
  callback(); callback();
  assert.equal(frames.size, 1);
  const [id, fn] = [...frames][0];
  frames.delete(id); fn();
  assert.equal(renders, 2);
  assert.equal(frames.size, 0);
  callback();
  stop();
  assert.equal(frames.size, 0);
  assert.equal(clears, 1);
  callback();
  assert.equal(frames.size, 0);
});
