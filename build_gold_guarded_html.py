"""Build gold_guarded.html from ndx_guarded.html (Gold tab, max 1x default)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "ndx_guarded.html"
DST = ROOT / "gold_guarded.html"

REPLACEMENTS = [
    ("Strategy — Nasdaq 100 Guarded", "Strategy — Gold Guarded (max 1x)"),
    ('href="ndx_guarded.html#signalPage" aria-current="page">Guarded A5/B25 (Nasdaq 100)</a>',
     'href="ndx_guarded.html#signalPage">Guarded A5/B25 (Nasdaq 100)</a>'),
    ('href="index.html#momentumSignalPage">Momentum Strategy Research</a>',
     'href="gold_guarded.html#signalPage" aria-current="page">Guarded A5/B25 (Gold, max 1x)</a>\n'
     '    <a class="site-nav-link" href="index.html#momentumSignalPage">Momentum Strategy Research</a>'),
    ("Guarded A5/B25 SMA20 Lead Signal (Nasdaq 100)", "Guarded A5/B25 SMA20 Lead Signal (Gold, max 1x)"),
    (
        "Levered <strong>Guarded A5/B25/X40/Y15 SMA20 Lead</strong> on <code>^NDX</code> (Nasdaq 100), mirroring the SPX default parameters.",
        "Guarded <strong>A5/B25/X40/Y15 SMA20 Lead</strong> on <code>GC=F</code> (COMEX gold continuous futures). "
        "Recovery tiers still arm at -5% / -25%, but <strong>max leverage is capped at 1x</strong> on this tab "
        "(no 2x/3x exposure). Price history is a rolled futures series, not a spot ETF.",
    ),
    ("hold <strong>1x</strong> Nasdaq 100 exposure only when the NDX close is above the 20-day SMA",
     "hold <strong>1x</strong> gold exposure only when the GC=F close is above the 20-day SMA"),
    ("if the Nasdaq 100 is down", "if gold is down"),
    ("from its closing high-water mark", "from its GC=F closing high-water mark"),
    ("after the Nasdaq 100 rises", "after gold rises"),
    ("delayed NDX quote", "delayed gold quote"),
    ("Optional NDX live", "Optional GC=F live"),
    ("manual NDX level", "manual gold level"),
    ("NDX Close vs 20-Day SMA", "Gold (GC=F) Close vs 20-Day SMA"),
    ('aria-label="NDX close and 20-day SMA chart"', 'aria-label="GC=F close and 20-day SMA chart"'),
    ('aria-label="NDX buy and hold versus default strategy equity chart"', 'aria-label="Gold buy and hold versus default strategy equity chart"'),
    ("NDX close", "GC=F close"),
    ("NDX return % (orange)", "Gold return % (orange)"),
    ("2x trigger (A)</th><td>-5% drawdown from Nasdaq 100 high-water close",
     "2x trigger (A)</th><td>-5% drawdown from GC=F high-water close"),
    ("3x trigger (B)</th><td>-25% drawdown from Nasdaq 100 high-water close",
     "3x trigger (B)</th><td>-25% drawdown from GC=F high-water close"),
    (
        "2x/3x exposure can start when price is within 0.75% below SMA20.",
        "recovery tiers arm at -5% / -25% but exposure stays at <strong>1x max</strong> when the lead guard passes.",
    ),
    ("NDX vs Default Strategy Equity", "Gold vs Default Strategy Equity"),
    ("historical NDX daily closes", "historical GC=F daily closes"),
    ("NDX buy-and-hold", "Gold buy-and-hold"),
    ("Nasdaq 100 and T-bill", "gold (GC=F) and T-bill"),
    ("S&amp;P 500 UCITS / ETP Instruments", "Gold &amp; Related Instruments"),
    (
        "Reference list of 1x, 2x, and 3x S&amp;P 500 products commonly used by UK and international (II) investors.",
        "Reference list of gold ETFs/ETCs for UK and international investors. Back-test and signal use "
        "<code>GC=F</code> futures; listed products track spot bullion with fees and roll differences.",
    ),
    ("ndx_guarded.js?v=20260522nav", "gold_guarded.js?v=20260522gold"),
]

html = SRC.read_text(encoding="utf-8")
for old, new in REPLACEMENTS:
    if old not in html:
        raise SystemError(f"build_gold_guarded_html: missing pattern: {old!r}")
    html = html.replace(old, new)

# Strategy rules: clarify 1x cap on recovery tiers
html = html.replace(
    "<li><strong>2x recovery tier:</strong>",
    "<li><strong>2x recovery tier (capped at 1x on site):</strong>",
)
html = html.replace(
    "<li><strong>3x recovery tier:</strong>",
    "<li><strong>3x recovery tier (capped at 1x on site):</strong>",
)

DST.write_text(html, encoding="utf-8")
print(f"Wrote {DST.name} ({len(html)} bytes)")
