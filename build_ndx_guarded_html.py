"""Assemble ndx_guarded.html from index.html sections."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
index = (ROOT / "index.html").read_text(encoding="utf-8")
s0 = index.index("<style>")
s1 = index.index("</style>") + len("</style>")
styles = index[s0:s1]
lines = index.splitlines()


def extract(start_marker: str, end_marker: str) -> str:
    start = next(i for i, line in enumerate(lines) if start_marker in line)
    end = next(i for i, line in enumerate(lines) if end_marker in line and i > start)
    return "\n".join(lines[start:end])


signal_inner = extract('id="signalPage"', 'id="backtestPage"')
for marker in (
    '<section class="card section-gap">\n    <h2>Guarded Strategy Calculator</h2>',
    '<section class="card section-gap">\n    <h2>Parameter Optimizer</h2>',
):
    if marker in signal_inner:
        signal_inner = signal_inner[: signal_inner.index(marker)]

replacements = [
    ("SPX", "NDX"),
    ("S&amp;P", "Nasdaq 100"),
    ("Optional SPX live", "Optional NDX live"),
    ('aria-label="SPX close', 'aria-label="NDX close'),
    ("<span>SPX close</span>", "<span>NDX close</span>"),
    ("SPX reference (orange)", "NDX buy &amp; hold (orange)"),
    ("from S&amp;P high-water", "from NDX high-water"),
    ("enter a manual SPX level", "enter a manual NDX level"),
    ("delayed SPX quote", "delayed NDX quote (Yahoo ^NDX or manual)"),
]
for old, new in replacements:
    signal_inner = signal_inner.replace(old, new)

backtest_inner = extract('id="backtestPage"', 'id="monteCarloPage"')
backtest_inner = backtest_inner.replace("SPX", "NDX").replace("S&amp;P", "Nasdaq 100")
backtest_inner = backtest_inner.replace("<strong>39.09%</strong>", '<strong id="kpiDefaultCagr">-</strong>')
backtest_inner = backtest_inner.replace("<strong>-27.51%</strong>", '<strong id="kpiDefaultMaxDd">-</strong>')
backtest_inner = backtest_inner.replace("<strong>3.164</strong>", '<strong id="kpiDefaultSharpe">-</strong>')
backtest_inner = backtest_inner.replace("<strong>27.88%</strong>", '<strong id="kpiDefaultVol">-</strong>')
backtest_inner = backtest_inner.replace("<strong>$1,965,783</strong>", '<strong id="kpiDefaultEnd">-</strong>')
backtest_inner = re.sub(
    r"<tbody>\s*<tr><td>Buy.*?</tbody>",
    '<tbody id="comparisonTableBody"><tr><td colspan="8">Loading…</td></tr></tbody>',
    backtest_inner,
    count=1,
    flags=re.S,
)
backtest_inner = backtest_inner.replace(
    "1996-05-17 to 2026-05-15",
    '<span id="backtestSampleRange">-</span>',
)
backtest_inner = backtest_inner.replace("SPX vs Default Strategy Equity", "NDX vs Default Strategy Equity")
backtest_inner = backtest_inner.replace("SPX buy-and-hold", "NDX buy-and-hold")
backtest_inner = backtest_inner.replace(
    '<span class="spx">SPX reference (orange)</span>',
    '<span class="spx">NDX buy &amp; hold (orange)</span>',
)

mc_inner = extract('id="monteCarloPage"', 'id="momentumStrategy"')
mc_inner = mc_inner.replace("S&amp;P and T-bill", "Nasdaq 100 and T-bill")
mc_inner = mc_inner.replace("<strong>36.96%</strong>", '<strong id="mcMedianCagr">-</strong>')
mc_inner = mc_inner.replace("<strong>-28.18%</strong>", '<strong id="mcMedianMaxDd">-</strong>')
mc_inner = re.sub(
    r"<tr><td>Probability max drawdown is worse than -35%</td><td>22.0%</td></tr>",
    '<tr><td>Probability max drawdown is worse than -35%</td><td id="mcProbDd35">-</td></tr>',
    mc_inner,
)
mc_inner = re.sub(
    r"<tr><td>Probability max drawdown is worse than -40%</td><td>10.0%</td></tr>",
    '<tr><td>Probability max drawdown is worse than -40%</td><td id="mcProbDd40">-</td></tr>',
    mc_inner,
)
mc_inner = re.sub(
    r"<tr><td>Probability max drawdown is worse than -50%</td><td>1.5%</td></tr>",
    '<tr><td>Probability max drawdown is worse than -50%</td><td id="mcProbDd50">-</td></tr>',
    mc_inner,
)
mc_inner = re.sub(
    r"<tr><td>Probability ending below starting capital</td><td>0.0%</td></tr>",
    '<tr><td>Probability ending below starting capital</td><td id="mcProbBelowStart">-</td></tr>',
    mc_inner,
)
mc_inner = re.sub(
    r"<tbody>\s*<tr><td>Cash days</td>.*?</tbody>",
    '<tbody id="diagnosticsBody"><tr><td colspan="4">Loading…</td></tr></tbody>',
    mc_inner,
    count=1,
    flags=re.S,
)

html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Nasdaq 100 Guarded Strategy</title>
  <link rel="icon" type="image/svg+xml" href="favicon.svg" />
{styles}
</head>
<body>
<main>
  <h1>Strategy</h1>
  <p>
    A live dashboard and research library for systematic market strategies. Each strategy gets its own tab,
    with signal, back-test, and Monte Carlo validation shown separately.
  </p>

  <nav class="site-nav" aria-label="Strategies">
    <a class="site-nav-link" href="index.html#signalPage">Guarded A5/B25 SMA20 Lead (SPX)</a>
    <a class="site-nav-link active" href="ndx_guarded.html#signalPage" aria-current="page">Guarded A5/B25 (Nasdaq 100)</a>
    <a class="site-nav-link" href="index.html#momentumSignalPage">Momentum Strategy Research</a>
  </nav>

  <section id="guardedStrategy" class="strategy active">
  <section class="card" style="margin-bottom: 18px;">
    <h2>Guarded A5/B25 SMA20 Lead Signal (Nasdaq 100)</h2>
    <p>
      Levered <strong>Guarded A5/B25/X40/Y15 SMA20 Lead</strong> on <code>^NDX</code> (Nasdaq 100), mirroring the SPX default parameters.
      Buy-and-hold reference: <strong id="kpiBhCagr">-</strong> CAGR, <strong id="kpiBhMaxDd">-</strong> max drawdown.
    </p>
    <p id="siteDataGenerated" class="small"></p>
    <nav class="site-nav" aria-label="Guarded strategy sections">
      <button type="button" class="active" data-page-target="signalPage">Signal</button>
      <button type="button" data-page-target="backtestPage">Back-test</button>
      <button type="button" data-page-target="monteCarloPage">Monte Carlo</button>
    </nav>
  </section>
{signal_inner}
{backtest_inner}
{mc_inner}
  </section>
</main>
<script src="site-nav.js"></script>
<script src="ndx_guarded.js"></script>
</body>
</html>
"""
(ROOT / "ndx_guarded.html").write_text(html, encoding="utf-8")
print(f"Wrote ndx_guarded.html ({len(html)} bytes)")
