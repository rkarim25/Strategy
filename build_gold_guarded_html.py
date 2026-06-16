"""Build gold_guarded.html from ndx_guarded.html (Gold tab, max 1x default).

The Gold page is a label/copy transform of the Nasdaq 100 Guarded page:
asset-specific text is swapped for gold, the runtime-hydrated tables are reset
to their placeholder state (live numbers load from gold_guarded_site_data.json
at runtime, not from this scaffold), and the script tags switch from the NDX
bundle to gold_guarded.js (dropping etp-leverage.js, which the max-1x tab does
not use).

Every transform is guarded: if an expected pattern is missing the build aborts
with a clear error rather than silently emitting a half-converted page. That is
the tripwire that flags drift when ndx_guarded.html is regenerated.

NOTE: the static "Legacy Guard SMA Sensitivity" (A10/B20) table holds
asset-specific figures that a label swap cannot derive. This builder leaves the
NDX figures in place; restore the gold figures (or hydrate from JSON) before
publishing the regenerated page.

Run as a script to (re)write gold_guarded.html; importing the module has no
side effects.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "ndx_guarded.html"
DST = ROOT / "gold_guarded.html"

# Literal label / copy swaps applied in order. Each (old, new): `old` must exist
# in the source or the build aborts. Order matters where one pattern is a
# substring of another -- the NDX aria-labels and the base-trend rule are
# rewritten before the bare "NDX close" legend swap so their text is consumed
# first.
REPLACEMENTS = [
    ("<title>Nasdaq 100 Guarded Strategy</title>", "<title>Strategy — Gold Guarded (max 1x)</title>"),
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
    ("Strategy equity (blue)", "Strategy return % (blue)"),
    ("NDX reference (orange)", "Gold return % (orange)"),
    ("2x trigger (A)</th><td>-5% drawdown from Nasdaq 100 high-water close",
     "2x trigger (A)</th><td>-5% drawdown from GC=F high-water close"),
    ("3x trigger (B)</th><td>-25% drawdown from Nasdaq 100 high-water close",
     "3x trigger (B)</th><td>-25% drawdown from GC=F high-water close"),
    (
        "These results use the project backtest engine with <strong>listed 2x/3x ETP daily returns</strong> "
        "(QQQ/LQQ/LQQ3 or listed Nasdaq 100 ETPs) when available, synthetic daily-reset fill before ETP inception, "
        "$100 starting capital, $10 fixed annual inflows, and 0.10% rebalance cost on leverage changes.",
        "These results use the project backtest engine with $100 starting capital, $10 fixed annual inflows, "
        "0.10% rebalance cost, and the engine funding-cost model. The default strategy is "
        "<strong>Guarded A5/B25 SMA20 Lead</strong>: base 1x exposure is allowed only above SMA20, while "
        "recovery tiers arm at -5% / -25% but exposure stays at <strong>1x max</strong> when the lead guard passes.",
    ),
    ("Calmar = CAGR / absolute max drawdown; multiple = end value divided by discounted contributions.",
     "Calmar = CAGR / absolute max drawdown. Full comparison table and equity chart below use the same engine assumptions as the SPX dashboard."),
    ("Loading static historical back-test data...",
     "Loading static historical back-test data. Chart shows cumulative return (%) from 0% at the start of the selected range."),
    ("NDX vs Default Strategy Equity", "Gold vs Default Strategy Equity"),
    ("historical NDX daily closes", "historical GC=F daily closes"),
    ("NDX buy-and-hold", "Gold buy-and-hold"),
    ("Nasdaq 100 and T-bill", "gold (GC=F) and T-bill"),
]


def _sub_once(pattern: str, repl: str, html: str, what: str, flags: int = 0) -> str:
    """re.sub that must replace exactly once, else abort (drift tripwire)."""
    html, n = re.subn(pattern, repl, html, count=1, flags=flags)
    if n != 1:
        raise SystemError(f"build_gold_guarded_html: {what} (matched {n} times, expected 1)")
    return html


def build() -> str:
    html = SRC.read_text(encoding="utf-8")

    for old, new in REPLACEMENTS:
        if old not in html:
            raise SystemError(f"build_gold_guarded_html: missing pattern: {old!r}")
        html = html.replace(old, new)

    # Recovery tiers are capped at 1x on this tab -- annotate both list items.
    for tier in ("2x", "3x"):
        marker = f"<li><strong>{tier} recovery tier:</strong>"
        if marker not in html:
            raise SystemError(f"build_gold_guarded_html: missing pattern: {marker!r}")
        html = html.replace(marker, f"<li><strong>{tier} recovery tier (capped at 1x on site):</strong>")

    # Drop the two static, NDX-only KPI cards (no id, not hydrated, absent on the
    # gold page). Match on the stable labels so changing figures don't break it.
    html = _sub_once(
        r'\s*<div class="metric-card"><span class="small">Contribution NPV</span>.*?</div>'
        r'\s*<div class="metric-card"><span class="small">End / NPV multiple</span>.*?</div>',
        "",
        html,
        "could not drop NDX NPV metric cards",
        flags=re.S,
    )

    # Reset the runtime-hydrated tables to placeholders. gold_guarded.js fills
    # these from JSON at load; resetting keeps the scaffold asset-neutral and
    # strips the NDX/ETP diagnostics copy regardless of the committed numbers.
    html = _sub_once(
        r'<tbody id="diagnosticsBody">.*?</tbody>',
        '<tbody id="diagnosticsBody"><tr><td colspan="4">Loading…</td></tr></tbody>',
        html,
        "could not reset diagnosticsBody",
        flags=re.S,
    )
    for prob_id in ("mcProbDd35", "mcProbDd40", "mcProbDd50", "mcProbBelowStart"):
        html = _sub_once(
            rf'(<td id="{prob_id}">)[^<]*(</td>)',
            r"\1-\2",
            html,
            f"could not reset {prob_id}",
        )

    # Script tags: the max-1x gold tab drops etp-leverage.js and loads
    # gold_guarded.js in place of ndx_guarded.js (keeping the cache version).
    html = _sub_once(
        r'\n[^\n]*<script src="etp-leverage\.js[^"]*"></script>',
        "",
        html,
        "could not drop etp-leverage.js script tag",
    )
    if 'src="ndx_guarded.js?v=' not in html:
        raise SystemError("build_gold_guarded_html: missing ndx_guarded.js script tag")
    html = html.replace('src="ndx_guarded.js?v=', 'src="gold_guarded.js?v=')

    # Safety net: no Nasdaq/NDX asset labels (or the NDX script/page references)
    # should survive into the gold page.
    leftovers = [tok for tok in ("Nasdaq", "NDX", "^NDX", "ndx_guarded") if tok in html]
    if leftovers:
        raise SystemError(f"build_gold_guarded_html: leftover NDX tokens after transform: {leftovers}")

    return html


def main() -> None:
    html = build()
    DST.write_text(html, encoding="utf-8")
    print(f"Wrote {DST.name} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
