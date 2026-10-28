const { test } = require('node:test');
const assert = require('node:assert');
const { priceFormatter, RANGES, lastPoints, rebase, movingAverage, averagePoints } = require('../../app/static/markets.js');

const series = { t: ['d1', 'd2', 'd3', 'd4', 'd5', 'd6'], v: [100, 110, 121, 99, 108.9, 120] };

test('lastPoints keeps the most recent closes and tolerates a range longer than the history', () => {
  assert.deepStrictEqual(lastPoints(series, 2), [{ time: 'd5', value: 108.9 }, { time: 'd6', value: 120 }]);
  assert.strictEqual(lastPoints(series, 500).length, 6);
});

test('rebase starts the range at 100, so indices on different scales compare', () => {
  const big = { t: series.t, v: series.v.map((v) => v * 250) };   // a 25,000-point index next to a 100-point one
  assert.deepStrictEqual(rebase(series, 3), rebase(big, 3));
  assert.deepStrictEqual(rebase(series, 3).map((p) => p.value), [100, 110, 121.21]);   // 99 / 99 ... 108.9 / 99 ... 120 / 99
});

test('movingAverage is null until a full window exists, then a plain mean', () => {
  assert.deepStrictEqual(movingAverage([1, 2, 3, 4], 2), [null, 1.5, 2.5, 3.5]);
  assert.deepStrictEqual(movingAverage([5, 5], 3), [null, null]);
});

test('averagePoints uses the whole history, then cuts to the range (a short range still has its long average)', () => {
  const long = { t: Array.from({ length: 300 }, (_, i) => `d${i}`), v: Array.from({ length: 300 }, (_, i) => i + 1) };
  const points = averagePoints(long, 200, RANGES['1M']);
  assert.strictEqual(points.length, 21);                      // every day of the month has a 200-day average
  assert.strictEqual(points[0].time, 'd279');
  assert.strictEqual(points.at(-1).value, 200.5);             // mean of 101..300
});

test('big index levels read as whole numbers, small ones (VIX, currency) keep their decimals', () => {
  assert.strictEqual(priceFormatter(26477.81), '26,478');
  assert.strictEqual(priceFormatter(17.6), '17.6');
  assert.strictEqual(priceFormatter(95.2345), '95.23');
});

test('the ranges are trading sessions in ascending order', () => {
  const sessions = Object.values(RANGES);
  assert.deepStrictEqual(sessions, [...sessions].sort((a, b) => a - b));
});
