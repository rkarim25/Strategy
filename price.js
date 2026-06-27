/**
 * Charts — a TradingView/Bloomberg-style charting workstation built on KLineChart (vendored v9.8.12).
 * Asset registry (price_assets.json, grouped by class) · candle/bar/area · linear/log/% axis · range presets ·
 * timeframes 1m/5m/15m/30m/1h/4h/1D (intraday via the quote proxy, 4h aggregated, 60s auto-refresh) ·
 * comprehensive indicators with editable parameters · drawing palette + custom "Measure %" overlay (retained
 * across timeframe/zoom) · live last price · private per-asset notes + drawings (passphrase-gated, localStorage).
 * Interactive Signal Playbook: each rule has parameter inputs whose backtest recomputes live, a "plot" toggle
 * (draws the indicator with the same params), a "signals" toggle (▲ buy / ▼ sell markers on the chart, via a
 * custom-indicator draw callback), and a "notes" toggle (preloaded explanation of the buy/sell logic and why).
 */
(function () {
  "use strict";
  const QUOTE = "https://spx-quote-proxy.rkarim88.workers.dev";
  const STORE = "https://lab-strategy-store.rkarim88.workers.dev";
  const CLOUD_KEY = "lab_cloud_key";
  const TICKER_DV01 = { "^IRX": 0.25, "2YY=F": 1.9, "^FVX": 4.7, "^FVX+^TNX": 6.3, "^TNX": 8.6, "^TYX": 18.5 }; // ≈ modified duration (DV01 per $100); 7Y interpolated 5Y/10Y
  const RECESSIONS = [["1953-07-01", "1954-05-31"], ["1957-08-01", "1958-04-30"], ["1960-04-01", "1961-02-28"], ["1969-12-01", "1970-11-30"], ["1973-11-01", "1975-03-31"], ["1980-01-01", "1980-07-31"], ["1981-07-01", "1982-11-30"], ["1990-07-01", "1991-03-31"], ["2001-03-01", "2001-11-30"], ["2007-12-01", "2009-06-30"], ["2020-02-01", "2020-04-30"]].map(([s, e]) => [Date.parse(s), Date.parse(e)]); // NBER US recessions
  const TICK2ID = { "^IRX": "ust3m", "2YY=F": "ust2y", "^FVX": "ust5y", "^TNX": "ust10y", "^TYX": "ust30y" }; // curve leg ticker → curve id
  let INVERSIONS = []; // 2s10s/3m10y inverted ranges (loaded from ust_inversions.json)
  const UP = "#15803d", DN = "#b42318";
  const RANGES = [["1M", 21], ["3M", 63], ["6M", 126], ["1Y", 252], ["2Y", 504], ["5Y", 1260], ["Max", null]];
  const TFS = [
    { id: "1m", label: "1m", interval: "1m", range: "7d", show: 180 },
    { id: "5m", label: "5m", interval: "5m", range: "60d", show: 160 },
    { id: "15m", label: "15m", interval: "15m", range: "60d", show: 170 },
    { id: "30m", label: "30m", interval: "30m", range: "60d", show: 170 },
    { id: "1h", label: "1h", interval: "60m", range: "730d", show: 200 },
    { id: "4h", label: "4h", interval: "60m", range: "730d", show: 200, aggMs: 4 * 3600 * 1000 },
    { id: "D", label: "1D", interval: null },
  ];
  const POLL_MS = 60000;
  const TYPES = [["candle_solid", "Candles"], ["ohlc", "Bars"], ["area", "Area"]];
  const AXES = [["normal", "Linear"], ["log", "Log"], ["percentage", "%"]];
  const MAIN_INDS = [["MA", "MA"], ["EMA", "EMA"], ["SMA", "SMA"], ["BOLL", "Bollinger"], ["BBI", "BBI"], ["SAR", "SAR"]];
  const SUB_INDS = [["VOL", "Volume"], ["MACD", "MACD"], ["RSI", "RSI"], ["KDJ", "KDJ"], ["CCI", "CCI"], ["WR", "Williams %R"],
    ["DMI", "DMI/ADX"], ["OBV", "OBV"], ["ROC", "ROC"], ["TRIX", "TRIX"], ["BIAS", "BIAS"], ["MTM", "Momentum"],
    ["PSY", "PSY"], ["BRAR", "BRAR"], ["CR", "CR"], ["VR", "VR"], ["EMV", "EMV"], ["DMA", "DMA"], ["AO", "AO"], ["PVT", "PVT"]];
  const MAIN_SET = new Set(MAIN_INDS.map(([v]) => v));
  const DEFAULTS = { MA: [5, 10, 30, 60], EMA: [6, 12, 20], SMA: [12, 2], BOLL: [20, 2], BBI: [3, 6, 12, 24], SAR: [2, 2, 20],
    VOL: [5, 10, 20], MACD: [12, 26, 9], RSI: [6, 12, 24], KDJ: [9, 3, 3], CCI: [13], WR: [6, 10, 14], DMI: [14, 6], OBV: [30],
    ROC: [12, 6], TRIX: [12, 9], BIAS: [6, 12, 24], MTM: [6, 10], PSY: [12, 6], BRAR: [26], CR: [26, 10, 20, 40, 60],
    VR: [24, 30], EMV: [14, 9], DMA: [10, 50, 10], AO: [5, 34], PVT: [] };
  const TOOLS = [
    ["cursor", "Cursor"], ["segment", "Trend line"], ["rayLine", "Ray"], ["horizontalStraightLine", "Horizontal"],
    ["verticalStraightLine", "Vertical"], ["priceLine", "Price line"], ["parallelStraightLine", "Parallel"],
    ["fibonacciLine", "Fibonacci"], ["simpleAnnotation", "Text"], ["measurePct", "Measure %"],
  ];
  const nfmt = (x) => (x == null || !isFinite(x) ? "—" : Math.abs(x) < 10 ? x.toLocaleString(undefined, { maximumFractionDigits: 4 }) : x.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  const pct = (x) => (x == null || !isFinite(x) ? "—" : (x * 100).toFixed(1) + "%");
  const f2 = (x) => (x == null || !isFinite(x) ? "—" : x.toFixed(2));
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // ---------- indicator math (Signal Playbook backtests) ----------
  function sma(a, n) { const o = Array(a.length).fill(null); let s = 0; for (let i = 0; i < a.length; i++) { s += a[i]; if (i >= n) s -= a[i - n]; if (i >= n - 1) o[i] = s / n; } return o; }
  function ema(a, n) { const o = Array(a.length).fill(null); const k = 2 / (n + 1); let e = null; for (let i = 0; i < a.length; i++) { e = e == null ? a[i] : a[i] * k + e * (1 - k); if (i >= n - 1) o[i] = e; } return o; }
  function rstd(a, n) { const o = Array(a.length).fill(null); for (let i = n - 1; i < a.length; i++) { let m = 0; for (let j = i - n + 1; j <= i; j++) m += a[j]; m /= n; let v = 0; for (let j = i - n + 1; j <= i; j++) v += (a[j] - m) ** 2; o[i] = Math.sqrt(v / n); } return o; }
  function rsiArr(a, n) { const o = Array(a.length).fill(null); let g = 0, l = 0; for (let i = 1; i < a.length; i++) { const ch = a[i] - a[i - 1], gg = Math.max(ch, 0), ll = Math.max(-ch, 0); if (i <= n) { g += gg; l += ll; if (i === n) { g /= n; l /= n; o[i] = 100 - 100 / (1 + (l === 0 ? 1e9 : g / l)); } } else { g = (g * (n - 1) + gg) / n; l = (l * (n - 1) + ll) / n; o[i] = 100 - 100 / (1 + (l === 0 ? 1e9 : g / l)); } } return o; }
  function macdP(a, f, s, sig) { const ef = ema(a, f), es = ema(a, s); const m = a.map((_, i) => (ef[i] == null || es[i] == null ? null : ef[i] - es[i])); const g = ema(m.map((v) => v == null ? 0 : v), sig).map((v, i) => (m[i] == null ? null : v)); return { macd: m, signal: g }; }
  function rollMax(a, n) { const o = Array(a.length).fill(null); for (let i = n - 1; i < a.length; i++) { let x = -Infinity; for (let j = i - n + 1; j <= i; j++) if (a[j] > x) x = a[j]; o[i] = x; } return o; }
  function rollMin(a, n) { const o = Array(a.length).fill(null); for (let i = n - 1; i < a.length; i++) { let x = Infinity; for (let j = i - n + 1; j <= i; j++) if (a[j] < x) x = a[j]; o[i] = x; } return o; }
  function stoch(c, hi, lo, kn, dn) { const k = Array(c.length).fill(null); if (!hi || !lo) return { k, d: k }; for (let i = kn - 1; i < c.length; i++) { let h = -Infinity, l = Infinity; for (let j = i - kn + 1; j <= i; j++) { if (hi[j] > h) h = hi[j]; if (lo[j] < l) l = lo[j]; } k[i] = h > l ? ((c[i] - l) / (h - l)) * 100 : 50; } const d = sma(k.map((x) => (x == null ? 0 : x)), dn).map((x, i) => (k[i] == null ? null : x)); return { k, d }; }
  function willR(c, hi, lo, n) { const o = Array(c.length).fill(null); if (!hi || !lo) return o; for (let i = n - 1; i < c.length; i++) { let h = -Infinity, l = Infinity; for (let j = i - n + 1; j <= i; j++) { if (hi[j] > h) h = hi[j]; if (lo[j] < l) l = lo[j]; } o[i] = h > l ? ((h - c[i]) / (h - l)) * -100 : -50; } return o; }
  function cci(c, hi, lo, n) { if (!hi || !lo) return Array(c.length).fill(null); const tp = c.map((x, i) => (hi[i] + lo[i] + x) / 3); const ma = sma(tp, n); const o = Array(c.length).fill(null); for (let i = n - 1; i < c.length; i++) { let md = 0; for (let j = i - n + 1; j <= i; j++) md += Math.abs(tp[j] - ma[i]); md /= n; o[i] = md ? (tp[i] - ma[i]) / (0.015 * md) : 0; } return o; }
  function backtest(c, posArr) { const n = c.length, eq = Array(n), ret = Array(n); let e = 100; for (let i = 0; i < n; i++) { const r = i ? (posArr[i - 1] || 0) * (c[i] / c[i - 1] - 1) : 0; e *= 1 + r; eq[i] = e; ret[i] = r; } return { eq, ret }; }
  // yield-as-PnL: while invested you earn the yield as daily carry (rate% / 252), ignoring bond price moves
  function btYield(y, posArr) { const n = y.length, eq = Array(n), ret = Array(n); let e = 100; for (let i = 0; i < n; i++) { const r = i ? (posArr[i - 1] || 0) * ((y[i - 1] || 0) / 100 / 252) : 0; e *= 1 + r; eq[i] = e; ret[i] = r; } return { eq, ret }; }
  // leveraged backtest with costs: financing FIN/yr on the borrowed (>1x) portion + COST per unit of leverage change
  function btLev(c, lev, costs) { const n = c.length, eq = Array(n), ret = Array(n); let e = 100; const FIN = 0.04, COST = costs ? 0.0005 : 0; for (let i = 0; i < n; i++) { const held = i ? lev[i - 1] : 0, chg = Math.abs((i ? lev[i - 1] : 0) - (i > 1 ? lev[i - 2] : 0)); const r = i ? held * (c[i] / c[i - 1] - 1) - Math.max(0, held - 1) * (FIN / 252) - chg * COST : 0; e *= 1 + r; eq[i] = e; ret[i] = r; } return { eq, ret }; }
  function ddFromHigh(c, w) { const hi = rollMax(c, w); return c.map((x, i) => (hi[i] ? x / hi[i] - 1 : 0)); }
  function rvol(c, w) { const r = c.map((x, i) => (i ? x / c[i - 1] - 1 : 0)); const o = Array(c.length).fill(0); for (let i = w; i < c.length; i++) { let m = 0; for (let j = i - w + 1; j <= i; j++) m += r[j]; m /= w; let v = 0; for (let j = i - w + 1; j <= i; j++) v += (r[j] - m) ** 2; o[i] = Math.sqrt(v / w) * Math.sqrt(252); } return o; }
  function stats(eq, ret, posArr) { const n = eq.length; if (n < 30) return { cagr: NaN, vol: NaN, sharpe: NaN, maxdd: NaN, end: eq[n - 1], pin: NaN }; const yrs = n / 252, cagr = Math.pow(eq[n - 1] / 100, 1 / yrs) - 1; let m = 0; for (const r of ret) m += r; m /= n; let v = 0; for (const r of ret) v += (r - m) ** 2; const vol = Math.sqrt(v / (n - 1)) * Math.sqrt(252); let pk = -1e9, mdd = 0; for (const x of eq) { if (x > pk) pk = x; const dd = x / pk - 1; if (dd < mdd) mdd = dd; } let inn = 0; for (const p of posArr) inn += p > 0 ? 1 : 0; return { cagr, vol, sharpe: vol ? (m * 252) / vol : NaN, maxdd: mdd, end: eq[n - 1], pin: inn / n }; }

  const STRATS = [
    { key: "gc", name: "Golden Cross", params: [{ k: "fast", label: "Fast SMA", d: 50, min: 2, max: 300 }, { k: "slow", label: "Slow SMA", d: 200, min: 5, max: 400 }],
      sig: (c, p) => { const a = sma(c, p.fast), b = sma(c, p.slow); return c.map((_, i) => (a[i] != null && b[i] != null && a[i] >= b[i]) ? 1 : 0); },
      plot: { ind: "MA", cp: (p) => [p.fast, p.slow] }, buy: (p) => `SMA${p.fast} crosses above SMA${p.slow}`, sell: (p) => `SMA${p.fast} below SMA${p.slow}`,
      note: "Buy when the faster average crosses above the slower one; sell when it crosses back below. <b>Why:</b> the crossover confirms recent prices have decisively overtaken the long-run trend, so you ride sustained advances and step aside in sustained declines. <b>Trade-off:</b> it lags turning points and gets whipsawed in flat, choppy markets." },
    { key: "trend", name: "Trend filter", params: [{ k: "win", label: "SMA", d: 200, min: 5, max: 400 }],
      sig: (c, p) => { const b = sma(c, p.win); return c.map((x, i) => (b[i] != null && x >= b[i]) ? 1 : 0); },
      plot: { ind: "MA", cp: (p) => [p.win] }, buy: (p) => `Close rises above SMA${p.win}`, sell: (p) => `Close falls below SMA${p.win}`,
      note: "Hold only while price closes above its long moving average; go to cash below it. <b>Why:</b> bear markets spend most of their time under the trend line, so this simple filter sidesteps the deepest drawdowns. <b>Trade-off:</b> frequent small whipsaws when price oscillates around the line." },
    { key: "bandtrend", name: "Band trend (SMA ±%)", params: [{ k: "win", label: "SMA", d: 200, min: 5, max: 400 }, { k: "band", label: "Band %", d: 3, min: 0, max: 15, step: 0.5 }],
      sig: (c, p) => { const s = sma(c, p.win); const b = p.band / 100; let st = 0; return c.map((x, i) => { if (s[i] != null) { if (x > s[i] * (1 + b)) st = 1; else if (x < s[i] * (1 - b)) st = 0; } return st; }); },
      plot: { ind: "MA", cp: (p) => [p.win] }, buy: (p) => `Close rises >${p.band}% above SMA${p.win}`, sell: (p) => `Close falls >${p.band}% below SMA${p.win}`,
      note: "The site's <b>Water</b> family: go long when price closes more than X% <i>above</i> its long SMA and exit to cash when it closes more than X% <i>below</i> — a dead-band (hysteresis) around the trend line. <b>Why:</b> the band filters out whipsaws right at the average, cutting trades and false signals versus a plain SMA cross. <b>Tuning:</b> on the S&P a slightly shorter SMA (~175) with a ±3% band has historically trimmed drawdown at roughly equal return — the most defensible tweak to the SMA200 ±3% default (though the edge is thin and not robust across every era)." },
    { key: "macd", name: "MACD", params: [{ k: "fast", label: "Fast", d: 12, min: 2, max: 50 }, { k: "slow", label: "Slow", d: 26, min: 3, max: 100 }, { k: "signal", label: "Signal", d: 9, min: 2, max: 50 }],
      sig: (c, p) => { const m = macdP(c, p.fast, p.slow, p.signal); return c.map((_, i) => (m.macd[i] != null && m.signal[i] != null && m.macd[i] >= m.signal[i]) ? 1 : 0); },
      plot: { ind: "MACD", cp: (p) => [p.fast, p.slow, p.signal] }, buy: (p) => `MACD(${p.fast},${p.slow}) crosses above signal ${p.signal}`, sell: () => "MACD crosses below signal",
      note: "Buy when the MACD line (fast EMA − slow EMA) crosses above its signal line; sell when it crosses below. <b>Why:</b> the difference of two EMAs reacts to momentum shifts earlier than a single moving average. <b>Trade-off:</b> noisy and prone to false signals in range-bound markets." },
    { key: "rsi", name: "RSI momentum", params: [{ k: "period", label: "Period", d: 14, min: 2, max: 50 }, { k: "level", label: "Level", d: 50, min: 1, max: 99 }],
      sig: (c, p) => { const r = rsiArr(c, p.period); return c.map((_, i) => (r[i] != null && r[i] >= p.level) ? 1 : 0); },
      plot: { ind: "RSI", cp: (p) => [p.period] }, buy: (p) => `RSI(${p.period}) rises above ${p.level}`, sell: (p) => `RSI falls below ${p.level}`,
      note: "Stay long while RSI is above the midline (50) and in cash below it. <b>Why:</b> RSI above 50 means average gains outweigh average losses — a clean momentum-regime filter. <b>Note:</b> the famous 30/70 oversold/overbought reading is a <i>mean-reversion</i> signal instead (buy oversold, sell overbought)." },
    { key: "boll", name: "Bollinger reversion", params: [{ k: "win", label: "Window", d: 20, min: 5, max: 100 }, { k: "mult", label: "Std×", d: 2, min: 0.5, max: 4, step: 0.1 }],
      sig: (c, p) => { const mid = sma(c, p.win), sd = rstd(c, p.win); let s = 0; return c.map((x, i) => { if (mid[i] == null) return 0; if (s === 0 && x < mid[i] - p.mult * sd[i]) s = 1; else if (s === 1 && x > mid[i]) s = 0; return s; }); },
      plot: { ind: "BOLL", cp: (p) => [p.win, p.mult] }, buy: (p) => `Close dips below the lower band (${p.win}, ${p.mult}σ)`, sell: () => "Close returns above the mid band",
      note: "Buy when price stretches below the lower band (statistically cheap) and exit when it reverts to the middle band. <b>Why:</b> prices tend to snap back toward their average after extreme moves. <b>Trade-off:</b> dangerous in strong trends, where 'cheap' just keeps getting cheaper." },
    { key: "donch", name: "Donchian breakout", params: [{ k: "win", label: "Window", d: 20, min: 3, max: 200 }],
      sig: (c, p) => { const hi = rollMax(c, p.win), lo = rollMin(c, p.win); let s = 0; return c.map((x, i) => { if (i < p.win) return 0; if (x >= hi[i - 1]) s = 1; else if (x <= lo[i - 1]) s = 0; return s; }); },
      plot: null, buy: (p) => `Close makes a new ${p.win}-day high`, sell: (p) => `Close makes a new ${p.win}-day low`,
      note: "Buy when price breaks to a new N-day high; sell when it breaks to a new N-day low. <b>Why:</b> a fresh extreme means the move has overcome all recent resistance/support — the core of classic turtle trend-following. <b>Trade-off:</b> many false breakouts in sideways ranges." },
    { key: "emacross", name: "EMA Cross", params: [{ k: "fast", label: "Fast EMA", d: 12, min: 2, max: 100 }, { k: "slow", label: "Slow EMA", d: 26, min: 3, max: 200 }],
      sig: (c, p) => { const a = ema(c, p.fast), b = ema(c, p.slow); return c.map((_, i) => (a[i] != null && b[i] != null && a[i] >= b[i]) ? 1 : 0); },
      plot: { ind: "EMA", cp: (p) => [p.fast, p.slow] }, buy: (p) => `EMA${p.fast} crosses above EMA${p.slow}`, sell: (p) => `EMA${p.fast} below EMA${p.slow}`,
      note: "Like the Golden Cross but with exponential averages that weight recent prices more, so it turns a touch faster. <b>Why:</b> quicker trend confirmation, at the cost of a few more whipsaws than plain SMAs." },
    { key: "rsirev", name: "RSI reversion", params: [{ k: "period", label: "Period", d: 14, min: 2, max: 50 }, { k: "lower", label: "Buy <", d: 30, min: 1, max: 49 }, { k: "upper", label: "Exit >", d: 70, min: 51, max: 99 }],
      sig: (c, p) => { const r = rsiArr(c, p.period); let s = 0; return c.map((_, i) => { if (r[i] == null) return 0; if (s === 0 && r[i] < p.lower) s = 1; else if (s === 1 && r[i] > p.upper) s = 0; return s; }); },
      plot: { ind: "RSI", cp: (p) => [p.period] }, buy: (p) => `RSI(${p.period}) drops below ${p.lower} (oversold)`, sell: (p) => `RSI rises above ${p.upper} (overbought)`,
      note: "The classic oversold/overbought rule: buy when RSI falls below the lower band, sell when it pushes above the upper. <b>Why:</b> momentum extremes often precede short-term snapbacks. <b>Trade-off:</b> fights strong trends — oversold can stay oversold for a long time." },
    { key: "macdzero", name: "MACD zero-line", params: [{ k: "fast", label: "Fast", d: 12, min: 2, max: 50 }, { k: "slow", label: "Slow", d: 26, min: 3, max: 100 }],
      sig: (c, p) => { const m = macdP(c, p.fast, p.slow, 9); return c.map((_, i) => (m.macd[i] != null && m.macd[i] >= 0) ? 1 : 0); },
      plot: { ind: "MACD", cp: (p) => [p.fast, p.slow, 9] }, buy: (p) => `MACD(${p.fast},${p.slow}) rises above zero`, sell: () => "MACD falls below zero",
      note: "Hold while the MACD line is above zero (fast EMA above slow EMA), exit below it. <b>Why:</b> the zero line is a pure trend gauge — above zero, the shorter average leads. Smoother than the signal-line cross, with fewer trades." },
    { key: "willr", name: "Williams %R", params: [{ k: "period", label: "Period", d: 14, min: 2, max: 50 }, { k: "level", label: "Long ≥", d: -50, min: -99, max: -1 }],
      sig: (c, p, hi, lo) => { const w = willR(c, hi, lo, p.period); return c.map((_, i) => (w[i] != null && w[i] >= p.level) ? 1 : 0); },
      plot: { ind: "WR", cp: (p) => [p.period] }, buy: (p) => `Williams %R(${p.period}) above ${p.level}`, sell: (p) => `%R below ${p.level}`,
      note: "Williams %R shows where the close sits in the recent high–low range (0 = top, −100 = bottom). Hold in the upper half. <b>Why:</b> closing near recent highs signals buying pressure. <b>Trade-off:</b> a fast oscillator, prone to whipsaws." },
    { key: "stoch", name: "Stochastic %K/%D", params: [{ k: "kp", label: "%K", d: 14, min: 2, max: 50 }, { k: "dp", label: "%D", d: 3, min: 1, max: 20 }],
      sig: (c, p, hi, lo) => { const s = stoch(c, hi, lo, p.kp, p.dp); return c.map((_, i) => (s.k[i] != null && s.d[i] != null && s.k[i] >= s.d[i]) ? 1 : 0); },
      plot: { ind: "KDJ", cp: (p) => [p.kp, p.dp, p.dp] }, buy: () => "%K crosses above %D", sell: () => "%K crosses below %D",
      note: "The Stochastic oscillator compares the close to its recent range; trade the %K-vs-%D crossover. <b>Why:</b> %K leading %D flags building momentum within the range. <b>Trade-off:</b> best in ranges, noisy in strong trends." },
    { key: "cci", name: "CCI", params: [{ k: "period", label: "Period", d: 20, min: 3, max: 100 }, { k: "level", label: "Long ≥", d: 0, min: -200, max: 200 }],
      sig: (c, p, hi, lo) => { const v = cci(c, hi, lo, p.period); return c.map((_, i) => (v[i] != null && v[i] >= p.level) ? 1 : 0); },
      plot: { ind: "CCI", cp: (p) => [p.period] }, buy: (p) => `CCI(${p.period}) above ${p.level}`, sell: (p) => `CCI below ${p.level}`,
      note: "The Commodity Channel Index measures how far price is from its average in units of mean deviation. Hold while CCI is above the threshold. <b>Why:</b> positive CCI marks an uptrend bias; ±100 are common breakout markers. <b>Trade-off:</b> unbounded and jumpy." },
    { key: "rsidip", name: "RSI dip + SMA exit", params: [{ k: "rp", label: "RSI period", d: 2, min: 2, max: 30 }, { k: "level", label: "Buy RSI<", d: 20, min: 1, max: 50 }, { k: "win", label: "Exit SMA", d: 200, min: 20, max: 400 }, { k: "band", label: "Exit band %", d: 5, min: 0, max: 15, step: 0.5 }, { k: "trend", label: "Trend filt 1/0", d: 1, min: 0, max: 1 }],
      sig: (c, p) => { const r = rsiArr(c, p.rp), s = sma(c, p.win), b = p.band / 100; let st = 0; return c.map((x, i) => { if (st === 0) { if (r[i] != null && r[i] < p.level && (p.trend < 1 || (s[i] != null && x >= s[i]))) st = 1; } else { if (s[i] != null && x < s[i] * (1 - b)) st = 0; } return st; }); },
      plot: { ind: "RSI", cp: (p) => [p.rp] }, buy: (p) => `RSI(${p.rp}) dips below ${p.level}${p.trend >= 1 ? " while above SMA" + p.win : ""}`, sell: (p) => `Close falls >${p.band}% below SMA${p.win}`,
      note: "<b>Buy oversold dips inside an uptrend, exit on a trend break.</b> Enter when a fast RSI drops below the threshold (a short-term dip) while price is still above its long SMA (trend filter on); exit only when price closes more than X% below that SMA. <b>Why:</b> the RSI dip times cheaper entries than a plain trend rule, while the SMA-band exit keeps you out of sustained downtrends. On the S&P, <b>RSI2&lt;20 + trend, exit SMA200 −5%</b> was the one rule in a 1,500-config sweep to beat the SMA200 ±3% default on CAGR, drawdown AND Sharpe across the full, 50-year and 30-year windows — a modest but robust edge." },
  ];

  // shared with the custom signal-marker indicator (set per active strategy in run())
  let ACTIVE_SIGNAL = null;
  function registerIndicators() {
    if (!window.klinecharts) return;
    try {
      klinecharts.registerOverlay({
        name: "measurePct", totalStep: 3, needDefaultPointFigure: true, needDefaultXAxisFigure: true, needDefaultYAxisFigure: true,
        createPointFigures: ({ overlay, coordinates }) => {
          if (coordinates.length < 2) return [];
          const p = overlay.points; const v0 = p[0].value, v1 = p[1].value; if (v0 == null || v1 == null) return [];
          const diff = v1 - v0, pc = v0 ? (diff / v0) * 100 : 0, up = diff >= 0;
          const days = (p[0].timestamp != null && p[1].timestamp != null) ? Math.round(Math.abs(p[1].timestamp - p[0].timestamp) / 864e5) : null;
          const bars = (p[0].dataIndex != null && p[1].dataIndex != null) ? Math.abs(p[1].dataIndex - p[0].dataIndex) : null;
          const c0 = coordinates[0], c1 = coordinates[1];
          const x = Math.min(c0.x, c1.x), w = Math.max(1, Math.abs(c1.x - c0.x)), y = Math.min(c0.y, c1.y), h = Math.max(1, Math.abs(c1.y - c0.y));
          const col = up ? UP : DN, s = up ? "+" : "";
          const label = `${s}${pc.toFixed(2)}%   ${s}${nfmt(diff)}` + (bars != null ? `   ${bars} bars` : "") + (days != null ? ` · ${days}d` : "");
          return [
            { type: "rect", attrs: { x, y, width: w, height: h }, styles: { style: "stroke_fill", color: up ? "rgba(21,128,61,.10)" : "rgba(180,35,24,.10)", borderColor: col, borderSize: 1, borderStyle: "dashed" }, ignoreEvent: true },
            { type: "text", attrs: { x: (c0.x + c1.x) / 2, y: y - 4, text: label, align: "center", baseline: "bottom" }, styles: { color: "#fff", backgroundColor: col, size: 12, weight: "bold", paddingLeft: 7, paddingRight: 7, paddingTop: 3, paddingBottom: 3, borderRadius: 4 } },
          ];
        },
      });
    } catch (_) {}
    try {
      klinecharts.registerIndicator({
        name: "STRATSIGNAL", figures: [], calc: (dataList) => dataList.map(() => ({})),
        draw: ({ ctx, kLineDataList, visibleRange, xAxis, yAxis }) => {
          if (!ACTIVE_SIGNAL) return false;
          const buys = ACTIVE_SIGNAL.buys, sells = ACTIVE_SIGNAL.sells;
          for (let i = Math.max(0, visibleRange.from); i < visibleRange.to; i++) {
            const d = kLineDataList[i]; if (!d) continue;
            const isB = buys.has(d.timestamp), isS = sells.has(d.timestamp); if (!isB && !isS) continue;
            const x = xAxis.convertToPixel(i), y = yAxis.convertToPixel(isB ? d.low : d.high);
            const yy = isB ? y + 11 : y - 11; ctx.fillStyle = isB ? UP : DN; ctx.beginPath();
            if (isB) { ctx.moveTo(x, yy - 8); ctx.lineTo(x - 5, yy + 2); ctx.lineTo(x + 5, yy + 2); }
            else { ctx.moveTo(x, yy + 8); ctx.lineTo(x - 5, yy - 2); ctx.lineTo(x + 5, yy - 2); }
            ctx.closePath(); ctx.fill();
          }
          return false;
        },
      });
    } catch (_) {}
    try {
      klinecharts.registerIndicator({
        name: "RECESSION", figures: [], calc: (dataList) => dataList.map(() => ({})),
        draw: ({ ctx, kLineDataList, visibleRange, xAxis, bounding }) => {
          const from = Math.max(0, visibleRange.from), to = visibleRange.to, H = (bounding && bounding.height) || 2000;
          ctx.fillStyle = "rgba(110,110,120,0.13)";
          for (const [s, e] of RECESSIONS) {
            let x0 = null, x1 = null;
            for (let i = from; i < to; i++) { const d = kLineDataList[i]; if (!d) continue; if (d.timestamp >= s && d.timestamp <= e) { const x = xAxis.convertToPixel(i); if (x0 === null) x0 = x; x1 = x; } }
            if (x0 !== null) ctx.fillRect(x0 - 1, 0, (x1 - x0) + 2, H);
          }
          return false;
        },
      });
    } catch (_) {}
    try {
      klinecharts.registerIndicator({
        name: "INVERSION", figures: [], calc: (dataList) => dataList.map(() => ({})),
        draw: ({ ctx, kLineDataList, visibleRange, xAxis, bounding }) => {
          if (!INVERSIONS.length) return false;
          const from = Math.max(0, visibleRange.from), to = visibleRange.to, H = (bounding && bounding.height) || 2000;
          ctx.fillStyle = "rgba(214,138,18,0.14)"; // amber = curve inverted (2s10s/3m10y)
          for (const [s, e] of INVERSIONS) {
            let x0 = null, x1 = null;
            for (let i = from; i < to; i++) { const d = kLineDataList[i]; if (!d) continue; if (d.timestamp >= s && d.timestamp <= e) { const x = xAxis.convertToPixel(i); if (x0 === null) x0 = x; x1 = x; } }
            if (x0 !== null) ctx.fillRect(x0 - 1, 0, (x1 - x0) + 2, H);
          }
          return false;
        },
      });
    } catch (_) {}
  }

  function injectStyles() {
    if (document.getElementById("charts-styles")) return;
    const s = document.createElement("style"); s.id = "charts-styles";
    s.textContent = `
      .cbar{display:flex;gap:18px;flex-wrap:wrap;align-items:center;margin:6px 0;}
      .cbar .lbl{font-size:11.5px;font-weight:700;color:#6e6e73;margin-right:6px;text-transform:uppercase;letter-spacing:.03em;}
      .cbar select{font:inherit;font-size:14px;font-weight:600;padding:8px 12px;border-radius:10px;border:1px solid var(--line);background:#fff;}
      .seg{display:inline-flex;gap:5px;flex-wrap:wrap;}
      .seg button{font:inherit;font-size:12.5px;font-weight:600;padding:6px 12px;border-radius:999px;border:1px solid var(--line);background:#fff;cursor:pointer;transition:all .12s;}
      .seg button:hover{border-color:var(--accent);}
      .seg button.active{background:var(--accent);color:#fff;border-color:var(--accent);}
      .seg button.tool.active{background:#1d1d1f;border-color:#1d1d1f;}
      .live{display:inline-flex;align-items:center;gap:7px;font-size:13px;margin-left:auto;}
      .live .dot{width:8px;height:8px;border-radius:50%;background:var(--muted);}
      .live.on .dot{background:var(--good);box-shadow:0 0 0 3px rgba(48,209,88,.18);}
      #chart{width:100%;height:560px;border:1px solid var(--line);border-radius:12px;overflow:hidden;}
      @media(max-width:680px){#chart{height:62vh;}}
      details.ind-panel{margin:6px 0;border:1px solid var(--line);border-radius:12px;padding:2px 14px;background:rgba(255,255,255,.6);}
      details.ind-panel summary{font-size:12.5px;font-weight:700;cursor:pointer;padding:8px 0;color:#1d1d1f;}
      details.ind-panel[open] summary{border-bottom:1px solid var(--line);margin-bottom:6px;}
      .ind-grp{display:flex;gap:8px;align-items:center;margin:7px 0;flex-wrap:wrap;}
      .ipar{font-size:12px;display:inline-flex;align-items:center;gap:5px;border:1px solid var(--line);border-radius:8px;padding:3px 8px;background:#fff;}
      .ipar input{font:inherit;font-size:12px;border:none;width:84px;outline:none;}
      .notes-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px;}
      .notes-row button{font:inherit;font-size:13px;font-weight:600;padding:8px 14px;border-radius:10px;border:1px solid var(--line);background:#fff;cursor:pointer;}
      .notes-row button.apply{background:var(--accent);color:#fff;border-color:var(--accent);}
      #notes{width:100%;box-sizing:border-box;font:inherit;font-size:13px;padding:11px 13px;border-radius:10px;border:1px solid var(--line);resize:vertical;}
      table.pb{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px;}
      table.pb th,table.pb td{padding:9px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap;vertical-align:top;}
      table.pb th:first-child,table.pb td:first-child{text-align:left;white-space:normal;}
      table.pb th{font-size:11px;color:#6e6e73;text-transform:uppercase;letter-spacing:.03em;font-weight:700;}
      table.pb tr.bh{background:rgba(0,0,0,.035);font-weight:700;}
      table.pb .sig{font-size:11.5px;color:#6e6e73;margin:3px 0 5px;}
      table.pb .num{font-variant-numeric:tabular-nums;}
      table.pb .win{color:${UP};font-weight:700;}
      .pbp{display:flex;gap:7px;flex-wrap:wrap;margin-top:4px;}
      .pbp label{font-size:11px;color:#6e6e73;display:inline-flex;align-items:center;gap:4px;}
      .pbp input{font:inherit;font-size:12px;width:56px;padding:4px 6px;border-radius:7px;border:1px solid var(--line);}
      .pbacts{display:flex;flex-direction:column;gap:4px;align-items:stretch;min-width:74px;}
      .pb-btn{font:inherit;font-size:11.5px;font-weight:600;padding:5px 9px;border-radius:8px;border:1px solid var(--line);background:#fff;cursor:pointer;white-space:nowrap;}
      .pb-btn:hover{border-color:var(--accent);}
      .pb-btn.on{background:var(--accent);color:#fff;border-color:var(--accent);}
      .pb-btn.sig.on{background:#1d1d1f;border-color:#1d1d1f;}
      .pb-btn:disabled{opacity:.35;cursor:default;}
      tr.noterow td{background:rgba(0,113,227,.05);border-bottom:2px solid var(--line);font-size:12.5px;line-height:1.55;color:#333;padding:10px 14px;}
      #playbook,#leader{overflow-x:auto;-webkit-overflow-scrolling:touch;}
      @media(max-width:680px){
        table.pb th,table.pb td{padding:7px 7px;font-size:12px;}
        .pbacts{min-width:64px;} .pb-btn{padding:5px 7px;font-size:11px;}
        .cbar{gap:10px;} .pbp input{width:48px;}
        h1{font-size:24px;} h2{font-size:18px;}
      }
    `;
    document.head.appendChild(s);
  }

  function run() {
    injectStyles(); registerIndicators();
    if (window.STRATEGY_PAGE_TITLE) document.title = window.STRATEGY_PAGE_TITLE;
    const state = { asset: "spx", tf: "D", type: "candle_solid", yAxis: "normal", tool: "cursor", tfLastTs: 0,
      indicators: Object.fromEntries(MAIN_INDS.concat(SUB_INDS).map(([v]) => [v, false])),
      indParams: Object.fromEntries(Object.entries(DEFAULTS).map(([k, v]) => [k, v.slice()])),
      stratParams: Object.fromEntries(STRATS.map((s) => [s.key, Object.fromEntries(s.params.map((q) => [q.k, q.d]))])),
      plotted: {}, signalKey: null, notesOpen: {}, curClose: [], curTs: [], curHigh: [], curLow: [],
      lev: { mult: 1, ddThr: -10, volThr: 18, costs: false }, pnl: { mode: "bps", perBp: 0 }, recession: false, inversion: false, carry: false };
    const D = { id: "", ticker: "", label: "", kind: "price", klass: "", legs: null, cr: null, dv01: 1, n: 0, dates: [], close: [], high: [], low: [], daily: [], ddh: [], rv: [] };
    let chart = null, ASSETS = [], drawings = [], saveTimer = null, restoring = false, pollTimer = null, LEADER = [], CURVE = [], pendingBest = null;

    const app = document.getElementById("app");
    app.innerHTML = `
      <h1 id="cTitle">Charts</h1>
      <p class="lede">Candlestick charts with indicators, drawing tools and multiple timeframes. Tune any indicator's
        parameters, and the <b>Signal Playbook</b> below backtests common buy/sell rules on this asset — plot the indicator,
        show ▲ buy / ▼ sell markers on the chart, and read what each signal means, all from the same parameters.</p>
      <div class="card">
        <div class="cbar">
          <div><span class="lbl">Asset</span><select id="assetSel"></select></div>
          <div class="live" id="live"><span class="dot"></span><span id="liveTxt">live —</span></div>
        </div>
        <div class="cbar">
          <div><span class="lbl">Timeframe</span><span class="seg" id="tfSeg"></span></div>
          <div><span class="lbl">Type</span><span class="seg" id="typeSeg"></span></div>
          <div><span class="lbl">Axis</span><span class="seg" id="axisSeg"></span></div>
          <div><span class="lbl">Range</span><span class="seg" id="rangeSeg"></span></div>
        </div>
        <details class="ind-panel">
          <summary>Indicators — overlays &amp; studies · click to expand, then edit parameters of active ones</summary>
          <div class="ind-grp"><span class="lbl">On&nbsp;price</span><span class="seg" id="indMain"></span></div>
          <div class="ind-grp"><span class="lbl">Studies</span><span class="seg" id="indSub"></span></div>
          <div class="ind-grp" id="indParams"></div>
        </details>
        <div class="cbar">
          <div><span class="lbl">Draw</span><span class="seg" id="toolSeg"></span></div>
          <div class="seg"><button id="undoBtn">Undo</button><button id="clearBtn">Clear all</button><button id="recBtn"><span style="color:#9a9aa2">▦</span> Recessions</button><button id="invBtn"><span style="color:#d68a12">⊘</span> Inversions</button></div>
        </div>
        <div id="chart"></div>
        <p class="meta" id="hint" style="margin-top:8px">Scroll to zoom · drag to pan · pick a draw tool then click points on the chart.</p>
      </div>
      <div class="card" id="curveCard" style="display:none">
        <h2 style="margin-bottom:2px">US Treasury curve <span class="meta" id="curveAsof" style="font-weight:400"></span></h2>
        <div id="curveSvg" style="overflow-x:auto"></div>
        <div id="curveFlags" class="meta" style="margin-top:6px"></div>
      </div>
      <div class="card" id="leaderCard" style="display:none">
        <h2 style="margin-bottom:2px">Curve strategy leaderboard <span class="meta" style="font-weight:400">— best backtested rule per UST instrument</span></h2>
        <p class="meta" style="margin-top:4px">A comprehensive sweep (26 strategy/parameter configs × 12 instruments) over each instrument's full history, ranked by <b>Sharpe</b> of the directional P&L (bps). <b>Load</b> applies a rule to the chart + playbook below. Educational only — not advice.</p>
        <div id="leaderNote" class="meta" style="margin:4px 0 2px"></div>
        <div id="leader"></div>
      </div>
      <div class="card">
        <h2 style="margin-bottom:2px">Signal playbook <span class="meta" id="pbAsset" style="font-weight:400"></span></h2>
        <p class="meta" style="margin-top:4px">Edit a rule's parameters → its <b>backtest updates live</b> (long-or-cash, next-day fills, cash 0%, no costs, full daily history).
          <b>plot</b> = draw the indicator · <b>signals</b> = ▲/▼ markers on the chart · <b>notes</b> = what the buy/sell signal means. Educational only — not advice.</p>
        <div class="cbar" id="levBar" style="margin:2px 0 4px">
          <div><span class="lbl">Leverage</span><span class="seg" id="levSeg"></span></div>
          <span id="levSafe" style="display:none;font-size:12px;color:#6e6e73">go <b id="levMultLbl">2×</b> when DD &gt; <input id="levDD" type="number" step="1" style="width:48px;font:inherit;font-size:12px;padding:3px 5px;border-radius:7px;border:1px solid var(--line)"> % &amp; 20-day vol &lt; <input id="levVol" type="number" step="1" style="width:48px;font:inherit;font-size:12px;padding:3px 5px;border-radius:7px;border:1px solid var(--line)"> %</span>
          <div><span class="lbl">Costs</span><span class="seg" id="costSeg"></span></div>
        </div>
        <div class="cbar" id="pnlBar" style="display:none;margin:2px 0 4px">
          <div><span class="lbl">P&amp;L unit</span><span class="seg" id="pnlSeg"></span></div>
          <span id="pnlPerBp" style="display:none;font-size:12px;color:#6e6e73">$ per bp (trade DV01) <input id="perBpInput" type="number" step="50" style="width:88px;font:inherit;font-size:12px;padding:3px 6px;border-radius:7px;border:1px solid var(--line)"></span>
          <label style="font-size:12px;color:#6e6e73;display:inline-flex;align-items:center;gap:5px;cursor:pointer"><input type="checkbox" id="carryChk"> carry/roll in P&amp;L</label>
        </div>
        <div id="playbook"><p class="meta">Loading…</p></div>
      </div>
      <div class="card">
        <h2>Notes <span class="meta" id="notesStatus" style="font-weight:400"></span></h2>
        <div class="notes-row"><button id="cloudBtn" class="apply">☁ Save to cloud</button><span class="meta" id="cloudAuth"></span></div>
        <textarea id="notes" rows="5" placeholder="Your private notes for this asset (saved locally; ☁ for cross-device)…"></textarea>
        <p class="meta" style="margin-top:8px">Your notes, drawings, indicator &amp; strategy parameters are <b>private</b> and saved per asset — passphrase to view/save, auto-saved in this browser meanwhile.</p>
      </div>`;

    const $ = (id) => document.getElementById(id);
    const segActive = (c, b) => c.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
    const findBtn = (c, v) => [...c.querySelectorAll("button")].find((b) => b.dataset.v === v);
    function makeSeg(host, items, isActive, onPick, cls) { host.innerHTML = ""; items.forEach(([val, label]) => { const b = document.createElement("button"); if (cls) b.className = cls; b.textContent = label; b.dataset.v = val; if (isActive(val)) b.classList.add("active"); b.onclick = () => onPick(val, b); host.appendChild(b); }); }
    function safe(fn) { try { return fn(); } catch (e) { status("error: " + (e.message || e)); } }

    chart = klinecharts.init($("chart"));
    chart.setStyles({
      grid: { horizontal: { color: "#eee" }, vertical: { color: "#f4f4f4" } },
      candle: { type: state.type, bar: { upColor: UP, downColor: DN, noChangeColor: "#888", upBorderColor: UP, downBorderColor: DN, upWickColor: UP, downWickColor: DN }, priceMark: { last: { show: true }, high: { show: true }, low: { show: true } }, tooltip: { showRule: "always", showType: "rect" } },
      indicator: { lastValueMark: { show: false } }, yAxis: { type: state.yAxis }, xAxis: { tickText: { color: "#8a8a8e" } },
    });
    window.addEventListener("resize", () => chart && chart.resize());
    setTimeout(() => chart && chart.resize(), 60);

    makeSeg($("tfSeg"), TFS.map((t) => [t.id, t.label]), (v) => v === state.tf, (v, b) => { state.tf = v; segActive($("tfSeg"), b); applyTF(); });
    makeSeg($("typeSeg"), TYPES, (v) => v === state.type, (v, b) => { state.type = v; safe(() => chart.setStyles({ candle: { type: v } })); segActive($("typeSeg"), b); scheduleSave(); });
    makeSeg($("axisSeg"), AXES, (v) => v === state.yAxis, (v, b) => { state.yAxis = v; safe(() => chart.setStyles({ yAxis: { type: v } })); segActive($("axisSeg"), b); scheduleSave(); });
    makeSeg($("rangeSeg"), RANGES, () => false, (days, b) => { setRange(days); segActive($("rangeSeg"), b); });
    makeSeg($("indMain"), MAIN_INDS, (v) => state.indicators[v], (v, b) => { toggleIndicator(v); b.classList.toggle("active", state.indicators[v]); scheduleSave(); });
    makeSeg($("indSub"), SUB_INDS, (v) => state.indicators[v], (v, b) => { toggleIndicator(v); b.classList.toggle("active", state.indicators[v]); scheduleSave(); });
    makeSeg($("toolSeg"), TOOLS, (v) => v === state.tool, (v, b) => { pickTool(v); segActive($("toolSeg"), b); }, "tool");
    $("undoBtn").onclick = undoDrawing;
    $("clearBtn").onclick = clearDrawings;
    $("recBtn").onclick = () => { state.recession = !state.recession; $("recBtn").classList.toggle("active", state.recession); safe(() => { if (state.recession) chart.createIndicator("RECESSION", true, { id: "candle_pane" }); else chart.removeIndicator("candle_pane", "RECESSION"); }); };
    $("invBtn").onclick = () => { state.inversion = !state.inversion; $("invBtn").classList.toggle("active", state.inversion); safe(() => { if (state.inversion) chart.createIndicator("INVERSION", true, { id: "candle_pane" }); else chart.removeIndicator("candle_pane", "INVERSION"); }); };
    $("carryChk").onchange = () => { state.carry = $("carryChk").checked; renderPlaybook(); };

    // leverage / costs controls (drive the playbook backtests)
    function syncLevUI() { const L = state.lev; segActive($("levSeg"), findBtn($("levSeg"), String(L.mult))); segActive($("costSeg"), findBtn($("costSeg"), L.costs ? "1" : "0")); $("levSafe").style.display = L.mult > 1 ? "" : "none"; $("levMultLbl").textContent = L.mult + "×"; $("levDD").value = L.ddThr; $("levVol").value = L.volThr; }
    makeSeg($("levSeg"), [["1", "1×/cash"], ["2", "2× safe"], ["3", "3× safe"]], (v) => +v === state.lev.mult, (v) => { state.lev.mult = +v; syncLevUI(); renderPlaybook(); scheduleSave(); });
    makeSeg($("costSeg"), [["0", "Off"], ["1", "On"]], (v) => (+v === 1) === state.lev.costs, (v) => { state.lev.costs = +v === 1; syncLevUI(); renderPlaybook(); scheduleSave(); });
    $("levDD").onchange = () => { const x = parseFloat($("levDD").value); if (isFinite(x)) { state.lev.ddThr = x; renderPlaybook(); scheduleSave(); } };
    $("levVol").onchange = () => { const x = parseFloat($("levVol").value); if (isFinite(x)) { state.lev.volThr = x; renderPlaybook(); scheduleSave(); } };
    syncLevUI();
    makeSeg($("pnlSeg"), [["bps", "Yield Δ (bps)"], ["usd", "DV01 $"]], (v) => v === state.pnl.mode, (v) => { state.pnl.mode = v; syncPnlUI(); renderPlaybook(); scheduleSave(); });
    $("perBpInput").onchange = () => { const x = parseFloat($("perBpInput").value); if (isFinite(x) && x > 0) { state.pnl.perBp = x; renderPlaybook(); } };

    function setRange(days) { const w = Math.max(200, $("chart").clientWidth - 70); const n = days ? Math.min(days, D.n || days) : (D.n || days || 250); safe(() => { chart.setBarSpace(Math.max(0.5, Math.min(40, w / n))); chart.scrollToRealTime(0); }); }

    // ---- timeframe / intraday ----
    function aggregate(bars, ms) { if (!ms) return bars; const out = []; let cur = null, key = null; for (const b of bars) { const k = Math.floor(b.timestamp / ms); if (k !== key) { if (cur) out.push(cur); cur = { timestamp: k * ms, open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume || 0 }; key = k; } else { cur.high = Math.max(cur.high, b.high); cur.low = Math.min(cur.low, b.low); cur.close = b.close; cur.volume += b.volume || 0; } } if (cur) out.push(cur); return out; }
    function setCur(bars) { state.curClose = bars.map((b) => b.close); state.curTs = bars.map((b) => b.timestamp); state.curHigh = bars.map((b) => b.high); state.curLow = bars.map((b) => b.low); }
    function stopPoll() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }
    function combineLegs(legBars) {   // align legs by timestamp, combine to one OHLC series (spread/fly)
      const maps = legBars.map((l) => { const m = new Map(); l.bars.forEach((b) => m.set(b.timestamp, b)); return { w: l.w, m }; });
      const out = [];
      for (const t of maps[0].m.keys()) {
        if (!maps.every((mm) => mm.m.has(t))) continue;
        let o = 0, h = 0, lo = 0, c = 0;
        for (const { w, m } of maps) { const b = m.get(t); o += w * b.open; c += w * b.close; h += w > 0 ? w * b.high : w * b.low; lo += w > 0 ? w * b.low : w * b.high; }
        out.push({ timestamp: t, open: +o.toFixed(4), high: +h.toFixed(4), low: +lo.toFixed(4), close: +c.toFixed(4), volume: 0 });
      }
      out.sort((a, b) => a.timestamp - b.timestamp); return out;
    }
    function fetchIntradayBars(tf) {
      const url = (sym) => QUOTE + "/?mode=intraday&symbol=" + encodeURIComponent(sym) + "&interval=" + tf.interval + "&range=" + tf.range + "&_=" + Date.now();
      if (D.legs && D.legs.length) {
        return Promise.all(D.legs.map((leg) => fetch(url(leg.t)).then((r) => r.json()).then((j) => ({ w: leg.w, bars: j.bars || [] }))))
          .then((legBars) => { if (legBars.some((l) => !l.bars.length)) throw new Error("a leg lacks intraday"); return { bars: combineLegs(legBars), ticker: D.ticker }; });
      }
      return fetch(url(D.ticker)).then((r) => r.json()).then((j) => ({ bars: j.bars || [], ticker: j.ticker || D.ticker }));
    }
    function applyTF() {
      stopPoll();
      const tf = TFS.find((t) => t.id === state.tf) || TFS[TFS.length - 1];
      if (!tf.interval) { safe(() => { chart.applyNewData(D.daily || []); chart.resize(); }); setRange(126); reapplyDrawings(); setCur(D.daily || []); refreshSignals(); state.tfLastTs = 0; $("hint").textContent = "Daily bars · scroll to zoom · drag to pan · pick a draw tool then click points."; return; }
      status("loading " + tf.label + "…");
      fetchIntradayBars(tf)
        .then(({ bars: raw, ticker }) => {
          let bars = raw || []; if (!bars.length) throw new Error("no intraday data"); if (tf.aggMs) bars = aggregate(bars, tf.aggMs);
          safe(() => { chart.applyNewData(bars); chart.resize(); });
          const w = Math.max(200, $("chart").clientWidth - 70), show = Math.min(bars.length, tf.show || 180);
          safe(() => { chart.setBarSpace(Math.max(1, Math.min(14, w / show))); chart.scrollToRealTime(0); });
          reapplyDrawings(); setCur(bars); refreshSignals(); state.tfLastTs = bars[bars.length - 1].timestamp;
          status(tf.label + " · " + bars.length + " bars" + (D.legs ? " (computed)" : ""));
          $("hint").textContent = tf.label + " intraday · auto-refreshing every " + (POLL_MS / 1000) + "s · " + (ticker || D.ticker);
          pollTimer = setInterval(() => refreshTF(tf), POLL_MS);
        })
        .catch((e) => { status("intraday unavailable: " + e.message); });
    }
    function refreshTF(tf) { fetchIntradayBars(tf).then(({ bars: raw }) => { let bars = raw || []; if (tf.aggMs) bars = aggregate(bars, tf.aggMs); let n = 0; for (const b of bars) { if (b.timestamp >= state.tfLastTs) { safe(() => chart.updateData(b)); state.tfLastTs = Math.max(state.tfLastTs, b.timestamp); n++; } } if (n) { setCur(bars); refreshSignals(); fetchLive(); } }).catch(() => {}); }

    // ---- indicators ----
    const paneId = (name) => "pane_" + name.toLowerCase();
    const indPane = (name) => (MAIN_SET.has(name) ? "candle_pane" : paneId(name));
    function createInd(name) { const cp = state.indParams[name]; const v = cp && cp.length ? { name, calcParams: cp } : name; safe(() => chart.createIndicator(v, MAIN_SET.has(name), { id: indPane(name) })); }
    function overrideInd(name) { safe(() => chart.overrideIndicator({ name, calcParams: state.indParams[name] }, indPane(name))); }
    function toggleIndicator(name) { const on = !state.indicators[name]; state.indicators[name] = on; if (on) createInd(name); else safe(() => chart.removeIndicator(indPane(name), name)); renderIndParams(); }
    function renderIndParams() {
      const host = $("indParams"); const active = Object.keys(state.indicators).filter((n) => state.indicators[n] && DEFAULTS[n] && DEFAULTS[n].length);
      if (!active.length) { host.innerHTML = ""; return; }
      host.innerHTML = `<span class="lbl">Params</span>` + active.map((n) => `<span class="ipar"><b>${n}</b><input data-ind="${n}" value="${state.indParams[n].join(",")}" title="comma-separated calc params"></span>`).join("");
      host.querySelectorAll("input[data-ind]").forEach((inp) => { inp.onchange = () => { const arr = inp.value.split(",").map((x) => parseFloat(x)).filter((x) => isFinite(x)); if (arr.length) { state.indParams[inp.dataset.ind] = arr; overrideInd(inp.dataset.ind); scheduleSave(); } }; });
    }
    function syncIndChips() { [...$("indMain").querySelectorAll("button"), ...$("indSub").querySelectorAll("button")].forEach((b) => b.classList.toggle("active", !!state.indicators[b.dataset.v])); }
    function syncIndicators(target) { Object.keys(state.indicators).forEach((name) => { const want = !!(target && target[name]); if (state.indicators[name] !== want) toggleIndicator(name); }); syncIndChips(); }

    // ---- signal markers (custom-indicator draw callback) ----
    function refreshSignals() {
      if (!state.signalKey) { ACTIVE_SIGNAL = null; safe(() => chart.removeIndicator("candle_pane", "STRATSIGNAL")); return; }
      const st = STRATS.find((s) => s.key === state.signalKey); const c = state.curClose;
      if (!st || !c || !c.length) { ACTIVE_SIGNAL = null; return; }
      const pos = st.sig(c, state.stratParams[st.key], state.curHigh, state.curLow); const buys = new Set(), sells = new Set();
      for (let i = 1; i < pos.length; i++) { if (pos[i] === pos[i - 1]) continue; (pos[i] === 1 ? buys : sells).add(state.curTs[i]); }
      ACTIVE_SIGNAL = { buys, sells };
      safe(() => { chart.removeIndicator("candle_pane", "STRATSIGNAL"); chart.createIndicator("STRATSIGNAL", true, { id: "candle_pane" }); });
    }
    function toggleSignals(key) { state.signalKey = state.signalKey === key ? null : key; refreshSignals(); renderPlaybook(); }

    // ---- drawing ----
    function pickTool(name) { state.tool = name; if (name === "cursor") return; let extend; if (name === "simpleAnnotation") extend = (window.prompt("Annotation text:") || "").trim() || "note"; safe(() => chart.createOverlay({ name, extendData: extend, onDrawEnd: (e) => { recordDrawing(e.overlay); pickTool("cursor"); segActive($("toolSeg"), findBtn($("toolSeg"), "cursor")); return false; } })); }
    const validDraw = (d) => d && d.name && Array.isArray(d.points) && d.points.length && d.points.every((p) => p && p.value != null && isFinite(p.value));
    function recordDrawing(o) { if (restoring || !o || !o.points || !o.points.length) return; const pts = o.points.map((p) => ({ timestamp: p.timestamp, value: p.value })); if (pts.some((p) => p.value == null)) return; const i = drawings.findIndex((d) => d.id === o.id), rec = { id: o.id, name: o.name, points: pts, extendData: o.extendData }; if (i >= 0) drawings[i] = rec; else drawings.push(rec); scheduleSave(); }
    function reapplyDrawings() { restoring = true; safe(() => chart.removeOverlay()); const keep = drawings.filter(validDraw); drawings = []; keep.forEach((d) => { const id = safe(() => chart.createOverlay({ name: d.name, points: d.points, extendData: d.extendData })); if (id) drawings.push({ id, name: d.name, points: d.points, extendData: d.extendData }); }); restoring = false; }
    function undoDrawing() { const last = drawings.pop(); if (last) safe(() => chart.removeOverlay(last.id)); scheduleSave(); }
    function clearDrawings() { safe(() => chart.removeOverlay()); drawings = []; scheduleSave(); }

    // ---- persistence ----
    const lsKey = (id) => "chart_" + id;
    const getKey = () => { try { return localStorage.getItem(CLOUD_KEY) || ""; } catch (_) { return ""; } };
    function setKey(k) { try { k ? localStorage.setItem(CLOUD_KEY, k) : localStorage.removeItem(CLOUD_KEY); } catch (_) {} updateAuth(); }
    function status(msg) { $("notesStatus").textContent = msg ? "· " + msg : ""; }
    function updateAuth() { const el = $("cloudAuth"); if (getKey()) { el.innerHTML = `signed in · <a href="#" id="logout">log out</a>`; el.querySelector("#logout").onclick = (e) => { e.preventDefault(); setKey(""); status("logged out"); }; } else el.textContent = "not signed in"; }
    function ensureKey() { const k = getKey(); if (k) return Promise.resolve(k); const entry = (window.prompt("Passphrase to save/view private notes:") || "").trim(); if (!entry) return Promise.resolve(""); return fetch(STORE + "/api/auth", { method: "POST", headers: { "X-Lab-Key": entry } }).then((r) => { if (!r.ok) { status("wrong passphrase"); return ""; } setKey(entry); return entry; }).catch(() => { status("login failed"); return ""; }); }
    function snapshot() { return { notes: $("notes").value || "", drawings: drawings.map(({ id, ...d }) => d), settings: { type: state.type, yAxis: state.yAxis, indicators: state.indicators, indParams: state.indParams, stratParams: state.stratParams, lev: state.lev, carry: state.carry, pnl: { mode: state.pnl.mode, perBp: state.pnl.perBp } } }; }
    function saveLocal() { try { localStorage.setItem(lsKey(D.id), JSON.stringify(snapshot())); } catch (_) {} }
    function scheduleSave() { if (saveTimer) clearTimeout(saveTimer); saveTimer = setTimeout(() => { saveTimer = null; saveLocal(); status("saved locally"); }, 600); }
    $("cloudBtn").onclick = () => { ensureKey().then((key) => { if (!key) return; updateAuth(); status("saving…"); fetch(STORE + "/api/chart/" + D.id, { method: "POST", headers: { "Content-Type": "application/json", "X-Lab-Key": key }, body: JSON.stringify(snapshot()) }).then((r) => { if (r.status === 401) { setKey(""); throw new Error("login expired"); } if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }).then(() => status("saved to cloud ✓")).catch((e) => status("cloud save failed: " + e.message)); }); };
    $("notes").addEventListener("input", scheduleSave);

    function applySnapshot(snap) {
      restoring = true;
      $("notes").value = snap.notes || "";
      const st = snap.settings || {};
      if (st.type) { state.type = st.type; safe(() => chart.setStyles({ candle: { type: st.type } })); segActive($("typeSeg"), findBtn($("typeSeg"), st.type)); }
      if (st.yAxis) { state.yAxis = st.yAxis; safe(() => chart.setStyles({ yAxis: { type: st.yAxis } })); segActive($("axisSeg"), findBtn($("axisSeg"), st.yAxis)); }
      if (st.indParams) Object.keys(st.indParams).forEach((k) => { if (Array.isArray(st.indParams[k])) state.indParams[k] = st.indParams[k].slice(); });
      if (st.stratParams) Object.keys(st.stratParams).forEach((k) => { if (state.stratParams[k]) Object.assign(state.stratParams[k], st.stratParams[k]); });
      if (st.lev && typeof st.lev === "object") { Object.assign(state.lev, st.lev); syncLevUI(); }
      if (typeof st.carry === "boolean") state.carry = st.carry;
      if (st.pnl && typeof st.pnl === "object") { if (st.pnl.mode) state.pnl.mode = st.pnl.mode; if (isFinite(st.pnl.perBp) && st.pnl.perBp > 0) state.pnl.perBp = st.pnl.perBp; }
      syncPnlUI();
      syncIndicators(st.indicators); renderIndParams();
      drawings = [];
      (snap.drawings || []).filter(validDraw).forEach((d) => { const id = safe(() => chart.createOverlay({ name: d.name, points: d.points, extendData: d.extendData })); if (id) drawings.push({ id, name: d.name, points: d.points, extendData: d.extendData }); });
      restoring = false; renderPlaybook();
    }
    function loadNotes() {
      safe(() => chart.removeOverlay()); drawings = [];
      const local = (() => { try { return JSON.parse(localStorage.getItem(lsKey(D.id))) || null; } catch (_) { return null; } })();
      const key = getKey();
      if (key) { status("loading…"); fetch(STORE + "/api/chart/" + D.id, { headers: { "X-Lab-Key": key } }).then((r) => { if (r.status === 401) { setKey(""); throw new Error("login expired"); } return r.json(); }).then((snap) => { const has = snap && (snap.notes || (snap.drawings && snap.drawings.length) || snap.settings); applySnapshot(has ? snap : (local || {})); status(has && snap.savedAt ? "from cloud" : ""); }).catch(() => { applySnapshot(local || {}); status("offline — local"); }); }
      else applySnapshot(local || {});
    }

    function fetchLive() {
      const live = $("live"), txt = $("liveTxt"); txt.textContent = "live —"; live.classList.remove("on");
      if (D.kind === "spread") { txt.textContent = "curve spread (computed)"; return; }
      fetch(QUOTE + "/?mode=quote&symbol=" + encodeURIComponent(D.ticker) + "&_=" + Date.now()).then((r) => r.json()).then((q) => {
        if (!q || !(q.price > 0) || (q.ticker || "").toUpperCase() !== D.ticker.toUpperCase()) { txt.textContent = "live unavailable"; return; }
        const prev = D.close[D.n - 1], chg = (q.price / prev - 1) * 100, s = chg >= 0 ? "+" : "";
        live.classList.add("on"); txt.innerHTML = `<b>${esc(D.ticker)} ${nfmt(q.price)}</b> <span style="color:${chg >= 0 ? UP : DN}">${s}${chg.toFixed(2)}%</span> <span style="color:#8a8a8e">· ${esc(q.timestamp || "")}</span>`;
      }).catch(() => { txt.textContent = "live unavailable"; });
    }

    // ---- interactive signal playbook ----
    function plotStrategy(key) {
      const st = STRATS.find((s) => s.key === key); if (!st || !st.plot) return; const ind = st.plot.ind;
      if (state.plotted[key]) { delete state.plotted[key]; if (state.indicators[ind]) { state.indicators[ind] = false; safe(() => chart.removeIndicator(indPane(ind), ind)); } }
      else { state.plotted[key] = true; state.indParams[ind] = st.plot.cp(state.stratParams[key]); if (state.indicators[ind]) safe(() => chart.removeIndicator(indPane(ind), ind)); state.indicators[ind] = true; createInd(ind); }
      syncIndChips(); renderIndParams(); renderPlaybook(); scheduleSave();
    }
    function renderPlaybook() {
      const c = D.close, host = $("playbook"); $("pbAsset").textContent = D.dates.length ? "· " + D.label + " · " + D.dates[0] + " → " + D.dates[D.n - 1] : "";
      if (!c || c.length < 250) { host.innerHTML = `<p class="meta">Not enough history for a meaningful backtest.</p>`; return; }
      const isY = D.kind === "yield", isS = D.kind === "spread", L = state.lev;
      $("levBar").style.display = (isY || isS) ? "none" : "";
      const levArr = (pos) => (L.mult > 1 && !isY && !isS && D.ddh.length === c.length) ? pos.map((p, i) => (p ? ((D.ddh[i] > L.ddThr / 100 && D.rv[i] < L.volThr / 100) ? L.mult : 1) : 0)) : pos;
      let crArr = null; // per-day carry+roll in series units (set below when the carry toggle is on)
      function spreadStats(pos) {
        let cum = 0, peak = 0, mdd = 0, hit = 0, days = 0; const pnl = [];
        for (let i = 1; i < c.length; i++) { const dir = pos[i - 1] ? 1 : -1, cs = crArr ? crArr[i] : 0, x = dir * (c[i] - c[i - 1] + cs); pnl.push(x); cum += x; if (cum > peak) peak = cum; if (cum - peak < mdd) mdd = cum - peak; if (x > 0) hit++; days++; }
        const yrs = c.length / 252, m = pnl.reduce((a, b) => a + b, 0) / pnl.length; let v = 0; for (const x of pnl) v += (x - m) ** 2; const vol = Math.sqrt(Math.max(0, v / Math.max(1, pnl.length - 1)));
        return { annbps: (cum * 100) / yrs, maxddbps: mdd * 100, sharpe: vol ? (m / vol) * Math.sqrt(252) : 0, hit: days ? hit / days : 0, total: cum * 100 };
      }
      const isDelta = isS || isY;   // UST instruments trade directionally: P&L = position × change-in-series (bps)
      // bake carry+roll into the backtest. D.cr = per-date carry+roll (bps/3m) for LONG the instrument, from the
      // actual curve on each date; falls back to today's curve held flat if the historical series is absent.
      crArr = null;
      if (isDelta && state.carry) {
        if (D.cr && D.cr.length === c.length) crArr = D.cr.map((v) => (v == null ? 0 : v) / 63 / 100); // CR bps/3m → /63 days /100 → series units
        else { const k = (instrCR() || 0) / 63 / 100; crArr = c.map(() => k); }
      }
      const evalp = (pos) => { if (isDelta) return spreadStats(pos); const la = levArr(pos); const r = btLev(c, la, L.costs); const s = stats(r.eq, r.ret, la); s.avglev = la.reduce((a, b) => a + b, 0) / la.length; return s; };
      const lc = (s) => `${pct(s.pin)}${(L.mult > 1 && !isDelta) ? ` · ${s.avglev.toFixed(2)}×` : ""}`;
      $("pnlBar").style.display = isDelta ? "" : "none";
      const usd = isDelta && state.pnl.mode === "usd", pb = state.pnl.perBp || 1;
      const COLS = isDelta
        ? (usd
          ? [["Ann $", (m) => "$" + Math.round(m.annbps * pb).toLocaleString()], ["Max DD $", (m) => "$" + Math.round(m.maxddbps * pb).toLocaleString()], ["Sharpe", (m) => f2(m.sharpe)], ["Hit %", (m) => pct(m.hit)], ["Total $", (m) => "$" + Math.round(m.total * pb).toLocaleString()]]
          : [["Ann bps", (m) => Math.round(m.annbps)], ["Max DD bps", (m) => Math.round(m.maxddbps)], ["Sharpe", (m) => f2(m.sharpe)], ["Hit %", (m) => pct(m.hit)], ["Total bps", (m) => Math.round(m.total).toLocaleString()]])
        : [["CAGR", (m) => pct(m.cagr)], ["Max DD", (m) => pct(m.maxdd)], ["Sharpe", (m) => f2(m.sharpe)], ["% in", (m) => lc(m)], ["$100→", (m) => "$" + Math.round(m.end).toLocaleString()]];
      const winKey = isDelta ? "total" : "cagr";
      const ones = c.map(() => 1), bh = evalp(ones);
      const head = `<tr><th>Strategy, signal &amp; parameters</th>${COLS.map(([h]) => `<th>${h}</th>`).join("")}<th>Show</th></tr>`;
      const bhName = isY ? "Static long rates" : isS ? "Static steepener" : "Buy &amp; hold", bhSub = isY ? "always long rates" : isS ? "always long steepener" : "always invested";
      const bhRow = `<tr class="bh"><td>${bhName}<div class="sig">${bhSub}</div></td>${COLS.map(([, f]) => `<td class="num">${f(bh)}</td>`).join("")}<td></td></tr>`;
      const body = STRATS.map((st) => {
        const p = state.stratParams[st.key], pos = st.sig(c, p, D.high, D.low), s = evalp(pos);
        const inputs = st.params.map((q) => `<label>${esc(q.label)}<input type="number" data-k="${st.key}" data-p="${q.k}" value="${p[q.k]}" min="${q.min}" max="${q.max}" step="${q.step || 1}"></label>`).join("");
        const plotBtn = st.plot ? `<button class="pb-btn ${state.plotted[st.key] ? "on" : ""}" data-plot="${st.key}">${state.plotted[st.key] ? "✓ plot" : "plot"}</button>` : `<button class="pb-btn" disabled title="no chart overlay">plot</button>`;
        const sigBtn = `<button class="pb-btn sig ${state.signalKey === st.key ? "on" : ""}" data-sig="${st.key}">${state.signalKey === st.key ? "✓ signals" : "signals"}</button>`;
        const noteBtn = `<button class="pb-btn ${state.notesOpen[st.key] ? "on" : ""}" data-note="${st.key}">notes</button>`;
        const sigTxt = isDelta ? `▲ ${isY ? "long rates" : "long steepener"}: ${esc(st.buy(p))} · ▼ ${isY ? "long duration" : "flattener"}: ${esc(st.sell(p))}` : `▲ ${esc(st.buy(p))} · ▼ ${esc(st.sell(p))}`;
        const cells = COLS.map(([, f], idx) => (idx === 0 ? `<td class="num ${s[winKey] > bh[winKey] ? "win" : ""}">${f(s)}</td>` : `<td class="num">${f(s)}</td>`)).join("");
        const row = `<tr><td><b>${esc(st.name)}</b><div class="sig">${sigTxt}</div><div class="pbp">${inputs}</div></td>${cells}<td><div class="pbacts">${plotBtn}${sigBtn}${noteBtn}</div></td></tr>`;
        const noteRow = state.notesOpen[st.key] ? `<tr class="noterow"><td colspan="7">${st.note}</td></tr>` : "";
        return row + noteRow;
      }).join("");
      const caps = [];
      if (isY) caps.push(`<b>Rate trade</b> (bps). <b>Long (+1) = long rates</b> — profit when the yield <i>rises</i> (short duration); <b>short (−1) = long duration</b> — profit when it falls. P&L = position × daily change in the yield. Strategies signal on the <i>yield level</i>. <b>Hit %</b> = share of days the position made money.`);
      if (isS) caps.push(`<b>Steepness spread</b> (% points; ×100 = bps). <b>Long the steepener</b> when the rule fires, <b>short (flattener)</b> when not; P&L = position × change in the spread. Strategies signal on the <i>spread level</i>. <b>Hit %</b> = share of days the position made money.`);
      if (usd) caps.push(`<b>DV01 $ P&L</b> at <b>$${(state.pnl.perBp || 0).toLocaleString()}/bp</b> (≈ this trade's DV01, edit above). Sharpe &amp; Hit % are scale-free; bps × $/bp = dollars.`);
      if (isDelta && state.carry) caps.push((D.cr && D.cr.length === c.length)
        ? `<b>Carry/roll ON (historical)</b> — each day adds the position's carry+roll <b>computed from the actual curve on that date</b>, so the drift flips sign with the regime (a long-rates trade <i>earns</i> carry when the curve is inverted, <i>pays</i> when it's normal). Carry uses exact yield levels; the roll term interpolates the available tenors (cruder pre-2021).`
        : `<b>Carry/roll ON</b> — each day adds the position's carry+roll drift from the <b>current</b> curve held constant (historical series unavailable for this instrument).`);
      if (!isDelta && L.mult > 1) caps.push(`<b>${L.mult}× when safe</b> — levered while in trend AND drawdown &gt; ${L.ddThr}% AND 20-day vol &lt; ${L.volThr}%, else 1× (cash when out). ${L.costs ? "Costs ON (5bps/switch + 4%/yr financing)." : "No costs."} Leverage lifts CAGR but <b>deepens drawdowns and usually lowers Sharpe</b> — that's the trade-off; the “% in” column shows average leverage.`);
      else if (!isDelta && L.costs) caps.push(`Costs ON — 5 bps per switch.`);
      const cap = caps.length ? `<p class="meta" style="margin:0 0 6px">${caps.join(" ")}</p>` : "";
      host.innerHTML = cap + `<table class="pb"><thead>${head}</thead><tbody>${bhRow}${body}</tbody></table>`;
      host.querySelectorAll("input[data-k]").forEach((inp) => { inp.onchange = () => {
        const v = parseFloat(inp.value); if (!isFinite(v)) return; const key = inp.dataset.k, pk = inp.dataset.p; state.stratParams[key][pk] = v;
        const st = STRATS.find((s) => s.key === key);
        if (state.plotted[key] && st.plot) { state.indParams[st.plot.ind] = st.plot.cp(state.stratParams[key]); overrideInd(st.plot.ind); renderIndParams(); }
        if (state.signalKey === key) refreshSignals();
        renderPlaybook(); scheduleSave();
      }; });
      host.querySelectorAll("button[data-plot]").forEach((b) => { b.onclick = () => plotStrategy(b.dataset.plot); });
      host.querySelectorAll("button[data-sig]").forEach((b) => { b.onclick = () => toggleSignals(b.dataset.sig); });
      host.querySelectorAll("button[data-note]").forEach((b) => { b.onclick = () => { state.notesOpen[b.dataset.note] = !state.notesOpen[b.dataset.note]; renderPlaybook(); }; });
    }

    // ---- curve strategy leaderboard (best backtested rule per UST instrument) ----
    function instrCR() {  // carry+roll (bps per ~3m) of being LONG this instrument (long rates / long steepener / long fly), from the live curve
      if (!CURVE.length) return null;
      const crBy = {}; CURVE.forEach((q) => { crBy[q.id] = (q.roll3m || 0) + (q.carry3m || 0); });
      let cr = 0;
      if (D.legs && D.legs.length) { for (const lg of D.legs) { const id = TICK2ID[lg.t]; if (id && crBy[id] != null) cr += lg.w * crBy[id]; } return -cr; }
      if (D.kind === "yield" && crBy[D.id] != null) return -crBy[D.id];
      return null;
    }
    function renderLeader() {
      const card = $("leaderCard"), host = $("leader"), note = $("leaderNote");
      const isUST = ["Rates", "Steepness", "Butterfly"].includes(D.klass);
      card.style.display = isUST ? "" : "none";
      if (!isUST || !LEADER.length) return;
      const sigCell = (b) => `<span style="color:${b.signalNow ? UP : DN};font-weight:700;white-space:nowrap">${b.signalNow ? "▲" : "▼"} ${esc(b.signalLabel)}</span>`;
      const rc = (() => { const c = D.close; if (!c || c.length < 60) return ""; const n = c.length, cv = c[n - 1]; let m = 0; for (const x of c) m += x; m /= n; let v = 0; for (const x of c) v += (x - m) ** 2; const sd = Math.sqrt(v / n); let bl = 0; for (const x of c) if (x <= cv) bl++; const last = c.slice(-252), lo = Math.min(...last), hi = Math.max(...last); const z = sd ? (cv - m) / sd : 0; const u = (x) => D.kind === "spread" ? (x * 100).toFixed(0) + "bps" : x.toFixed(2) + (D.kind === "yield" ? "%" : ""); return `Now <b>${u(cv)}</b> · z-score <b style="color:${Math.abs(z) > 1.5 ? (z > 0 ? DN : UP) : "#444"}">${z >= 0 ? "+" : ""}${z.toFixed(2)}σ</b> · <b>${(bl / n * 100).toFixed(0)}th</b> percentile of history · 1y range ${u(lo)}–${u(hi)}`; })();
      const cur = LEADER.find((e) => e.id === D.id);
      const crq = instrCR();  // bps/3m for long-the-instrument; the live trade may be short → flip
      let carryTxt = "";
      if (crq != null && cur) { const cy = (cur.best.signalNow ? 1 : -1) * crq * 4; carryTxt = ` · carry/roll on the live trade <b style="color:${cy >= 0 ? UP : DN}">${cy >= 0 ? "earns" : "pays"} ~${Math.abs(cy).toFixed(0)} bps/yr</b>`; }
      note.innerHTML = (cur ? `<b>${esc(cur.label)}:</b> ${cur.explain} <span style="color:#8a8a8e">(best: ${esc(cur.best.name)} — ${esc(Object.entries(cur.best.params).map(([k, v]) => k + " " + v).join(", "))}, Sharpe ${f2(cur.best.metrics.sharpe)})</span> · <b>Now: ${sigCell(cur.best)}</b> <span class="meta">as of ${esc(cur.best.asof || "")}</span>` : "") + (rc ? `<br><span style="color:#444">${rc}${carryTxt}</span>` : "");
      const rows = LEADER.slice().sort((a, b) => b.best.metrics.sharpe - a.best.metrics.sharpe);
      const head = `<tr><th>Instrument</th><th>Best rule</th><th>Sharpe</th><th>Ann bps</th><th>Total bps</th><th>Hit %</th><th>Signal now</th><th></th></tr>`;
      const body = rows.map((e) => { const m = e.best.metrics, pr = Object.entries(e.best.params).map(([k, v]) => k + " " + v).join(", ");
        return `<tr class="${e.id === D.id ? "bh" : ""}"><td><b>${esc(e.label)}</b> <span class="meta">${esc(e.klass)}</span></td><td>${esc(e.best.name)}<div class="sig">${esc(pr)}</div></td><td class="num">${f2(m.sharpe)}</td><td class="num">${Math.round(m.annbps)}</td><td class="num">${Math.round(m.total).toLocaleString()}</td><td class="num">${pct(m.hit)}</td><td>${sigCell(e.best)}</td><td><button class="pb-btn" data-load="${esc(e.id)}">Load</button></td></tr>`; }).join("");
      host.innerHTML = `<table class="pb"><thead>${head}</thead><tbody>${body}</tbody></table>`;
      host.querySelectorAll("button[data-load]").forEach((b) => (b.onclick = () => applyBest(LEADER.find((e) => e.id === b.dataset.load))));
    }
    function applyBest(e) { if (!e) return; if (e.id === D.id) applyStrategy(e.best, true); else { pendingBest = e.best; $("assetSel").value = e.id; loadAsset(e.id); } }
    function applyStrategy(best, scroll) {
      if (state.stratParams[best.key]) Object.assign(state.stratParams[best.key], best.params);
      state.signalKey = best.key; state.notesOpen[best.key] = true;
      renderPlaybook(); refreshSignals(); scheduleSave();
      if (scroll) { const pb = $("playbook"); if (pb) pb.scrollIntoView({ behavior: "smooth", block: "nearest" }); }
    }
    function syncPnlUI() { if (!$("pnlSeg")) return; segActive($("pnlSeg"), findBtn($("pnlSeg"), state.pnl.mode)); $("pnlPerBp").style.display = state.pnl.mode === "usd" ? "" : "none"; $("perBpInput").value = state.pnl.perBp || 0; if ($("carryChk")) $("carryChk").checked = state.carry; }
    function renderCurve() {
      const card = $("curveCard"); const isUST = ["Rates", "Steepness", "Butterfly"].includes(D.klass);
      card.style.display = (isUST && CURVE.length) ? "" : "none";
      if (!isUST || !CURVE.length) return;
      $("curveAsof").textContent = "as of " + (CURVE[CURVE.length - 1].date || "");
      const W = 620, H = 190, padL = 46, padR = 18, padT = 16, padB = 30;
      const ys = CURVE.map((c) => c.yield); let ymin = Math.min(...ys), ymax = Math.max(...ys); const pad = (ymax - ymin) * 0.18 || 0.2; ymin -= pad; ymax += pad;
      const lx = Math.log(0.25), rx = Math.log(30);
      const X = (yr) => padL + (Math.log(yr) - lx) / (rx - lx) * (W - padL - padR);
      const Y = (v) => padT + (1 - (v - ymin) / (ymax - ymin)) * (H - padT - padB);
      let grid = "";
      for (let k = 0; k <= 4; k++) { const v = ymin + (ymax - ymin) * k / 4, y = Y(v).toFixed(1); grid += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#eee"/><text x="${padL - 6}" y="${(+y + 3).toFixed(1)}" text-anchor="end" font-size="10" fill="#8a8a8e">${v.toFixed(2)}</text>`; }
      const poly = CURVE.map((c) => `${X(c.years).toFixed(1)},${Y(c.yield).toFixed(1)}`).join(" ");
      let dots = "";
      CURVE.forEach((c) => { const x = X(c.years).toFixed(1), y = Y(c.yield).toFixed(1); dots += `<circle cx="${x}" cy="${y}" r="3.5" fill="#0071e3"/><text x="${x}" y="${(+y - 8).toFixed(1)}" text-anchor="middle" font-size="10.5" font-weight="700" fill="#1d1d1f">${c.yield.toFixed(2)}</text><text x="${x}" y="${H - padB + 14}" text-anchor="middle" font-size="10" fill="#8a8a8e">${esc(c.id.replace("ust", "").toUpperCase())}</text>`; });
      $("curveSvg").innerHTML = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px;height:auto">${grid}<polyline points="${poly}" fill="none" stroke="#0071e3" stroke-width="2"/>${dots}</svg>`;
      const yv = (id) => { const c = CURVE.find((x) => x.id === id); return c ? c.yield : null; };
      const flags = [["2s10s", "ust2y", "ust10y"], ["3m10y", "ust3m", "ust10y"], ["5s30s", "ust5y", "ust30y"]].map(([nm, a, b]) => { const v = (yv(b) - yv(a)) * 100, inv = v < 0; return `<b>${nm}</b> ${v >= 0 ? "+" : ""}${v.toFixed(0)}bps <span style="color:${inv ? DN : UP};font-weight:600">${inv ? "INVERTED" : v > 60 ? "steep" : "flat-ish"}</span>`; }).join(" &nbsp;·&nbsp; ");
      const tn = (c) => c.id.replace("ust", "").toUpperCase();
      const roll = CURVE.map((c) => `${tn(c)} ${c.roll3m >= 0 ? "+" : ""}${c.roll3m}`).join(" · ");
      const bestRoll = CURVE.reduce((a, b) => (b.roll3m > a.roll3m ? b : a), CURVE[0]);
      const carry = CURVE.filter((c) => c.id !== "ust3m").map((c) => `${tn(c)} ${c.carry3m >= 0 ? "+" : ""}${c.carry3m}`).join(" · ");
      $("curveFlags").innerHTML = "Slope: " + flags
        + `<br><span style="color:#444">3m roll-down (bps): ${roll} — richest in the <b>${tn(bestRoll)}</b>.</span>`
        + `<br><span style="color:#8a8a8e">3m carry vs the 3M bill (bps): ${carry} — grows with tenor on an upward curve.</span>`;
    }

    function loadAsset(id) {
      state.asset = id;
      fetch("price_" + id + ".json?v=" + Date.now()).then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }).then((d) => {
        D.id = id; D.ticker = d.ticker; D.label = d.asset_label || id; D.kind = d.kind || "price"; D.klass = d.klass || ""; D.legs = d.legs || null; D.cr = d.cr || null; D.n = d.close.length; D.dates = d.dates; D.close = d.close; D.high = d.high; D.low = d.low;
        D.ddh = ddFromHigh(d.close, 252); D.rv = rvol(d.close, 20);
        D.dv01 = D.legs ? Math.max(...D.legs.map((l) => TICKER_DV01[l.t] || 1)) : (TICKER_DV01[D.ticker] || 8.6);
        state.pnl.perBp = Math.round(D.dv01 * 1000);   // ≈ trade DV01 in $/bp (per ~$10mm); user-editable
        if (D.kind === "spread" && state.yAxis !== "normal") { state.yAxis = "normal"; safe(() => chart.setStyles({ yAxis: { type: "normal" } })); segActive($("axisSeg"), findBtn($("axisSeg"), "normal")); }  // log/% invalid for spreads that go negative
        $("cTitle").textContent = D.label + " — chart";
        D.daily = d.close.map((c, i) => ({ timestamp: d.timestamp[i], open: d.open[i], high: d.high[i], low: d.low[i], close: c, volume: d.volume ? d.volume[i] : 0 }));
        safe(() => chart.removeOverlay()); drawings = [];
        applyTF(); loadNotes(); fetchLive(); renderPlaybook(); renderLeader(); renderCurve(); syncPnlUI();
        if (pendingBest) { applyStrategy(pendingBest, true); pendingBest = null; }
        else { const e = LEADER.find((x) => x.id === D.id); if (e && ["Rates", "Steepness", "Butterfly"].includes(D.klass)) applyStrategy(e.best, false); }   // best rule = default for every UST trade
      }).catch((e) => { status("could not load " + id + " — " + e.message); });
    }

    updateAuth();
    fetch("price_assets.json?v=" + Date.now()).then((r) => r.json())
      .then((list) => { ASSETS = list; })
      .catch(() => { ASSETS = [{ id: "spx", label: "S&P 500", klass: "Indices", ticker: "^GSPC" }, { id: "ndx", label: "Nasdaq 100", klass: "Indices", ticker: "^NDX" }]; })
      .then(() => fetch("ust_strategies.json?v=" + Date.now()).then((r) => r.json()).then((l) => { LEADER = l || []; }).catch(() => { LEADER = []; }))
      .then(() => fetch("ust_curve.json?v=" + Date.now()).then((r) => r.json()).then((l) => { CURVE = l || []; }).catch(() => { CURVE = []; }))
      .then(() => fetch("ust_inversions.json?v=" + Date.now()).then((r) => r.json()).then((l) => { INVERSIONS = (l || []).map(([s, e]) => [Date.parse(s), Date.parse(e)]); }).catch(() => { INVERSIONS = []; }))
      .then(() => { const sel = $("assetSel"), groups = {}; ASSETS.forEach((a) => { (groups[a.klass] = groups[a.klass] || []).push(a); }); sel.innerHTML = Object.keys(groups).map((g) => `<optgroup label="${esc(g)}">` + groups[g].map((a) => `<option value="${esc(a.id)}">${esc(a.label)}</option>`).join("") + `</optgroup>`).join(""); sel.value = state.asset; sel.onchange = () => loadAsset(sel.value); loadAsset(state.asset); });
  }

  function boot() { if (!window.klinecharts || !document.getElementById("app")) { setTimeout(boot, 30); return; } if (window.SP && SP.injectStyles) SP.injectStyles(); run(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
