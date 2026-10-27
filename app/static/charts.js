// Candlestick + indicator charts (TradingView Lightweight Charts v4).
// Shared helpers first; renderCharts = daily swing page, renderIntradayCharts = 5-minute page.
/* global LightweightCharts */

// The dark ink palette (tailwind.config.js): emerald up, rose down, sky entry; one place for every colour.
const COLORS = {
  up: '#34d399', down: '#fb7185', band: '#8b9ab0', level: '#64748b',
  entry: '#38bdf8', stop: '#fb7185', target: '#34d399',
  fast: '#38bdf8', mid: '#a78bfa', slow: '#fb923c', trail: '#2dd4bf',
  upFaint: '#34d39999', downFaint: '#fb718599',
  surface: '#11101b', text: '#cfcde0', grid: '#1e1c33', border: '#3a3852',
};

function newChart(id, extra = {}) {
  return LightweightCharts.createChart(document.getElementById(id), {
    autoSize: true,
    layout: { background: { color: COLORS.surface }, textColor: COLORS.text },
    grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
    rightPriceScale: { borderColor: COLORS.border },
    timeScale: { borderColor: COLORS.border },
    ...extra,
  });
}

function addLine(chart, data, color, opts = {}) {
  const series = chart.addLineSeries({
    color, lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false, ...opts,
  });
  series.setData(data);
  return series;
}

function addCandles(chart, d) {
  const candles = chart.addCandlestickSeries({
    upColor: COLORS.up, downColor: COLORS.down, borderVisible: false,
    wickUpColor: COLORS.up, wickDownColor: COLORS.down,
  });
  candles.setData(d.candles);
  const volume = chart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: 'vol' });
  chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  volume.setData(d.volume);
  return candles;
}

function addLevels(series, levels) {
  const { LineStyle } = LightweightCharts;
  levels.forEach((lv) => series.createPriceLine({
    price: lv.price, color: COLORS.level, lineWidth: 1, lineStyle: LineStyle.Dotted,
    axisLabelVisible: false, title: lv.title,
  }));
}

function addPlan(series, plan) {
  if (!plan) return;
  [['entry', COLORS.entry, 'Entry'], ['stop', COLORS.stop, 'Stop'],
   ['target1', COLORS.target, 'T1'], ['target2', COLORS.target, 'T2']].forEach(([key, color, title]) =>
    series.createPriceLine({ price: plan[key], color, lineWidth: 2, title }));
}

function addRsi(chart, data) {
  const { LineStyle } = LightweightCharts;
  const rsi = addLine(chart, data, COLORS.mid, { lastValueVisible: true });
  [70, 30].forEach((level) => rsi.createPriceLine({
    price: level, color: COLORS.band, lineWidth: 1, lineStyle: LineStyle.Dashed,
    axisLabelVisible: false, title: String(level),
  }));
}

// keep panes scrolled/zoomed together (guard prevents ping-pong between panes)
function syncCharts(charts) {
  let syncing = false;
  charts.forEach((source) => source.timeScale().subscribeVisibleLogicalRangeChange((range) => {
    if (!range || syncing) return;
    syncing = true;
    charts.filter((c) => c !== source).forEach((c) => c.timeScale().setVisibleLogicalRange(range));
    syncing = false;
  }));
}

function renderCharts(d) {
  const { LineStyle } = LightweightCharts;
  const price = newChart('price-chart');
  const candles = addCandles(price, d);
  addLine(price, d.bb_upper, COLORS.band, { lineWidth: 1, lineStyle: LineStyle.Dashed });
  addLine(price, d.bb_lower, COLORS.band, { lineWidth: 1, lineStyle: LineStyle.Dashed });
  addLine(price, d.ema20, COLORS.fast, { lineWidth: 1 });
  addLine(price, d.sma50, COLORS.mid);
  addLine(price, d.sma200, COLORS.slow, { lineWidth: 2 });
  addLine(price, d.st_line, COLORS.trail, { lineWidth: 1, lineStyle: LineStyle.SparseDotted });
  addLevels(candles, d.levels);
  addPlan(candles, d.plan);

  const rsi = newChart('rsi-chart');
  addRsi(rsi, d.rsi);

  const macd = newChart('macd-chart');
  const hist = macd.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false });
  hist.setData(d.macd_hist.map((p) => ({ ...p, color: p.value >= 0 ? COLORS.upFaint : COLORS.downFaint })));
  addLine(macd, d.macd, COLORS.entry);
  addLine(macd, d.macd_signal, COLORS.slow);

  syncCharts([price, rsi, macd]);
  price.timeScale().fitContent();
}

function renderIntradayCharts(d) {
  const { LineStyle } = LightweightCharts;
  // times arrive as IST wall-clock encoded as UTC epochs, so the UTC axis reads in IST
  const intraday = { timeScale: { borderColor: COLORS.border, timeVisible: true, secondsVisible: false } };
  const price = newChart('intraday-chart', intraday);
  const candles = addCandles(price, d);
  addLine(price, d.vwap_u2, COLORS.band, { lineWidth: 1, lineStyle: LineStyle.Dashed });
  addLine(price, d.vwap_l2, COLORS.band, { lineWidth: 1, lineStyle: LineStyle.Dashed });
  addLine(price, d.vwap, COLORS.entry, { lineWidth: 2 });
  addLine(price, d.ema9, COLORS.fast, { lineWidth: 1 });
  addLine(price, d.ema21, COLORS.mid, { lineWidth: 1 });
  addLevels(candles, d.levels);
  addPlan(candles, d.plan);

  const rsi = newChart('intraday-rsi', intraday);
  addRsi(rsi, d.rsi);

  syncCharts([price, rsi]);
  price.timeScale().fitContent();
}
