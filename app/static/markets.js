// Market overview charts (TradingView Lightweight Charts v4): compare all indices, one index in detail.
// Pure helpers first (unit-tested in tests/js/markets.test.js), then the chart wiring. Uses the shared helpers
// and COLORS from charts.js, which the page loads first.
/* global LightweightCharts, COLORS, newChart */

const RANGES = { '1M': 21, '3M': 63, '6M': 126, '1Y': 252, '2Y': 504 };   // trading sessions behind each range button
// Categorical colours for the compare lines. No red and no green: those mean bad and good everywhere else in the app.
const LINE_COLORS = ['#38bdf8', '#a78bfa', '#fbbf24', '#f472b6', '#e2e8f0'];
const priceFormatter = (price) => price.toLocaleString('en-US', { maximumFractionDigits: price >= 1000 ? 0 : 2 });
const round = (value, places) => Math.round(value * 10 ** places) / 10 ** places;

// the last `sessions` closes of a {t: [date], v: [close]} series, as chart points
function lastPoints(series, sessions) {
  const from = Math.max(0, series.v.length - sessions);
  return series.t.slice(from).map((time, i) => ({ time, value: series.v[from + i] }));
}

// the same closes rebased so the first one of the range is 100: lines on different scales become comparable
function rebase(series, sessions) {
  const points = lastPoints(series, sessions);
  const base = points[0].value;
  return points.map((p) => ({ time: p.time, value: round((p.value / base) * 100, 2) }));
}

// simple moving average per position; null until a full window of closes exists
function movingAverage(values, window) {
  let sum = 0;
  return values.map((value, i) => {
    sum += value;
    if (i >= window) sum -= values[i - window];
    return i >= window - 1 ? sum / window : null;
  });
}

// a moving average over the whole stored history, then cut to the visible range (so a 1M view still has its 200-DMA)
function averagePoints(series, window, sessions) {
  const average = movingAverage(series.v, window);
  const from = Math.max(0, series.v.length - sessions);
  return series.t.slice(from)
    .map((time, i) => ({ time, value: average[from + i] }))
    .filter((p) => p.value !== null)
    .map((p) => ({ time: p.time, value: round(p.value, 4) }));
}

// ---- wiring ----

function legendButton(series, color, onToggle) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'chip chip-legend';
  button.setAttribute('aria-pressed', 'true');
  const swatch = document.createElement('span');
  swatch.className = 'inline-block h-2.5 w-5 rounded-full';
  swatch.style.background = color;
  swatch.setAttribute('aria-hidden', 'true');
  button.append(swatch, series.name);
  button.addEventListener('click', () => {
    const on = button.getAttribute('aria-pressed') !== 'true';
    button.setAttribute('aria-pressed', String(on));
    onToggle(on);
  });
  return button;
}

function renderMarkets(payload) {
  const all = payload.series;
  const comparable = all.filter((s) => s.kind === 'index');
  if (!all.length) return;
  const state = { range: '1Y', selected: all.find((s) => s.symbol === payload.selected) ?? all[0] };

  Object.keys(RANGES).forEach((label) => {   // the range buttons come from RANGES, so the two can never disagree
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'chip';
    chip.dataset.range = label;
    chip.textContent = label;
    document.getElementById('market-ranges').append(chip);
  });

  const compare = newChart('compare-chart');
  const lines = Object.fromEntries(comparable.map((s, i) => [s.symbol, compare.addLineSeries({
    color: LINE_COLORS[i % LINE_COLORS.length], lineWidth: 2, priceLineVisible: false, lastValueVisible: true,
  })]));
  const baseline = compare.addLineSeries({   // its own series, so hiding an index can never hide the 100 line
    color: COLORS.level, lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dotted,
    priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
  });
  comparable.forEach((s, i) => document.getElementById('compare-legend').append(
    legendButton(s, LINE_COLORS[i % LINE_COLORS.length], (on) => lines[s.symbol].applyOptions({ visible: on }))));

  const detail = newChart('index-chart', { localization: { priceFormatter } });
  const area = detail.addAreaSeries({ lineColor: COLORS.entry, lineWidth: 2, priceLineVisible: false,
    topColor: 'rgba(56, 189, 248, 0.28)', bottomColor: 'rgba(56, 189, 248, 0)' });
  const sma50 = detail.addLineSeries({ color: COLORS.mid, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
  const sma200 = detail.addLineSeries({ color: COLORS.slow, lineWidth: 2, priceLineVisible: false, lastValueVisible: false });

  function draw() {
    const sessions = RANGES[state.range];
    comparable.forEach((s) => lines[s.symbol].setData(rebase(s, sessions)));
    const span = comparable.length ? rebase(comparable[0], sessions) : [];
    baseline.setData(span.length ? [{ time: span[0].time, value: 100 }, { time: span.at(-1).time, value: 100 }] : []);
    compare.timeScale().fitContent();
    area.setData(lastPoints(state.selected, sessions));
    sma50.setData(averagePoints(state.selected, 50, sessions));
    sma200.setData(averagePoints(state.selected, 200, sessions));
    detail.timeScale().fitContent();
    document.getElementById('index-title').textContent = `${state.selected.name}, last ${state.range}`;
    document.querySelectorAll('[data-index]').forEach((card) =>
      card.setAttribute('aria-pressed', String(card.dataset.index === state.selected.symbol)));
    document.querySelectorAll('[data-range]').forEach((chip) =>
      chip.setAttribute('aria-pressed', String(chip.dataset.range === state.range)));
  }

  document.addEventListener('click', (event) => {
    const card = event.target.closest('[data-index]');
    const chip = event.target.closest('[data-range]');
    if (card) state.selected = all.find((s) => s.symbol === card.dataset.index) ?? state.selected;
    else if (chip) state.range = chip.dataset.range;
    else return;
    draw();
  });
  draw();
}

if (typeof module !== 'undefined') module.exports = { priceFormatter, RANGES, lastPoints, rebase, movingAverage, averagePoints };
