"""SMA20 guarded vs non-guarded on REAL 2x ETPs, max real-ETP history.

SPX 2x -> XS2D.L (real from 2010-03-18); NDX 2x -> LQQ.PA (real from 2008-01-02).
$100 start, $10/year fixed inflow, 1% rebalance cost (repo engine defaults).
Leverage capped at 2x so we can use the long 2x-ETP window (3x ETPs only list 2012+).
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import TRADING_COST_FROM_MID_PCT, PortfolioEngine  # noqa: E402
from etp_leverage import (  # noqa: E402
    NDX_ETP,
    SPX_ETP,
    EtpBundle,
    build_etp_return_panel,
    etp_coverage_summary,
)
from metrics import comprehensive_stats  # noqa: E402
from test_guarded_balanced_candidate import guarded_strategy_leverage  # noqa: E402
from test_tiered_dd_recovery_guarded import (  # noqa: E402
    ANNUAL_INFLOW_USD,
    BASE_SMA_WINDOW,
    sma_cash_leverage,
)

TBILL_TICKER = "^IRX"
DEFAULT_SPEC = dict(
    trigger_a=0.05, trigger_b=0.25, lead_pct_below_sma20=0.0075, x_return=0.40, y_return=0.15
)


def make_engine() -> PortfolioEngine:
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,  # $10/yr
    )


def _close(ticker: str) -> pd.Series:
    df = yf.download(ticker, period="max", auto_adjust=True, progress=False)
    return df["Close"].dropna().astype(float).squeeze()


def load_prices(index_ticker: str, etp_2x: str) -> tuple[pd.DataFrame, pd.Timestamp]:
    idx = _close(index_ticker)
    tb = _close(TBILL_TICKER)
    etp = _close(etp_2x)
    real_start = etp.index[0]  # first real 2x-ETP session
    idx.index = idx.index.tz_localize(None)
    tb.index = tb.index.tz_localize(None)
    prices = pd.DataFrame({"spx_close": idx, "tbill_rate": tb / 100.0})
    prices = prices.sort_index().ffill().dropna(how="any")
    prices = prices.loc[prices.index >= real_start.tz_localize(None)]
    return prices, real_start.tz_localize(None)


def run_one(name: str, prices: pd.DataFrame, lev: pd.Series, panel: pd.DataFrame) -> dict:
    res = make_engine().run(prices, lev, name=name, etp_returns=panel)
    s = comprehensive_stats(res.equity, res.daily_returns)
    lv = res.leverage
    return {
        "strategy": name,
        "start": prices.index[0].date().isoformat(),
        "end": prices.index[-1].date().isoformat(),
        "years": round((prices.index[-1] - prices.index[0]).days / 365.25, 1),
        "start_$": 100.0,
        "end_$": float(res.equity.iloc[-1]),
        "cagr": s["cagr"],
        "max_dd": s["max_drawdown"],
        "vol": s["volatility"],
        "sharpe": s["sharpe"],
        "pct_cash": float((lv <= 0).mean() * 100.0),
        "pct_1x": float(((lv > 0) & (lv < 1.5)).mean() * 100.0),
        "pct_2x": float((lv >= 1.5).mean() * 100.0),
        "rebal": res.rebalance_count,
    }


def analyse(asset_label: str, index_ticker: str, bundle: EtpBundle) -> list[dict]:
    prices, real_start = load_prices(index_ticker, bundle.etf_2x)
    panel = build_etp_return_panel(prices, bundle)
    cov = etp_coverage_summary(panel)
    print(
        f"\n### {asset_label}  via {bundle.etf_2x} (2x) + {bundle.etf_1x} (1x)\n"
        f"    window {prices.index[0].date()} -> {prices.index[-1].date()} "
        f"({len(prices)} sessions)  | real-2x coverage {cov['pct_real_2x']}%",
        flush=True,
    )

    # Non-guarded SMA20: above SMA20 -> 2x ETP, else cash
    lev_ng = sma_cash_leverage(prices, BASE_SMA_WINDOW, 2.0)
    # Guarded SMA20 (website default A5/B25 lead-0.75 X40/Y15), capped at 2x
    lev_g_raw, _ = guarded_strategy_leverage(prices, **DEFAULT_SPEC)
    lev_g = lev_g_raw.clip(upper=2.0)
    # References
    lev_bh2 = pd.Series(2.0, index=prices.index)
    lev_bh1 = pd.Series(1.0, index=prices.index)

    rows = [
        run_one(f"{asset_label} 2x  SMA20 non-guarded", prices, lev_ng, panel),
        run_one(f"{asset_label} 2x  SMA20 GUARDED (cap 2x)", prices, lev_g, panel),
        run_one(f"{asset_label} 2x  Buy&Hold (ref)", prices, lev_bh2, panel),
        run_one(f"{asset_label} 1x  Buy&Hold (ref)", prices, lev_bh1, panel),
    ]
    return rows


def fmt(rows: list[dict]) -> str:
    out = []
    hdr = (
        f"{'strategy':<34}{'start':>11}{'end':>12}{'yrs':>5}"
        f"{'CAGR':>8}{'maxDD':>8}{'vol':>8}{'Sharpe':>8}{'end $':>10}"
        f"{'%cash':>7}{'%1x':>6}{'%2x':>6}{'reb':>5}"
    )
    out.append(hdr)
    out.append("-" * len(hdr))
    for r in rows:
        out.append(
            f"{r['strategy']:<34}{r['start']:>11}{r['end']:>12}{r['years']:>5.1f}"
            f"{r['cagr']*100:>7.2f}%{r['max_dd']*100:>7.1f}%{r['vol']*100:>7.1f}%"
            f"{r['sharpe']:>8.2f}{r['end_$']:>10,.0f}"
            f"{r['pct_cash']:>6.1f}%{r['pct_1x']:>5.1f}%{r['pct_2x']:>5.1f}%{r['rebal']:>5d}"
        )
    return "\n".join(out)


def main() -> int:
    print(f"Run: {datetime.today().date()}  |  $100 start, $10/yr inflow, 1% rebalance cost")
    all_rows: list[dict] = []
    for label, idx, bundle in [
        ("SPX", "^GSPC", SPX_ETP),
        ("NDX", "^NDX", NDX_ETP),
    ]:
        rows = analyse(label, idx, bundle)
        print(fmt(rows))
        all_rows.extend(rows)
    out_csv = ROOT / "scratch" / "sma20_real_etp_2x_results.csv"
    pd.DataFrame(all_rows).to_csv(out_csv, index=False)
    print(f"\nCSV -> {out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
