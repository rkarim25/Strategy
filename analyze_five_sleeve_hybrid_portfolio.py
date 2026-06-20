"""Five-sleeve portfolio: US full Guarded lev, others max 1x."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from analyze_cross_asset_guarded_1x import guarded_lead_leverage
from analyze_multi_asset_guarded_scan import panel_for_close
from engine import INITIAL_CAPITAL, PortfolioEngine, TRADING_COST_FROM_MID_PCT
from metrics import comprehensive_stats
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD

TICKERS = {"SPX": "^GSPC", "Nasdaq": "^NDX", "FTSE250": "^FTMC", "EM": "EEM", "Gold": "GLD"}
WEIGHTS = {"SPX": 0.40, "Nasdaq": 0.15, "FTSE250": 0.16, "EM": 0.14, "Gold": 0.15}


def guarded_returns(panel: pd.DataFrame, max_lev: float) -> pd.Series:
    """Use equity.pct_change(); engine.daily_returns omits costs/inflows."""
    eng = PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )
    lev, _ = guarded_lead_leverage(panel, max_leverage=max_lev)
    equity = eng.run(panel, lev, name="g").equity
    return equity.pct_change().fillna(0.0).dropna()


def combine(R: pd.DataFrame, weights: dict) -> pd.Series:
    w = pd.Series(weights).reindex(R.columns) / pd.Series(weights).sum()
    return (R * w).sum(axis=1)


def stats(daily: pd.Series) -> str:
    eq = (1 + daily).cumprod() * INITIAL_CAPITAL
    s = comprehensive_stats(eq, daily)
    return (
        f"CAGR {s['cagr']*100:.1f}% | vol {s['volatility']*100:.1f}% | "
        f"Sharpe {s['sharpe']:.2f} | max DD {s['max_drawdown']*100:.1f}%"
    )


def main() -> None:
    end = datetime.today()
    start = end - timedelta(days=int(30 * 365.25))
    raw = yf.download(list(TICKERS.values()) + ["^IRX"], start=start.strftime("%Y-%m-%d"), auto_adjust=True, progress=False)
    closes = raw["Close"].sort_index().ffill()
    tbill = closes["^IRX"] / 100

    configs = {
        "SPX": 3.0,
        "Nasdaq": 3.0,
        "FTSE250": 1.0,
        "EM": 1.0,
        "Gold": 1.0,
    }
    all_1x = {k: 1.0 for k in TICKERS}
    R_hybrid, R_1x = {}, {}
    for name, tic in TICKERS.items():
        panel = panel_for_close(closes[tic].dropna(), tbill)
        R_hybrid[name] = guarded_returns(panel, configs[name])
        R_1x[name] = guarded_returns(panel, 1.0)
    H = pd.DataFrame(R_hybrid).dropna(how="any")
    O = pd.DataFrame(R_1x).dropna(how="any")
    print(f"Window: {H.index[0].date()} -> {H.index[-1].date()}\n")
    print("Hybrid (US full lev, others 1x):", stats(combine(H, WEIGHTS)))
    print("All sleeves max 1x:           ", stats(combine(O, WEIGHTS)))
    print("All sleeves full lev:         ", end=" ")
    R_full = {}
    for name, tic in TICKERS.items():
        panel = panel_for_close(closes[tic].dropna(), tbill)
        R_full[name] = guarded_returns(panel, 3.0)
    print(stats(combine(pd.DataFrame(R_full).dropna(how="any"), WEIGHTS)))


if __name__ == "__main__":
    main()
