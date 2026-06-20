"""
Five-sleeve hybrid portfolio back-test with semi-annual rebalancing.

Policy (PORTFOLIO.md):
  40% S&P 500, 15% Nasdaq, 16% FTSE 250, 14% MSCI EM, 15% gold
  Guarded A5/B25 lead 0.75% X40/Y15 — full 2x/3x on US, max 1x elsewhere
  Rebalance to strategic weights every 6 months (Jan & Jul, first session)

Assumptions aligned with site engine:
  $100 start, $10/year portfolio inflow (split by weight on inflow day)
  1% trading cost on sleeve-level Guarded rebalances (inside each sleeve sim)
  0.1% portfolio rebalance cost on turnover when resetting sleeve weights
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from analyze_cross_asset_guarded_1x import guarded_lead_leverage
from analyze_multi_asset_guarded_scan import panel_for_close
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from etp_leverage import NDX_ETP, SPX_ETP
from metrics import comprehensive_stats
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD

OUTPUT_DIR = Path("output") / "five_sleeve_portfolio_rebalance"
PORTFOLIO_REBALANCE_COST_PCT = 0.001  # 0.1% on turnover between sleeves

TICKERS = {
    "S&P 500": "^GSPC",
    "Nasdaq 100": "^NDX",
    "FTSE 250": "^FTMC",
    "MSCI EM": "EEM",
    "Gold": "GLD",
}

WEIGHTS = {
    "S&P 500": 0.40,
    "Nasdaq 100": 0.15,
    "FTSE 250": 0.16,
    "MSCI EM": 0.14,
    "Gold": 0.15,
}

MAX_LEV = {
    "S&P 500": 3.0,
    "Nasdaq 100": 3.0,
    "FTSE 250": 1.0,
    "MSCI EM": 1.0,
    "Gold": 1.0,
}

REBALANCE_MONTHS = {1, 7}  # semi-annual: January & July

SLEEVE_ETP = {
    "S&P 500": SPX_ETP,
    "Nasdaq 100": NDX_ETP,
}


def run_guarded_sleeve(
    panel: pd.DataFrame,
    max_lev: float,
    *,
    annual_inflow_abs: float,
    sleeve_name: str | None = None,
) -> tuple[pd.Series, pd.Series]:
    """
    Returns (equity, daily_returns).

    daily_returns must be equity.pct_change(), NOT engine.port_ret:
    port_ret is the levered index return only; it ignores rebalance trading costs
    and annual inflows, so (1+r).cumprod() overstates CAGR badly at high leverage.
    """
    eng = PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_abs=annual_inflow_abs,
    )
    lev, _ = guarded_lead_leverage(panel, max_leverage=max_lev)
    etp = SLEEVE_ETP.get(sleeve_name or "") if max_lev > 1.0 else None
    res = eng.run(panel, lev, name="Guarded", etp_bundle=etp)
    equity = res.equity
    daily = equity.pct_change().fillna(0.0)
    return equity, daily


def rebalance_flag(dates: pd.DatetimeIndex) -> pd.Series:
    """True on first trading day of Jan/Jul each year."""
    out = pd.Series(False, index=dates)
    prev_month = None
    for dt in dates:
        if dt.month in REBALANCE_MONTHS and prev_month != dt.month:
            out.loc[dt] = True
        prev_month = dt.month
    return out


def simulate_portfolio(
    returns: pd.DataFrame,
    weights: dict[str, float],
    *,
    do_rebalance: bool,
    initial: float = INITIAL_CAPITAL,
    annual_inflow: float = ANNUAL_INFLOW_USD,
    rebalance_cost_pct: float = PORTFOLIO_REBALANCE_COST_PCT,
) -> tuple[pd.Series, pd.Series, list[dict], pd.DataFrame]:
    cols = [c for c in weights if c in returns.columns]
    w = pd.Series({c: weights[c] for c in cols})
    w = w / w.sum()
    R = returns[cols].fillna(0.0)
    flags = rebalance_flag(R.index) if do_rebalance else pd.Series(False, index=R.index)

    holdings = (w * initial).to_dict()
    cash = 0.0
    equity_hist = []
    weight_hist = []
    events: list[dict] = []

    prev_year: int | None = None
    for i, dt in enumerate(R.index):
        if prev_year is not None and dt.year != prev_year:
            inflow = annual_inflow
            for c in cols:
                holdings[c] += inflow * w[c]
            events.append({"date": dt.date().isoformat(), "type": "annual_inflow", "amount": inflow})
        prev_year = dt.year

        for c in cols:
            holdings[c] *= 1.0 + float(R.loc[dt, c])

        aum = sum(holdings.values()) + cash

        if flags.loc[dt]:
            target = {c: float(w[c] * aum) for c in cols}
            turnover = sum(abs(target[c] - holdings[c]) for c in cols)
            cost = turnover * rebalance_cost_pct
            aum_after_cost = max(aum - cost, 0.0)
            for c in cols:
                holdings[c] = float(w[c] * aum_after_cost)
            cash = 0.0
            aum = aum_after_cost
            events.append(
                {
                    "date": dt.date().isoformat(),
                    "type": "rebalance",
                    "portfolio_value": round(aum, 2),
                    "turnover": round(turnover, 2),
                    "cost": round(cost, 4),
                }
            )

        aum = sum(holdings.values()) + cash
        equity_hist.append(aum)
        weight_hist.append({c: holdings[c] / aum if aum > 0 else w[c] for c in cols})

    equity = pd.Series(equity_hist, index=R.index, name="equity")
    port_ret = equity.pct_change().fillna(0.0)
    weights_df = pd.DataFrame(weight_hist, index=R.index)
    return equity, port_ret, events, weights_df


def stats_row(label: str, equity: pd.Series, port_ret: pd.Series) -> dict:
    st = comprehensive_stats(equity, port_ret)
    return {
        "portfolio": label,
        "cagr_pct": round(st["cagr"] * 100, 2),
        "ann_volatility_pct": round(st["volatility"] * 100, 2),
        "sharpe": round(float(st["sharpe"]), 3) if st["sharpe"] == st["sharpe"] else None,
        "max_drawdown_pct": round(st["max_drawdown"] * 100, 2),
        "calmar": round(float(st["calmar"]), 3) if st["calmar"] == st["calmar"] else None,
        "end_$": round(float(equity.iloc[-1]), 2),
        "start_date": equity.index[0].date().isoformat(),
        "end_date": equity.index[-1].date().isoformat(),
        "trading_days": int(len(equity)),
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    end = datetime.today()
    start = end - timedelta(days=int(30 * 365.25))

    print("Downloading prices...", flush=True)
    raw = yf.download(
        list(TICKERS.values()) + ["^IRX"],
        start=start.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )
    closes = raw["Close"].sort_index().ffill()
    tbill = closes["^IRX"] / 100.0

    sleeve_returns: dict[str, pd.Series] = {}
    sleeve_rows: list[dict] = []

    for name, tic in TICKERS.items():
        panel = panel_for_close(closes[tic].dropna(), tbill)
        # Standalone sleeve stats: full $10/yr on that sleeve (same as site asset pages)
        equity, daily = run_guarded_sleeve(
            panel,
            MAX_LEV[name],
            annual_inflow_abs=ANNUAL_INFLOW_USD,
            sleeve_name=name,
        )
        st = comprehensive_stats(equity, daily)
        sleeve_rows.append(
            {
                "sleeve": name,
                "weight_pct": round(WEIGHTS[name] * 100, 1),
                "max_leverage": MAX_LEV[name],
                "cagr_pct": round(st["cagr"] * 100, 2),
                "max_drawdown_pct": round(st["max_drawdown"] * 100, 2),
                "sharpe": round(float(st["sharpe"]), 3),
                "end_$": round(float(equity.iloc[-1]), 2),
            }
        )

    # Portfolio combine: no per-sleeve inflow (added once at portfolio level in simulate_portfolio)
    for name, tic in TICKERS.items():
        panel = panel_for_close(closes[tic].dropna(), tbill)
        _, daily = run_guarded_sleeve(
            panel, MAX_LEV[name], annual_inflow_abs=0.0, sleeve_name=name
        )
        sleeve_returns[name] = daily

    R = pd.DataFrame(sleeve_returns).dropna(how="any")
    print(f"Common window: {R.index[0].date()} -> {R.index[-1].date()} ({len(R)} days)\n")

    eq_rebal, ret_rebal, events_rebal, w_rebal = simulate_portfolio(
        R, WEIGHTS, do_rebalance=True
    )
    eq_drift, ret_drift, events_drift, w_drift = simulate_portfolio(
        R, WEIGHTS, do_rebalance=False
    )

    summary_rows = [
        stats_row("Hybrid + semi-annual rebalance (Jan/Jul)", eq_rebal, ret_rebal),
        stats_row("Hybrid + buy-and-hold weights (drift)", eq_drift, ret_drift),
    ]

    pd.DataFrame(sleeve_rows).to_csv(OUTPUT_DIR / "sleeve_guarded_stats.csv", index=False)
    pd.DataFrame(summary_rows).to_csv(OUTPUT_DIR / "portfolio_summary.csv", index=False)
    eq_rebal.to_csv(OUTPUT_DIR / "portfolio_equity_semiannual_rebal.csv", header=["equity"])
    w_rebal.to_csv(OUTPUT_DIR / "portfolio_weights_semiannual_rebal.csv")
    pd.DataFrame(events_rebal).to_csv(OUTPUT_DIR / "rebalance_events.csv", index=False)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "policy": {
            "weights_pct": {k: round(v * 100, 1) for k, v in WEIGHTS.items()},
            "strategy": "Guarded A5/B25 X40/Y15 lead 0.75%",
            "us_leverage": "full 2x/3x",
            "other_leverage": "max 1x",
            "rebalance": "Semi-annual (first trading day of January and July)",
            "initial_capital": INITIAL_CAPITAL,
            "annual_inflow_usd": ANNUAL_INFLOW_USD,
            "sleeve_trading_cost_pct": TRADING_COST_FROM_MID_PCT,
            "portfolio_rebalance_cost_pct": PORTFOLIO_REBALANCE_COST_PCT,
            "return_series": "equity.pct_change() per sleeve (includes costs; not raw port_ret)",
            "sleeve_cagr_note": "Per-sleeve rows: engine equity, $10/yr each (site convention)",
        },
        "sleeves": sleeve_rows,
        "portfolio": summary_rows,
        "rebalance_event_count": len([e for e in events_rebal if e["type"] == "rebalance"]),
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("=== Per-sleeve Guarded (hybrid leverage) ===")
    print(pd.DataFrame(sleeve_rows).to_string(index=False))
    print("\n=== Combined portfolio ===")
    print(pd.DataFrame(summary_rows).to_string(index=False))
    print(f"\nRebalance events: {payload['rebalance_event_count']}")
    print(f"Wrote {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
