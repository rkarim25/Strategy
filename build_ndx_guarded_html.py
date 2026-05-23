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


def placeholder_strong(html: str, element_id: str, fallback: str = "-") -> str:
    return re.sub(
        rf'(<strong id="{re.escape(element_id)}">)[^<]*(</strong>)',
        rf"\1{fallback}\2",
        html,
        count=1,
    )


signal_inner = extract('id="signalPage"', 'id="backtestPage"')
signal_truncated = False
for marker in (
    '<section class="card section-gap">\n    <h2>Guarded Strategy Calculator</h2>',
    '<section class="card section-gap">\n    <h2>Parameter Optimizer</h2>',
):
    if marker in signal_inner:
        signal_inner = signal_inner[: signal_inner.index(marker)]
        signal_truncated = True
# Truncating before calculator/optimizer removes index.html's closing </section> for signalPage.
# Without it, backtest/monte-carlo nest inside signalPage and stay hidden (.page { display: none }).
if signal_truncated:
    signal_inner = signal_inner.rstrip() + "\n\n  </section>\n"

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
backtest_inner = backtest_inner.replace(
    "(SPYL/XS2D/3USL)",
    "(QQQ/LQQ/LQQ3 or listed Nasdaq 100 ETPs)",
)
for kid in (
    "kpiDefaultCagr",
    "kpiDefaultMaxDd",
    "kpiDefaultSharpe",
    "kpiDefaultVol",
    "kpiDefaultCalmar",
    "kpiDefaultEnd",
):
    backtest_inner = placeholder_strong(backtest_inner, kid)
backtest_inner = re.sub(
    r"<tbody>\s*<tr><td>Buy.*?</tbody>",
    '<tbody id="comparisonTableBody"><tr><td colspan="8">Loading…</td></tr></tbody>',
    backtest_inner,
    count=1,
    flags=re.S,
)
backtest_inner = re.sub(
    r"Full sample: <span id=\"backtestSampleRange\">[^<]*</span>",
    'Full sample: <span id="backtestSampleRange">-</span>',
    backtest_inner,
    count=1,
)
backtest_inner = backtest_inner.replace("SPX vs Default Strategy Equity", "NDX vs Default Strategy Equity")
backtest_inner = backtest_inner.replace("SPX buy-and-hold", "NDX buy-and-hold")
backtest_inner = re.sub(
    r'<p id="backtestCallout" class="callout">.*?</p>',
    '<p id="backtestCallout" class="callout">Loading back-test summary…</p>',
    backtest_inner,
    count=1,
    flags=re.S,
)

mc_inner = extract('id="monteCarloPage"', 'id="instrumentsPage"')
mc_inner = mc_inner.replace("S&amp;P and T-bill", "Nasdaq 100 and T-bill")
for kid in ("mcMedianCagr", "mcMedianMaxDd"):
    mc_inner = placeholder_strong(mc_inner, kid)
mc_inner = re.sub(
    r"<tr><td>Probability max drawdown is worse than -35%</td><td>[^<]*</td></tr>",
    '<tr><td>Probability max drawdown is worse than -35%</td><td id="mcProbDd35">-</td></tr>',
    mc_inner,
    count=1,
)
mc_inner = re.sub(
    r"<tr><td>Probability max drawdown is worse than -40%</td><td>[^<]*</td></tr>",
    '<tr><td>Probability max drawdown is worse than -40%</td><td id="mcProbDd40">-</td></tr>',
    mc_inner,
    count=1,
)
mc_inner = re.sub(
    r"<tr><td>Probability max drawdown is worse than -50%</td><td>[^<]*</td></tr>",
    '<tr><td>Probability max drawdown is worse than -50%</td><td id="mcProbDd50">-</td></tr>',
    mc_inner,
    count=1,
)
mc_inner = re.sub(
    r"<tr><td>Probability ending below starting capital</td><td>[^<]*</td></tr>",
    '<tr><td>Probability ending below starting capital</td><td id="mcProbBelowStart">-</td></tr>',
    mc_inner,
    count=1,
)
mc_inner = re.sub(
    r"<tbody>\s*<tr><td>Lead 0\.75.*?</tbody>",
    '<tbody id="mcComparisonBody"><tr><td colspan="8">Loading Monte Carlo summary…</td></tr></tbody>',
    mc_inner,
    count=1,
    flags=re.S,
)
mc_inner = re.sub(
    r"<tbody>\s*<tr><td>Cash days</td>.*?</tbody>",
    '<tbody id="diagnosticsBody"><tr><td colspan="4">Loading…</td></tr></tbody>',
    mc_inner,
    count=1,
    flags=re.S,
)

strategy_nav = """
  <nav class="site-nav" aria-label="Strategies">
    <a class="site-nav-link" href="index.html#signalPage">Guarded A5/B25 SMA20 Lead (SPX)</a>
    <a class="site-nav-link active" href="ndx_guarded.html#signalPage" aria-current="page">Guarded A5/B25 (Nasdaq 100)</a>
    <a class="site-nav-link" href="gold_guarded.html#signalPage">Guarded A5/B25 (Gold, max 1x)</a>
    <a class="site-nav-link" href="ftse250_guarded.html#signalPage">Guarded A5/B25 (FTSE 250, max 1x)</a>
    <a class="site-nav-link" href="msci_em_guarded.html#signalPage">Guarded A5/B25 (MSCI EM, max 1x)</a>
    <a class="site-nav-link" href="dax_guarded.html#signalPage">Guarded A5/B25 (DAX, max 1x)</a>
    <a class="site-nav-link" href="msci_world_guarded.html#signalPage">Guarded A5/B25 (MSCI World, max 1x)</a>
    <a class="site-nav-link" href="index.html#momentumSignalPage">Momentum Strategy Research</a>
  </nav>
""".strip()

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

{strategy_nav}

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
