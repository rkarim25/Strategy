/**
 * Charts — a TradingView/Bloomberg-style charting workstation built on KLineChart (vendored v9.8.12).
 * Asset registry (price_assets.json, grouped by class) · candle/bar/area · linear/log/% axis · range presets ·
 * timeframes 1m/5m/15m/30m/1h/4h/1D (intraday via the quote proxy, 4h aggregated, 60s auto-refresh) ·
 * comprehensive indicators with editable parameters · drawing palette + custom "Measure %" overlay (retained
 * across timeframe/zoom) · live last price · private per-asset notes + drawings (passphrase-gated, localStorage).
 * Interactive Signal Playbook: each rule has parameter inputs whose backtest recomputes live, a "plot" toggle
 * (draws the indicator with the same params), a "signals" toggle (▲ buy / ▼ sell markers on the chart, via a
 * custom-indicator draw callback), and a "notes" toggle (preloaded explanation of the buy/sell logic and why).
 *
 * Plus (SPX/NDX): a technical-indicator SIGNAL DASHBOARD (signals_{spx,ndx}.json — A–D graded by backtested edge,
 * live 0–100 strength, composite → suggested leverage, show-on-chart, view-backtest) and a one-click ANALYST
 * (live bundle of signals + official signal + news + the current chart view + a screenshot → quant report +
 * copy-prompt/worker; shared brain analyst_prompt.md). Drawing adds free-draw→Enhance shapes, rectangle/circle,
 * an erase tool (click or box-select), notes that link to + move with a drawing, and a full price-alert system
 * (on-chart 🔔 markers, a managed Price-alerts section, edit/rename/delete/drag, right-click-to-set anywhere,
 * trend/ray line-following). Overlays carry stable ids so links/alerts survive applyNewData + reload.
 * See docs/website.md (Charts) and docs/oneclick-analyst.md.
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
  let ALERT_LINES = []; // [{value,label}] active price-alert levels, drawn on the chart by the ALERTLINE indicator
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]; // UK date format dd-MMM-yy
  const p2 = (n) => String(n).padStart(2, "0");
  function ukTs(ts, withTime) { const d = new Date(ts); if (!isFinite(d.getTime())) return ""; const s = p2(d.getDate()) + "-" + MON[d.getMonth()] + "-" + String(d.getFullYear()).slice(-2); return withTime ? s + " " + p2(d.getHours()) + ":" + p2(d.getMinutes()) : s; }
  const ukClock = (ts) => { try { return new Date(ts == null ? Date.now() : ts).toLocaleTimeString("en-GB", { timeZone: "Europe/London", hour: "2-digit", minute: "2-digit", second: "2-digit" }); } catch (_) { return ""; } }; // wall-clock time in UK (Europe/London), correct regardless of the viewer's own timezone
  function ukd(str) { if (!str) return ""; const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(str); return m ? p2(+m[3]) + "-" + MON[+m[2] - 1] + "-" + m[1].slice(-2) : str; } // "YYYY-MM-DD" → "dd-MMM-yy"
  function isoOf(ts) { const d = new Date(ts); return d.getFullYear() + "-" + p2(d.getMonth() + 1) + "-" + p2(d.getDate()); }
  const UP = "#15803d", DN = "#b42318";
  const TRANSP = "rgba(0,0,0,0)"; // KLineChart's built-in candle bars are hidden in Bars mode; the HLOC indicator draws symmetric H/L/O/C bars instead
  let BAR_MODE = true; // true ⇒ "Bars" (ohlc) type active ⇒ the HLOC indicator renders
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
    recessions: ["Recession shading (NBER)", "The grey bands mark official <b>U.S. recessions</b> as dated by the National Bureau of Economic Research — the standard arbiter. A recession is a broad, sustained fall in economic activity (not just 'two negative GDP quarters'): 1973-75, 1980-82, 1990-91, 2001, 2008-09, 2020, etc.<br><br><b>Why it's here:</b> to put price in context — you can see at a glance how this asset behaved going <b>into</b>, <b>during</b>, and <b>out of</b> each downturn.<br><br><b>What to expect:</b> markets lead the economy by roughly <b>6 months</b>, so equities usually <b>top out before</b> a recession is officially declared and <b>bottom before it ends</b> — the worst of the drawdown tends to sit in the <b>first half</b> of a grey band. Defensive assets (long bonds, gold) and trend-following / move-to-cash strategies tend to do best here. Turn on the amber <b>Inversions</b> too — they usually appear a year or more <i>before</i> the grey bands, as the early warning."],
    inversions: ["Yield-curve inversion", "Normally a longer bond yields <b>more</b> than a shorter one — you demand extra to lock your money up for longer, so the yield curve slopes <b>up</b>. An <b>inversion</b> is when that flips: short-term yields rise <b>above</b> long-term yields (e.g. the 2-year yields more than the 10-year, or the 3-month more than the 10-year). The amber bands mark periods when the <b>2s10s</b> or <b>3m10y</b> spread was negative.<br><br><b>Why it matters:</b> an inverted curve is the market betting the central bank has hiked rates so high it will be forced to <b>cut</b> them later — i.e. a slowdown is coming. It's the most reliable <b>recession predictor</b> in modern history: the curve has inverted before <i>every</i> U.S. recession since the 1960s, typically <b>12–18 months ahead</b>.<br><br><b>What to expect:</b> an inversion is <b>not a sell signal by itself</b> — equities often keep climbing for many months after it first inverts. The historically dangerous moment is when the curve <b>re-steepens back above zero</b> (the 'un-inversion'), which often coincides with the recession actually starting and the deepest equity drawdown. Compare the amber inversion bands with the grey recession bands to see that lead-lag for yourself."],
  };
  const MAIN_SET = new Set(MAIN_INDS.map(([v]) => v));
  const DEFAULTS = { MA: [5, 10, 30, 60], EMA: [6, 12, 20], SMA: [12, 2], BOLL: [20, 2], BBI: [3, 6, 12, 24], SAR: [2, 2, 20],
    VOL: [5, 10, 20], MACD: [12, 26, 9], RSI: [14], KDJ: [9, 3, 3], CCI: [13], WR: [6, 10, 14], DMI: [14, 6], OBV: [30],
    ROC: [12, 6], TRIX: [12, 9], BIAS: [6, 12, 24], MTM: [6, 10], PSY: [12, 6], BRAR: [26], CR: [26, 10, 20, 40, 60],
    VR: [24, 30], EMV: [14, 9], DMA: [10, 50, 10], AO: [5, 34], PVT: [] };
  const TOOLS = [
    ["cursor", "Cursor"], ["erase", "🗑 Erase"], ["segment", "Trend line"], ["rayLine", "Ray"], ["horizontalStraightLine", "Horizontal"],
    ["verticalStraightLine", "Vertical"], ["priceLine", "Price line"], ["parallelStraightLine", "Parallel"],
    ["fibonacciLine", "Fibonacci"], ["noteText", "Note"], ["measurePct", "Measure %"],
    ["freeDraw", "✎ Free draw"], ["rectShape", "▭ Rectangle"], ["circleShape", "◯ Circle"],
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
    try {   // freehand stroke (drawn via the capture layer, then right-click → enhance into a shape)
      klinecharts.registerOverlay({
        name: "freeDraw", totalStep: 2, needDefaultPointFigure: false, needDefaultXAxisFigure: false, needDefaultYAxisFigure: false,
        createPointFigures: ({ coordinates }) => (coordinates.length < 2 ? [] : [{ type: "line", attrs: { coordinates }, styles: { color: "#0071e3", size: 2 } }]),
      });
    } catch (_) {}
    try {   // rectangle / square (two opposite corners)
      klinecharts.registerOverlay({
        name: "rectShape", totalStep: 3, needDefaultPointFigure: true, needDefaultXAxisFigure: true, needDefaultYAxisFigure: true,
        createPointFigures: ({ coordinates }) => {
          if (coordinates.length < 2) return [];
          const a = coordinates[0], b = coordinates[1], x = Math.min(a.x, b.x), y = Math.min(a.y, b.y), w = Math.max(1, Math.abs(b.x - a.x)), h = Math.max(1, Math.abs(b.y - a.y));
          return [{ type: "rect", attrs: { x, y, width: w, height: h }, styles: { style: "stroke_fill", color: "rgba(0,113,227,.05)", borderColor: "#0071e3", borderSize: 1.5 } }];
        },
      });
    } catch (_) {}
    try {   // circle (centre + edge → pixel radius)
      klinecharts.registerOverlay({
        name: "circleShape", totalStep: 3, needDefaultPointFigure: true, needDefaultXAxisFigure: true, needDefaultYAxisFigure: true,
        createPointFigures: ({ coordinates }) => {
          if (coordinates.length < 2) return [];
          const a = coordinates[0], b = coordinates[1], r = Math.max(1, Math.hypot(b.x - a.x, b.y - a.y));
          return [{ type: "circle", attrs: { x: a.x, y: a.y, r }, styles: { style: "stroke_fill", color: "rgba(0,113,227,.05)", borderColor: "#0071e3", borderSize: 1.5 } }];
        },
      });
    } catch (_) {}
    try {
      klinecharts.registerIndicator({   // symmetric HLOC bars — KLineChart's built-in ohlc draws a stunted close tick; we draw H/L line + equal-length open(left)/close(right) ticks
        name: "HLOC", figures: [], calc: (dataList) => dataList.map(() => ({})),
        draw: ({ ctx, kLineDataList, visibleRange, xAxis, yAxis }) => {
          if (!BAR_MODE) return false;
          const from = Math.max(0, visibleRange.from), to = visibleRange.to; if (to - from < 1) return false;
          let pitch = 6; if (to - from >= 2) pitch = Math.abs(xAxis.convertToPixel(from + 1) - xAxis.convertToPixel(from)) || pitch;
          const tick = Math.max(1, Math.min(pitch * 0.42, 11));            // open/close tick length, each side, symmetric — capped so it never spills into the neighbour
          const lw = pitch >= 5 ? Math.min(Math.max(Math.round(pitch * 0.12), 1), 2.5) : 1; // high-low line thickness
          const thin = lw <= 1; ctx.lineCap = "butt"; ctx.setLineDash([]); // clear any dash left on the shared ctx by a prior indicator (ALERTLINE/RSI)
          for (let i = from; i < to; i++) {
            const d = kLineDataList[i]; if (!d) continue;
            const x = xAxis.convertToPixel(i);
            const xc = thin ? Math.round(x) + 0.5 : x;                     // crisp 1px line on a half-pixel
            const yH = yAxis.convertToPixel(d.high), yL = yAxis.convertToPixel(d.low);
            const yO = thin ? Math.round(yAxis.convertToPixel(d.open)) + 0.5 : yAxis.convertToPixel(d.open);
            const yC = thin ? Math.round(yAxis.convertToPixel(d.close)) + 0.5 : yAxis.convertToPixel(d.close);
            ctx.strokeStyle = d.close > d.open ? UP : (d.close < d.open ? DN : "#888"); ctx.lineWidth = lw;
            ctx.beginPath(); ctx.moveTo(xc, yH); ctx.lineTo(xc, yL); ctx.stroke();        // high → low
            ctx.beginPath(); ctx.moveTo(xc - tick, yO); ctx.lineTo(xc, yO); ctx.stroke();  // open tick (left)
            ctx.beginPath(); ctx.moveTo(xc, yC); ctx.lineTo(xc + tick, yC); ctx.stroke();  // close tick (right)
          }
          return false;
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
    try {
      klinecharts.registerIndicator({
        name: "ALERTLINE", figures: [], calc: (dataList) => dataList.map(() => ({})),
        draw: ({ ctx, bounding, yAxis }) => {
          if (!ALERT_LINES.length) return false;
          const W = (bounding && bounding.width) || 0;
          ALERT_LINES.forEach((a) => {
            const y = yAxis.convertToPixel(a.value); if (!isFinite(y)) return;
            ctx.strokeStyle = "rgba(214,138,18,0.55)"; ctx.setLineDash([5, 4]); ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(a.sloped ? W * 0.55 : 0, y); ctx.lineTo(W, y); ctx.stroke(); ctx.setLineDash([]);
            const tag = "🔔 " + a.label + (a.sloped ? " ↗" : "");
            ctx.font = "11px -apple-system,sans-serif"; ctx.textAlign = "right"; ctx.textBaseline = "middle";
            const tw = ctx.measureText(tag).width + 12;
            ctx.fillStyle = "#d68a12"; ctx.fillRect(W - tw - 3, y - 9, tw, 18);
            ctx.fillStyle = "#fff"; ctx.fillText(tag, W - 9, y);
          });
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
      .chart-card{margin-top:4px;padding-top:8px;padding-bottom:8px;}
      .ctrlbar{gap:6px 14px;margin:2px 0 6px;}
      .ctrlbar .lbl{margin-right:4px;}
      .ctrlbar .seg button{padding:4px 9px;font-size:11.5px;}
      .ctrlbar select{padding:5px 9px;font-size:13px;max-width:168px;}
      .ctrlbar .live{margin-left:6px;}
      .chart-card details.ind-panel{margin:3px 0;padding:0 12px;}
      .chart-card details.ind-panel summary{padding:6px 0;font-size:12px;}
      .dsig-arrow{display:inline-block;transition:transform .15s ease;}
      details.dsig[open] .dsig-arrow{transform:rotate(180deg);}
      .dw-swatches{display:flex;gap:6px;padding:8px 14px 4px;flex-wrap:wrap;align-items:center;}
      .dw-swatch{width:18px;height:18px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 0 1px var(--line);cursor:pointer;padding:0;}
      .dw-swatch:hover{transform:scale(1.15);}
      .alert-row.tracked{background:rgba(214,138,18,.10);border-left:3px solid #d68a12;}
      #chart{width:100%;height:clamp(460px,74vh,840px);border:1px solid var(--line);border-radius:12px;overflow:hidden;}
      @media(max-width:680px){#chart{height:68vh;}}
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
      .dash-comp{display:flex;gap:18px;flex-wrap:wrap;align-items:stretch;border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin:8px 0 14px;background:rgba(255,255,255,.6);}
      .dash-state{flex:1;min-width:230px;}
      .dash-lev{text-align:right;min-width:140px;display:flex;flex-direction:column;justify-content:center;}
      .dash-lev .big{font-size:46px;font-weight:800;line-height:1;color:#1d1d1f;font-variant-numeric:tabular-nums;}
      .dash-net{height:8px;border-radius:999px;background:#ececf0;position:relative;margin:9px 0 5px;}
      .dash-net .fill{position:absolute;height:8px;border-radius:999px;}
      .dash-net .mid{position:absolute;left:50%;top:-3px;width:1px;height:14px;background:#c7c7cc;}
      .dsig{border-bottom:1px solid var(--line);padding:10px 2px;}
      .dsig>summary{display:flex;align-items:center;gap:12px;cursor:pointer;list-style:none;}
      .dsig>summary::-webkit-details-marker{display:none;}
      .dsig>summary:hover{background:rgba(0,0,0,.018);}
      .dgrade{font-size:11.5px;font-weight:800;width:22px;height:22px;border-radius:999px;display:inline-flex;align-items:center;justify-content:center;flex:none;}
      .dbar{height:6px;border-radius:999px;background:#ececf0;overflow:hidden;}
      .dbar i{display:block;height:6px;border-radius:999px;}
      .dbtn{font:inherit;font-size:12px;font-weight:600;padding:6px 11px;border-radius:999px;border:1px solid var(--line);background:#fff;color:#48484a;cursor:pointer;}
      .dbtn:hover:not(:disabled){border-color:var(--accent);}
      .dbtn.on{background:var(--accent);color:#fff;border-color:var(--accent);}
      .dbtn:disabled{opacity:.4;cursor:default;}
      @media(max-width:680px){.dash-lev{text-align:left;min-width:0;}.dsig>summary{flex-wrap:wrap;}}
      .alert-row{display:flex;align-items:center;gap:11px;padding:10px 2px;border-bottom:1px solid var(--line);flex-wrap:wrap;}
      .alert-row .a-bell{color:#d68a12;font-size:16px;flex:none;}
      .alert-row .a-acts{margin-left:auto;display:flex;gap:6px;}
      .alert-row .a-acts button{font:inherit;font-size:12px;font-weight:600;padding:5px 11px;border-radius:999px;border:1px solid var(--line);background:#fff;color:#48484a;cursor:pointer;}
      .alert-row .a-acts button:hover{border-color:var(--accent);}
      .alert-row .a-acts button.del:hover{border-color:var(--bad);color:var(--bad);}
      .alert-row input.a-edit{font:inherit;font-size:13px;padding:5px 9px;border-radius:8px;border:1px solid var(--accent);width:130px;}
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
    const state = { asset: "spx", tf: "D", dispAggMs: 0, type: "ohlc", yAxis: "normal", tool: "cursor", tfLastTs: 0,
      indicators: Object.fromEntries(MAIN_INDS.concat(SUB_INDS).map(([v]) => [v, false])),
      indParams: Object.fromEntries(Object.entries(DEFAULTS).map(([k, v]) => [k, v.slice()])),
      stratParams: Object.fromEntries(STRATS.map((s) => [s.key, Object.fromEntries(s.params.map((q) => [q.k, q.d]))])),
      plotted: {}, signalKey: null, notesOpen: {}, curClose: [], curTs: [], curHigh: [], curLow: [],
      lev: { mult: 1, ddThr: -10, volThr: 18, costs: false }, pnl: { mode: "bps", perBp: 0 }, recession: false, inversion: false, carry: false,
      grid: "both", decimals: "auto", ylab: "out", crosshair: true, autoTA: false, studySig: null, drawingsHidden: false, alertsHidden: false };
    const D = { id: "", ticker: "", label: "", kind: "price", klass: "", legs: null, cr: null, dv01: 1, n: 0, dates: [], close: [], high: [], low: [], daily: [], ddh: [], rv: [] };
    let chart = null, ASSETS = [], drawings = [], saveTimer = null, restoring = false, pollTimer = null, LEADER = [], CURVE = [], pendingBest = null;

    const app = document.getElementById("app");
    app.innerHTML = `
      <div class="card chart-card">
        <div class="cbar ctrlbar">
          <div><span class="lbl">Asset</span><select id="assetSel"></select></div>
          <div><span class="lbl">TF</span><span class="seg" id="tfSeg"></span></div>
          <div><span class="lbl">Type</span><span class="seg" id="typeSeg"></span></div>
          <div><span class="lbl">Axis</span><span class="seg" id="axisSeg"></span></div>
          <div><span class="lbl">Range</span><span class="seg" id="rangeSeg"></span>
            <span style="display:inline-flex;align-items:center;gap:4px;margin-left:6px;font-size:12px;color:#6e6e73">
              <input id="rngFrom" type="date" style="font:inherit;font-size:12px;padding:3px 6px;border-radius:7px;border:1px solid var(--line)">
              <span>→</span>
              <input id="rngTo" type="date" style="font:inherit;font-size:12px;padding:3px 6px;border-radius:7px;border:1px solid var(--line)">
              <button id="rngApply" class="seg" style="padding:4px 10px">Go</button>
            </span></div>
          <div class="live" id="live"><span class="dot"></span><span id="liveTxt">live —</span></div>
          <button id="cloudBtnTop" class="seg" style="padding:5px 12px;font-weight:600" title="Your notes, drawings, indicators &amp; alerts auto-save in this browser. Click to sync them to the cloud (cross-device) — auto-syncs after sign-in.">☁ Save</button>
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
        <details class="ind-panel" id="drawPanel">
          <summary>Draw &amp; tools — drawing tools · undo · clear · auto-analysis · recessions · inversions · show/hide drawings &amp; alerts</summary>
          <div class="ind-grp"><span class="lbl">Draw</span><span class="seg" id="toolSeg"></span></div>
          <div class="ind-grp"><div class="seg"><button id="undoBtn">Undo</button><button id="clearBtn">Clear all</button><button id="autoBtn">⚡ Auto-analysis</button><button id="recBtn" title="Shade US recessions · right-click: what they are &amp; what to expect"><span style="color:#9a9aa2">▦</span> Recessions</button><button id="invBtn" title="Shade yield-curve inversions · right-click: what an inversion means &amp; what to expect"><span style="color:#d68a12">⊘</span> Inversions</button><button id="drawToggle" class="active" title="Show or hide all your drawings">👁 Drawings</button><button id="alertToggle" class="active" title="Show or hide price-alert markers on the chart (alerts still fire)">🔔 Alerts</button></div></div>
        </details>
        <div id="chart"></div>
        <p class="meta" id="hint" style="margin-top:8px">Scroll to zoom · drag to pan · pick a draw tool then click points · <b>✎ Free draw</b> to sketch freehand, then <b>right-click → Enhance</b> to snap it into a clean circle / square / rectangle / trend / ray / channel · <b>🗑 Erase</b> tool: click a drawing to delete it, or drag a box to erase everything inside · <b>right-click the chart</b> to set a price alert at that level (or add a note) · <b>right-click any drawing</b> to enhance / erase / set a price alert / <b>📝 Attach a linked note</b> that moves with it · hover a drawing and press <b>Delete</b> to remove it.</p>
        <details id="autoCard" class="ind-panel" style="display:none;margin-top:8px">
          <summary>Auto-analysis notes — trend lines, Fibonacci &amp; signals · click to expand</summary>
          <div id="autoNotes" style="font-size:13px;line-height:1.6"></div>
        </details>
      </div>
      <div class="card" id="alertCard" style="display:none">
        <h2 style="margin-bottom:2px">Price alerts <span class="meta" id="alertCount" style="font-weight:400"></span></h2>
        <p class="meta" style="margin-top:4px">Alerts set on your drawings — a toast + beep fires when price crosses the level (while this tab is open). The level is marked on the chart with a 🔔. Edit or delete here, or by right-clicking the drawing.</p>
        <div id="alertList"></div>
      </div>
      <div class="card" id="dashCard" style="display:none">
        <h2 style="margin-bottom:2px">Signal dashboard <span class="meta" id="dashAsof" style="font-weight:400"></span></h2>
        <p class="meta" style="margin-top:4px">Each indicator is graded by its <b>backtested edge</b> vs buy &amp; hold (<b>A</b> strong → <b>D</b> weak), and the <b>strength</b> bar shows how hard it's firing right now. The composite is a trust-weighted read of all signals → an <b>independent suggested leverage</b>. Click a row for the evidence, to plot it on the chart, or to open its backtest. Educational only — not advice.</p>
        <div style="margin:2px 0 10px"><button id="analystBtn" style="font:inherit;font-size:13.5px;font-weight:700;padding:10px 16px;border-radius:11px;border:0;background:#1d1d1f;color:#fff;cursor:pointer">🧠 Run one-click Analyst — full read + action plan</button></div>
        <div id="dashComposite"></div>
        <div id="dashList"></div>
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
        <div class="notes-row"><span class="meta" id="cloudAuth"></span></div>
        <textarea id="notes" rows="5" placeholder="Your private notes for this asset (auto-saved in this browser; ☁ Save at the top syncs cross-device)…"></textarea>
        <p class="meta" style="margin-top:8px">Your notes, drawings, indicators &amp; alerts are <b>private</b> and <b>auto-saved</b> per asset — instantly in this browser, and synced to the cloud automatically once you’ve signed in via <b>☁ Save</b> (top right).</p>
      </div>`;

    const $ = (id) => document.getElementById(id);
    const segActive = (c, b) => c.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
    const findBtn = (c, v) => [...c.querySelectorAll("button")].find((b) => b.dataset.v === v);
    function makeSeg(host, items, isActive, onPick, cls) { host.innerHTML = ""; items.forEach(([val, label]) => { const b = document.createElement("button"); if (cls) b.className = cls; b.textContent = label; b.dataset.v = val; if (isActive(val)) b.classList.add("active"); b.onclick = () => onPick(val, b); host.appendChild(b); }); }
    function safe(fn) { try { return fn(); } catch (e) { status("error: " + (e.message || e)); } }

    chart = klinecharts.init($("chart")); window.__chart = chart;   // expose the instance (harmless) — aids debugging the headless-canvas paths
    chart.setStyles({
      grid: { horizontal: { color: "#eee" }, vertical: { color: "#f4f4f4" } },
      candle: { type: state.type, bar: { upColor: UP, downColor: DN, noChangeColor: "#888", upBorderColor: UP, downBorderColor: DN, upWickColor: UP, downWickColor: DN }, priceMark: { last: { show: true }, high: { show: true }, low: { show: true } }, tooltip: { showRule: "always", showType: "rect" } },
      indicator: { lastValueMark: { show: false } }, yAxis: { type: state.yAxis }, xAxis: { tickText: { color: "#8a8a8e" } },
    });
    // KLineChart's formatDate is positional (dateTimeFormat, timestamp, …) — find the epoch-ms arg robustly.
    safe(() => chart.setCustomApi({ formatDate: function () { var ts = null; for (var i = 0; i < arguments.length; i++) { var a = arguments[i]; if (typeof a === "number" && a > 1e11) { ts = a; break; } if (a && typeof a === "object" && typeof a.timestamp === "number") { ts = a.timestamp; break; } } return ts == null ? "" : ukTs(ts, state.tf !== "D"); } }));
    $("chart").addEventListener("contextmenu", (ev) => { ev.preventDefault(); setTimeout(() => { if (drawMenuEl) return; if (showAlertMenuAt(ev)) return; showEmptyMenu(); }, 0); }); // right-click: overlay menu → alert marker → empty = set-alert / note menu
    window.addEventListener("resize", () => chart && chart.resize());
    setTimeout(() => chart && chart.resize(), 60);

    makeSeg($("tfSeg"), TFS.map((t) => [t.id, t.label]), (v) => v === state.tf, (v, b) => { state.tf = v; segActive($("tfSeg"), b); applyTF(); });
    function applyBarMode() {   // Bars (ohlc) ⇒ hide KLineChart's built-in candle bars + draw symmetric HLOC via the indicator; Candles/Area ⇒ restore real colours, drop the indicator
      BAR_MODE = state.type === "ohlc";
      const bar = BAR_MODE
        ? { upColor: TRANSP, downColor: TRANSP, noChangeColor: TRANSP, upBorderColor: TRANSP, downBorderColor: TRANSP, noChangeBorderColor: TRANSP, upWickColor: TRANSP, downWickColor: TRANSP, noChangeWickColor: TRANSP }
        : { upColor: UP, downColor: DN, noChangeColor: "#888", upBorderColor: UP, downBorderColor: DN, upWickColor: UP, downWickColor: DN };
      safe(() => chart.setStyles({ candle: { type: state.type, bar } }));
      safe(() => { chart.removeIndicator("candle_pane", "HLOC"); if (BAR_MODE) chart.createIndicator("HLOC", true, { id: "candle_pane" }); }); // remove-then-add so repeated calls (asset switches) never stack duplicate HLOC instances
    }
    makeSeg($("typeSeg"), TYPES, (v) => v === state.type, (v, b) => { state.type = v; applyBarMode(); segActive($("typeSeg"), b); scheduleSave(); });
    applyBarMode();   // forced to Bars on load — install the HLOC renderer immediately
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
      if (id === "inversions") return wrap(`<text x="160" y="15" font-size="9.5" fill="#6e6e73" text-anchor="middle">the yield curve: yield (↑) vs maturity (→)</text><path d="M30,98 C95,84 210,58 300,44" fill="none" stroke="#9a9aa2" stroke-width="2.2"/><text x="298" y="40" font-size="9" fill="#9a9aa2" text-anchor="end">normal — long &gt; short</text><path d="M30,52 C95,66 210,92 300,104" fill="none" stroke="#d68a12" stroke-width="2.2"/><text x="298" y="116" font-size="9" fill="#d68a12" text-anchor="end">inverted — short &gt; long</text><text x="30" y="126" font-size="8.5" fill="#8a8a8e">3M</text><text x="292" y="126" font-size="8.5" fill="#8a8a8e">30Y →</text>`);
      if (id === "recessions") return wrap(`<rect x="142" y="16" width="74" height="104" fill="rgba(110,110,120,0.16)"/><text x="179" y="28" font-size="9" fill="#6e6e73" text-anchor="middle">recession</text><path d="M20,88 C70,64 110,42 142,40 C152,39 160,54 179,86 C194,110 208,96 234,74 C262,50 286,40 300,36" fill="none" stroke="#0071e3" stroke-width="2"/><path d="M135,40 l-6,-9 l12,0 z" fill="${dn}"/><text x="118" y="32" font-size="8.5" fill="${dn}" text-anchor="middle">tops first</text><path d="M179,90 l-5,9 l10,0 z" fill="${up}"/><text x="179" y="116" font-size="8.5" fill="${up}" text-anchor="middle">bottoms inside</text>`);
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
    $("recBtn").onclick = () => { state.recession = !state.recession; $("recBtn").classList.toggle("active", state.recession); if (state.recession) status("Grey = NBER US recessions · right-click for what to expect"); safe(() => { if (state.recession) chart.createIndicator("RECESSION", true, { id: "candle_pane" }); else chart.removeIndicator("candle_pane", "RECESSION"); }); };
    $("invBtn").onclick = () => { state.inversion = !state.inversion; $("invBtn").classList.toggle("active", state.inversion); if (state.inversion) status("Amber = yield-curve inversions (recession warning) · right-click to learn more"); safe(() => { if (state.inversion) chart.createIndicator("INVERSION", true, { id: "candle_pane" }); else chart.removeIndicator("candle_pane", "INVERSION"); }); };
    $("recBtn").oncontextmenu = (e) => { e.preventDefault(); showIndHelp("recessions"); };
    $("invBtn").oncontextmenu = (e) => { e.preventDefault(); showIndHelp("inversions"); };
    $("drawToggle").onclick = () => { state.drawingsHidden = !state.drawingsHidden; const show = !state.drawingsHidden; $("drawToggle").classList.toggle("active", show); if (show) reapplyDrawings(); else safe(() => chart.removeOverlay()); status(show ? "drawings shown" : "all drawings hidden"); };
    $("alertToggle").onclick = () => { state.alertsHidden = !state.alertsHidden; const show = !state.alertsHidden; $("alertToggle").classList.toggle("active", show); refreshAlertLines(); status(show ? "price-alert markers shown" : "alert markers hidden (alerts still fire)"); };
    // ---- Auto-analysis: swing pivots → support/resistance trend lines + Fibonacci + buy/sell signals, all with notes ----
    let autoIds = [];
    function clearAutoTA() { autoIds.forEach((id) => safe(() => chart.removeOverlay(id))); autoIds = []; AUTO_SIG = { buys: new Set(), sells: new Set() }; safe(() => chart.removeIndicator("candle_pane", "AUTOTA")); $("autoCard").style.display = "none"; $("autoNotes").innerHTML = ""; }
    function computeAutoTA() {
      const daily = D.daily || []; if (daily.length < 60) return null;
      const seg = daily.slice(Math.max(0, daily.length - 300)); // ~14 months of daily bars
      const N = seg.length, hi = seg.map((b) => b.high), lo = seg.map((b) => b.low), cl = seg.map((b) => b.close), ts = seg.map((b) => b.timestamp);
      const range = Math.max(...hi) - Math.min(...lo) || 1, tol = range * 0.012; // ~1.2% of range = a "touch"
      const pivotsOf = (vals, isHigh) => { const k = 5, p = []; for (let i = k; i < N - k; i++) { let ext = true; for (let j = i - k; j <= i + k; j++) { if (j === i) continue; if (isHigh ? vals[j] >= vals[i] : vals[j] <= vals[i]) { ext = false; break; } } if (ext) p.push(i); } return p; };
      const ph = pivotsOf(hi, true), pl = pivotsOf(lo, false);
      // Best-fit trend lines: score every pivot-pair line by touches + non-violation + length + recency, keep the top 2 distinct.
      function fit(piv, vals, isRes) {
        if (piv.length < 2) return [];
        const cand = [];
        for (let a = 0; a < piv.length - 1; a++) for (let b = a + 1; b < piv.length; b++) {
          const i1 = piv[a], i2 = piv[b]; if (i2 - i1 < 10) continue;
          const slope = (vals[i2] - vals[i1]) / (i2 - i1), at = (x) => vals[i1] + slope * (x - i1);
          let viol = 0, touches = 0;
          for (let x = i1; x < N; x++) { const d = vals[x] - at(x); if (isRes ? d > tol * 1.5 : d < -tol * 1.5) viol++; }
          for (const pp of piv) if (pp >= i1 && Math.abs(vals[pp] - at(pp)) <= tol) touches++;
          if (viol > N * 0.05) continue;
          cand.push({ i1, i2, slope, at, touches, score: touches * 3 + (i2 / N) * 2 + (i2 - i1) / N + (viol === 0 ? 1.5 : 0) });
        }
        cand.sort((x, y) => y.score - x.score);
        const out = [];
        for (const c of cand) { if (out.some((o) => Math.abs(o.at(N - 1) - c.at(N - 1)) < tol * 3 && Math.abs(o.slope - c.slope) < (range / N) * 0.4)) continue; out.push(c); if (out.length >= 2) break; }
        return out.map((c) => ({ kind: isRes ? "resistance" : "support", touches: c.touches, slope: c.slope, at: c.at, i1: c.i1, i2: c.i2, p0: { timestamp: ts[c.i1], value: vals[c.i1] }, p1: { timestamp: ts[c.i2], value: vals[c.i2] }, d0: ts[c.i1], d1: ts[c.i2] }));
      }
      const resLines = fit(ph, hi, true), supLines = fit(pl, lo, false), tl = resLines.concat(supLines);
      // Channel: take the strongest line and project a parallel rail to the farthest opposite extreme.
      let channel = null;
      const best = (resLines[0] && (!supLines[0] || resLines[0].touches >= supLines[0].touches)) ? resLines[0] : supLines[0];
      if (best) {
        const opp = best.kind === "resistance" ? lo : hi, sign = best.kind === "resistance" ? -1 : 1; let off = 0;
        for (let x = best.i1; x < N; x++) { const dd = sign * (opp[x] - best.at(x)); if (dd > off) off = dd; }
        if (off > range * 0.05) channel = { kind: best.kind, width: off, p0: { timestamp: ts[best.i1], value: best.at(best.i1) + sign * off }, p1: { timestamp: ts[best.i2], value: best.at(best.i2) + sign * off } };
      }
      let Hi = 0, Lo = 0; for (let i = 0; i < N; i++) { if (hi[i] > hi[Hi]) Hi = i; if (lo[i] < lo[Lo]) Lo = i; }
      const dir = Hi > Lo ? "up" : "down", hiV = hi[Hi], loV = lo[Lo], span = hiV - loV || 1;
      const levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1].map((r) => ({ r, v: dir === "up" ? hiV - span * r : loV + span * r }));
      const mid = levels[3].v, sig = [];
      for (let i = Math.max(Hi, Lo) + 1; i < N; i++) { if (cl[i - 1] <= mid && cl[i] > mid) sig.push({ ts: ts[i], type: "buy" }); else if (cl[i - 1] >= mid && cl[i] < mid) sig.push({ ts: ts[i], type: "sell" }); }
      return { tl, channel, dir, hiV, loV, hiTs: ts[Hi], loTs: ts[Lo], levels, sig: sig.slice(-6) };
    }
    function applyAutoTA() {
      clearAutoTA();
      const a = computeAutoTA(); if (!a) { status("not enough data for auto-analysis"); return; }
      // trend lines as forward-projecting RAYS (rayLine extends through p1 into the future)
      a.tl.forEach((t) => { const col = t.kind === "resistance" ? DN : UP; const id = safe(() => chart.createOverlay({ name: "rayLine", points: [t.p0, t.p1], lock: true, styles: { line: { color: col, size: 2 } } })); if (id) autoIds.push(id); });
      if (a.channel) { const col = a.channel.kind === "resistance" ? DN : UP; const id = safe(() => chart.createOverlay({ name: "rayLine", points: [a.channel.p0, a.channel.p1], lock: true, styles: { line: { color: col, size: 1, style: "dashed" } } })); if (id) autoIds.push(id); }
      const fid = safe(() => chart.createOverlay({ name: "fibonacciLine", points: [{ timestamp: a.dir === "up" ? a.loTs : a.hiTs, value: a.dir === "up" ? a.loV : a.hiV }, { timestamp: a.dir === "up" ? a.hiTs : a.loTs, value: a.dir === "up" ? a.hiV : a.loV }], lock: true })); if (fid) autoIds.push(fid);
      AUTO_SIG = { buys: new Set(a.sig.filter((s) => s.type === "buy").map((s) => s.ts)), sells: new Set(a.sig.filter((s) => s.type === "sell").map((s) => s.ts)) };
      safe(() => { chart.removeIndicator("candle_pane", "AUTOTA"); chart.createIndicator("AUTOTA", true, { id: "candle_pane" }); });
      renderAutoNotes(a);
    }
    function renderAutoNotes(a) {
      const dec = (v) => nfmt(v), L = a.levels;
      const note = (title, body) => `<details style="border-bottom:1px solid var(--line);padding:7px 0"><summary style="cursor:pointer;font-weight:600;color:#1d1d1f">${title}</summary><div style="color:#444;margin:5px 0 2px;padding-left:4px">${body}</div></details>`;
      let html = `<p class="meta" style="margin:6px 0 8px">Detected from the last ~14 months of daily bars: best-fit support/resistance lines (ranked by touches), a channel if price is trending in one, plus Fibonacci and momentum signals. Mechanical guides — confirm with your own read.</p>`;
      a.tl.forEach((t) => { const slopeWord = t.slope > 0 ? "rising" : t.slope < 0 ? "falling" : "flat"; html += note(`${t.kind === "resistance" ? "🔻 Resistance" : "🔺 Support"} line — ${t.touches} touch${t.touches === 1 ? "" : "es"}`, `A ${slopeWord} ${t.kind} line, validated by <b>${t.touches}</b> swing ${t.kind === "resistance" ? "highs" : "lows"} from <b>${ukd(isoOf(t.d0))}</b> onward and projected forward as a ray. <b>Signal:</b> a decisive close ${t.kind === "resistance" ? "<b>above</b> it is a breakout (buy); until then it caps rallies" : "<b>below</b> it is a breakdown (sell); until then it supports dips"}. More touches = a more reliable line.`); });
      if (a.channel) html += note("📏 Channel", `Price is travelling in a <b>${a.channel.kind === "resistance" ? "descending" : "ascending"} channel</b> — the ${a.channel.kind} line with a parallel rail ${dec(a.channel.width)} away. <b>Use:</b> buy near the lower rail, sell/trim near the upper rail, and treat a clean break of either rail as the channel ending (often the start of the next trend).`);
      html += note("📐 Fibonacci retracement", `Of the dominant ${a.dir === "up" ? "up-leg" : "down-leg"} from <b>${dec(a.loV)}</b> to <b>${dec(a.hiV)}</b>. Key levels: 38.2% ${dec(L[2].v)} · 50% ${dec(L[3].v)} · 61.8% ${dec(L[4].v)}. <b>Signal:</b> in an uptrend these are pullback <b>support</b> (buy-the-dip); in a downtrend <b>resistance</b> (sell-the-rally). A bounce from 61.8% that holds is the classic continuation entry.`);
      const buys = a.sig.filter((s) => s.type === "buy"), sells = a.sig.filter((s) => s.type === "sell");
      html += note(`🟢 Buy / 🔴 Sell signals (${buys.length}/${sells.length})`, `Fire when price <b>reclaims (buy)</b> or <b>loses (sell)</b> the 50% retracement (${dec(L[3].v)}) — a simple momentum trigger. Most recent buy: ${buys.length ? ukd(isoOf(buys[buys.length - 1].ts)) : "—"}; sell: ${sells.length ? ukd(isoOf(sells[sells.length - 1].ts)) : "—"}.`);
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
      if (!tf.interval) { safe(() => { chart.applyNewData(D.daily || []); chart.resize(); }); state.dispAggMs = 0; setCur(D.daily || []); setRange(252); reapplyDrawings(); refreshSignals(); if (state.autoTA) applyAutoTA(); state.tfLastTs = 0; $("hint").innerHTML = "Daily bars · live, auto-refreshing every " + (POLL_MS / 1000) + "s · scroll to zoom · drag to pan · <b>right-click a drawing</b> to edit / erase / set a price alert · hover one and press <b>Delete</b> to remove."; extendDailyLive(); pollTimer = setInterval(() => { extendDailyLive(); fetchLive(); }, POLL_MS); return; }
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
    // Keep the daily (1D) view real-time: the committed price_<id>.json lags a few days, so merge fresh daily bars
    // (incl. today's forming bar) straight from the free quote proxy — same Yahoo source as intraday, no paid feed.
    function extendDailyLive() {
      if (D.kind !== "price" || (D.legs && D.legs.length)) return;   // UST yields / computed spreads aren't on the proxy
      fetch(QUOTE + "/?mode=intraday&symbol=" + encodeURIComponent(D.ticker) + "&interval=1d&range=3mo&_=" + Date.now()).then((r) => r.json()).then((j) => {
        if (!j || (j.ticker || "").toUpperCase() !== (D.ticker || "").toUpperCase()) return;   // ticker-match safeguard (proxy may fall back to a wrong symbol's last close)
        const live = (j.bars || []).filter((b) => b && b.close > 0); if (!live.length) return;
        const prevLastTs = D.daily.length ? D.daily[D.daily.length - 1].timestamp : 0;   // to detect a genuine NEW bar (vs only the forming bar updating)
        const byTs = new Map(D.daily.map((b) => [b.timestamp, b]));
        const dateOf = new Map(D.daily.map((b, i) => [b.timestamp, D.dates[i]]));
        const changed = [];
        for (const b of live) {
          const bar = { timestamp: b.timestamp, open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume || 0 };
          const ex = byTs.get(b.timestamp);
          if (!ex) { byTs.set(b.timestamp, bar); dateOf.set(b.timestamp, isoOf(b.timestamp)); changed.push(bar); }
          else if (ex.close !== bar.close || ex.high !== bar.high || ex.low !== bar.low || ex.open !== bar.open) { byTs.set(b.timestamp, bar); changed.push(bar); }
        }
        if (!changed.length) return;
        const merged = [...byTs.values()].sort((a, b) => a.timestamp - b.timestamp);
        D.daily = merged; D.n = merged.length;
        D.dates = merged.map((b) => dateOf.get(b.timestamp) || isoOf(b.timestamp));
        D.close = merged.map((b) => b.close); D.high = merged.map((b) => b.high); D.low = merged.map((b) => b.low);
        D.ddh = ddFromHigh(D.close, 252); D.rv = rvol(D.close, 20);
        const c = ASSET_CACHE[D.id]; if (c) { c.dates = D.dates; c.timestamp = merged.map((b) => b.timestamp); c.open = merged.map((b) => b.open); c.high = D.high; c.low = D.low; c.close = D.close; c.volume = merged.map((b) => b.volume); }
        if (state.tf === "D") {
          changed.sort((a, b) => a.timestamp - b.timestamp).forEach((b) => safe(() => chart.updateData(b))); setCur(merged); refreshSignals();
          // a genuinely NEW bar shifts the data length → re-anchor drawings to the now-current dataset so trend lines don't
          // jump on reload (their saved timestamps re-resolve against the same bars they were drawn on). Skip mid-draw / menu-open.
          const appended = merged.length && merged[merged.length - 1].timestamp > prevLastTs;
          if (appended && drawings.length && pendingOverlayId == null && !drawMenuEl) reapplyDrawings();
        }
        renderPlaybook();
      }).catch(() => {});
    }

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
    let pendingOverlayId = null, drawMenuEl = null, lastMouse = { x: 120, y: 120 }, hoverOverlayId = null, selOverlayId = null, ALERTS = [], pendingLink = null, rearmTool = null;
    document.addEventListener("mousemove", (e) => { lastMouse = { x: e.clientX, y: e.clientY }; });
    // Right-click while a draw tool is armed: cancel the in-progress (sticky) draw BEFORE KLineChart consumes the
    // right-click — otherwise the first right-click on an existing drawing just cancels the pending draw and the
    // menu doesn't open. We re-arm the tool when the menu closes (closeDrawMenu) so sticky drawing still works.
    $("chart").addEventListener("pointerdown", (e) => {
      if (e.button !== 2 || pendingOverlayId == null) return;
      safe(() => chart.removeOverlay(pendingOverlayId)); pendingOverlayId = null;
      const t = state.tool; if (t !== "cursor" && t !== "erase" && t !== "freeDraw") rearmTool = t;
    }, true);
    // every overlay: right-click → edit/erase/alert menu; track hover + selection so the Delete key can remove it
    function mkOverlay(spec) {
      const oid = spec.id || ("dw_" + Date.now().toString(36) + "_" + Math.floor(Math.random() * 1e9).toString(36));   // stable, unique → survives reapply so note↔drawing links hold
      const colorStyles = spec.color ? { styles: overlayColorStyles(spec.color) } : {};   // restore a custom colour on (re)create
      return safe(() => chart.createOverlay({ ...spec, ...colorStyles, id: oid,
        needDefaultXAxisFigure: false, needDefaultYAxisFigure: false,   // suppress the blue per-endpoint date/price tags on the axes (they overlap into unreadable blocks for 2-point lines)
        onClick: (e) => { if (state.tool === "erase") { eraseOverlay(e.overlay); status("🗑 erased"); return true; } return false; },
        onRightClick: (e) => { showDrawMenu(e.overlay); return true; },
        onPressedMoveStart: (e) => { if (ALERTS.some((a) => a.id === e.overlay.id)) safe(() => chart.removeIndicator("candle_pane", "ALERTLINE")); return false; },   // hide the 🔔 marker while dragging an alerted drawing
        onPressedMoveEnd: (e) => { recordDrawing(e.overlay); repositionLinkedNotes(e.overlay.id); return false; },
        onMouseEnter: (e) => { hoverOverlayId = e.overlay.id; return false; },
        onMouseLeave: (e) => { if (hoverOverlayId === e.overlay.id) hoverOverlayId = null; return false; },
        onSelected: (e) => { selOverlayId = e.overlay.id; return false; },
        onDeselected: (e) => { if (selOverlayId === e.overlay.id) selOverlayId = null; return false; },
      }));
    }
    // Delete / Backspace removes the selected (or hovered) drawing — unless you're typing in a field
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Delete" && e.key !== "Backspace") return;
      const t = e.target; if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      const id = selOverlayId || hoverOverlayId; if (id == null) return;
      e.preventDefault(); eraseOverlay({ id }); selOverlayId = hoverOverlayId = null; closeDrawMenu();
    });
    function pickTool(name) {
      state.tool = name;
      if (pendingOverlayId != null) { safe(() => chart.removeOverlay(pendingOverlayId)); pendingOverlayId = null; } // cancel any in-progress draw
      const host = $("chart"); if (host) host.style.cursor = name === "erase" ? "crosshair" : "";
      if (name === "erase") status("🗑 Erase mode: click a drawing to delete it, or drag a box to erase everything inside · pick Cursor to pan/draw again");
      if (name === "cursor" || name === "freeDraw" || name === "erase") return;   // these aren't click-to-draw tools
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
    // ---- freehand capture (Free draw tool): capture-phase pointer events block the chart's own pan,
    // we draw the live stroke on a transient canvas, then turn it into a freeDraw overlay on release ----
    let freeCap = null;
    function freeStart(e) {
      if (state.tool !== "freeDraw" || e.button !== 0) return;
      const host = $("chart"); if (!host) return;
      e.stopPropagation(); e.preventDefault();
      const rect = host.getBoundingClientRect(); host.style.position = host.style.position || "relative";
      const cv = document.createElement("canvas"); cv.width = host.clientWidth; cv.height = host.clientHeight;
      cv.style.cssText = "position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:5";
      host.appendChild(cv);
      freeCap = { cv, ctx: cv.getContext("2d"), rect, pts: [[e.clientX - rect.left, e.clientY - rect.top]] };
    }
    function freeMove(e) {
      if (!freeCap) return; e.stopPropagation();
      const x = e.clientX - freeCap.rect.left, y = e.clientY - freeCap.rect.top, last = freeCap.pts[freeCap.pts.length - 1];
      if (Math.hypot(x - last[0], y - last[1]) < 3) return;
      freeCap.pts.push([x, y]);
      const c = freeCap.ctx; c.clearRect(0, 0, freeCap.cv.width, freeCap.cv.height); c.strokeStyle = "#0071e3"; c.lineWidth = 2; c.lineJoin = "round"; c.lineCap = "round"; c.beginPath();
      freeCap.pts.forEach((p, i) => (i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]))); c.stroke();
    }
    function freeEnd(e) {
      if (!freeCap) return; e.stopPropagation();
      const cap = freeCap; freeCap = null; cap.cv.remove();
      if (cap.pts.length < 2) return;
      const points = cap.pts.map(([x, y]) => safe(() => chart.convertFromPixel({ x, y }, { paneId: "candle_pane" })))
        .filter((p) => p && p.value != null && isFinite(p.value)).map((p) => ({ timestamp: p.timestamp, value: p.value }));
      if (points.length < 2) return;
      const id = mkOverlay({ name: "freeDraw", points });
      if (id) { recordDrawing({ id, name: "freeDraw", points }); status("Free-draw added — right-click it to enhance into a clean shape"); }
    }
    $("chart").addEventListener("pointerdown", freeStart, true);
    window.addEventListener("pointermove", freeMove, true);
    window.addEventListener("pointerup", freeEnd, true);
    // ---- Erase tool: click a drawing to delete it, or drag a box to erase everything inside ----
    let eraseSel = null;
    const pxOf = (p, ts) => safe(() => chart.convertToPixel({ timestamp: (p.timestamp != null ? p.timestamp : ts), value: p.value }, { paneId: "candle_pane" }));
    const ptIn = (p, b) => p && p.x >= b.x0 && p.x <= b.x1 && p.y >= b.y0 && p.y <= b.y1;
    function segRect(x0, y0, x1, y1, b) {   // Liang–Barsky segment-vs-rect intersection
      let t0 = 0, t1 = 1; const dx = x1 - x0, dy = y1 - y0, P = [-dx, dx, -dy, dy], Q = [x0 - b.x0, b.x1 - x0, y0 - b.y0, b.y1 - y0];
      for (let i = 0; i < 4; i++) { if (P[i] === 0) { if (Q[i] < 0) return false; } else { const r = Q[i] / P[i]; if (P[i] < 0) { if (r > t1) return false; if (r > t0) t0 = r; } else { if (r < t0) return false; if (r < t1) t1 = r; } } }
      return true;
    }
    function overlayHit(d, box) {
      const ts = (state.curTs && state.curTs.length) ? state.curTs[state.curTs.length - 1] : Date.now(), pts = d.points || [];
      const yOf = (value) => { const p = safe(() => chart.convertToPixel({ timestamp: ts, value }, { paneId: "candle_pane" })); return p ? p.y : null; };
      if (d.name === "horizontalStraightLine" || d.name === "priceLine") { const y = yOf(pts[0].value); return y != null && y >= box.y0 && y <= box.y1; }
      if (d.name === "fibonacciLine" && pts.length >= 2) return overlayLevels(d, ts).some((lv) => { const y = yOf(lv.value); return y != null && y >= box.y0 && y <= box.y1; });
      const pix = pts.map((p) => pxOf(p, ts)).filter(Boolean); if (!pix.length) return false;
      if (d.name === "circleShape" && pix.length >= 2) { const c = pix[0], r = Math.hypot(pix[1].x - c.x, pix[1].y - c.y), cx = Math.max(box.x0, Math.min(c.x, box.x1)), cy = Math.max(box.y0, Math.min(c.y, box.y1)); return Math.hypot(c.x - cx, c.y - cy) <= r; }
      if (d.name === "rectShape" && pix.length >= 2) { const rx0 = Math.min(pix[0].x, pix[1].x), rx1 = Math.max(pix[0].x, pix[1].x), ry0 = Math.min(pix[0].y, pix[1].y), ry1 = Math.max(pix[0].y, pix[1].y); return !(rx1 < box.x0 || rx0 > box.x1 || ry1 < box.y0 || ry0 > box.y1); }
      if (pix.some((p) => ptIn(p, box))) return true;
      for (let i = 1; i < pix.length; i++) if (segRect(pix[i - 1].x, pix[i - 1].y, pix[i].x, pix[i].y, box)) return true;
      return false;
    }
    function eraseStart(e) {
      if (state.tool !== "erase" || e.button !== 0) return;
      const host = $("chart"); if (!host) return;
      e.stopPropagation(); e.preventDefault();
      const rect = host.getBoundingClientRect(); host.style.position = host.style.position || "relative";
      const cv = document.createElement("canvas"); cv.width = host.clientWidth; cv.height = host.clientHeight;
      cv.style.cssText = "position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:6";
      host.appendChild(cv);
      eraseSel = { cv, ctx: cv.getContext("2d"), rect, x0: e.clientX - rect.left, y0: e.clientY - rect.top, x1: e.clientX - rect.left, y1: e.clientY - rect.top, moved: false };
    }
    function eraseMove(e) {
      if (!eraseSel) return; e.stopPropagation();
      eraseSel.x1 = e.clientX - eraseSel.rect.left; eraseSel.y1 = e.clientY - eraseSel.rect.top;
      if (Math.hypot(eraseSel.x1 - eraseSel.x0, eraseSel.y1 - eraseSel.y0) > 4) eraseSel.moved = true;
      const c = eraseSel.ctx, x = Math.min(eraseSel.x0, eraseSel.x1), y = Math.min(eraseSel.y0, eraseSel.y1), w = Math.abs(eraseSel.x1 - eraseSel.x0), h = Math.abs(eraseSel.y1 - eraseSel.y0);
      c.clearRect(0, 0, eraseSel.cv.width, eraseSel.cv.height); c.fillStyle = "rgba(215,0,21,0.08)"; c.strokeStyle = "rgba(215,0,21,0.7)"; c.lineWidth = 1; c.setLineDash([4, 3]); c.fillRect(x, y, w, h); c.strokeRect(x, y, w, h); c.setLineDash([]);
    }
    function eraseEnd(e) {
      if (!eraseSel) return; e.stopPropagation();
      const sel = eraseSel; eraseSel = null; sel.cv.remove();
      const box = { x0: Math.min(sel.x0, sel.x1), y0: Math.min(sel.y0, sel.y1), x1: Math.max(sel.x0, sel.x1), y1: Math.max(sel.y0, sel.y1) };
      if (!sel.moved) { box.x0 -= 7; box.y0 -= 7; box.x1 += 7; box.y1 += 7; }   // a click → small hit area around the point
      const hits = drawings.filter((d) => overlayHit(d, box));
      if (!hits.length) { if (sel.moved) status("nothing in the box to erase"); return; }
      hits.slice().forEach((d) => eraseOverlay({ id: d.id, name: d.name }));
      status("🗑 erased " + hits.length + (hits.length === 1 ? " drawing" : " drawings"));
    }
    $("chart").addEventListener("pointerdown", eraseStart, true);
    window.addEventListener("pointermove", eraseMove, true);
    window.addEventListener("pointerup", eraseEnd, true);
    // ---- enhance: turn any drawing (esp. a freehand) into a proper circle/square/rect/trend/ray/channel ----
    const ENHANCE = [["circle", "○ Circle"], ["square", "□ Square"], ["rect", "▭ Rectangle"], ["trend", "／ Trend line"], ["ray", "→ Ray"], ["channel", "▤ Channel"]];
    const ENHANCEABLE = new Set(["freeDraw"]);   // Enhance = snap a freehand sketch into a clean shape; it's meaningless for already-precise drawings
    function squarePoints(minT, maxT, minV, maxV) {
      const a = safe(() => chart.convertToPixel({ timestamp: minT, value: maxV }, { paneId: "candle_pane" }));
      const b = safe(() => chart.convertToPixel({ timestamp: maxT, value: minV }, { paneId: "candle_pane" }));
      if (!a || !b) return [{ timestamp: minT, value: maxV }, { timestamp: maxT, value: minV }];
      const s = Math.min(Math.abs(b.x - a.x), Math.abs(b.y - a.y));
      const corner = safe(() => chart.convertFromPixel({ x: a.x + (b.x >= a.x ? s : -s), y: a.y + (b.y >= a.y ? s : -s) }, { paneId: "candle_pane" }));
      return corner ? [{ timestamp: minT, value: maxV }, { timestamp: corner.timestamp, value: corner.value }] : [{ timestamp: minT, value: maxV }, { timestamp: maxT, value: minV }];
    }
    function circlePoints(minT, maxT, minV, maxV) {
      const cT = (minT + maxT) / 2, cV = (minV + maxV) / 2;
      const ctr = safe(() => chart.convertToPixel({ timestamp: cT, value: cV }, { paneId: "candle_pane" }));
      const cor = safe(() => chart.convertToPixel({ timestamp: maxT, value: maxV }, { paneId: "candle_pane" }));
      let edge = { timestamp: maxT, value: cV };
      if (ctr && cor) { const r = Math.max(Math.abs(cor.x - ctr.x), Math.abs(cor.y - ctr.y)); const ep = safe(() => chart.convertFromPixel({ x: ctr.x + r, y: ctr.y }, { paneId: "candle_pane" })); if (ep) edge = { timestamp: ep.timestamp, value: ep.value }; }
      return [{ timestamp: cT, value: cV }, edge];
    }
    function enhanceTo(overlay, shape) {
      const rec = drawings.find((d) => d.id === overlay.id) || { points: (overlay.points || []).map((p) => ({ timestamp: p.timestamp, value: p.value })) };
      const pts = rec.points; if (!pts || pts.length < 2) return;
      const ts = pts.map((p) => p.timestamp), vs = pts.map((p) => p.value);
      const minT = Math.min(...ts), maxT = Math.max(...ts), minV = Math.min(...vs), maxV = Math.max(...vs), start = pts[0], end = pts[pts.length - 1];
      const seg = [{ timestamp: start.timestamp, value: start.value }, { timestamp: end.timestamp, value: end.value }];
      let name, np;
      if (shape === "trend") { name = "segment"; np = seg; }
      else if (shape === "ray") { name = "rayLine"; np = seg; }
      else if (shape === "channel") { name = "parallelStraightLine"; np = seg.concat([{ timestamp: start.timestamp, value: (start.value <= (minV + maxV) / 2 ? maxV : minV) }]); }
      else if (shape === "rect") { name = "rectShape"; np = [{ timestamp: minT, value: maxV }, { timestamp: maxT, value: minV }]; }
      else if (shape === "square") { name = "rectShape"; np = squarePoints(minT, maxT, minV, maxV); }
      else if (shape === "circle") { name = "circleShape"; np = circlePoints(minT, maxT, minV, maxV); }
      else return;
      safe(() => chart.removeOverlay(overlay.id)); const i = drawings.findIndex((d) => d.id === overlay.id); if (i >= 0) drawings.splice(i, 1); removeAlert(overlay.id);
      const id = mkOverlay({ name, points: np }); if (id) recordDrawing({ id, name, points: np }); scheduleSave();
      pickTool("cursor"); segActive($("toolSeg"), findBtn($("toolSeg"), "cursor"));   // land in Cursor so the new shape can be dragged/resized immediately
      status("Enhanced ✓ — drag the shape to move it, drag a handle to resize, right-click to change");
    }
    function drawMenuOutside(e) { if (drawMenuEl && !drawMenuEl.contains(e.target)) closeDrawMenu(); }
    function closeDrawMenu() { if (drawMenuEl) { drawMenuEl.remove(); drawMenuEl = null; document.removeEventListener("mousedown", drawMenuOutside); } if (rearmTool && pendingOverlayId == null && state.tool === rearmTool) { const t = rearmTool; rearmTool = null; armTool(t); } }
    // ---- drawing colour + trend-line angle ----
    const DRAW_DEFAULT = "#0071e3", DRAW_ALERT = "#d68a12";   // default blue · amber = a tracked (alerted) line
    const SWATCHES = ["#0071e3", "#15803d", "#b42318", "#d68a12", "#7c3aed", "#0aa2c0", "#1d1d1f"];
    function overlayColorStyles(c) { const fill = c + "1f"; return { line: { color: c }, polygon: { color: fill, borderColor: c }, circle: { color: fill, borderColor: c }, arc: { color: c }, text: { color: c } }; }
    function recolorOverlay(overlay, c) {
      const d = drawings.find((x) => x.id === overlay.id) || (recordDrawing(overlay), drawings.find((x) => x.id === overlay.id));
      if (d) d.color = c;
      if (!ALERTS.some((a) => a.id === overlay.id)) safe(() => chart.overrideOverlay({ id: overlay.id, styles: overlayColorStyles(c) }));   // an alerted line stays amber until the alert is removed
      scheduleSave(); status("colour changed");
    }
    function applyDrawingColors() {   // re-assert each drawing's colour (alerted → amber so you can see WHICH line is tracked)
      drawings.forEach((d) => { const c = ALERTS.some((a) => a.id === d.id) ? DRAW_ALERT : (d.color || DRAW_DEFAULT); safe(() => chart.overrideOverlay({ id: d.id, styles: overlayColorStyles(c) })); });
    }
    const toPx = (pt) => {   // resolve a drawing point to chart pixels — dataIndex first (a future/edge point has a null timestamp but a valid dataIndex)
      if (!pt || pt.value == null) return null;
      const q = { value: pt.value };
      if (pt.dataIndex != null) q.dataIndex = pt.dataIndex; else if (pt.timestamp != null) q.timestamp = pt.timestamp; else return null;
      const r = safe(() => chart.convertToPixel(q, { paneId: "candle_pane" }));
      return r && isFinite(r.x) && isFinite(r.y) ? r : null;
    };
    function trendAngleInfo(overlay) {   // visual angle vs horizontal (steepness at current zoom) + % move over the span
      const p = (overlay.points || []).filter((x) => x && x.value != null && (x.dataIndex != null || x.timestamp != null)); if (p.length < 2) return null;
      const A = toPx(p[0]), B = toPx(p[1]); if (!A || !B) return null;
      const L = A.x <= B.x ? A : B, R = A.x <= B.x ? B : A;
      const angle = Math.atan2(-(R.y - L.y), Math.max(1, R.x - L.x)) * 180 / Math.PI;   // up-to-the-right = positive
      const haveTs = p[0].timestamp != null && p[1].timestamp != null;
      const e0 = !haveTs || p[0].timestamp <= p[1].timestamp ? p[0] : p[1], e1 = !haveTs || p[0].timestamp <= p[1].timestamp ? p[1] : p[0];
      const pct = e0.value ? (e1.value / e0.value - 1) * 100 : 0, days = haveTs ? Math.round((e1.timestamp - e0.timestamp) / 864e5) : null;
      const mid = toPx({ value: (p[0].value + p[1].value) / 2,
        dataIndex: (p[0].dataIndex != null && p[1].dataIndex != null) ? (p[0].dataIndex + p[1].dataIndex) / 2 : undefined,
        timestamp: haveTs ? (p[0].timestamp + p[1].timestamp) / 2 : undefined });
      return { angle, pct, days, mid };
    }
    function floatLabel(px, py, text) {
      const el = document.createElement("div"); el.textContent = text;
      el.style.cssText = `position:fixed;left:${px}px;top:${py}px;transform:translate(-50%,-135%);z-index:9998;background:#1d1d1f;color:#fff;font:600 12.5px -apple-system,sans-serif;padding:6px 11px;border-radius:9px;box-shadow:0 8px 24px rgba(0,0,0,.28);pointer-events:none;transition:opacity .5s;white-space:nowrap`;
      document.body.appendChild(el); setTimeout(() => { el.style.opacity = "0"; }, 3200); setTimeout(() => el.remove(), 3800);
    }
    function showTrendAngle(overlay) {
      const info = trendAngleInfo(overlay); if (!info) { floatLabel(lastMouse.x, lastMouse.y, "📐 couldn't measure this line"); status("couldn't measure this line"); return; }
      const txt = `📐 ${info.angle >= 0 ? "+" : ""}${info.angle.toFixed(1)}° vs horizontal  ·  ${info.pct >= 0 ? "+" : ""}${info.pct.toFixed(1)}%${info.days ? " over " + info.days + "d" : ""}`;
      const host = $("chart").getBoundingClientRect();
      const px = info.mid && isFinite(info.mid.x) ? host.left + info.mid.x : lastMouse.x;
      const py = info.mid && isFinite(info.mid.y) ? host.top + info.mid.y : lastMouse.y;
      floatLabel(px, py, txt); status(txt.replace("📐 ", "Trend angle "));
    }
    function showDrawMenu(overlay) {
      closeDrawMenu();
      selOverlayId = overlay.id;   // right-clicking selects it, so the Delete key also works
      const isNote = overlay.name === "noteText" || overlay.name === "simpleAnnotation";
      const m = document.createElement("div");
      m.style.cssText = `position:fixed;left:${Math.min(lastMouse.x, innerWidth - 190)}px;top:${Math.min(lastMouse.y, innerHeight - 130)}px;z-index:9999;background:#fff;border:1px solid var(--line);border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.18);overflow:hidden;min-width:172px;`;
      const item = (label, fn, danger) => { const b = document.createElement("button"); b.textContent = label; b.style.cssText = `display:block;width:100%;text-align:left;padding:9px 16px;border:0;background:#fff;cursor:pointer;font:inherit;font-size:13px;color:${danger ? "#d70015" : "#1d1d1f"}`; b.onmouseenter = () => (b.style.background = "#f2f2f7"); b.onmouseleave = () => (b.style.background = "#fff"); b.onclick = (ev) => { ev.stopPropagation(); closeDrawMenu(); fn(); }; return b; };
      if (isNote) m.appendChild(item("✎  Edit note", () => editAnnotation(overlay)));
      else {
        const aTs = (state.curTs && state.curTs.length) ? state.curTs[state.curTs.length - 1] : Date.now();
        const aLv = overlayLevels({ name: overlay.name, points: (overlay.points || []) }, aTs);
        if (aLv.length) {   // line-type → can alert; show the actual price(s) it triggers at
          const on = ALERTS.some((a) => a.id === overlay.id);
          const at = aLv.length === 1 ? "at " + nfmt(aLv[0].value) : aLv.length + " levels (" + aLv.map((x) => nfmt(x.value)).join(", ") + ")";
          if (on) {
            m.appendChild(item("✎  Rename alert", () => editAlertFromMenu(overlay.id, "name")));
            if (aLv.length === 1 && (overlay.name === "horizontalStraightLine" || overlay.name === "priceLine")) m.appendChild(item("✎  Edit alert price", () => editAlertLevel(overlay.id)));
            m.appendChild(item("🔕  Remove price alert (" + at + ")", () => toggleAlert(overlay)));
          } else m.appendChild(item("🔔  Set price alert — " + at, () => toggleAlert(overlay)));
        }
      }
      if (!isNote) m.appendChild(item("📝  Attach linked note", () => attachNote(overlay)));   // note rides along when this drawing moves
      if (isNote) { const nr = drawings.find((d) => d.id === overlay.id); if (nr && nr.linkedTo) m.appendChild(item("🔗  Detach from drawing", () => { nr.linkedTo = undefined; nr.offset = undefined; scheduleSave(); status("note detached — now free-standing"); })); }
      if (isSloping(overlay.name)) m.appendChild(item("📐  Show angle (steepness)", () => showTrendAngle(overlay)));
      if (ENHANCEABLE.has(overlay.name)) ENHANCE.forEach(([k, lbl]) => m.appendChild(item("Enhance → " + lbl, () => enhanceTo(overlay, k))));
      if (!isNote) {   // colour swatches — recolour any line/shape
        const sw = document.createElement("div"); sw.className = "dw-swatches";
        const swl = document.createElement("span"); swl.textContent = "Colour"; swl.style.cssText = "font-size:11px;color:#6e6e73;margin-right:3px"; sw.appendChild(swl);
        SWATCHES.forEach((c) => { const b = document.createElement("button"); b.className = "dw-swatch"; b.style.background = c; b.title = c; b.onmousedown = (ev) => ev.stopPropagation(); b.onclick = (ev) => { ev.stopPropagation(); closeDrawMenu(); recolorOverlay(overlay, c); }; sw.appendChild(b); });
        m.appendChild(sw);
      }
      m.appendChild(item("🗑  Erase  (or press Delete)", () => eraseOverlay(overlay), true));
      document.body.appendChild(m); drawMenuEl = m;
      setTimeout(() => document.addEventListener("mousedown", drawMenuOutside), 0);   // close on OUTSIDE click only (was closing before the button click registered)
    }
    function eraseOverlay(o) {
      safe(() => chart.removeOverlay(o.id)); const i = drawings.findIndex((d) => d.id === o.id); if (i >= 0) drawings.splice(i, 1);
      drawings.filter((d) => d.linkedTo === o.id).slice().forEach((n) => { safe(() => chart.removeOverlay(n.id)); const j = drawings.findIndex((d) => d.id === n.id); if (j >= 0) drawings.splice(j, 1); removeAlert(n.id); });   // remove notes linked to it
      if (pendingLink && pendingLink.linkedTo === o.id) pendingLink = null;
      removeAlert(o.id); scheduleSave(); syncAlerts();
    }
    // attach a note that's pinned to a drawing — it rides along when the drawing is moved
    function attachNote(parent) {
      const rec = drawings.find((d) => d.id === parent.id) || { points: (parent.points || []).map((p) => ({ timestamp: p.timestamp, value: p.value })) };
      const a = rec.points && rec.points[0]; if (!a) return;
      const r = $("chart").getBoundingClientRect();
      const dp = safe(() => chart.convertFromPixel({ x: lastMouse.x - r.left, y: lastMouse.y - r.top }, { paneId: "candle_pane" }));
      const pt = (dp && dp.value != null) ? { timestamp: dp.timestamp, value: dp.value } : { timestamp: a.timestamp, value: a.value };
      const id = mkOverlay({ name: "noteText", extendData: " ", points: [pt] }); if (!id) return;
      pendingLink = { noteId: id, linkedTo: parent.id, offset: { dt: pt.timestamp - a.timestamp, dv: pt.value - a.value } };
      inlineNote(lastMouse.x, lastMouse.y, "", id, [pt]);
    }
    function repositionLinkedNotes(parentId) {
      const parent = drawings.find((d) => d.id === parentId); if (!parent || !parent.points || !parent.points[0]) return;
      const a = parent.points[0];
      drawings.filter((d) => d.linkedTo === parentId).forEach((note) => { const off = note.offset || { dt: 0, dv: 0 }, np = { timestamp: a.timestamp + off.dt, value: a.value + off.dv }; note.points = [np]; safe(() => chart.overrideOverlay({ id: note.id, points: [np] })); });
    }
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
    // right-click empty chart space → drop a price line at that level and set an alert on it
    function addAlertHere() {
      const rect = $("chart").getBoundingClientRect();
      const dp = safe(() => chart.convertFromPixel({ x: lastMouse.x - rect.left, y: lastMouse.y - rect.top }, { paneId: "candle_pane" }));
      if (!dp || dp.value == null) { status("couldn't read a price there — try again on the chart"); return; }
      const pts = [{ timestamp: dp.timestamp, value: dp.value }];
      const id = mkOverlay({ name: "priceLine", points: pts });
      if (!id) return;
      recordDrawing({ id, name: "priceLine", points: pts });
      toggleAlert({ id, name: "priceLine", points: pts });
    }
    // right-click on empty chart → choose: set a price alert here, or add a note
    function showEmptyMenu() {
      closeDrawMenu();
      const rect = $("chart").getBoundingClientRect();
      const dp = safe(() => chart.convertFromPixel({ x: lastMouse.x - rect.left, y: lastMouse.y - rect.top }, { paneId: "candle_pane" }));
      const price = (dp && dp.value != null) ? dp.value : null;
      const m = document.createElement("div");
      m.style.cssText = `position:fixed;left:${Math.min(lastMouse.x, innerWidth - 230)}px;top:${Math.min(lastMouse.y, innerHeight - 110)}px;z-index:9999;background:#fff;border:1px solid var(--line);border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.18);overflow:hidden;min-width:208px;`;
      const item = (label, fn) => { const b = document.createElement("button"); b.textContent = label; b.style.cssText = "display:block;width:100%;text-align:left;padding:9px 16px;border:0;background:#fff;cursor:pointer;font:inherit;font-size:13px;color:#1d1d1f"; b.onmouseenter = () => (b.style.background = "#f2f2f7"); b.onmouseleave = () => (b.style.background = "#fff"); b.onclick = (e) => { e.stopPropagation(); closeDrawMenu(); fn(); }; return b; };
      if (price != null) m.appendChild(item("🔔  Set price alert here — at " + nfmt(price), addAlertHere));
      m.appendChild(item("📝  Add note here", addNoteHere));
      document.body.appendChild(m); drawMenuEl = m;
      setTimeout(() => document.addEventListener("mousedown", drawMenuOutside), 0);
    }
    // ---- Price alerts on drawings (varies by drawing): the "level(s)" a drawing represents at the latest bar ----
    let lastLivePrice = null, toastTimer = null;
    function overlayLevels(d, ts) {
      const p = d.points || []; if (!p.length) return [];
      const nm = d.name;
      const at = (a, b, t) => (a.timestamp === b.timestamp ? b.value : a.value + (b.value - a.value) * (t - a.timestamp) / (b.timestamp - a.timestamp));
      if (nm === "horizontalStraightLine" || nm === "priceLine") return [{ value: p[0].value, label: "horizontal level" }];
      if (nm === "verticalStraightLine" || nm === "noteText" || nm === "simpleAnnotation" || nm === "measurePct") return [];
      if (nm === "fibonacciLine" && p.length >= 2) { const hi = Math.max(p[0].value, p[1].value), lo = Math.min(p[0].value, p[1].value), sp = hi - lo; return [0.236, 0.382, 0.5, 0.618, 0.786].map((r) => ({ value: hi - sp * r, label: (r * 100).toFixed(1) + "% Fib" })); }
      if (p.length >= 2) { const out = [{ value: at(p[0], p[1], ts), label: "trend line" }]; if (nm === "parallelStraightLine" && p[2]) { const off = p[2].value - at(p[0], p[1], p[2].timestamp); out.push({ value: at(p[0], p[1], ts) + off, label: "channel rail" }); } return out; }
      return [{ value: p[0].value, label: "level" }];
    }
    function toggleAlert(o) {
      if (ALERTS.some((a) => a.id === o.id)) { removeAlert(o.id); syncAlerts(); status("🔕 alert removed"); return; }
      const ts = (state.curTs && state.curTs.length) ? state.curTs[state.curTs.length - 1] : Date.now();
      const lv = overlayLevels(o, ts), vals = lv.map((x) => nfmt(x.value)).join(" · ");
      const sloping = o.name === "segment" || o.name === "rayLine" || o.name === "parallelStraightLine" || o.name === "straightLine";
      ALERTS.push({ id: o.id, sides: [] });
      if (window.Notification && Notification.permission === "default") { try { Notification.requestPermission(); } catch (_) {} }
      if (lastLivePrice != null) checkAlerts(lastLivePrice);   // seed the current side so it doesn't fire immediately
      const where = sloping ? "where this line sits now (" + vals + ") — and because it slopes, the trigger updates each bar as the line moves"
        : (lv.length > 1 ? "each of these levels: " + vals : vals);
      syncAlerts();
      status("🔔 Alert set at " + where + ". You'll get a toast + beep when price crosses" + (lv.length > 1 ? " any of them" : " it") + " (while this tab is open). See the Price alerts section below to manage it.");
    }
    function removeAlert(id) { const i = ALERTS.findIndex((a) => a.id === id); if (i >= 0) ALERTS.splice(i, 1); }
    function checkAlerts(price) {
      if (price == null || !isFinite(price) || !ALERTS.length) return;
      const ts = (state.curTs && state.curTs.length) ? state.curTs[state.curTs.length - 1] : Date.now();
      ALERTS.forEach((al) => {
        const d = drawings.find((x) => x.id === al.id); if (!d) { removeAlert(al.id); return; }
        overlayLevels(d, ts).forEach((lv, k) => {
          if (!isFinite(lv.value)) return;
          const side = price >= lv.value ? 1 : -1;
          if (al.sides[k] != null && al.sides[k] !== side) fireAlert(lv, side, price);
          al.sides[k] = side;
        });
      });
    }
    function fireAlert(lv, side, price) {
      const msg = `${D.label}: price broke ${side > 0 ? "ABOVE" : "BELOW"} your ${lv.label} (${nfmt(lv.value)}) — now ${nfmt(price)}`;
      status("🔔 " + msg); showToast(msg); beep();
      try { if (window.Notification && Notification.permission === "granted") new Notification("Chart alert", { body: msg }); } catch (_) {}
    }
    function showToast(msg) {
      let t = $("alertToast");
      if (!t) { t = document.createElement("div"); t.id = "alertToast"; t.style.cssText = "position:fixed;left:50%;top:18px;transform:translateX(-50%);z-index:10002;background:#1d1d1f;color:#fff;font:inherit;font-size:14px;font-weight:600;padding:12px 20px;border-radius:12px;box-shadow:0 12px 36px rgba(0,0,0,.32);max-width:90vw;text-align:center;cursor:pointer"; t.onclick = () => (t.style.display = "none"); document.body.appendChild(t); }
      t.textContent = "🔔 " + msg; t.style.display = "block";
      clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.style.display = "none"; }, 8000);
    }
    function beep() { try { const a = new (window.AudioContext || window.webkitAudioContext)(); const o = a.createOscillator(), g = a.createGain(); o.connect(g); g.connect(a.destination); o.frequency.value = 880; g.gain.value = 0.05; o.start(); setTimeout(() => { o.stop(); a.close(); }, 170); } catch (_) {} }
    // ---- price-alert denotation (🔔 on chart) + the dedicated Price alerts section ----
    const alertTs = () => (state.curTs && state.curTs.length) ? state.curTs[state.curTs.length - 1] : Date.now();
    const isSloping = (name) => name === "segment" || name === "rayLine" || name === "parallelStraightLine" || name === "straightLine";
    const drawingTypeLabel = (name) => ({ horizontalStraightLine: "Horizontal line", priceLine: "Price line", segment: "Trend line", rayLine: "Ray", parallelStraightLine: "Channel", fibonacciLine: "Fibonacci", rectShape: "Rectangle", circleShape: "Circle", freeDraw: "Freehand", noteText: "Note" }[name]) || "Drawing";
    function refreshAlertLines() {
      const ts = alertTs(), lines = [];
      ALERTS.forEach((a) => { const d = drawings.find((x) => x.id === a.id); if (!d) return; const sloped = isSloping(d.name); overlayLevels(d, ts).forEach((lv) => { if (isFinite(lv.value)) lines.push({ value: lv.value, label: nfmt(lv.value), sloped }); }); });
      ALERT_LINES = lines;
      safe(() => { chart.removeIndicator("candle_pane", "ALERTLINE"); if (lines.length && !state.alertsHidden) chart.createIndicator("ALERTLINE", true, { id: "candle_pane" }); });
    }
    function syncAlerts() { refreshAlertLines(); renderAlerts(); applyDrawingColors(); }
    function renderAlerts() {
      const card = $("alertCard"), host = $("alertList"); if (!card || !host) return;
      ALERTS = ALERTS.filter((a) => drawings.some((d) => d.id === a.id));   // drop alerts whose drawing is gone
      if (!ALERTS.length) { card.style.display = "none"; host.innerHTML = ""; if ($("alertCount")) $("alertCount").textContent = ""; return; }
      card.style.display = ""; if ($("alertCount")) $("alertCount").textContent = "· " + ALERTS.length + (ALERTS.length === 1 ? " alert" : " alerts");
      const ts = alertTs();
      host.innerHTML = ALERTS.map((a) => {
        const d = drawings.find((x) => x.id === a.id), lv = overlayLevels(d, ts), t = drawingTypeLabel(d.name), levels = lv.map((x) => nfmt(x.value)).join(" · ");
        const editable = lv.length === 1 && (d.name === "horizontalStraightLine" || d.name === "priceLine");
        const sloped = isSloping(d.name), nowVal = lv.length && isFinite(lv[0].value) ? lv[0].value : null;
        const ang = sloped ? (trendAngleInfo({ name: d.name, points: d.points }) || {}).angle : null;   // identify WHICH trend line by its steepness
        const where = sloped ? (nowVal != null ? "crosses ≈ " + nfmt(nowVal) + " now (rises with the line)" : "tracks the line — drag it to set the level") : (lv.length > 1 ? levels : "at " + (nowVal != null ? nfmt(nowVal) : "—"));
        const angTag = ang != null ? ` · <b style="color:${DRAW_ALERT}">${ang >= 0 ? "+" : ""}${ang.toFixed(0)}°</b>` : "";
        return `<div class="alert-row${sloped ? " tracked" : ""}" data-id="${esc(a.id)}"><span class="a-bell">🔔</span><span style="min-width:0"><b>${esc(a.label || t)}</b><div class="meta">${esc(t)}${angTag} · ${where}</div></span><span class="a-acts">${editable ? `<button data-ap="${esc(a.id)}">Edit price</button>` : ""}<button data-an="${esc(a.id)}">Rename</button><button class="del" data-ad="${esc(a.id)}">Delete</button></span></div>`;
      }).join("");
      host.querySelectorAll("button[data-ad]").forEach((b) => (b.onclick = () => { removeAlert(b.dataset.ad); syncAlerts(); status("alert deleted"); }));
      host.querySelectorAll("button[data-an]").forEach((b) => (b.onclick = () => alertInlineEdit(b, "name")));
      host.querySelectorAll("button[data-ap]").forEach((b) => (b.onclick = () => alertInlineEdit(b, "price")));
    }
    function alertInlineEdit(btn, mode) {
      const row = btn.closest(".alert-row"), id = row.dataset.id, a = ALERTS.find((x) => x.id === id), d = drawings.find((x) => x.id === id); if (!a || !d) return;
      const acts = row.querySelector(".a-acts"), cur = mode === "price" ? nfmt(overlayLevels(d, alertTs())[0].value) : (a.label || drawingTypeLabel(d.name));
      acts.innerHTML = `<input class="a-edit" value="${esc(cur)}" placeholder="${mode === "price" ? "price" : "name"}"><button data-save>Save</button><button data-cancel>Cancel</button>`;
      const inp = acts.querySelector("input"); inp.focus(); inp.select();
      const save = () => {
        if (mode === "name") a.label = inp.value.trim() || undefined;
        else { const v = parseFloat(inp.value.replace(/[^0-9.\-]/g, "")); if (isFinite(v)) { d.points = [{ timestamp: d.points[0].timestamp, value: v }]; safe(() => chart.overrideOverlay({ id, points: d.points })); a.sides = []; } }
        scheduleSave(); syncAlerts();
      };
      acts.querySelector("[data-save]").onclick = save;
      acts.querySelector("[data-cancel]").onclick = () => renderAlerts();
      inp.onkeydown = (e) => { e.stopPropagation(); if (e.key === "Enter") save(); else if (e.key === "Escape") renderAlerts(); };
    }
    function editAlertFromMenu(id, mode) {
      syncAlerts(); const card = $("alertCard"); if (card) card.scrollIntoView({ behavior: "smooth", block: "nearest" });
      setTimeout(() => { const row = $("alertList").querySelector('.alert-row[data-id="' + id + '"]'); if (!row) return; const b = row.querySelector(mode === "price" ? "button[data-ap]" : "button[data-an]"); if (b) b.click(); }, 80);
    }
    // inline editor for an alert's level (price) — opens right where you clicked
    function editAlertLevel(id) {
      const a = ALERTS.find((x) => x.id === id), d = drawings.find((x) => x.id === id); if (!a || !d) return;
      const lv = overlayLevels(d, alertTs()), editable = lv.length === 1 && (d.name === "horizontalStraightLine" || d.name === "priceLine");
      if (!editable) { status("this alert tracks a sloped/multi-level drawing — move the drawing to change its level"); return; }
      const inp = document.createElement("input"); inp.type = "text"; inp.value = nfmt(lv[0].value); inp.placeholder = "new price";
      inp.style.cssText = `position:fixed;left:${Math.min(Math.max(8, lastMouse.x), innerWidth - 160)}px;top:${Math.min(Math.max(8, lastMouse.y), innerHeight - 44)}px;z-index:10001;font:inherit;font-size:13px;padding:6px 10px;border:1.5px solid #d68a12;border-radius:8px;background:#fff;box-shadow:0 8px 26px rgba(0,0,0,.22);width:120px`;
      document.body.appendChild(inp); inp.focus(); inp.select();
      let done = false;
      const finish = (commit) => { if (done) return; done = true; inp.remove(); if (!commit) return; const v = parseFloat(inp.value.replace(/[^0-9.\-]/g, "")); if (!isFinite(v)) return; d.points = [{ timestamp: d.points[0].timestamp, value: v }]; safe(() => chart.overrideOverlay({ id: d.id, points: d.points })); a.sides = []; scheduleSave(); syncAlerts(); status("alert level → " + nfmt(v)); };
      inp.onkeydown = (e) => { e.stopPropagation(); if (e.key === "Enter") finish(true); else if (e.key === "Escape") finish(false); };
      inp.onblur = () => finish(true);
    }
    // right-click ON the alert marker (the 🔔 line) → edit its level / delete it
    function showAlertMenuAt(ev) {
      if (state.alertsHidden || !ALERTS.length) return false;
      const rect = $("chart").getBoundingClientRect(), cy = ev.clientY - rect.top, ts = alertTs();
      let best = null, bestDy = 7;
      ALERTS.forEach((a) => { const d = drawings.find((x) => x.id === a.id); if (!d) return; overlayLevels(d, ts).forEach((lv) => { const p = safe(() => chart.convertToPixel({ timestamp: ts, value: lv.value }, { paneId: "candle_pane" })); if (!p) return; const dy = Math.abs(p.y - cy); if (dy < bestDy) { bestDy = dy; best = { alert: a, drawing: d, value: lv.value, editable: (overlayLevels(d, ts).length === 1 && (d.name === "horizontalStraightLine" || d.name === "priceLine")) }; } }); });
      if (!best) return false;
      closeDrawMenu();
      const m = document.createElement("div");
      m.style.cssText = `position:fixed;left:${Math.min(ev.clientX, innerWidth - 200)}px;top:${Math.min(ev.clientY, innerHeight - 120)}px;z-index:9999;background:#fff;border:1px solid var(--line);border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.18);overflow:hidden;min-width:188px;`;
      const item = (label, fn, danger) => { const b = document.createElement("button"); b.textContent = label; b.style.cssText = `display:block;width:100%;text-align:left;padding:9px 16px;border:0;background:#fff;cursor:pointer;font:inherit;font-size:13px;color:${danger ? "#d70015" : "#1d1d1f"}`; b.onmouseenter = () => (b.style.background = "#f2f2f7"); b.onmouseleave = () => (b.style.background = "#fff"); b.onclick = (e) => { e.stopPropagation(); closeDrawMenu(); fn(); }; return b; };
      const head = document.createElement("div"); head.textContent = "🔔 Alert · " + nfmt(best.value); head.style.cssText = "padding:8px 16px;font-size:11.5px;font-weight:700;color:#6e6e73;border-bottom:1px solid var(--line)"; m.appendChild(head);
      if (best.editable) m.appendChild(item("✎  Edit level", () => editAlertLevel(best.alert.id)));
      m.appendChild(item("✎  Rename alert", () => editAlertFromMenu(best.alert.id, "name")));
      m.appendChild(item("🔕  Delete alert", () => { removeAlert(best.alert.id); syncAlerts(); status("alert deleted"); }, true));
      document.body.appendChild(m); drawMenuEl = m;
      setTimeout(() => document.addEventListener("mousedown", drawMenuOutside), 0);
      return true;
    }
    const validDraw = (d) => d && d.name && Array.isArray(d.points) && d.points.length && d.points.every((p) => p && p.value != null && isFinite(p.value));
    function recordDrawing(o) {
      if (restoring || !o || !o.points || !o.points.length) return;
      const lastTs = (state.curTs && state.curTs.length) ? state.curTs[state.curTs.length - 1] : null;
      const pts = o.points.map((p) => ({ timestamp: (p.timestamp == null || !isFinite(p.timestamp)) && lastTs != null ? lastTs : p.timestamp, value: p.value })); if (pts.some((p) => p.value == null || p.timestamp == null)) return;   // clamp a null/future-area timestamp to the last bar so the line can't jump to the far left on reload
      const i = drawings.findIndex((d) => d.id === o.id), prev = i >= 0 ? drawings[i] : null, rec = { id: o.id, name: o.name, points: pts, extendData: o.extendData, color: prev ? prev.color : undefined };
      const link = (pendingLink && pendingLink.noteId === o.id) ? pendingLink : null;   // a freshly-attached note
      if (link) { rec.linkedTo = link.linkedTo; rec.offset = link.offset; pendingLink = null; }
      else if (prev && prev.linkedTo) {   // an existing linked note got moved → re-anchor its offset to the parent
        rec.linkedTo = prev.linkedTo; const par = drawings.find((d) => d.id === prev.linkedTo);
        rec.offset = (par && par.points && par.points[0]) ? { dt: pts[0].timestamp - par.points[0].timestamp, dv: pts[0].value - par.points[0].value } : prev.offset;
      }
      if (i >= 0) drawings[i] = rec; else drawings.push(rec); scheduleSave();
      const movedAlert = ALERTS.find((a) => a.id === o.id); if (movedAlert) { movedAlert.sides = []; syncAlerts(); }   // alerted drawing moved → re-anchor its trigger level (re-seed so it doesn't fire from the move itself)
    }
    function reapplyDrawings() { restoring = true; safe(() => chart.removeOverlay()); if (state.drawingsHidden) { restoring = false; syncAlerts(); return; } const keep = drawings.filter(validDraw); drawings = []; keep.forEach((d) => { const id = mkOverlay({ id: d.id, name: d.name, points: d.points, extendData: d.extendData, color: d.color }); if (id) drawings.push({ id, name: d.name, points: d.points, extendData: d.extendData, linkedTo: d.linkedTo, offset: d.offset, color: d.color }); }); restoring = false; syncAlerts(); }
    function undoDrawing() { const last = drawings.pop(); if (last) { safe(() => chart.removeOverlay(last.id)); removeAlert(last.id); } scheduleSave(); syncAlerts(); }
    function clearDrawings() { safe(() => chart.removeOverlay()); drawings = []; ALERTS = []; scheduleSave(); syncAlerts(); }

    // ---- persistence ----
    const lsKey = (id) => "chart_" + id;
    const getKey = () => { try { return localStorage.getItem(CLOUD_KEY) || ""; } catch (_) { return ""; } };
    function setKey(k) { try { k ? localStorage.setItem(CLOUD_KEY, k) : localStorage.removeItem(CLOUD_KEY); } catch (_) {} updateAuth(); }
    function status(msg) { $("notesStatus").textContent = msg ? "· " + msg : ""; }
    function updateAuth() { const el = $("cloudAuth"); if (getKey()) { el.innerHTML = `signed in · <a href="#" id="logout">log out</a>`; el.querySelector("#logout").onclick = (e) => { e.preventDefault(); setKey(""); status("logged out"); }; } else el.textContent = "not signed in"; }
    function ensureKey() { const k = getKey(); if (k) return Promise.resolve(k); const entry = (window.prompt("Passphrase to save/view private notes:") || "").trim(); if (!entry) return Promise.resolve(""); return fetch(STORE + "/api/auth", { method: "POST", headers: { "X-Lab-Key": entry } }).then((r) => { if (!r.ok) { status("wrong passphrase"); return ""; } setKey(entry); return entry; }).catch(() => { status("login failed"); return ""; }); }
    function snapshot() { return { notes: $("notes").value || "", drawings: drawings.map(({ id, name, points, extendData, linkedTo, offset, color }) => ({ id, name, points, extendData, linkedTo, offset, color })), alerts: ALERTS.map((a) => ({ id: a.id, label: a.label })), settings: { type: state.type, yAxis: state.yAxis, indicators: state.indicators, indParams: state.indParams, stratParams: state.stratParams, lev: state.lev, carry: state.carry, pnl: { mode: state.pnl.mode, perBp: state.pnl.perBp } } }; }
    function saveLocal() { try { localStorage.setItem(lsKey(D.id), JSON.stringify(snapshot())); } catch (_) {} }
    function pushCloud(announce) {   // sync the snapshot to the cloud store; silent unless announce
      const key = getKey(); if (!key) return Promise.resolve(false);
      if (announce) status("syncing…");
      return fetch(STORE + "/api/chart/" + D.id, { method: "POST", headers: { "Content-Type": "application/json", "X-Lab-Key": key }, body: JSON.stringify(snapshot()) })
        .then((r) => { if (r.status === 401) { setKey(""); throw new Error("login expired"); } if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
        .then(() => { if (announce) status("synced to cloud ✓"); return true; }).catch((e) => { status("cloud sync failed: " + e.message); return false; });
    }
    function scheduleSave() {   // everything auto-saves: instantly to this browser, and (once signed in) synced to the cloud — no button needed
      if (saveTimer) clearTimeout(saveTimer);
      saveTimer = setTimeout(() => { saveTimer = null; saveLocal(); if (getKey()) pushCloud(false).then((ok) => { if (ok) status("saved · synced ☁"); }); else status("saved locally"); }, 600);
    }
    function manualCloudSave() { ensureKey().then((key) => { if (!key) { status("sign in to sync across devices"); return; } updateAuth(); pushCloud(true); }); }   // ☁ Save: sign in if needed, then sync now (afterwards every change auto-syncs)
    if ($("cloudBtn")) $("cloudBtn").onclick = manualCloudSave;       // legacy bottom button (removed from layout) — guarded
    if ($("cloudBtnTop")) $("cloudBtnTop").onclick = manualCloudSave; // neat top-bar button
    $("notes").addEventListener("input", scheduleSave);

    function applySnapshot(snap) {
      restoring = true;
      $("notes").value = snap.notes || "";
      const st = snap.settings || {};
      state.type = "ohlc"; applyBarMode(); segActive($("typeSeg"), findBtn($("typeSeg"), "ohlc")); // chart type is forced to Bars on every load — saved st.type is intentionally ignored
      if (st.yAxis) { state.yAxis = st.yAxis; safe(() => chart.setStyles({ yAxis: { type: st.yAxis } })); segActive($("axisSeg"), findBtn($("axisSeg"), st.yAxis)); }
      if (st.indParams) Object.keys(st.indParams).forEach((k) => { if (Array.isArray(st.indParams[k])) state.indParams[k] = st.indParams[k].slice(); });
      if (st.stratParams) Object.keys(st.stratParams).forEach((k) => { if (state.stratParams[k]) Object.assign(state.stratParams[k], st.stratParams[k]); });
      if (st.lev && typeof st.lev === "object") { Object.assign(state.lev, st.lev); syncLevUI(); }
      if (typeof st.carry === "boolean") state.carry = st.carry;
      if (st.pnl && typeof st.pnl === "object") { if (st.pnl.mode) state.pnl.mode = st.pnl.mode; if (isFinite(st.pnl.perBp) && st.pnl.perBp > 0) state.pnl.perBp = st.pnl.perBp; }
      syncPnlUI();
      syncIndicators(st.indicators); renderIndParams();
      drawings = [];
      (snap.drawings || []).filter(validDraw).forEach((d) => { const id = mkOverlay({ id: d.id, name: d.name, points: d.points, extendData: d.extendData, color: d.color }); if (id) drawings.push({ id, name: d.name, points: d.points, extendData: d.extendData, linkedTo: d.linkedTo, offset: d.offset, color: d.color }); });
      ALERTS = (snap.alerts || []).filter((a) => drawings.some((d) => d.id === a.id)).map((a) => ({ id: a.id, label: a.label, sides: [] }));
      restoring = false; renderPlaybook(); syncAlerts();
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
        live.classList.add("on"); txt.innerHTML = `<b>${esc(D.ticker)} ${nfmt(q.price)}</b> <span style="color:${chg >= 0 ? UP : DN}">${s}${chg.toFixed(2)}%</span> <span style="color:#8a8a8e">· ${esc(q.timestamp || "")} · updated ${ukClock()} UK</span>`;
        lastLivePrice = q.price; checkAlerts(q.price);   // alert when the live price crosses any alerted drawing
        renderDashboard();   // refresh the signal dashboard against the live price (spx/ndx only)
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

    // ---- Technical-indicator signal dashboard (S&P 500 & Nasdaq 100 only) ----
    // Reads signals_<asset>.json (graded backtest evidence) and evaluates each signal's CURRENT
    // direction + 0-100 strength live from price (evaluators mirror research/signal_state.py), then
    // a trust-weighted composite → independent suggested leverage.
    const SIG_CACHE = {}; let DASH_VIX = null;
    const GRADE_C = { A: ["#e3f4ea", "var(--good)"], B: ["#e4f0fb", "var(--accent)"], C: ["#fbf0d8", "#9a6b00"], D: ["#fbe9e9", "var(--bad)"] };
    const sq = (x, sc) => Math.round((50 + 50 * Math.tanh(x / sc)) * 10) / 10;
    const smaL = (c, n) => { if (c.length < n) return null; let s = 0; for (let i = c.length - n; i < c.length; i++) s += c[i]; return s / n; };
    const lastNN = (a) => { for (let i = a.length - 1; i >= 0; i--) if (a[i] != null) return a[i]; return null; };
    const emaL = (c, n) => lastNN(ema(c, n));
    const rsiL = (c, n) => lastNN(rsiArr(c, n));
    function beatTxt(ev) { const f = ev.beats_bh || {}, y = []; if (f.sharpe) y.push("Sharpe"); if (f.calmar) y.push("Calmar"); if (f.dd) y.push("drawdown"); if (f.cagr) y.push("return"); if (!y.length) return "does not beat buy & hold risk-adjusted"; const last = y.pop(); return "beats buy & hold on " + (y.length ? y.join(", ") + " & " + last : last); }
    function dashEval(sig, c, month, vix) {
      const last = c[c.length - 1], p = sig.params || {}, g = (x) => (x >= 0 ? "+" : "") + (x * 100).toFixed(1) + "%";
      switch (sig.rule) {
        case "ma_trend": { const n = p.window, ma = p.type === "ema" ? emaL(c, n) : smaL(c, n); if (ma == null) return null; const x = last / ma - 1; return { dir: last >= ma ? 1 : -1, strength: sq(x, 0.05), read: `${nfmt(last)} vs ${n}-day ${p.type === "ema" ? "EMA" : "SMA"} ${nfmt(ma)} (${g(x)})` }; }
        case "ma_band": { const n = p.window, b = p.band, ma = p.type === "ema" ? emaL(c, n) : smaL(c, n); if (ma == null) return null; const up = ma * (1 + b), lo = ma * (1 - b); let d, x; if (last >= up) { d = 1; x = last / up - 1; } else if (last <= lo) { d = -1; x = last / lo - 1; } else { d = last >= ma ? 1 : -1; x = (last / ma - 1) * 0.5; } return { dir: d, strength: sq(x, 0.05), read: `${nfmt(last)} vs ${n}-day band [${nfmt(lo)} – ${nfmt(up)}]` }; }
        case "cross": { const f = p.fast, s = p.slow, e = p.type === "ema", mf = e ? emaL(c, f) : smaL(c, f), ms = e ? emaL(c, s) : smaL(c, s); if (mf == null || ms == null) return null; const x = mf / ms - 1; return { dir: mf >= ms ? 1 : -1, strength: sq(x, 0.05), read: `${f}-day ${nfmt(mf)} ${mf >= ms ? "›" : "‹"} ${s}-day ${nfmt(ms)}` }; }
        case "momentum": { const lb = p.lookback; if (c.length <= lb) return null; const ref = c[c.length - 1 - lb], x = last / ref - 1; return { dir: x >= 0 ? 1 : -1, strength: sq(x, 0.15), read: `${nfmt(last)} vs ${Math.round(lb / 21)}-mo-ago ${nfmt(ref)} (${g(x)})` }; }
        case "macd": { const m = macdP(c, p.fast, p.slow, p.signal), ml = lastNN(m.macd), sl = lastNN(m.signal); if (ml == null || sl == null) return null; const x = (ml - sl) / (0.01 * last); return { dir: ml >= sl ? 1 : -1, strength: sq(x, 1), read: `MACD ${nfmt(ml)} ${ml >= sl ? "›" : "‹"} signal ${nfmt(sl)}` }; }
        case "bollinger": { const n = p.window, sd = p.std, mid = smaL(c, n); if (mid == null) return null; const std = lastNN(rstd(c, n)) || 1, lo = mid - sd * std, up = mid + sd * std, pb = up > lo ? (last - lo) / (up - lo) : 0.5; let d, x; if (last <= lo) { d = 1; x = (lo - last) / std; } else if (last >= mid) { d = -1; x = (last - mid) / std; } else { d = 1; x = (mid - last) / std * 0.4; } return { dir: d, strength: sq(x, 1.5), read: `%B ${Math.round(pb * 100)}% (band ${nfmt(lo)}–${nfmt(up)})` }; }
        case "rsi_osc": { const r = rsiL(c, p.period || 14); if (r == null) return null; const lo = p.low || 30, hi = p.high || 70; let d; if (r <= lo) d = 1; else if (r >= hi) d = -1; else d = r < 50 ? 1 : -1; return { dir: d, strength: sq((50 - r) / 50, 0.6), read: `RSI(${p.period || 14}) ${Math.round(r)}` }; }
        case "rsi_oversold": { const r = rsiL(c, p.period || 14), ma = smaL(c, p.smaWin || 200); if (r == null || ma == null) return null; const lo = p.low || 30, ok = last >= ma; let d, x; if (r <= lo && ok) { d = 1; x = (lo - r) / 30; } else { d = -1; x = (r - lo) / 40; } return { dir: d, strength: sq(x, 0.6), read: `RSI(14) ${Math.round(r)}, ${ok ? "above" : "below"} 200-day` }; }
        case "sell_in_may": { const inS = [11, 12, 1, 2, 3, 4].includes(month); return { dir: inS ? 1 : -1, strength: 68, read: inS ? "Winter half (Nov–Apr): invested" : "Summer half (May–Oct): seasonally weak" }; }
        case "vix_regime": { if (vix == null) return null; const calm = p.calm, stress = p.stress; let d, x; if (vix <= calm) { d = 1; x = (calm - vix) / 10; } else if (vix >= stress) { d = -1; x = (vix - stress) / 15; } else { d = vix < (calm + stress) / 2 ? 1 : -1; x = 0; } return { dir: d, strength: sq(x, 0.8), read: `VIX ${vix.toFixed(1)}` }; }
        case "dd_from_high": { let hi = -Infinity; for (const v of c) if (v > hi) hi = v; const dd = last / hi - 1; let d, x; if (dd >= -0.05) { d = 1; x = (0.05 + dd) / 0.05; } else if (dd >= -0.20) { d = 1; x = (0.20 + dd) / 0.30; } else { d = -1; x = (-0.20 - dd) / 0.30; } return { dir: d, strength: sq(x, 0.6), read: `${dd >= 0 ? "+" : ""}${(dd * 100).toFixed(1)}% from high` }; }
      }
      return null;
    }
    function dashComposite(sigs) {
      let num = 0, den = 0, longs = 0, votes = 0;
      sigs.forEach((s) => { if (s.kind !== "vote" || !s.st) return; votes++; if (s.st.dir > 0) longs++; const w = (s.st.strength / 100) * s.reliability; num += s.st.dir * w; den += w; });
      const net = den ? num / den : 0;
      let onum = 0, oden = 0;
      sigs.forEach((s) => { if (s.kind !== "overlay" || !s.st) return; const w = s.reliability, b = s.st.dir > 0 ? s.st.strength / 100 : 1 - s.st.strength / 100; onum += b * w; oden += w; });
      const budget = oden ? onum / oden : 0.6;
      let base; if (net <= -0.2) base = 0; else if (net < 0.25) base = 1; else if (net < 0.6) base = 2; else base = 3;
      if (base === 3 && (net < 0.70 || budget < 0.80)) base = 2.5;
      if (base >= 2 && budget < 0.50) base -= 0.5;
      const lev = Math.round(Math.max(0, Math.min(3, base)) * 2) / 2;
      let label; if (net >= 0.6) label = "Strong Risk-On"; else if (net >= 0.25) label = "Risk-On"; else if (net > -0.25) label = "Neutral"; else if (net > -0.6) label = "Risk-Off"; else label = "Strong Risk-Off";
      return { net, label, lev, budget, longs, votes };
    }
    function dashPos(sig) {   // full-history 0/1 position for the ▲/▼ chart markers
      const c = D.close, p = sig.params || {}; if (!c || c.length < 60) return null;
      switch (sig.rule) {
        case "ma_trend": { const ma = p.type === "ema" ? ema(c, p.window) : sma(c, p.window); return c.map((x, i) => (ma[i] != null && x >= ma[i]) ? 1 : 0); }
        case "ma_band": { const s = p.type === "ema" ? ema(c, p.window) : sma(c, p.window), b = p.band; let st = 0; return c.map((x, i) => { if (s[i] != null) { if (x > s[i] * (1 + b)) st = 1; else if (x < s[i] * (1 - b)) st = 0; } return st; }); }
        case "cross": { const a = p.type === "ema" ? ema(c, p.fast) : sma(c, p.fast), bb = p.type === "ema" ? ema(c, p.slow) : sma(c, p.slow); return c.map((_, i) => (a[i] != null && bb[i] != null && a[i] >= bb[i]) ? 1 : 0); }
        case "momentum": { const lb = p.lookback; return c.map((x, i) => (i >= lb && c[i - lb]) ? (x / c[i - lb] - 1 >= 0 ? 1 : 0) : 0); }
        case "macd": { const m = macdP(c, p.fast, p.slow, p.signal); return c.map((_, i) => (m.macd[i] != null && m.signal[i] != null && m.macd[i] >= m.signal[i]) ? 1 : 0); }
        case "bollinger": { const mid = sma(c, p.window), sd = rstd(c, p.window); let st = 0; return c.map((x, i) => { if (mid[i] == null) return 0; if (st === 0 && x < mid[i] - p.std * sd[i]) st = 1; else if (st === 1 && x > mid[i]) st = 0; return st; }); }
        case "rsi_osc": { const r = rsiArr(c, p.period || 14); let st = 0; return c.map((_, i) => { if (r[i] == null) return st; if (r[i] < (p.low || 30)) st = 1; else if (r[i] > (p.high || 70)) st = 0; return st; }); }
        case "rsi_oversold": { const r = rsiArr(c, p.period || 14), s = sma(c, p.smaWin || 200); let st = 0; return c.map((x, i) => { if (st === 0) { if (r[i] != null && r[i] < (p.low || 30) && s[i] != null && x >= s[i]) st = 1; } else { if (s[i] != null && (x < s[i] || (r[i] != null && r[i] > 70))) st = 0; } return st; }); }
        case "sell_in_may": { return (D.dates || []).map((ds) => ([11, 12, 1, 2, 3, 4].includes(+String(ds).slice(5, 7)) ? 1 : 0)); }
        default: return null;   // risk overlays (VIX, drawdown) have no buy/sell marker series
      }
    }
    function dashShow(sig) {
      if (!sig) return; const data = SIG_CACHE[state.asset]; if (!data) return;
      const clearPlot = (s) => { if (s && s.plot) { const ind = s.plot.indicator; if (state.indicators[ind]) { state.indicators[ind] = false; safe(() => chart.removeIndicator(indPane(ind), ind)); } } };
      if (state.dashShown === sig.id) {
        state.dashShown = null; removeStudySignals(); clearPlot(sig);
      } else {
        if (state.dashShown) clearPlot(data.signals.find((s) => s.id === state.dashShown));
        state.dashShown = sig.id;
        const pos = dashPos(sig);
        if (pos) { STUDY_SIG = studyMarks(pos); state.studySig = null; safe(() => { chart.removeIndicator("candle_pane", "STUDYSIG"); chart.createIndicator("STUDYSIG", true, { id: "candle_pane" }); }); }
        else removeStudySignals();
        if (sig.plot) { const ind = sig.plot.indicator; state.indParams[ind] = sig.plot.params.slice(); if (state.indicators[ind]) safe(() => chart.removeIndicator(indPane(ind), ind)); state.indicators[ind] = true; createInd(ind); }
        status("Showing " + sig.name + " on the chart"); const ch = $("chart"); if (ch) ch.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
      syncIndChips(); renderIndParams();
      $("dashList").querySelectorAll("button[data-show]").forEach((b) => { const on = state.dashShown === b.dataset.show; b.classList.toggle("on", on); b.textContent = on ? "✓ on chart" : "Show on chart"; });
    }
    function dashBacktest(sig) {
      const data = SIG_CACHE[state.asset], ev = sig.evidence, b = data.benchmark; const old = $("dashBtOv"); if (old) old.remove();
      const row = (l, v) => `<tr><td style="padding:4px 0;color:var(--muted)">${l}</td><td style="padding:4px 0;text-align:right;font-weight:600">${v}</td></tr>`;
      const ov = document.createElement("div"); ov.id = "dashBtOv";
      ov.style.cssText = "position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,.42);display:flex;align-items:center;justify-content:center;padding:18px;";
      ov.innerHTML = `<div style="background:#fff;border-radius:16px;max-width:540px;width:100%;max-height:86vh;overflow:auto;padding:22px 24px;box-shadow:0 24px 70px rgba(0,0,0,.32)">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:8px"><div><h3 style="margin:0;font-size:19px;color:#1d1d1f">${esc(sig.name)}</h3><div class="meta" style="margin-top:2px">Grade ${sig.grade} · backtested as <b>${esc(ev.strategy_label)}</b></div></div><button id="dashBtX" style="border:0;background:#f0f0f3;border-radius:50%;width:30px;height:30px;font-size:18px;line-height:1;cursor:pointer;flex:none;color:#48484a">×</button></div>
        <div style="font-size:13.5px;line-height:1.6;color:#333;margin-bottom:12px">${esc(sig.why || "")}</div>
        <table style="width:100%;font-size:13px;border-collapse:collapse">${row("Sample", esc(ev.sample))}${row("CAGR", pct(ev.cagr / 100))}${row("Volatility", ev.vol != null ? ev.vol.toFixed(1) + "%" : "—")}${row("Sharpe", f2(ev.sharpe))}${row("Sortino", f2(ev.sortino))}${row("Calmar", f2(ev.calmar))}${row("Max drawdown", ev.maxdd != null ? ev.maxdd.toFixed(1) + "%" : "—")}${ev.win_rate != null ? row("Daily win rate", ev.win_rate.toFixed(0) + "%") : ""}${ev.pct_cash != null ? row("Time in cash", ev.pct_cash.toFixed(0) + "%") : ""}</table>
        <div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--line);font-size:12.5px;color:#444">vs <b>${esc(b.label)}</b> over ${esc(b.sample)}: Sharpe ${f2(b.sharpe)} · Calmar ${f2(b.calmar)} · Max DD ${b.maxdd != null ? b.maxdd.toFixed(0) + "%" : "—"}. This rule <b>${beatTxt(ev)}</b>.</div>
        <p class="meta" style="margin:12px 0 0">Source: ${esc(data.source)}. Cost-aware, lagged, out-of-sample. Educational only — not advice.</p></div>`;
      document.body.appendChild(ov); ov.onclick = (e) => { if (e.target === ov) ov.remove(); }; $("dashBtX").onclick = () => ov.remove();
      document.addEventListener("keydown", function k(e) { if (e.key === "Escape") { ov.remove(); document.removeEventListener("keydown", k); } });
    }
    function renderDashboard() {
      const card = $("dashCard"); if (!card) return; const data = SIG_CACHE[state.asset], c = D.close;
      if (!data || (state.asset !== "spx" && state.asset !== "ndx") || !c || c.length < 60) { card.style.display = "none"; return; }
      card.style.display = "";
      const cEval = c.slice(); if (typeof lastLivePrice === "number" && lastLivePrice > 0 && state.tf === "D") cEval[cEval.length - 1] = lastLivePrice;
      const month = +String(D.dates[D.n - 1] || "").slice(5, 7);
      const sigs = data.signals.map((s) => Object.assign({}, s, { st: dashEval(s, cEval, month, DASH_VIX) }));
      const comp = dashComposite(sigs);
      $("dashAsof").textContent = "· " + D.label + " · live read";
      const pos = comp.net >= 0, w = (Math.abs(comp.net) * 50).toFixed(1), col = pos ? "var(--good)" : "var(--bad)";
      const fillStyle = pos ? `left:50%;width:${w}%` : `left:${50 - w}%;width:${w}%`;
      $("dashComposite").innerHTML = `<div class="dash-comp">
        <div class="dash-state">
          <div class="meta" style="margin-bottom:3px">Composite market read</div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px"><span style="width:10px;height:10px;border-radius:50%;background:${col}"></span><span style="font-size:20px;font-weight:700;color:#1d1d1f">${esc(comp.label)}</span></div>
          <div class="dash-net"><div class="mid"></div><div class="fill" style="${fillStyle};background:${col}"></div></div>
          <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted)"><span>Risk-off</span><span>net ${comp.net >= 0 ? "+" : ""}${comp.net.toFixed(2)}</span><span>Risk-on</span></div>
          <div style="font-size:13px;color:#444;margin-top:9px"><b>${comp.longs} of ${comp.votes}</b> directional signals long · risk budget <b>${Math.round(comp.budget * 100)}%</b></div>
        </div>
        <div class="dash-lev"><div class="meta" style="margin-bottom:2px">Suggested leverage</div><div class="big">${comp.lev.toFixed(1)}×</div><div class="meta" style="margin-top:5px">independent composite</div></div></div>`;
      const open = new Set([...$("dashList").querySelectorAll("details[open]")].map((d) => d.dataset.id));
      $("dashList").innerHTML = sigs.map((s) => {
        const st = s.st, isLong = st && st.dir > 0, gc = GRADE_C[s.grade] || GRADE_C.C, ev = s.evidence;
        const dirTxt = !st ? "—" : (isLong ? "Long" : "Cash"), dirCol = !st ? "var(--muted)" : (isLong ? "var(--good)" : "var(--muted)"), barCol = isLong ? "var(--good)" : "#b0b0b6", str = st ? Math.round(st.strength) : 0;
        const shown = state.dashShown === s.id, canShow = s.kind === "vote";
        return `<details class="dsig" data-id="${esc(s.id)}"${open.has(s.id) ? " open" : ""}>
          <summary>
            <span class="dgrade" style="background:${gc[0]};color:${gc[1]}">${s.grade}</span>
            <span style="flex:1;min-width:0"><span style="font-size:14px;color:#1d1d1f">${esc(s.name)}</span><span style="display:block;font-size:12px;color:var(--muted)">${st ? esc(st.read) : "awaiting data"}</span></span>
            <span style="width:118px;flex:none"><span style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-bottom:3px"><span style="color:${dirCol};font-weight:600">${dirTxt}</span><span>${st ? str : "–"}</span></span><span class="dbar"><i style="width:${str}%;background:${barCol}"></i></span></span>
            <span class="dsig-arrow" style="color:var(--muted);font-size:12px">▾</span>
          </summary>
          <div style="padding:11px 0 3px 34px">
            <div style="font-size:13px;color:#444;line-height:1.6;margin-bottom:9px">${esc(s.why || "")}</div>
            <div style="display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:#444;margin-bottom:11px"><span>Sharpe <b>${f2(ev.sharpe)}</b></span><span>Calmar <b>${f2(ev.calmar)}</b></span><span>Max DD <b>${ev.maxdd != null ? ev.maxdd.toFixed(0) + "%" : "—"}</b></span><span style="color:var(--muted)">${beatTxt(ev)}</span></div>
            <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="dbtn ${shown ? "on" : ""}" data-show="${esc(s.id)}"${canShow ? "" : " disabled title=\"risk overlay — no chart series\""}>${shown ? "✓ on chart" : "Show on chart"}</button><button class="dbtn" data-bt="${esc(s.id)}">View backtest</button></div>
          </div></details>`;
      }).join("");
      $("dashList").querySelectorAll("button[data-show]").forEach((b) => { b.onclick = (e) => { e.preventDefault(); dashShow(data.signals.find((s) => s.id === b.dataset.show)); }; });
      $("dashList").querySelectorAll("button[data-bt]").forEach((b) => { b.onclick = (e) => { e.preventDefault(); dashBacktest(data.signals.find((s) => s.id === b.dataset.bt)); }; });
    }
    function loadDashboard(id) {
      state.dashShown = null;
      const fin = () => renderDashboard();
      if (id === "spx" || id === "ndx") {
        if (!SIG_CACHE[id]) fetch("signals_" + id + ".json").then((r) => (r.ok ? r.json() : null)).then((d) => { if (d) SIG_CACHE[id] = d; fin(); }).catch(fin);
        else fin();
        if (DASH_VIX == null) fetch(QUOTE + "/?mode=quote&symbol=vix&_=" + Date.now()).then((r) => r.json()).then((q) => { if (q && q.price > 0) { DASH_VIX = q.price; renderDashboard(); } }).catch(() => {});
      } else fin();
    }

    // ---- One-click Analyst: live bundle (both assets) → quant report + copy-prompt (+ optional worker) ----
    // Set ANALYST_WORKER to a deployed worker URL (cloudflare_market_analyst_worker.js) to render the
    // Claude-written narrative inline; left empty, the copy-prompt route runs the same analysis in any
    // Claude window. The shared brain is analyst_prompt.md (also used by the skill + the worker).
    const ANALYST_WORKER = "";
    let ANALYST_PROMPT = null;
    const aJson = (u) => fetch(u).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    const getAsset = (id) => (ASSET_CACHE[id] ? Promise.resolve(ASSET_CACHE[id]) : aJson("price_" + id + ".json").then((d) => { if (d) ASSET_CACHE[id] = d; return d; }));
    const daysSince = (iso) => { if (!iso) return null; const d = new Date(String(iso).slice(0, 10) + "T00:00:00Z"); return isNaN(d) ? null : Math.floor((Date.now() - d.getTime()) / 864e5); };
    const liveQuote = (s) => fetch(QUOTE + "/?mode=quote&symbol=" + s + "&_=" + Date.now()).then((r) => r.json()).then((j) => (j && j.price > 0 ? j.price : null)).catch(() => null);
    // Capture WHAT THE USER IS LOOKING AT: timeframe, the visible window's price action, their
    // drawings/levels, and the overlays they've turned on — so the Analyst reads the actual chart.
    function buildChartView() {
      const r1 = (x) => (isFinite(x) ? Math.round(x * 10) / 10 : null), r2 = (x) => (isFinite(x) ? Math.round(x * 100) / 100 : null);
      const tfLbl = (TFS.find((t) => t.id === state.tf) || {}).label || state.tf;
      const v = { asset: state.asset, ticker: D.ticker, label: D.label, timeframe: tfLbl, chart_type: state.type, axis: state.yAxis,
        active_overlays: Object.keys(state.indicators).filter((n) => state.indicators[n]).map((n) => ({ indicator: n, params: state.indParams[n] })) };
      let dl = null, vr = null;
      try { dl = chart && chart.getDataList ? chart.getDataList() : null; } catch (_) {}
      try { vr = chart && chart.getVisibleRange ? chart.getVisibleRange() : null; } catch (_) {}
      if (dl && dl.length) {
        let from = vr ? Math.max(0, vr.from | 0) : 0, to = vr ? Math.min(dl.length, vr.to | 0) : dl.length;
        if (to <= from) { from = 0; to = dl.length; }
        const seg = dl.slice(from, to), last = dl[dl.length - 1];
        const highs = seg.map((b) => b.high), lows = seg.map((b) => b.low), vHi = Math.max(...highs), vLo = Math.min(...lows);
        v.visible = { from_date: isoOf(seg[0].timestamp), to_date: isoOf(seg[seg.length - 1].timestamp), bars_shown: seg.length,
          last: r2(last.close), visible_high: r2(vHi), visible_low: r2(vLo),
          pct_from_visible_high: r1((last.close / vHi - 1) * 100), pct_above_visible_low: r1((last.close / vLo - 1) * 100),
          visible_range_pct: r1((vHi / vLo - 1) * 100), change_across_window_pct: r1((seg[seg.length - 1].close / seg[0].close - 1) * 100) };
      }
      const c = D.close;
      if (c && c.length > 5) {
        const last = c[c.length - 1], w = c.slice(-252), hi52 = Math.max(...w), lo52 = Math.min(...w), chg = (n) => (c.length > n ? r1((last / c[c.length - 1 - n] - 1) * 100) : null);
        v.price_action = { last: r2(last), dist_from_52w_high_pct: r1((last / hi52 - 1) * 100), above_52w_low_pct: r1((last / lo52 - 1) * 100),
          change_5d_pct: chg(5), change_21d_pct: chg(21), change_63d_pct: chg(63),
          ann_vol_20d_pct: (D.rv && D.rv.length) ? r1(D.rv[D.rv.length - 1] * 100) : null,
          drawdown_from_high_pct: (D.ddh && D.ddh.length) ? r1(D.ddh[D.ddh.length - 1] * 100) : null };
      }
      const ts = (state.curTs && state.curTs.length) ? state.curTs[state.curTs.length - 1] : Date.now();
      v.drawings = (drawings || []).map((d) => {
        const o = { type: d.name }; const lv = overlayLevels({ name: d.name, points: d.points || [] }, ts);
        if (d.name === "noteText" || d.name === "simpleAnnotation") o.note = d.extendData || "";
        if (lv.length) o.levels = lv.map((x) => ({ label: x.label, value: r2(x.value) }));
        if (d.points && d.points.length >= 2) { o.from_date = isoOf(d.points[0].timestamp); o.to_date = isoOf(d.points[d.points.length - 1].timestamp); }
        return o;
      });
      if (state.autoTA && (AUTO_SIG.buys.size || AUTO_SIG.sells.size)) v.auto_analysis = { buy_markers: AUTO_SIG.buys.size, sell_markers: AUTO_SIG.sells.size };
      return v;
    }
    function chartImageUrl() { try { return chart && chart.getConvertPictureUrl ? chart.getConvertPictureUrl(true, "png", "#ffffff") : null; } catch (_) { return null; } }
    async function buildClientBundle() {
      await Promise.all([
        SIG_CACHE.spx ? 0 : aJson("signals_spx.json").then((d) => { if (d) SIG_CACHE.spx = d; }),
        SIG_CACHE.ndx ? 0 : aJson("signals_ndx.json").then((d) => { if (d) SIG_CACHE.ndx = d; }),
        ANALYST_PROMPT != null ? 0 : fetch("analyst_prompt.md").then((r) => r.text()).then((t) => { ANALYST_PROMPT = t; }).catch(() => { ANALYST_PROMPT = ""; }),
      ]);
      const [psp, pnd, osp, ond, news, lsp, lnd, lvix] = await Promise.all([
        getAsset("spx"), getAsset("ndx"), aJson("latest_signal.json"), aJson("latest_ndx_signal.json"),
        aJson("news_score.json"), liveQuote("spx"), liveQuote("ndx"), liveQuote("vix")]);
      const health = [];
      const block = (id, pj, oj, live) => {
        const sj = SIG_CACHE[id]; if (!sj || !pj || !pj.close) { health.push({ check: id + " data", status: "FAIL", detail: "signals or price file missing" }); return null; }
        const c = pj.close.slice(); if (live) c[c.length - 1] = live;
        const month = +String((pj.dates || [])[pj.dates.length - 1] || "").slice(5, 7);
        const sigs = sj.signals.map((s) => Object.assign({}, s, { st: dashEval(s, c, month, lvix) }));
        const k = dashComposite(sigs);
        const comp = { net: k.net, label: k.label, suggested_leverage: k.lev, risk_budget: k.budget, longs: k.longs, total_votes: k.votes, price: Math.round((live || c[c.length - 1]) * 100) / 100, vix: lvix, asof: live ? "live" : "snapshot" };
        const dd = daysSince((pj.dates || [])[pj.dates.length - 1]);
        health.push({ check: id + " price freshness", status: dd != null && dd <= 5 ? "PASS" : (dd != null && dd <= 14 ? "WARN" : "FAIL"), detail: "last bar " + (pj.dates || [])[pj.dates.length - 1] + " (" + dd + "d)" });
        health.push({ check: id + " live fetch", status: live ? "PASS" : "WARN", detail: live ? id.toUpperCase() + " " + nfmt(live) : "worker unreachable; snapshot close" });
        return { label: sj.asset_label, current: comp, benchmark: sj.benchmark, official_signal: (oj && oj.official_signal) || {},
          signals: sigs.map((s) => ({ id: s.id, name: s.name, grade: s.grade, kind: s.kind, reliability: s.reliability, why: s.why, state: s.st, evidence: { sharpe: s.evidence.sharpe, calmar: s.evidence.calmar, maxdd: s.evidence.maxdd, beats_bh: s.evidence.beats_bh, strategy_label: s.evidence.strategy_label, sample: s.evidence.sample } })) };
      };
      health.push({ check: "live VIX fetch", status: lvix ? "PASS" : "WARN", detail: lvix ? "VIX " + lvix.toFixed(1) : "worker unreachable; no live VIX" });
      return { generated_at: new Date().toISOString(), scope: ["spx", "ndx"], data_health: health,
        assets: { spx: block("spx", psp, osp, lsp), ndx: block("ndx", pnd, ond, lnd) },
        chart_view: buildChartView(),   // the chart the user is currently looking at
        chart_image: chartImageUrl(),   // PNG data URL (worker vision / copy-image button); stripped from the copy text
        news: news ? { score: news.score, label: news.label, explanation: news.explanation } : null };
    }
    function mdToHtml(md) {
      const lines = esc(md).split(/\r?\n/); let html = "", inList = false; const close = () => { if (inList) { html += "</ul>"; inList = false; } };
      for (let ln of lines) {
        ln = ln.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`(.+?)`/g, "<code>$1</code>");
        if (/^### /.test(ln)) { close(); html += `<h4 style="margin:12px 0 4px;font-size:14px">${ln.slice(4)}</h4>`; }
        else if (/^## /.test(ln)) { close(); html += `<h3 style="margin:14px 0 6px;font-size:16px">${ln.slice(3)}</h3>`; }
        else if (/^# /.test(ln)) { close(); html += `<h3 style="margin:14px 0 6px;font-size:16px">${ln.slice(2)}</h3>`; }
        else if (/^[-*] /.test(ln)) { if (!inList) { html += `<ul style="margin:4px 0 8px 20px">`; inList = true; } html += `<li>${ln.slice(2)}</li>`; }
        else if (ln.trim() === "") close();
        else { close(); html += `<p style="margin:6px 0">${ln}</p>`; }
      }
      close(); return html;
    }
    function analystAssetHtml(a) {
      if (!a || !a.current) return "";
      const c = a.current, off = a.official_signal || {};
      const top = (a.signals || []).filter((s) => s.grade === "A" || s.grade === "B").slice(0, 5).map((s) => { const st = s.state, isL = st && st.dir > 0; return `<li style="margin:2px 0"><b style="color:${isL ? UP : "#6e6e73"}">${isL ? "long" : "cash"}</b> · ${esc(s.name)} <span style="color:#8a8a8e">— grade ${s.grade}${st ? ", " + esc(st.read) : ""}</span></li>`; }).join("");
      let div = "";
      if (c.suggested_leverage != null && off.targetLeverage != null) {
        div = c.suggested_leverage !== off.targetLeverage
          ? `<div style="font-size:12.5px;color:#444;margin-top:6px;background:#fff7e6;border:1px solid #f0d9a0;border-radius:8px;padding:7px 10px">Composite <b>${c.suggested_leverage}×</b> vs official mechanical <b>${off.targetLeverage}×</b>${off.regime ? " (" + esc(off.regime) + ")" : ""} — ${esc(off.explanation || "the mechanical rule is the more conservative trade.")}</div>`
          : `<div style="font-size:12.5px;color:#444;margin-top:6px">Composite agrees with the official mechanical signal at <b>${off.targetLeverage}×</b>.</div>`;
      }
      const stCol = c.net >= 0.25 ? UP : (c.net <= -0.25 ? DN : "#6e6e73");
      return `<div style="margin:12px 0 4px;padding-top:10px;border-top:1px solid var(--line)">
        <div style="font-size:15px;font-weight:700;color:#1d1d1f">${esc(a.label)} — <span style="color:${stCol}">${esc(c.label)}</span> · net ${c.net >= 0 ? "+" : ""}${(+c.net).toFixed(2)} · suggested ${(+c.suggested_leverage).toFixed(1)}× · ${c.longs}/${c.total_votes} long${c.asof === "snapshot" ? ' <span class="meta">(snapshot — worker offline)</span>' : ""}</div>
        <ul style="margin:6px 0 4px 20px;font-size:13px;color:#333">${top}</ul>${div}</div>`;
    }
    function analystReportHtml(b) {
      const hc = (s) => ({ PASS: "#248a3d", WARN: "#b8860b", FAIL: "#d70015" }[s] || "#6e6e73");
      const worst = (b.data_health || []).some((h) => h.status === "FAIL") ? "FAIL" : ((b.data_health || []).some((h) => h.status === "WARN") ? "WARN" : "PASS");
      const health = (b.data_health || []).map((h) => `<span style="display:inline-flex;align-items:center;gap:5px;font-size:11.5px;margin:2px 10px 2px 0"><span style="width:7px;height:7px;border-radius:50%;background:${hc(h.status)}"></span>${esc(h.check)}</span>`).join("");
      const assets = ["spx", "ndx"].map((id) => analystAssetHtml(b.assets && b.assets[id])).join("");
      const cv = b.chart_view;
      const cvLine = cv ? `<div style="font-size:12px;color:#444;margin:8px 0 2px;background:#f0f6ff;border:1px solid #d7e6fb;border-radius:8px;padding:7px 10px">📈 Reading your chart: <b>${esc(cv.label)}</b> · ${esc(cv.timeframe)}${cv.visible ? " · " + cv.visible.bars_shown + " bars " + esc(cv.visible.from_date) + "→" + esc(cv.visible.to_date) : ""}${(cv.drawings && cv.drawings.length) ? " · <b>" + cv.drawings.length + "</b> of your drawings" : ""}${(cv.active_overlays && cv.active_overlays.length) ? " · overlays: " + esc(cv.active_overlays.map((o) => o.indicator).join(", ")) : ""}${b.chart_image ? " · screenshot captured" : ""}</div>` : "";
      const news = b.news ? `<p class="meta" style="margin:10px 0 0">News (7d): <b>${esc(b.news.label || "")}</b> ${b.news.score != null ? "(" + b.news.score + "/10)" : ""} — colour only, not a signal.</p>` : "";
      const gen = ANALYST_WORKER ? `<button id="analystGen" class="seg" style="padding:9px 14px;font-weight:700">✨ Generate AI assessment</button>` : "";
      const copyBtns = b.chart_image
        ? `<button id="analystCopyBoth" class="seg" style="padding:9px 14px;font-weight:700">📋 Copy prompt + chart image</button><button id="analystCopy" class="seg" style="padding:9px 14px">Prompt only</button><button id="analystImg" class="seg" style="padding:9px 14px">Image only</button>`
        : `<button id="analystCopy" class="seg" style="padding:9px 14px;font-weight:700">📋 Copy analyst prompt</button>`;
      return `<div style="margin-bottom:4px"><span style="font-size:11px;font-weight:700;color:${hc(worst)};text-transform:uppercase">Data health: ${worst}</span><div style="margin-top:4px">${health}</div></div>${cvLine}${assets}${news}
        <div id="analystNarr" style="margin-top:10px"></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:14px;border-top:1px solid var(--line);padding-top:12px">${gen}${copyBtns}</div>
        <p class="meta" style="margin:10px 0 0">${ANALYST_WORKER ? "One click runs Claude on the server. " : ""}Paste into any Claude chat — the prompt drops in as text and the chart attaches as an image. If a chat only takes one per paste, use <b>Prompt only</b> / <b>Image only</b>. Same quality as the API. Educational only — not advice.</p>`;
    }
    async function callAnalystWorker(bundle) {
      if (!ANALYST_WORKER) return null;
      try { const r = await fetch(ANALYST_WORKER, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(bundle) }); if (!r.ok) return null; const j = await r.json(); return j.markdown || j.text || null; } catch (_) { return null; }
    }
    async function openAnalyst() {
      const old = $("analystOv"); if (old) old.remove();
      const ov = document.createElement("div"); ov.id = "analystOv";
      ov.style.cssText = "position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,.45);display:flex;align-items:flex-start;justify-content:center;padding:24px 16px;overflow:auto;";
      ov.innerHTML = `<div style="background:#fff;border-radius:16px;max-width:680px;width:100%;padding:22px 24px;box-shadow:0 24px 70px rgba(0,0,0,.32)"><div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:6px"><h3 style="margin:0;font-size:20px;color:#1d1d1f">🧠 Market Analyst</h3><button id="analystX" style="border:0;background:#f0f0f3;border-radius:50%;width:30px;height:30px;font-size:18px;cursor:pointer;color:#48484a">×</button></div><div id="analystBody"><p class="meta">Pulling live data, validating it, and reading every signal…</p></div></div>`;
      document.body.appendChild(ov); ov.onclick = (e) => { if (e.target === ov) ov.remove(); }; $("analystX").onclick = () => ov.remove();
      document.addEventListener("keydown", function k(e) { if (e.key === "Escape") { ov.remove(); document.removeEventListener("keydown", k); } });
      let bundle; try { bundle = await buildClientBundle(); } catch (e) { const bd = $("analystBody"); if (bd) bd.innerHTML = `<p class="meta">Analyst failed to assemble the data: ${esc(e.message || e)}</p>`; return; }
      const body = $("analystBody"); if (!body) return; body.innerHTML = analystReportHtml(bundle);
      const cp = $("analystCopy"); if (cp) cp.onclick = () => { const slim = Object.assign({}, bundle); delete slim.chart_image; const imgNote = bundle.chart_image ? "\n\n(A screenshot of the chart the user is viewing is available — click \"Copy chart image\" and paste it alongside this for a visual read.)" : ""; const text = (ANALYST_PROMPT || "") + "\n\n---\n## analyst_bundle (live data)\n```json\n" + JSON.stringify(slim, null, 2) + "\n```" + imgNote + "\n\nProduce the assessment now, following the system prompt above."; navigator.clipboard.writeText(text).then(() => { cp.textContent = "✓ Copied — paste into any Claude chat"; }).catch(() => { cp.textContent = "copy failed — select & copy the page data"; }); };
      const ib = $("analystImg"); if (ib && bundle.chart_image) ib.onclick = async () => { try { const blob = await (await fetch(bundle.chart_image)).blob(); await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]); ib.textContent = "✓ Image copied — paste into Claude"; } catch (_) { const a = document.createElement("a"); a.href = bundle.chart_image; a.download = (D.id || "chart") + ".png"; a.click(); ib.textContent = "✓ Image downloaded"; } };
      const cb = $("analystCopyBoth"); if (cb && bundle.chart_image) cb.onclick = async () => {
        const slim = Object.assign({}, bundle); delete slim.chart_image;
        const text = (ANALYST_PROMPT || "") + "\n\n---\n## analyst_bundle (live data)\n```json\n" + JSON.stringify(slim, null, 2) + "\n```\n\nA screenshot of the chart the user is viewing is attached — read it visually. Produce the assessment now, following the system prompt above.";
        try {
          if (!window.ClipboardItem) throw new Error("no ClipboardItem");
          const imgBlob = await (await fetch(bundle.chart_image)).blob();
          await navigator.clipboard.write([new ClipboardItem({ "text/plain": new Blob([text], { type: "text/plain" }), "image/png": imgBlob })]);
          cb.textContent = "✓ Copied prompt + image — paste into Claude";
        } catch (_) { try { await navigator.clipboard.writeText(text); cb.textContent = "✓ Prompt copied — use ‘Image only’ for the chart"; } catch (e2) { cb.textContent = "copy failed"; } }
      };
      const gen = $("analystGen"); if (gen) gen.onclick = async () => { gen.disabled = true; gen.textContent = "Generating…"; const md = await callAnalystWorker(bundle); if (md) { $("analystNarr").innerHTML = `<div style="background:#f7f9fc;border:1px solid var(--line);border-radius:12px;padding:14px 16px">${mdToHtml(md)}</div>`; gen.textContent = "✓ AI assessment generated"; } else { gen.textContent = "AI worker unavailable — use Copy prompt"; gen.disabled = false; } };
    }
    if ($("analystBtn")) $("analystBtn").onclick = openAnalyst;

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
        { const ct = $("cTitle"); if (ct) ct.textContent = D.label + " — chart"; document.title = D.label + " — chart"; } // on-page title was removed for space; keep the browser-tab title per asset
        if ($("rngFrom") && D.dates.length) { $("rngFrom").min = $("rngTo").min = D.dates[0]; $("rngFrom").max = $("rngTo").max = D.dates[D.n - 1]; $("rngFrom").value = ""; $("rngTo").value = ""; }
        D.daily = d.close.map((c, i) => ({ timestamp: d.timestamp[i], open: d.open[i], high: d.high[i], low: d.low[i], close: c, volume: d.volume ? d.volume[i] : 0 }));
        safe(() => chart.removeOverlay()); drawings = []; removeStudySignals();
        applyTF(); loadNotes(); fetchLive(); renderPlaybook(); renderLeader(); renderCurve(); syncPnlUI(); loadDashboard(id);
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
