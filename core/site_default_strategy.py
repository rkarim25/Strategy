"""Per-asset DEFAULT (site ★ pick) strategy for the Strategy-site asset pages.

Each asset page shows ONE default strategy (its best "Water"-style 1x/cash trend rule where one
exists, otherwise the best available trend rule). These specs drive both the Python backtest emitters
and — via core.guarded_site_series.strategy_params_for — the shared strategy_page.js renderer's
manual-price recompute. Slugs absent here fall back to the legacy Guarded A5/B25 default.

Picks (chosen from the comprehensive sweep in output/strategy_results/ + user confirmation):
  ftse250    SMA20 1x/cash               Water  (designated default; best Sharpe of 9 Water rules)
  dax        SMA200 ±3% Band 1x/cash     Water  (designated default; band family like SPX)
  msci_em    SMA100 1x/cash              best 1x/cash trend (no strict Water exists)
  msci_world SMA200 1x/cash              best 1x/cash trend (no strict Water exists)
  gold       SMA50/150 Golden Cross      Stillwater-Octane pick (CAGR 12.97%, DD −23%, Calmar 0.56,
                                         Sharpe beats buy-&-hold; the faster 150 slow-line recovers CAGR
                                         over 50/200 while keeping the drawdown protection)
  3bal       SMA20 1x/cash               site default (3x EURO STOXX Banks ETP, cash-vs-in)
  lqq3       SMA200 1x/cash              best trend on the 3x Nasdaq ETP (dedicated sweep: Sharpe 0.86,
                                         Calmar 0.71, halves the −79% buy-&-hold drawdown to −48%)
"""

from __future__ import annotations

SITE_DEFAULT_STRATEGY: dict[str, dict] = {
    "ftse250": {"name": "SMA20 1x/cash", "kind": "sma", "window": 20},
    "dax": {"name": "SMA200 ±3% Band 1x/cash", "kind": "band", "window": 200, "band_pct": 0.03},
    "msci_em": {"name": "SMA100 1x/cash", "kind": "sma", "window": 100},
    "msci_world": {"name": "SMA200 1x/cash", "kind": "sma", "window": 200},
    "gold": {"name": "SMA50/150 Golden Cross 1x/cash", "kind": "gc", "fast": 50, "slow": 150},
    "lqq3": {"name": "SMA200 1x/cash", "kind": "sma", "window": 200},
    "3bal": {"name": "SMA20 1x/cash", "kind": "sma", "window": 20},
}
