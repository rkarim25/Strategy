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
  let AUTO_SIG = { buys: new Set(), sells: new Set() }; // auto-analysis buy/sell timestamps (drawn by the AUTOTA indicator)
  let STUDY_SIG = { buys: new Set(), sells: new Set() }; // "add buy/sell signals" from a study (drawn by the STUDYSIG indicator)
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]; // UK date format dd-MMM-yy
  const p2 = (n) => String(n).padStart(2, "0");
  function ukTs(ts, withTime) { const d = new Date(ts); if (!isFinite(d.getTime())) return ""; const s = p2(d.getDate()) + "-" + MON[d.getMonth()] + "-" + String(d.getFullYear()).slice(-2); return withTime ? s + " " + p2(d.getHours()) + ":" + p2(d.getMinutes()) : s; }
  function ukd(str) { if (!str) return ""; const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(str); return m ? p2(+m[3]) + "-" + MON[+m[2] - 1] + "-" + m[1].slice(-2) : str; } // "YYYY-MM-DD" → "dd-MMM-yy"
  function isoOf(ts) { const d = new Date(ts); return d.getFullYear() + "-" + p2(d.getMonth() + 1) + "-" + p2(d.getDate()); }
  const UP = "#15803d", DN = "#b42318";
  const RANGES = [[5, "1W"], [21, "1M"], [63, "3M"], [252, "1Y"], [1260, "5Y"], [2520, "10Y"]]; // [days, label] — makeSeg renders label, passes days
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
  // Right-click help for each overlay/study: what it is + the trading signals it gives.
  const HELP = {
    MA: ["Moving Average (MA)", "The simple average of the close over the last N bars — it smooths noise so you can see the underlying trend. A rising MA means an uptrend, falling means down, flat means a range. Common windows are 50 and 200 days.<br><br><b>Signals:</b> price crossing <b>above</b> the MA is bullish, <b>below</b> is bearish. A fast MA crossing above a slow MA is a <b>golden cross</b> (buy); crossing below is a <b>death cross</b> (sell). Price tends to bounce off a strong MA in a trend."],
    EMA: ["Exponential Moving Average (EMA)", "Like the MA but it weights recent prices more heavily, so it turns faster and lags less than a simple MA — at the cost of more false signals. The 12- and 26-period EMAs are the building blocks of MACD.<br><br><b>Signals:</b> same crossover logic as the MA (price/EMA and fast/slow EMA crosses) but you get the signal earlier. Good for catching trends quickly; expect more whipsaws in choppy markets."],
    SMA: ["Smoothed Moving Average (SMA)", "A moving average that carries forward its previous value, so it's even smoother and slower than an EMA — it filters out short-term noise to show only the dominant trend.<br><br><b>Signals:</b> use it as a trend filter — only take longs while price is above it, shorts while below. Crossovers are slower but more reliable than a simple MA; best for position trading, not scalping."],
    BOLL: ["Bollinger Bands (BOLL)", "A middle moving average with an upper and lower band set ±2 standard deviations away, so the bands <b>widen when volatility rises</b> and pinch in when it's calm.<br><br><b>Signals:</b> a touch of the upper band = strong/overbought, the lower band = weak/oversold. A <b>squeeze</b> (very narrow bands) often precedes a big move. Mean-reversion traders fade band touches back to the middle; trend traders buy a close <b>outside</b> the upper band as a breakout."],
    BBI: ["Bull & Bear Index (BBI)", "The average of four moving averages (3/6/12/24), combined into one consolidated trend line that's less jumpy than any single MA.<br><br><b>Signals:</b> price <b>above</b> BBI = bullish bias, <b>below</b> = bearish. Use it as a single clean trend filter; price reclaiming BBI after a dip is an early trend-resumption cue."],
    SAR: ["Parabolic SAR", "A trail of dots that follows price and <b>flips to the other side when the trend reverses</b> — a stop-and-reverse trend-following tool that also doubles as a trailing stop.<br><br><b>Signals:</b> dots <b>below</b> price = uptrend (stay long), dots <b>above</b> = downtrend (stay short). A flip from below to above is a sell/exit; above to below is a buy. Excellent in strong trends, but it whipsaws badly in sideways markets."],
    VOL: ["Volume (VOL)", "How much was traded in each bar — the conviction behind a price move. Price moves mean more when volume backs them.<br><br><b>Signals:</b> a breakout on <b>rising</b> volume is far more trustworthy; a rally on <b>falling</b> volume often fails. A sudden volume spike frequently marks a climax — the end of a move and a possible turning point."],
    MACD: ["MACD", "Moving Average Convergence/Divergence: the gap between the 12- and 26-EMA (the MACD line), a 9-EMA of that (the signal line), and the histogram of the difference. It captures momentum and trend in one study.<br><br><b>Signals:</b> MACD crossing <b>above</b> its signal line = buy, <b>below</b> = sell. Crossing the <b>zero line</b> confirms a trend change. <b>Divergence</b> — price making a new high while MACD doesn't — warns a reversal is near."],
    RSI: ["Relative Strength Index (RSI)", "A 0–100 momentum oscillator measuring the size of recent gains vs losses over N bars (usually 14).<br><br><b>Signals:</b> above <b>70</b> = overbought (watch for a pullback), below <b>30</b> = oversold (watch for a bounce). <b>Divergence</b> vs price flags reversals. In a strong uptrend RSI holds the 40–80 band (buy dips to ~40); in a downtrend it stays 20–60."],
    KDJ: ["Stochastic (KDJ)", "A stochastic oscillator with K, D and J lines showing where the close sits within the recent high–low range. The J line exaggerates the extremes.<br><br><b>Signals:</b> K crossing <b>above</b> D while oversold (<20) = buy; K crossing <b>below</b> D while overbought (>80) = sell. Best in ranges; in strong trends it can stay pinned at an extreme for a long time."],
    CCI: ["Commodity Channel Index (CCI)", "Measures how far price has strayed from its statistical average, normally oscillating within ±100.<br><br><b>Signals:</b> rising <b>above +100</b> signals an emerging uptrend (momentum buy) or overbought; dropping <b>below −100</b> signals a downtrend or oversold. Reversal traders fade moves back inside ±100; breakout traders ride moves beyond them."],
    WR: ["Williams %R", "A momentum oscillator running from 0 to −100 — essentially an inverted stochastic — showing where the close is within the recent range.<br><br><b>Signals:</b> above <b>−20</b> = overbought (possible sell), below <b>−80</b> = oversold (possible buy). Like RSI, it's best for spotting exhaustion and timing entries within a larger trend."],
    DMI: ["Directional Movement / ADX (DMI)", "+DI and −DI measure upward vs downward pressure, while ADX measures only the <b>strength</b> of the trend (not its direction).<br><br><b>Signals:</b> +DI <b>above</b> −DI = bullish, −DI above +DI = bearish. <b>ADX > 25</b> means a strong trend — trade with it; <b>ADX < 20</b> means a weak/range market where trend signals fail and you should fade extremes instead."],
    OBV: ["On-Balance Volume (OBV)", "A running tally that <b>adds</b> the day's volume on up closes and <b>subtracts</b> it on down closes, tracking whether volume is flowing into (accumulation) or out of (distribution) the asset.<br><br><b>Signals:</b> OBV rising with price <b>confirms</b> the trend. OBV <b>diverging</b> from price (price up, OBV flat/down) warns of a weak move likely to reverse. An OBV breakout can lead price."],
    ROC: ["Rate of Change (ROC)", "The percentage change in price over N bars — pure, unsmoothed momentum that oscillates around zero.<br><br><b>Signals:</b> ROC <b>above zero and rising</b> = accelerating uptrend; crossing zero flags a trend change. Extreme readings mark overbought/oversold; divergence vs price warns momentum is fading even as price grinds on."],
    TRIX: ["TRIX", "The rate of change of a <b>triple-smoothed</b> EMA, designed to strip out short-term noise and show only meaningful momentum, with a signal line.<br><br><b>Signals:</b> TRIX crossing <b>above</b> zero (or its signal line) = buy, <b>below</b> = sell. Very smooth, so it gives few whipsaws — but more lag, so it's a confirmation tool, not an early-entry one."],
    BIAS: ["Deviation Rate (BIAS)", "The percentage distance between price and its moving average — a measure of how <b>stretched</b> price is from fair value.<br><br><b>Signals:</b> a large <b>positive</b> bias means price is far above its average (overbought — mean-reversion sell); a large <b>negative</b> bias means oversold (buy). What counts as 'too far' differs by asset, so calibrate the threshold per market."],
    MTM: ["Momentum (MTM)", "The simplest momentum gauge: today's price minus the price N bars ago.<br><br><b>Signals:</b> MTM <b>above zero</b> = upward momentum, below = downward; crossing zero flags a shift. Rising MTM confirms a healthy trend; MTM rolling over while price still rises warns the move is tiring."],
    PSY: ["Psychological Line (PSY)", "The percentage of the last N bars that closed <b>up</b> — a simple sentiment/crowd gauge.<br><br><b>Signals:</b> very high (>75%) = excessive optimism, a contrarian <b>sell</b>; very low (<25%) = excessive pessimism, a contrarian <b>buy</b>. It works best at extremes as a fade signal, not in the middle of its range."],
    BRAR: ["Sentiment (BRAR)", "AR gauges intraday 'popularity' from where price opens vs the bar's high/low; BR gauges buying/selling willingness vs the prior close.<br><br><b>Signals:</b> high AR/BR = an overheated market (sell), low = oversold (buy). When BR and AR <b>diverge</b> it refines timing — e.g. BR falling below AR near a bottom often precedes a bounce."],
    CR: ["Energy Index (CR)", "Measures the strength of buying vs selling pressure around a mid-price, similar in spirit to BR, plotted with its own moving averages.<br><br><b>Signals:</b> CR crossing its averages signals momentum shifts; very high readings = overbought, very low = a bottoming zone. Crossovers of the CR lines are used to time entries and exits."],
    VR: ["Volume Ratio (VR)", "The ratio of volume on up bars to volume on down bars over N bars — it tells you whether a price move actually has volume behind it.<br><br><b>Signals:</b> high VR (>160) = heavy buying, a possible top; low VR (<40) = heavy selling, a possible bottom. Use it to confirm whether a breakout is backed by real participation."],
    EMV: ["Ease of Movement (EMV)", "Combines price change with volume to show how <b>easily</b> price moves — big moves on light volume score high.<br><br><b>Signals:</b> EMV <b>above zero</b> = price rising with little volume resistance (healthy advance); below zero = falling easily. Crossing zero flags a shift. High EMV means small volume can push price far — a sign of a frictionless trend."],
    DMA: ["Difference of MAs (DMA)", "The gap between a fast and a slow moving average, plotted with its own signal-line average.<br><br><b>Signals:</b> DMA crossing <b>above</b> its signal/zero line = buy, <b>below</b> = sell. A widening DMA means the trend is strengthening; a narrowing one means it's losing steam and may reverse."],
    AO: ["Awesome Oscillator (AO)", "The difference between a 5- and 34-period average of the bar's median price — momentum measured against the broader trend, shown as a histogram.<br><br><b>Signals:</b> histogram crossing <b>zero</b> (up = buy, down = sell); the <b>twin-peaks</b> pattern (two pushes below/above zero) flags reversals; a <b>saucer</b> (colour change without crossing zero) is an early continuation signal."],
    PVT: ["Price Volume Trend (PVT)", "Like OBV but it weights each bar's volume by the <b>percentage</b> price change, so big moves count more — a cumulative money-flow line.<br><br><b>Signals:</b> PVT trending with price <b>confirms</b> the move; divergence warns of a reversal. Because it scales by the size of the move, PVT often turns or breaks out slightly ahead of price."],
    fibonacciLine: ["Fibonacci retracement", "After a strong move, markets rarely run straight on — they <b>retrace</b> part of it before continuing. Fibonacci retracement marks the levels where that pullback most often stalls, taken from the Fibonacci ratios <b>23.6 · 38.2 · 50 · 61.8 · 78.6%</b>. The diagram above shows price impulsing up, pulling back to the 61.8% level, and bouncing.<br><br><b>How to draw it:</b> pick the <b>Fibonacci</b> tool, then click the two ends of the move — for an up-move click the swing <b>low</b> then the swing <b>high</b>; the levels appear between them (0% at the high, 100% at the low).<br><br><b>What each level means:</b><br>• <b>23.6 / 38.2%</b> — shallow pullback; a strong trend often holds here.<br>• <b>50%</b> — not a true Fibonacci ratio but widely watched: a 'half-back' of the move.<br>• <b>61.8%</b> — the <b>golden ratio</b> and the key decision level: hold it and the trend usually resumes; lose it and the move may be over.<br>• <b>78.6%</b> — last line of defence; beyond it the prior move is generally negated.<br><br><b>How to trade it:</b> in an <b>uptrend</b> the 38.2–61.8% band is a <b>buy-the-dip</b> zone — wait for price to reach a level and show a bounce (e.g. a bullish candle), buy, and stop just below the next level. In a <b>downtrend</b> the same levels are <b>sell-the-rally</b> resistance. <b>Confluence</b> is everything: a Fib level that lines up with a moving average, a prior high/low, or a trend line is where the highest-odds entries cluster.<br><br><b>Extensions</b> (127.2 / 161.8%) project <i>beyond</i> the move to estimate take-profit targets. Tip: the chart's <b>⚡ Auto-analysis</b> button draws the Fibonacci of the dominant recent swing for you automatically."],
    segment: ["Trend line", "A straight line between two points that maps support or resistance. <b>Draw:</b> pick the Trend tool, click the start, then the end (the tool stays selected so you can draw several). <b>Use:</b> connect two or more swing <b>lows</b> for an up-trend support line — buy near it, and treat a decisive close <b>below</b> as a breakdown; connect swing <b>highs</b> for resistance, where a close <b>above</b> is a breakout. The more times price touches a line, the more it matters. <b>Right-click</b> a line to edit or erase it."],
    noteText: ["Note", "A draggable sticky-note pinned to the chart. <b>Add:</b> pick the Note tool and click where you want it, or <b>right-click empty chart space</b>. <b>Drag</b> to reposition, <b>right-click → Edit</b> to change the text, or <b>Erase</b> to remove. Notes are saved with your private chart (passphrase), so they're there next time."],
    measurePct: ["Measure %", "Measures the move between two points. Pick <b>Measure %</b>, click the start and end, and it draws a box with the <b>% change</b>, the price change, and the number of bars/days between them — handy for sizing a rally or drawdown, or checking how far away a target is."],
  };
  const MAIN_SET = new Set(MAIN_INDS.map(([v]) => v));
  const DEFAULTS = { MA: [5, 10, 30, 60], EMA: [6, 12, 20], SMA: [12, 2], BOLL: [20, 2], BBI: [3, 6, 12, 24], SAR: [2, 2, 20],
    VOL: [5, 10, 20], MACD: [12, 26, 9], RSI: [14], KDJ: [9, 3, 3], CCI: [13], WR: [6, 10, 14], DMI: [14, 6], OBV: [30],
    ROC: [12, 6], TRIX: [12, 9], BIAS: [6, 12, 24], MTM: [6, 10], PSY: [12, 6], BRAR: [26], CR: [26, 10, 20, 40, 60],
    VR: [24, 30], EMV: [14, 9], DMA: [10, 50, 10], AO: [5, 34], PVT: [] };
  const TOOLS = [
    ["cursor", "Cursor"], ["segment", "Trend line"], ["rayLine", "Ray"], ["horizontalStraightLine", "Horizontal"],
    ["verticalStraightLine", "Vertical"], ["priceLine", "Price line"], ["parallelStraightLine", "Parallel"],
    ["fibonacciLine", "Fibonacci"], ["noteText", "Note"], ["measurePct", "Measure %"],
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
      klinecharts.registerOverlay({   // draggable sticky-note (needDefaultPointFigure → its point is a drag handle)
        name: "noteText", totalStep: 2, needDefaultPointFigure: true, needDefaultXAxisFigure: true, needDefaultYAxisFigure: true,
        createPointFigures: ({ overlay, coordinates }) => {
          if (!coordinates.length || !coordinates[0]) return [];
          const c = coordinates[0], text = String(overlay.extendData || "note");
          return [{ type: "text", attrs: { x: c.x, y: c.y, text, align: "left", baseline: "middle" }, styles: { color: "#1d1d1f", backgroundColor: "rgba(255,221,120,.96)", borderColor: "rgba(176,138,20,.7)", borderSize: 1, size: 12, paddingLeft: 8, paddingRight: 8, paddingTop: 4, paddingBottom: 4, borderRadius: 7 } }];
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
      klinecharts.registerIndicator({   // auto-analysis buy/sell markers (circles + arrow), distinct from the playbook STRATSIGNAL
        name: "AUTOTA", figures: [], calc: (dataList) => dataList.map(() => ({})),
        draw: ({ ctx, kLineDataList, visibleRange, xAxis, yAxis }) => {
          const buys = AUTO_SIG.buys, sells = AUTO_SIG.sells; if (!buys.size && !sells.size) return false;
          for (let i = Math.max(0, visibleRange.from); i < visibleRange.to; i++) {
            const d = kLineDataList[i]; if (!d) continue;
            const isB = buys.has(d.timestamp), isS = sells.has(d.timestamp); if (!isB && !isS) continue;
            const x = xAxis.convertToPixel(i), y = yAxis.convertToPixel(isB ? d.low : d.high), yy = isB ? y + 16 : y - 16;
            ctx.fillStyle = isB ? UP : DN; ctx.beginPath(); ctx.arc(x, yy, 7, 0, 2 * Math.PI); ctx.fill();
            ctx.fillStyle = "#fff"; ctx.font = "bold 9px -apple-system,sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(isB ? "B" : "S", x, yy + 0.5);
          }
          return false;
        },
      });
    } catch (_) {}
    try {
      klinecharts.registerIndicator({   // "Add buy/sell signals" from a study → ▲/▼ triangles
        name: "STUDYSIG", figures: [], calc: (dataList) => dataList.map(() => ({})),
        draw: ({ ctx, kLineDataList, visibleRange, xAxis, yAxis }) => {
          const buys = STUDY_SIG.buys, sells = STUDY_SIG.sells; if (!buys.size && !sells.size) return false;
          for (let i = Math.max(0, visibleRange.from); i < visibleRange.to; i++) {
            const d = kLineDataList[i]; if (!d) continue;
            const isB = buys.has(d.timestamp), isS = sells.has(d.timestamp); if (!isB && !isS) continue;
            const x = xAxis.convertToPixel(i), y = yAxis.convertToPixel(isB ? d.low : d.high), yy = isB ? y + 11 : y - 11;
            ctx.fillStyle = isB ? UP : DN; ctx.beginPath();
            if (isB) { ctx.moveTo(x, yy - 8); ctx.lineTo(x - 5, yy + 2); ctx.lineTo(x + 5, yy + 2); }
            else { ctx.moveTo(x, yy + 8); ctx.lineTo(x - 5, yy - 2); ctx.lineTo(x + 5, yy - 2); }
            ctx.closePath(); ctx.fill();
          }
          return false;
        },
      });
    } catch (_) {}
    try {
      klinecharts.registerIndicator({   // override KLineChart's 3-line RSI with the classic single line + 30/50/70 bands
        name: "RSI", shortName: "RSI", calcParams: [14], minValue: 0, maxValue: 100,
        figures: [{ key: "rsi", title: "RSI: ", type: "line" }],
        calc: (dataList, indi) => {
          const n = (indi.calcParams && indi.calcParams[0]) || 14; const out = []; let g = 0, l = 0;
          for (let i = 0; i < dataList.length; i++) {
            if (i === 0) { out.push({}); continue; }
            const ch = dataList[i].close - dataList[i - 1].close, gg = Math.max(ch, 0), ll = Math.max(-ch, 0);
            if (i <= n) { g += gg; l += ll; if (i === n) { g /= n; l /= n; out.push({ rsi: 100 - 100 / (1 + (l === 0 ? 1e9 : g / l)) }); } else out.push({}); }
            else { g = (g * (n - 1) + gg) / n; l = (l * (n - 1) + ll) / n; out.push({ rsi: 100 - 100 / (1 + (l === 0 ? 1e9 : g / l)) }); }
          }
          return out;
        },
        draw: ({ ctx, bounding, yAxis }) => {
          [[70, DN], [50, "#bbbbc0"], [30, UP]].forEach(([lvl, col]) => {
            const y = yAxis.convertToPixel(lvl); ctx.strokeStyle = col; ctx.setLineDash(lvl === 50 ? [2, 3] : [4, 3]); ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(bounding.width, y); ctx.stroke(); ctx.setLineDash([]);
            ctx.fillStyle = col; ctx.font = "10px -apple-system,sans-serif"; ctx.textAlign = "left"; ctx.fillText(String(lvl), 2, y - 2);
          });
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
      table.pb td:last-child{vertical-align:middle;}
      table.pb th:first-child,table.pb td:first-child{text-align:left;white-space:normal;}
      table.pb th{font-size:11px;color:#6e6e73;text-transform:uppercase;letter-spacing:.03em;font-weight:700;}
      table.pb tr.bh{background:rgba(0,0,0,.035);font-weight:700;}
      table.pb .sig{font-size:11.5px;color:#6e6e73;margin:3px 0 5px;}
      table.pb .num{font-variant-numeric:tabular-nums;}
      table.pb .win{color:${UP};font-weight:700;}
      .pbp{display:flex;gap:7px;flex-wrap:wrap;margin-top:4px;}
      .pbp label{font-size:11px;color:#6e6e73;display:inline-flex;align-items:center;gap:4px;}
      .pbp input{font:inherit;font-size:12px;width:56px;padding:4px 6px;border-radius:7px;border:1px solid var(--line);}
      .pbacts{display:flex;flex-direction:column;gap:5px;align-items:stretch;min-width:84px;}
      .pb-btn{font:inherit;font-size:11.5px;font-weight:600;padding:6px 10px;border-radius:999px;border:1px solid transparent;background:#f0f0f3;color:#48484a;cursor:pointer;white-space:nowrap;text-align:center;transition:background .12s,color .12s;}
      .pb-btn:hover:not(:disabled){background:#e4e4ea;}
      .pb-btn.pb-plot.on{background:var(--accent);color:#fff;}
      .pb-btn.sig.on{background:#34c759;color:#fff;}
      .pb-btn.pb-note.on{background:#5856d6;color:#fff;}
      .pb-btn:disabled{opacity:.4;cursor:default;}
      tr.noterow td{background:rgba(0,113,227,.05);border-bottom:2px solid var(--line);font-size:12.5px;line-height:1.55;color:#333;padding:10px 14px;}
      #playbook,#leader{overflow-x:auto;-webkit-overflow-scrolling:touch;}
      @media(max-width:680px){
        table.pb th,table.pb td{padding:7px 6px;font-size:12px;}
        .pbacts{min-width:0;flex-direction:row;flex-wrap:wrap;gap:4px;justify-content:flex-end;}
        .pb-btn{padding:6px 9px;font-size:11px;}
        .cbar{gap:10px;} .pbp input{width:46px;} .pbp label{font-size:10.5px;}
        table.pb .sig{font-size:11px;white-space:normal;}
        h1{font-size:24px;} h2{font-size:18px;}
      }
    `;
    document.head.appendChild(s);
  }

  function run() {
    injectStyles(); registerIndicators();
    if (window.STRATEGY_PAGE_TITLE) document.title = window.STRATEGY_PAGE_TITLE;
    const state = { asset: "spx", tf: "D", dispAggMs: 0, type: "candle_solid", yAxis: "normal", tool: "cursor", tfLastTs: 0,
      indicators: Object.fromEntries(MAIN_INDS.concat(SUB_INDS).map(([v]) => [v, false])),
      indParams: Object.fromEntries(Object.entries(DEFAULTS).map(([k, v]) => [k, v.slice()])),
      stratParams: Object.fromEntries(STRATS.map((s) => [s.key, Object.fromEntries(s.params.map((q) => [q.k, q.d]))])),
      plotted: {}, signalKey: null, notesOpen: {}, curClose: [], curTs: [], curHigh: [], curLow: [],
      lev: { mult: 1, ddThr: -10, volThr: 18, costs: false }, pnl: { mode: "bps", perBp: 0 }, recession: false, inversion: false, carry: false,
      grid: "both", decimals: "auto", ylab: "out", crosshair: true, autoTA: false, studySig: null };
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
          <div><span class="lbl">Range</span><span class="seg" id="rangeSeg"></span>
            <span style="display:inline-flex;align-items:center;gap:4px;margin-left:6px;font-size:12px;color:#6e6e73">
              <input id="rngFrom" type="date" style="font:inherit;font-size:12px;padding:3px 6px;border-radius:7px;border:1px solid var(--line)">
              <span>→</span>
              <input id="rngTo" type="date" style="font:inherit;font-size:12px;padding:3px 6px;border-radius:7px;border:1px solid var(--line)">
              <button id="rngApply" class="seg" style="padding:4px 10px">Go</button>
            </span></div>
        </div>
        <details class="ind-panel">
          <summary>Indicators — overlays &amp; studies · click to expand &amp; edit params · <b>right-click any for help, examples &amp; one-click signals</b></summary>
          <div class="ind-grp"><span class="lbl">On&nbsp;price</span><span class="seg" id="indMain"></span></div>
          <div class="ind-grp"><span class="lbl">Studies</span><span class="seg" id="indSub"></span></div>
          <div class="ind-grp" id="indParams"></div>
        </details>
        <details class="ind-panel">
          <summary>Axis &amp; format — grid density · decimals · y-axis labels · crosshair</summary>
          <div class="ind-grp" style="flex-wrap:wrap;gap:14px">
            <span><span class="lbl">Grid</span><span class="seg" id="gridSeg"></span></span>
            <span><span class="lbl">Decimals</span><span class="seg" id="decSeg"></span></span>
            <span><span class="lbl">Y&nbsp;labels</span><span class="seg" id="ylabSeg"></span></span>
            <span><span class="lbl">Crosshair</span><span class="seg" id="xhairSeg"></span></span>
          </div>
        </details>
        <div class="cbar">
          <div><span class="lbl">Draw</span><span class="seg" id="toolSeg"></span></div>
          <div class="seg"><button id="undoBtn">Undo</button><button id="clearBtn">Clear all</button><button id="autoBtn">⚡ Auto-analysis</button><button id="recBtn"><span style="color:#9a9aa2">▦</span> Recessions</button><button id="invBtn"><span style="color:#d68a12">⊘</span> Inversions</button></div>
        </div>
        <div id="chart"></div>
        <p class="meta" id="hint" style="margin-top:8px">Scroll to zoom · drag to pan · pick a draw tool then click points on the chart.</p>
        <details id="autoCard" class="ind-panel" style="display:none;margin-top:8px">
          <summary>Auto-analysis notes — trend lines, Fibonacci &amp; signals · click to expand</summary>
          <div id="autoNotes" style="font-size:13px;line-height:1.6"></div>
        </details>
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
    // KLineChart's formatDate is positional (dateTimeFormat, timestamp, …) — find the epoch-ms arg robustly.
    safe(() => chart.setCustomApi({ formatDate: function () { var ts = null; for (var i = 0; i < arguments.length; i++) { var a = arguments[i]; if (typeof a === "number" && a > 1e11) { ts = a; break; } if (a && typeof a === "object" && typeof a.timestamp === "number") { ts = a.timestamp; break; } } return ts == null ? "" : ukTs(ts, state.tf !== "D"); } }));
    $("chart").addEventListener("contextmenu", (ev) => { ev.preventDefault(); setTimeout(() => { if (drawMenuEl) return; addNoteHere(); }, 0); }); // right-click empty space → add a note
    window.addEventListener("resize", () => chart && chart.resize());
    setTimeout(() => chart && chart.resize(), 60);

    makeSeg($("tfSeg"), TFS.map((t) => [t.id, t.label]), (v) => v === state.tf, (v, b) => { state.tf = v; segActive($("tfSeg"), b); applyTF(); });
    makeSeg($("typeSeg"), TYPES, (v) => v === state.type, (v, b) => { state.type = v; safe(() => chart.setStyles({ candle: { type: v } })); segActive($("typeSeg"), b); scheduleSave(); });
    makeSeg($("axisSeg"), AXES, (v) => v === state.yAxis, (v, b) => { state.yAxis = v; safe(() => chart.setStyles({ yAxis: { type: v } })); segActive($("axisSeg"), b); scheduleSave(); });
    function applyGrid() { const g = state.grid; safe(() => chart.setStyles({ grid: { show: g !== "off", horizontal: { show: g !== "off" }, vertical: { show: g === "both" } } })); }
    function autoDec() {   // ~6 significant figures by magnitude, capped by the data's own precision (indices→2, FX→4, BTC→1, yields→1-2)
      const cl = D.close || []; if (!cl.length) return 2;
      const last = Math.abs(cl[cl.length - 1]) || 1;
      let dataDec = 0; for (let i = Math.max(0, cl.length - 60); i < cl.length; i++) { const s = String(cl[i]); const d = s.includes(".") ? s.split(".")[1].length : 0; if (d > dataDec) dataDec = d; }
      const intDigits = last >= 1 ? Math.floor(Math.log10(last)) + 1 : 0;
      return Math.max(0, Math.min(6, dataDec, 6 - intDigits));
    }
    function applyDecimals() { const d = state.decimals === "auto" ? autoDec() : +state.decimals; safe(() => chart.setPriceVolumePrecision(d, 0)); }
    makeSeg($("gridSeg"), [["both", "Both"], ["h", "Horiz"], ["off", "Off"]], (v) => v === state.grid, (v, b) => { state.grid = v; applyGrid(); segActive($("gridSeg"), b); scheduleSave(); });
    makeSeg($("decSeg"), [["auto", "Auto"], ["0", "0"], ["2", "2"], ["4", "4"]], (v) => v === state.decimals, (v, b) => { state.decimals = v; applyDecimals(); segActive($("decSeg"), b); scheduleSave(); });
    makeSeg($("ylabSeg"), [["out", "Outside"], ["in", "Inside"]], (v) => v === state.ylab, (v, b) => { state.ylab = v; safe(() => chart.setStyles({ yAxis: { inside: v === "in" } })); segActive($("ylabSeg"), b); scheduleSave(); });
    makeSeg($("xhairSeg"), [["1", "On"], ["0", "Off"]], (v) => (v === "1") === state.crosshair, (v, b) => { state.crosshair = v === "1"; safe(() => chart.setStyles({ crosshair: { show: state.crosshair } })); segActive($("xhairSeg"), b); scheduleSave(); });
    makeSeg($("rangeSeg"), RANGES, () => false, (days, b) => { if ($("rngFrom")) { $("rngFrom").value = ""; $("rngTo").value = ""; } setRange(days); segActive($("rangeSeg"), b); });
    $("rngApply").onclick = setDateRange;
    $("rngFrom").onchange = $("rngTo").onchange = () => { if ($("rngFrom").value && $("rngTo").value) setDateRange(); };
    makeSeg($("indMain"), MAIN_INDS, (v) => state.indicators[v], (v, b) => { toggleIndicator(v); b.classList.toggle("active", state.indicators[v]); scheduleSave(); });
    makeSeg($("indSub"), SUB_INDS, (v) => state.indicators[v], (v, b) => { toggleIndicator(v); b.classList.toggle("active", state.indicators[v]); scheduleSave(); });
    // ---- "Add buy/sell signals" from a study (standard rule per indicator) ----
    function bbiArr(c) { const a = sma(c, 3), b = sma(c, 6), d = sma(c, 12), e = sma(c, 24); return c.map((_, i) => (a[i] != null && b[i] != null && d[i] != null && e[i] != null) ? (a[i] + b[i] + d[i] + e[i]) / 4 : null); }
    function studyPos(id) {   // 0/1 position from the study's standard rule (null = this study confirms/visualises, no one-click rule)
      const c = D.close, hi = D.high, lo = D.low, n = c ? c.length : 0, cp = state.indParams[id] || [];
      if (!c || n < 30) return null;
      const above = (a, b) => c.map((_, i) => (a[i] != null && b[i] != null) ? (a[i] >= b[i] ? 1 : 0) : 0);
      const pAbove = (m) => c.map((x, i) => (m[i] != null && x >= m[i]) ? 1 : 0);
      switch (id) {
        case "MA": return above(sma(c, cp[0] || 10), sma(c, cp[cp.length - 1] || 60));
        case "EMA": return above(ema(c, cp[0] || 12), ema(c, cp[cp.length - 1] || 26));
        case "SMA": return pAbove(sma(c, cp[0] || 12));
        case "BBI": return pAbove(bbiArr(c));
        case "BOLL": { const w = cp[0] || 20, k = cp[1] || 2, mid = sma(c, w), sd = rstd(c, w); let s = 0; return c.map((x, i) => { if (mid[i] == null) return 0; if (s === 0 && x < mid[i] - k * sd[i]) s = 1; else if (s === 1 && x > mid[i]) s = 0; return s; }); }
        case "MACD": { const m = macdP(c, cp[0] || 12, cp[1] || 26, cp[2] || 9); return c.map((_, i) => (m.macd[i] != null && m.signal[i] != null && m.macd[i] >= m.signal[i]) ? 1 : 0); }
        case "RSI": { const r = rsiArr(c, cp[0] || 14); let s = 0; return c.map((_, i) => { if (r[i] == null) return s; if (r[i] < 30) s = 1; else if (r[i] > 70) s = 0; return s; }); }
        case "KDJ": { const k = stoch(c, hi, lo, cp[0] || 9, cp[1] || 3); return c.map((_, i) => (k.k[i] != null && k.d[i] != null && k.k[i] >= k.d[i]) ? 1 : 0); }
        case "CCI": { const x = cci(c, hi, lo, cp[0] || 20); let s = 0; return c.map((_, i) => { if (x[i] == null) return s; if (x[i] < -100) s = 1; else if (x[i] > 100) s = 0; return s; }); }
        case "WR": { const w = willR(c, hi, lo, cp[0] || 14); let s = 0; return c.map((_, i) => { if (w[i] == null) return s; if (w[i] < -80) s = 1; else if (w[i] > -20) s = 0; return s; }); }
        case "ROC": { const p = cp[0] || 12; return c.map((x, i) => (i >= p && c[i - p]) ? ((x / c[i - p] - 1) >= 0 ? 1 : 0) : 0); }
        case "MTM": { const p = cp[0] || 12; return c.map((x, i) => (i >= p) ? (x - c[i - p] >= 0 ? 1 : 0) : 0); }
        case "TRIX": { const p = cp[0] || 12; const e1 = ema(c, p), e2 = ema(e1.map((v) => v == null ? 0 : v), p), e3 = ema(e2.map((v) => v == null ? 0 : v), p); return e3.map((v, i) => (i > 0 && v != null && e3[i - 1] != null) ? (v - e3[i - 1] >= 0 ? 1 : 0) : 0); }
        case "BIAS": return pAbove(sma(c, cp[0] || 12));
        case "DMA": return above(sma(c, cp[0] || 10), sma(c, cp[1] || 50));
        case "AO": { const md = (hi && lo) ? c.map((x, i) => (hi[i] + lo[i]) / 2) : c; return above(sma(md, 5), sma(md, 34)); }
        case "PSY": { const p = cp[0] || 12; const ups = c.map((x, i) => (i > 0 && x > c[i - 1]) ? 1 : 0); const ps = sma(ups, p); let s = 0; return ps.map((v) => { if (v == null) return s; const pv = v * 100; if (pv < 25) s = 1; else if (pv > 75) s = 0; return s; }); }
        case "OBV": { const vol = (D.daily || []).map((b) => b.volume || 0); if (!vol.some((v) => v > 0)) return null; let o = 0; const obv = c.map((x, i) => { if (i > 0) o += (x > c[i - 1] ? 1 : x < c[i - 1] ? -1 : 0) * vol[i]; return o; }); return above(obv, ema(obv, 30)); }
        default: return null;
      }
    }
    function studyMarks(pos) { const buys = new Set(), sells = new Set(), ts = (D.daily || []).map((b) => b.timestamp); for (let i = 1; i < pos.length; i++) { if (pos[i - 1] === 0 && pos[i] === 1) buys.add(ts[i]); else if (pos[i - 1] === 1 && pos[i] === 0) sells.add(ts[i]); } return { buys, sells }; }
    function addStudySignals(id) { const pos = studyPos(id); if (!pos) { status("this study confirms rather than signals — no one-click markers"); return; } STUDY_SIG = studyMarks(pos); state.studySig = id; safe(() => { chart.removeIndicator("candle_pane", "STUDYSIG"); chart.createIndicator("STUDYSIG", true, { id: "candle_pane" }); }); status(STUDY_SIG.buys.size + " buys / " + STUDY_SIG.sells.size + " sells from " + (HELP[id] ? HELP[id][0] : id)); }
    function removeStudySignals() { STUDY_SIG = { buys: new Set(), sells: new Set() }; state.studySig = null; safe(() => chart.removeIndicator("candle_pane", "STUDYSIG")); }
    function signalExample(id) { const pos = studyPos(id); if (!pos) return ""; const m = studyMarks(pos), ts = (D.daily || []).map((b) => b.timestamp); let last = null, type = ""; for (let i = ts.length - 1; i >= 1; i--) { if (m.buys.has(ts[i])) { last = ts[i]; type = "buy"; break; } if (m.sells.has(ts[i])) { last = ts[i]; type = "sell"; break; } } if (last == null) return ""; return `<b>On ${esc(D.label)} now:</b> the latest signal was a <b style="color:${type === "buy" ? UP : DN}">${type === "buy" ? "▲ buy" : "▼ sell"}</b> on <b>${ukTs(last, false)}</b>.`; }
    // mini SVG diagrams illustrating the indicator + where it fires
    const DIAG = { RSI: "osc", KDJ: "osc", CCI: "osc", WR: "osc", PSY: "osc", BIAS: "osc", BRAR: "osc", CR: "osc", VR: "osc", MA: "cross", EMA: "cross", SMA: "cross", BBI: "cross", MACD: "cross", DMA: "cross", AO: "cross", DMI: "cross", BOLL: "bands", SAR: "sar", VOL: "vol", ROC: "zero", MTM: "zero", TRIX: "zero", EMV: "zero", OBV: "zero", PVT: "zero" };
    function indDiagram(id) {
      const up = UP, dn = DN, W = 320, H = 134;
      const wrap = (inner) => `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px;height:auto;display:block;margin:8px auto 12px;background:#fafafa;border:1px solid var(--line);border-radius:10px">${inner}</svg>`;
      const buyA = (x, y) => `<path d="M${x},${y} l-5,9 l10,0 z" fill="${up}"/><text x="${x}" y="${y + 24}" font-size="9" fill="${up}" text-anchor="middle" font-weight="700">BUY</text>`;
      const sellA = (x, y) => `<path d="M${x},${y} l-5,-9 l10,0 z" fill="${dn}"/><text x="${x}" y="${y - 14}" font-size="9" fill="${dn}" text-anchor="middle" font-weight="700">SELL</text>`;
      if (id === "fibonacciLine" || id === "fibonacci") {
        const lv = [["0%", 30], ["23.6%", 51], ["38.2%", 64], ["50%", 75], ["61.8%", 86], ["78.6%", 101], ["100%", 120]];
        let lines = lv.map(([t, y]) => `<line x1="150" y1="${y}" x2="300" y2="${y}" stroke="${t === "61.8%" ? up : "#c9c9cf"}" stroke-width="${t === "61.8%" ? 1.6 : 1}"/><text x="304" y="${y + 3}" font-size="8.5" fill="#6e6e73">${t}</text>`).join("");
        return wrap(`${lines}<path d="M20,120 L150,30" fill="none" stroke="#0071e3" stroke-width="2"/><path d="M150,30 C170,52 185,80 200,86 C220,93 240,60 300,40" fill="none" stroke="#0071e3" stroke-width="2"/>${buyA(200, 92)}<text x="60" y="84" font-size="9" fill="#0071e3" transform="rotate(-32 60 84)">impulse up</text><text x="150" y="20" font-size="8.5" fill="#6e6e73">swing high</text><text x="6" y="123" font-size="8.5" fill="#6e6e73">low</text>`);
      }
      const t = DIAG[id] || "cross";
      if (t === "osc") return wrap(`<line x1="20" y1="34" x2="290" y2="34" stroke="${dn}" stroke-dasharray="4 3"/><text x="24" y="30" font-size="9" fill="${dn}">overbought (sell zone)</text><line x1="20" y1="100" x2="290" y2="100" stroke="${up}" stroke-dasharray="4 3"/><text x="24" y="114" font-size="9" fill="${up}">oversold (buy zone)</text><path d="M20,70 C55,40 80,30 110,34 C140,40 150,98 185,100 C215,101 232,48 262,40 C285,34 295,52 300,62" fill="none" stroke="#0071e3" stroke-width="2"/>${buyA(185, 106)}${sellA(110, 28)}`);
      if (t === "cross") return wrap(`<path d="M20,98 C70,86 110,68 160,56 C210,44 260,38 300,34" fill="none" stroke="#0071e3" stroke-width="2"/><path d="M20,68 C70,72 120,68 160,64 C210,58 260,50 300,46" fill="none" stroke="#ff9500" stroke-width="2"/><text x="306" y="34" font-size="9" fill="#0071e3" text-anchor="end">fast</text><text x="306" y="58" font-size="9" fill="#ff9500" text-anchor="end">slow</text>${buyA(152, 70)}<text x="120" y="120" font-size="9" fill="#6e6e73">fast crosses above slow → buy (and vice-versa)</text>`);
      if (t === "bands") return wrap(`<path d="M20,38 C90,38 140,34 300,32" fill="none" stroke="#bbb" stroke-width="1.4"/><text x="22" y="34" font-size="8.5" fill="#999">upper</text><path d="M20,98 C90,98 140,102 300,104" fill="none" stroke="#bbb" stroke-width="1.4"/><text x="22" y="113" font-size="8.5" fill="#999">lower</text><path d="M20,68 C90,68 140,68 300,68" fill="none" stroke="#999" stroke-dasharray="3 3"/><path d="M20,80 C55,96 88,100 118,93 C158,83 175,38 212,34 C248,31 272,56 300,60" fill="none" stroke="#0071e3" stroke-width="2"/>${buyA(112, 104)}${sellA(208, 28)}`);
      if (t === "zero") return wrap(`<line x1="20" y1="66" x2="300" y2="66" stroke="#999" stroke-dasharray="3 3"/><text x="24" y="62" font-size="9" fill="#999">zero line</text><path d="M20,82 C60,86 90,74 120,66 C150,58 180,42 210,40 C246,38 272,54 300,60" fill="none" stroke="#0071e3" stroke-width="2"/>${buyA(118, 74)}<text x="120" y="120" font-size="9" fill="#6e6e73">crosses up through zero → buy</text>`);
      if (t === "sar") return wrap(`<path d="M20,92 C70,82 110,62 160,52 C210,42 252,54 300,72" fill="none" stroke="#0071e3" stroke-width="2"/><circle cx="50" cy="102" r="2.5" fill="${up}"/><circle cx="82" cy="98" r="2.5" fill="${up}"/><circle cx="114" cy="88" r="2.5" fill="${up}"/><circle cx="146" cy="76" r="2.5" fill="${up}"/><circle cx="206" cy="30" r="2.5" fill="${dn}"/><circle cx="238" cy="34" r="2.5" fill="${dn}"/><circle cx="270" cy="46" r="2.5" fill="${dn}"/>${buyA(46, 112)}${sellA(202, 24)}<text x="120" y="125" font-size="9" fill="#6e6e73">dots flip side = trend reversal</text>`);
      if (t === "vol") { let bars = ""; const hs = [28, 48, 24, 66, 92, 38, 33, 58, 78, 44]; hs.forEach((h, i) => { bars += `<rect x="${26 + i * 28}" y="${114 - h}" width="16" height="${h}" fill="${i === 4 ? up : "#c7c7cc"}"/>`; }); return wrap(`${bars}<text x="160" y="20" font-size="9" fill="${up}" text-anchor="middle">a breakout on a tall (high-volume) bar = confirmed</text>`); }
      return wrap("");
    }
    // right-click any overlay/study chip → detailed help (what it is + trading signals)
    function closeIndHelp() { const e = $("indHelpOv"); if (e) e.remove(); document.removeEventListener("keydown", indHelpEsc); }
    function indHelpEsc(e) { if (e.key === "Escape") closeIndHelp(); }
    function showIndHelp(id) {
      const h = HELP[id]; if (!h) return; closeIndHelp();
      const diag = indDiagram(id), ex = signalExample(id), hasSig = studyPos(id) != null, active = state.studySig === id;
      const noSig = !hasSig && (id === "VOL" || id === "SAR" || id === "DMI" || id === "BRAR" || id === "CR" || id === "VR" || id === "EMV" || id === "PVT");
      const sigBtn = hasSig
        ? `<button id="indHelpSig" style="margin-top:14px;width:100%;padding:11px;border:0;border-radius:10px;background:${active ? "#48484a" : UP};color:#fff;font:inherit;font-size:14px;font-weight:600;cursor:pointer">${active ? "✕ Remove these signals from the chart" : "➕ Add buy/sell signals to the chart"}</button>`
        : (noSig ? `<p class="meta" style="margin-top:12px">This study <b>confirms or visualises</b> rather than firing discrete buy/sell points — read it alongside a signalling study rather than trading it on its own.</p>` : "");
      const ov = document.createElement("div"); ov.id = "indHelpOv";
      ov.style.cssText = "position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,.42);display:flex;align-items:center;justify-content:center;padding:18px;";
      ov.innerHTML = `<div style="background:#fff;border-radius:16px;max-width:560px;width:100%;max-height:86vh;overflow:auto;padding:22px 24px;box-shadow:0 24px 70px rgba(0,0,0,.32)"><div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:6px"><h3 style="margin:0;font-size:19px;color:#1d1d1f">${esc(h[0])}</h3><button id="indHelpX" style="border:0;background:#f0f0f3;border-radius:50%;width:30px;height:30px;font-size:18px;line-height:1;cursor:pointer;flex:none;color:#48484a">×</button></div>${diag}<div style="font-size:14px;line-height:1.62;color:#333">${h[1]}</div>${ex ? `<p style="font-size:13px;background:#f0fbf4;border:1px solid #cfeede;border-radius:9px;padding:9px 12px;margin:12px 0 0;color:#333">${ex}</p>` : ""}${sigBtn}</div>`;
      document.body.appendChild(ov);
      ov.onclick = (e) => { if (e.target === ov) closeIndHelp(); };
      $("indHelpX").onclick = closeIndHelp;
      if ($("indHelpSig")) $("indHelpSig").onclick = () => { if (state.studySig === id) removeStudySignals(); else addStudySignals(id); closeIndHelp(); };
      document.addEventListener("keydown", indHelpEsc);
    }
    [$("indMain"), $("indSub")].forEach((seg) => seg && seg.addEventListener("contextmenu", (e) => { const b = e.target.closest("button[data-v]"); if (!b) return; e.preventDefault(); showIndHelp(b.dataset.v); }));
    makeSeg($("toolSeg"), TOOLS, (v) => v === state.tool, (v, b) => { pickTool(v); segActive($("toolSeg"), b); }, "tool");
    $("toolSeg").addEventListener("contextmenu", (e) => { const b = e.target.closest("button[data-v]"); if (!b || !HELP[b.dataset.v]) return; e.preventDefault(); showIndHelp(b.dataset.v); }); // right-click a draw tool (e.g. Fibonacci) → help
    $("undoBtn").onclick = undoDrawing;
    $("clearBtn").onclick = clearDrawings;
    $("recBtn").onclick = () => { state.recession = !state.recession; $("recBtn").classList.toggle("active", state.recession); safe(() => { if (state.recession) chart.createIndicator("RECESSION", true, { id: "candle_pane" }); else chart.removeIndicator("candle_pane", "RECESSION"); }); };
    $("invBtn").onclick = () => { state.inversion = !state.inversion; $("invBtn").classList.toggle("active", state.inversion); safe(() => { if (state.inversion) chart.createIndicator("INVERSION", true, { id: "candle_pane" }); else chart.removeIndicator("candle_pane", "INVERSION"); }); };
    // ---- Auto-analysis: swing pivots → support/resistance trend lines + Fibonacci + buy/sell signals, all with notes ----
    let autoIds = [];
    function clearAutoTA() { autoIds.forEach((id) => safe(() => chart.removeOverlay(id))); autoIds = []; AUTO_SIG = { buys: new Set(), sells: new Set() }; safe(() => chart.removeIndicator("candle_pane", "AUTOTA")); $("autoCard").style.display = "none"; $("autoNotes").innerHTML = ""; }
    function computeAutoTA() {
      const daily = D.daily || []; if (daily.length < 40) return null;
      const seg = daily.slice(Math.max(0, daily.length - 252)); // analyse the last ~year
      const hi = seg.map((b) => b.high), lo = seg.map((b) => b.low), cl = seg.map((b) => b.close), ts = seg.map((b) => b.timestamp);
      const k = 6, ph = [], pl = []; // swing pivots (fractals): extreme within ±k bars
      for (let i = k; i < seg.length - k; i++) { let isH = true, isL = true; for (let j = i - k; j <= i + k; j++) { if (j === i) continue; if (hi[j] >= hi[i]) isH = false; if (lo[j] <= lo[i]) isL = false; } if (isH) ph.push(i); if (isL) pl.push(i); }
      let Hi = 0, Lo = 0; for (let i = 0; i < seg.length; i++) { if (hi[i] > hi[Hi]) Hi = i; if (lo[i] < lo[Lo]) Lo = i; }
      const dir = Hi > Lo ? "up" : "down", hiV = hi[Hi], loV = lo[Lo], span = hiV - loV || 1;
      const levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1].map((r) => ({ r, v: dir === "up" ? hiV - span * r : loV + span * r }));
      const tl = [];
      if (ph.length >= 2) { const a = ph[ph.length - 2], b = ph[ph.length - 1]; tl.push({ kind: "resistance", p0: { timestamp: ts[a], value: hi[a] }, p1: { timestamp: ts[b], value: hi[b] }, d0: ts[a], d1: ts[b] }); }
      if (pl.length >= 2) { const a = pl[pl.length - 2], b = pl[pl.length - 1]; tl.push({ kind: "support", p0: { timestamp: ts[a], value: lo[a] }, p1: { timestamp: ts[b], value: lo[b] }, d0: ts[a], d1: ts[b] }); }
      const mid = levels[3].v, sig = []; // signals: reclaim/lose the 50% retracement after the dominant swing
      for (let i = Math.max(Hi, Lo) + 1; i < seg.length; i++) { if (cl[i - 1] <= mid && cl[i] > mid) sig.push({ ts: ts[i], type: "buy" }); else if (cl[i - 1] >= mid && cl[i] < mid) sig.push({ ts: ts[i], type: "sell" }); }
      return { tl, dir, hiV, loV, hiTs: ts[Hi], loTs: ts[Lo], levels, sig: sig.slice(-6) };
    }
    function applyAutoTA() {
      clearAutoTA();
      const a = computeAutoTA(); if (!a) { status("not enough data for auto-analysis"); return; }
      a.tl.forEach((t) => { const col = t.kind === "resistance" ? DN : UP; const id = safe(() => chart.createOverlay({ name: "segment", points: [t.p0, t.p1], lock: true, styles: { line: { color: col, size: 2, style: "dashed" } } })); if (id) autoIds.push(id); });
      const fid = safe(() => chart.createOverlay({ name: "fibonacciLine", points: [{ timestamp: a.dir === "up" ? a.loTs : a.hiTs, value: a.dir === "up" ? a.loV : a.hiV }, { timestamp: a.dir === "up" ? a.hiTs : a.loTs, value: a.dir === "up" ? a.hiV : a.loV }], lock: true })); if (fid) autoIds.push(fid);
      AUTO_SIG = { buys: new Set(a.sig.filter((s) => s.type === "buy").map((s) => s.ts)), sells: new Set(a.sig.filter((s) => s.type === "sell").map((s) => s.ts)) };
      safe(() => { chart.removeIndicator("candle_pane", "AUTOTA"); chart.createIndicator("AUTOTA", true, { id: "candle_pane" }); });
      renderAutoNotes(a);
    }
    function renderAutoNotes(a) {
      const dec = (v) => nfmt(v), L = a.levels;
      const note = (title, body) => `<details style="border-bottom:1px solid var(--line);padding:7px 0"><summary style="cursor:pointer;font-weight:600;color:#1d1d1f">${title}</summary><div style="color:#444;margin:5px 0 2px;padding-left:4px">${body}</div></details>`;
      let html = `<p class="meta" style="margin:6px 0 8px">Detected from the last ~year of daily bars. These are mechanical guides, not advice — always confirm with your own read.</p>`;
      a.tl.forEach((t) => { html += note(`${t.kind === "resistance" ? "🔻 Resistance trend line" : "🔺 Support trend line"}`, `Drawn through the last two swing ${t.kind === "resistance" ? "highs" : "lows"} (${ukd(isoOf(t.d0))} → ${ukd(isoOf(t.d1))}). <b>Signal:</b> a decisive close ${t.kind === "resistance" ? "<b>above</b> it is a breakout (buy)" : "<b>below</b> it is a breakdown (sell)"}; until then it tends to ${t.kind === "resistance" ? "cap rallies" : "support dips"}.`); });
      html += note("📐 Fibonacci retracement", `Of the dominant ${a.dir === "up" ? "up-leg" : "down-leg"} from <b>${dec(a.loV)}</b> to <b>${dec(a.hiV)}</b>. Key levels: 38.2% ${dec(L[2].v)} · 50% ${dec(L[3].v)} · 61.8% ${dec(L[4].v)}. <b>Signal:</b> in an uptrend these act as pullback <b>support</b> (buy-the-dip zones); in a downtrend as <b>resistance</b> (sell-the-rally zones). A bounce from 61.8% that holds is the classic continuation entry.`);
      const buys = a.sig.filter((s) => s.type === "buy"), sells = a.sig.filter((s) => s.type === "sell");
      html += note(`🟢 Buy signals (${buys.length})`, buys.length ? `Triggered when price <b>reclaimed the 50% retracement (${dec(L[3].v)})</b> from below — momentum turning up. Most recent: ${buys.slice(-3).map((s) => ukd(isoOf(s.ts))).join(", ")}.` : "None in the current window.");
      html += note(`🔴 Sell signals (${sells.length})`, sells.length ? `Triggered when price <b>lost the 50% retracement (${dec(L[3].v)})</b> from above — momentum turning down. Most recent: ${sells.slice(-3).map((s) => ukd(isoOf(s.ts))).join(", ")}.` : "None in the current window.");
      $("autoNotes").innerHTML = html; $("autoCard").style.display = "";
    }
    $("autoBtn").onclick = () => { state.autoTA = !state.autoTA; $("autoBtn").classList.toggle("active", state.autoTA); if (state.autoTA) applyAutoTA(); else clearAutoTA(); };
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

    // Zoom to the last `days` bars. resize() forces a re-measure+render (fixes a stalled/blank chart that
    // otherwise needs another click), and we re-assert on the next frame so the scroll lands after setBarSpace.
    // Show a daily-index window [loIdx, hiIdx). KLineChart can't render more than ~650 daily bars at its 1px
    // floor, so long windows auto-aggregate to weekly/monthly (like a real charting platform). resize() +
    // re-asserting the scroll on the next frame fixes the "needs a second click" stall.
    function showRange(loIdx, hiIdx) {
      const daily = D.daily || []; if (!daily.length || !chart) return;
      loIdx = Math.max(0, Math.min(loIdx, daily.length - 2)); hiIdx = Math.min(daily.length, Math.max(hiIdx, loIdx + 2));
      const span = hiIdx - loIdx, aggMs = span <= 650 ? 0 : (span <= 3500 ? 7 * 86400000 : 30 * 86400000); // daily / weekly / monthly
      const bars = aggMs ? aggregate(daily, aggMs) : daily;
      if (state.dispAggMs !== aggMs || state.tf !== "D") {   // resolution (or timeframe) changed → re-apply the data
        if (state.tf !== "D") { state.tf = "D"; stopPoll(); segActive($("tfSeg"), findBtn($("tfSeg"), "D")); }
        state.dispAggMs = aggMs;
        safe(() => { chart.applyNewData(bars); chart.resize(); }); setCur(bars); reapplyDrawings(); refreshSignals(); if (state.autoTA) applyAutoTA();
        $("hint").textContent = (aggMs ? (aggMs >= 30 * 86400000 ? "Monthly" : "Weekly") + " bars (long range)" : "Daily bars") + " · scroll to zoom · drag to pan.";
      }
      const loTs = daily[loIdx].timestamp, hiTs = daily[hiIdx - 1].timestamp;
      let a = 0; while (a < bars.length - 1 && bars[a].timestamp < loTs) a++;
      let b = bars.length - 1; while (b > 0 && bars[b].timestamp > hiTs) b--;
      const n = Math.max(2, b - a + 1), atEnd = b >= bars.length - 1;
      const apply = () => { const w = Math.max(200, $("chart").clientWidth - 70); safe(() => { chart.resize(); chart.setBarSpace(Math.max(0.5, Math.min(40, w / n))); if (atEnd) chart.scrollToRealTime(0); else chart.scrollToTimestamp(bars[b].timestamp, 0); }); };
      apply(); requestAnimationFrame(apply);
    }
    function setRange(days) { const daily = D.daily || []; if (!daily.length) return; const hi = daily.length; showRange(days ? hi - days : 0, hi); }
    function setDateRange() {
      const fromV = $("rngFrom").value, toV = $("rngTo").value, daily = D.daily || [];
      if (!daily.length || (!fromV && !toV)) return;
      const fromMs = fromV ? Date.parse(fromV) : daily[0].timestamp, toMs = toV ? Date.parse(toV) + 86400000 : daily[daily.length - 1].timestamp;
      let lo = 0; while (lo < daily.length - 1 && daily[lo].timestamp < fromMs) lo++;
      let hi = daily.length; while (hi > lo + 1 && daily[hi - 1].timestamp > toMs) hi--;
      segActive($("rangeSeg"), null); showRange(lo, hi);
    }

    // ---- timeframe / intraday ----
    function aggregate(bars, ms) { if (!ms) return bars; const out = []; let cur = null, key = null; for (const b of bars) { const k = Math.floor(b.timestamp / ms); if (k !== key) { if (cur) out.push(cur); cur = { timestamp: k * ms, open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume || 0 }; key = k; } else { cur.high = Math.max(cur.high, b.high); cur.low = Math.min(cur.low, b.low); cur.close = b.close; cur.volume += b.volume || 0; } } if (cur) out.push(cur); return out; }
    function setCur(bars) { state.curClose = bars.map((b) => b.close); state.curTs = bars.map((b) => b.timestamp); state.curHigh = bars.map((b) => b.high); state.curLow = bars.map((b) => b.low); applyDecimals(); } // re-assert y-axis precision (applyNewData resets it)
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
      if (!tf.interval) { safe(() => { chart.applyNewData(D.daily || []); chart.resize(); }); state.dispAggMs = 0; setCur(D.daily || []); setRange(252); reapplyDrawings(); refreshSignals(); if (state.autoTA) applyAutoTA(); state.tfLastTs = 0; $("hint").textContent = "Daily bars · scroll to zoom · drag to pan · pick a draw tool then click points."; return; }
      status("loading " + tf.label + "…");
      fetchIntradayBars(tf)
        .then(({ bars: raw, ticker }) => {
          let bars = raw || []; if (!bars.length) throw new Error("no intraday data"); if (tf.aggMs) bars = aggregate(bars, tf.aggMs);
          state.dispAggMs = -1;   // intraday display → a range click will rebuild the daily/aggregated view
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
    let pendingOverlayId = null, drawMenuEl = null, lastMouse = { x: 120, y: 120 };
    document.addEventListener("mousemove", (e) => { lastMouse = { x: e.clientX, y: e.clientY }; });
    // every overlay gets a right-click handler → edit/erase menu (used by new draws AND restored ones)
    function mkOverlay(spec) { return safe(() => chart.createOverlay({ ...spec, onRightClick: (e) => { showDrawMenu(e.overlay); return true; }, onPressedMoveEnd: (e) => { recordDrawing(e.overlay); return false; } })); } // onPressedMoveEnd persists drags
    function pickTool(name) {
      state.tool = name;
      if (pendingOverlayId != null) { safe(() => chart.removeOverlay(pendingOverlayId)); pendingOverlayId = null; } // cancel any in-progress draw
      if (name === "cursor") return;
      armTool(name);
    }
    // STICKY: re-arm the same tool after each drawing so it stays selected until you pick another tool / Cursor.
    function armTool(name) {
      pendingOverlayId = mkOverlay({ name, extendData: name === "noteText" ? " " : undefined, onDrawEnd: (e) => {
        pendingOverlayId = null;
        if (name === "noteText") { const pts = (e.overlay.points || []).map((p) => ({ timestamp: p.timestamp, value: p.value })); inlineNote(lastMouse.x, lastMouse.y, "", e.overlay.id, pts); }
        else recordDrawing(e.overlay);
        if (state.tool === name && name !== "cursor") armTool(name);
        return false;
      } });
    }
    function closeDrawMenu() { if (drawMenuEl) { drawMenuEl.remove(); drawMenuEl = null; } }
    function showDrawMenu(overlay) {
      closeDrawMenu();
      const m = document.createElement("div");
      m.style.cssText = `position:fixed;left:${Math.min(lastMouse.x, innerWidth - 160)}px;top:${Math.min(lastMouse.y, innerHeight - 90)}px;z-index:9999;background:#fff;border:1px solid var(--line);border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.18);overflow:hidden;min-width:140px;`;
      const item = (label, fn, danger) => { const b = document.createElement("button"); b.textContent = label; b.style.cssText = `display:block;width:100%;text-align:left;padding:9px 16px;border:0;background:#fff;cursor:pointer;font:inherit;font-size:13px;color:${danger ? "#d70015" : "#1d1d1f"}`; b.onmouseenter = () => (b.style.background = "#f2f2f7"); b.onmouseleave = () => (b.style.background = "#fff"); b.onclick = (ev) => { ev.stopPropagation(); closeDrawMenu(); fn(); }; return b; };
      if (overlay.name === "noteText" || overlay.name === "simpleAnnotation") m.appendChild(item("✎  Edit note", () => editAnnotation(overlay)));
      m.appendChild(item("🗑  Erase", () => eraseOverlay(overlay), true));
      document.body.appendChild(m); drawMenuEl = m;
      setTimeout(() => document.addEventListener("mousedown", closeDrawMenu, { once: true }), 0);
    }
    function eraseOverlay(o) { safe(() => chart.removeOverlay(o.id)); const i = drawings.findIndex((d) => d.id === o.id); if (i >= 0) drawings.splice(i, 1); scheduleSave(); }
    function editAnnotation(o) { const pts = (o.points || []).map((p) => ({ timestamp: p.timestamp, value: p.value })); inlineNote(lastMouse.x, lastMouse.y, o.extendData || "", o.id, pts); }
    // a small text box at the click point; the note shows in-chart LIVE as you type — Enter / click-away saves, Esc cancels, no OK
    function inlineNote(px, py, initial, id, pts) {
      const inp = document.createElement("input"); inp.type = "text"; inp.value = initial || ""; inp.placeholder = "type a note…";
      inp.style.cssText = `position:fixed;left:${Math.min(Math.max(8, px), innerWidth - 210)}px;top:${Math.min(Math.max(8, py), innerHeight - 44)}px;z-index:10001;font:inherit;font-size:13px;padding:6px 10px;border:1.5px solid ${UP};border-radius:8px;background:rgba(255,251,228,.99);box-shadow:0 8px 26px rgba(0,0,0,.22);min-width:170px`;
      document.body.appendChild(inp); inp.focus(); inp.select();
      let done = false;
      inp.oninput = () => safe(() => chart.overrideOverlay({ id, extendData: inp.value || " " }));   // live in-chart preview
      const finish = (commit) => {
        if (done) return; done = true; const v = inp.value.trim(); inp.remove();
        const existed = drawings.some((x) => x.id === id);
        if (commit && v) { safe(() => chart.overrideOverlay({ id, extendData: v })); if (existed) { const d = drawings.find((x) => x.id === id); if (d) d.extendData = v; } else recordDrawing({ id, name: "noteText", extendData: v, points: pts }); scheduleSave(); }
        else if (existed) safe(() => chart.overrideOverlay({ id, extendData: initial || "note" }));   // cancel an edit → restore
        else safe(() => chart.removeOverlay(id));   // cancel a brand-new note → remove
      };
      inp.onkeydown = (e) => { e.stopPropagation(); if (e.key === "Enter") finish(true); else if (e.key === "Escape") finish(false); };
      inp.onblur = () => finish(true);
    }
    // right-click empty chart → drop a note there and inline-edit it (no top-of-page prompt)
    function addNoteHere() {
      const rect = $("chart").getBoundingClientRect();
      const dp = safe(() => chart.convertFromPixel({ x: lastMouse.x - rect.left, y: lastMouse.y - rect.top }, { paneId: "candle_pane" }));
      if (!dp || dp.value == null) return;
      const pts = [{ timestamp: dp.timestamp, value: dp.value }];
      const id = mkOverlay({ name: "noteText", extendData: " ", points: pts });
      if (id) inlineNote(lastMouse.x, lastMouse.y, "", id, pts);
    }
    const validDraw = (d) => d && d.name && Array.isArray(d.points) && d.points.length && d.points.every((p) => p && p.value != null && isFinite(p.value));
    function recordDrawing(o) { if (restoring || !o || !o.points || !o.points.length) return; const pts = o.points.map((p) => ({ timestamp: p.timestamp, value: p.value })); if (pts.some((p) => p.value == null)) return; const i = drawings.findIndex((d) => d.id === o.id), rec = { id: o.id, name: o.name, points: pts, extendData: o.extendData }; if (i >= 0) drawings[i] = rec; else drawings.push(rec); scheduleSave(); }
    function reapplyDrawings() { restoring = true; safe(() => chart.removeOverlay()); const keep = drawings.filter(validDraw); drawings = []; keep.forEach((d) => { const id = mkOverlay({ name: d.name, points: d.points, extendData: d.extendData }); if (id) drawings.push({ id, name: d.name, points: d.points, extendData: d.extendData }); }); restoring = false; }
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
      (snap.drawings || []).filter(validDraw).forEach((d) => { const id = mkOverlay({ name: d.name, points: d.points, extendData: d.extendData }); if (id) drawings.push({ id, name: d.name, points: d.points, extendData: d.extendData }); });
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
      const c = D.close, host = $("playbook"); $("pbAsset").textContent = D.dates.length ? "· " + D.label + " · " + ukd(D.dates[0]) + " → " + ukd(D.dates[D.n - 1]) : "";
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
        const plotBtn = st.plot ? `<button class="pb-btn pb-plot ${state.plotted[st.key] ? "on" : ""}" data-plot="${st.key}">${state.plotted[st.key] ? "✓ plot" : "plot"}</button>` : `<button class="pb-btn pb-plot" disabled title="no chart overlay">plot</button>`;
        const sigBtn = `<button class="pb-btn sig ${state.signalKey === st.key ? "on" : ""}" data-sig="${st.key}">${state.signalKey === st.key ? "✓ signals" : "signals"}</button>`;
        const noteBtn = `<button class="pb-btn pb-note ${state.notesOpen[st.key] ? "on" : ""}" data-note="${st.key}">${state.notesOpen[st.key] ? "✓ notes" : "notes"}</button>`;
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
      note.innerHTML = (cur ? `<b>${esc(cur.label)}:</b> ${cur.explain} <span style="color:#8a8a8e">(best: ${esc(cur.best.name)} — ${esc(Object.entries(cur.best.params).map(([k, v]) => k + " " + v).join(", "))}, Sharpe ${f2(cur.best.metrics.sharpe)})</span> · <b>Now: ${sigCell(cur.best)}</b> <span class="meta">as of ${esc(ukd(cur.best.asof))}</span>` : "") + (rc ? `<br><span style="color:#444">${rc}${carryTxt}</span>` : "");
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
      $("curveAsof").textContent = "as of " + ukd(CURVE[CURVE.length - 1].date || "");
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

    const ASSET_CACHE = {};   // in-memory: switching back to an already-loaded asset is instant (no re-fetch)
    function loadAsset(id) {
      state.asset = id;
      const apply = (d) => {
        D.id = id; D.ticker = d.ticker; D.label = d.asset_label || id; D.kind = d.kind || "price"; D.klass = d.klass || ""; D.legs = d.legs || null; D.cr = d.cr || null; D.n = d.close.length; D.dates = d.dates; D.close = d.close; D.high = d.high; D.low = d.low;
        D.ddh = ddFromHigh(d.close, 252); D.rv = rvol(d.close, 20);
        D.dv01 = D.legs ? Math.max(...D.legs.map((l) => TICKER_DV01[l.t] || 1)) : (TICKER_DV01[D.ticker] || 8.6);
        state.pnl.perBp = Math.round(D.dv01 * 1000);   // ≈ trade DV01 in $/bp (per ~$10mm); user-editable
        if (D.kind === "spread" && state.yAxis !== "normal") { state.yAxis = "normal"; safe(() => chart.setStyles({ yAxis: { type: "normal" } })); segActive($("axisSeg"), findBtn($("axisSeg"), "normal")); }  // log/% invalid for spreads that go negative
        $("cTitle").textContent = D.label + " — chart";
        if ($("rngFrom") && D.dates.length) { $("rngFrom").min = $("rngTo").min = D.dates[0]; $("rngFrom").max = $("rngTo").max = D.dates[D.n - 1]; $("rngFrom").value = ""; $("rngTo").value = ""; }
        D.daily = d.close.map((c, i) => ({ timestamp: d.timestamp[i], open: d.open[i], high: d.high[i], low: d.low[i], close: c, volume: d.volume ? d.volume[i] : 0 }));
        safe(() => chart.removeOverlay()); drawings = []; removeStudySignals();
        applyTF(); loadNotes(); fetchLive(); renderPlaybook(); renderLeader(); renderCurve(); syncPnlUI();
        if (pendingBest) { applyStrategy(pendingBest, true); pendingBest = null; }
        else { const e = LEADER.find((x) => x.id === D.id); if (e && ["Rates", "Steepness", "Butterfly"].includes(D.klass)) applyStrategy(e.best, false); }   // best rule = default for every UST trade
      };
      if (ASSET_CACHE[id]) return apply(ASSET_CACHE[id]);
      fetch("price_" + id + ".json").then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }).then((d) => { ASSET_CACHE[id] = d; apply(d); }).catch((e) => { status("could not load " + id + " — " + e.message); });
    }

    updateAuth();
    // Load the registry + curve data AND the default asset all in parallel (was sequential), and drop the
    // ?v=Date.now() cache-busters so the browser actually caches (GitHub Pages: max-age=600 + ETag revalidation).
    Promise.all([
      fetch("price_assets.json").then((r) => r.json()).catch(() => [{ id: "spx", label: "S&P 500", klass: "Indices", ticker: "^GSPC" }, { id: "ndx", label: "Nasdaq 100", klass: "Indices", ticker: "^NDX" }]),
      fetch("ust_strategies.json").then((r) => r.json()).catch(() => []),
      fetch("ust_curve.json").then((r) => r.json()).catch(() => []),
      fetch("ust_inversions.json").then((r) => r.json()).catch(() => []),
      fetch("price_" + state.asset + ".json").then((r) => (r.ok ? r.json() : null)).then((d) => { if (d) ASSET_CACHE[state.asset] = d; }).catch(() => {}),
    ]).then(([assets, leader, curve, inv]) => {
      ASSETS = assets || []; LEADER = leader || []; CURVE = curve || []; INVERSIONS = (inv || []).map(([s, e]) => [Date.parse(s), Date.parse(e)]);
      const sel = $("assetSel"), groups = {}; ASSETS.forEach((a) => { (groups[a.klass] = groups[a.klass] || []).push(a); });
      sel.innerHTML = Object.keys(groups).map((g) => `<optgroup label="${esc(g)}">` + groups[g].map((a) => `<option value="${esc(a.id)}">${esc(a.label)}</option>`).join("") + `</optgroup>`).join("");
      sel.value = state.asset; sel.onchange = () => loadAsset(sel.value); loadAsset(state.asset);
    });
  }

  function boot() { if (!window.klinecharts || !document.getElementById("app")) { setTimeout(boot, 30); return; } if (window.SP && SP.injectStyles) SP.injectStyles(); run(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
