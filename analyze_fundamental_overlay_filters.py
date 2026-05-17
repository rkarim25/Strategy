"""Test fundamental and macro overlays on the current Guarded A5/B25 default.

The baseline is the current site default:
Guarded A5/B25/X40/Y15 with a 0.75% SMA20 recovery lead guard.

External macro/fundamental signals are lagged before they can affect leverage:
- daily FRED series: one market session
- monthly FRED/Shiller series: 21 market sessions

The intent is a compact, reproducible first-pass screen for drawdown overlays,
not a data-mined exhaustive optimizer.
"""

from __future__ import annotations

import json
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats
from test_guarded_balanced_candidate import guarded_strategy_leverage
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD


OUTPUT_DIR = Path("output") / "fundamental_overlay_tests"
RESULTS_CSV = OUTPUT_DIR / "overlay_results.csv"
CATEGORY_BEST_CSV = OUTPUT_DIR / "category_best.csv"
TOP_RANKED_CSV = OUTPUT_DIR / "top_ranked.csv"
ANNUAL_EQUITY_CSV = OUTPUT_DIR / "annual_equity_selected.csv"
METADATA_JSON = OUTPUT_DIR / "metadata.json"

BASELINE_SPEC = {
    "strategy": "Baseline Guarded A5/B25/X40/Y15 Lead 0.75",
    "trigger_a": 0.05,
    "trigger_b": 0.25,
    "lead_pct_below_sma20": 0.0075,
    "x_return": 0.40,
    "y_return": 0.15,
}

FRED_BASE_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
SHILLER_XLS_URLS = [
    "https://www.econ.yale.edu/~shiller/data/ie_data.xls",
    "https://img1.wsimg.com/blobby/go/e5e77e0b-59d1-44d9-ab25-4763ac982e53/downloads/441f0d2c-37e4-4803-b4e2-8fe10407fbf6/ie_data.xls?ver=1778098504874",
]


@dataclass(frozen=True)
class OverlaySpec:
    category: str
    name: str
    signal: str
    threshold: str
    action: str
    condition: Callable[[pd.DataFrame], pd.Series]
    data_series: tuple[str, ...]


def make_engine() -> PortfolioEngine:
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )


def fetch_fred_series(series_id: str) -> pd.Series:
    url = f"{FRED_BASE_URL}?id={series_id}&cosd=1900-01-01"
    df = pd.read_csv(url, na_values=["."])
    if df.empty or series_id not in df.columns:
        raise ValueError(f"FRED series {series_id} returned no usable data")
    dates = pd.to_datetime(df["observation_date"])
    values = pd.to_numeric(df[series_id], errors="coerce")
    out = pd.Series(values.to_numpy(dtype=float), index=dates, name=series_id).dropna()
    if out.empty:
        raise ValueError(f"FRED series {series_id} has no numeric observations")
    return out.sort_index()


def fetch_shiller_cape() -> pd.Series:
    # pandas needs a local file for some Excel engines/URL combinations.
    errors: list[str] = []
    content: bytes | None = None
    for url in SHILLER_XLS_URLS:
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                content = response.read()
            break
        except Exception as exc:  # noqa: BLE001 - try the current Shiller site mirror next.
            errors.append(f"{url}: {exc}")
    if content is None:
        raise ValueError("; ".join(errors))
    with tempfile.NamedTemporaryFile(suffix=".xls", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        raw = pd.read_excel(tmp_path, sheet_name="Data", skiprows=7)
    finally:
        tmp_path.unlink(missing_ok=True)

    date_col = raw.columns[0]
    cape_col = next((c for c in raw.columns if str(c).strip().lower() == "cape"), None)
    if cape_col is None:
        raise ValueError("Shiller workbook did not contain a CAPE column")

    data = raw[[date_col, cape_col]].copy()
    data[date_col] = pd.to_numeric(data[date_col], errors="coerce")
    data[cape_col] = pd.to_numeric(data[cape_col], errors="coerce")
    data = data.dropna()
    years = np.floor(data[date_col]).astype(int)
    months = np.rint((data[date_col] - years) * 100).astype(int).clip(1, 12)
    dates = pd.to_datetime(
        {"year": years, "month": months, "day": np.ones(len(data), dtype=int)}
    ) + pd.offsets.MonthEnd(0)
    out = pd.Series(data[cape_col].to_numpy(dtype=float), index=dates, name="CAPE")
    return out[out > 0].sort_index()


def align_signal(
    market_index: pd.DatetimeIndex,
    series: pd.Series,
    *,
    lag_sessions: int,
    scale: float = 1.0,
) -> pd.Series:
    aligned = series.sort_index().reindex(market_index).ffill()
    aligned = aligned.shift(lag_sessions)
    if scale != 1.0:
        aligned = aligned * scale
    return aligned


def load_signal_data(prices: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, dict[str, str]]]:
    signals = pd.DataFrame(index=prices.index)
    availability: dict[str, dict[str, str]] = {}

    fred_specs = {
        "HY_OAS": ("BAMLH0A0HYM2", 1, 0.01, "ICE BofA US High Yield OAS, FRED"),
        "IG_OAS": ("BAMLC0A0CM", 1, 0.01, "ICE BofA US Corporate OAS, FRED"),
        "T10Y3M": ("T10Y3M", 1, 0.01, "10-year Treasury minus 3-month Treasury, FRED"),
        "T10Y2Y": ("T10Y2Y", 1, 0.01, "10-year Treasury minus 2-year Treasury, FRED"),
        "DGS10": ("DGS10", 1, 0.01, "10-year Treasury constant maturity, FRED"),
        "UNRATE": ("UNRATE", 21, 0.01, "Civilian unemployment rate, FRED"),
        "SAHM": ("SAHMREALTIME", 21, 1.0, "Real-time Sahm Rule recession indicator, FRED"),
        "RECPROUSM156N": (
            "RECPROUSM156N",
            21,
            0.01,
            "Smoothed U.S. recession probabilities, FRED",
        ),
        "USREC": ("USREC", 21, 1.0, "NBER recession indicator, FRED"),
    }

    for label, (series_id, lag, scale, source) in fred_specs.items():
        try:
            raw = fetch_fred_series(series_id)
            signals[label] = align_signal(prices.index, raw, lag_sessions=lag, scale=scale)
            availability[label] = {
                "status": "available",
                "source": source,
                "raw_start": raw.index[0].date().isoformat(),
                "raw_end": raw.index[-1].date().isoformat(),
                "lag": f"{lag} market sessions",
            }
        except Exception as exc:  # noqa: BLE001 - keep research script resilient to data outages.
            availability[label] = {"status": "unavailable", "error": str(exc)}

    try:
        cape_raw = fetch_shiller_cape()
        signals["CAPE"] = align_signal(prices.index, cape_raw, lag_sessions=21)
        signals["EARNINGS_YIELD"] = 1.0 / signals["CAPE"]
        if "DGS10" in signals:
            signals["EY_MINUS_10Y"] = signals["EARNINGS_YIELD"] - signals["DGS10"]
        availability["CAPE"] = {
            "status": "available",
            "source": "Robert Shiller online data",
            "raw_start": cape_raw.index[0].date().isoformat(),
            "raw_end": cape_raw.index[-1].date().isoformat(),
            "lag": "21 market sessions",
        }
    except Exception as exc:  # noqa: BLE001
        availability["CAPE"] = {"status": "unavailable", "error": str(exc)}

    return signals, availability


def baseline_leverage(prices: pd.DataFrame) -> tuple[pd.Series, dict[str, float | int]]:
    return guarded_strategy_leverage(
        prices,
        trigger_a=float(BASELINE_SPEC["trigger_a"]),
        trigger_b=float(BASELINE_SPEC["trigger_b"]),
        lead_pct_below_sma20=float(BASELINE_SPEC["lead_pct_below_sma20"]),
        x_return=float(BASELINE_SPEC["x_return"]),
        y_return=float(BASELINE_SPEC["y_return"]),
    )


def apply_action(base_leverage: pd.Series, condition: pd.Series, action: str) -> pd.Series:
    cond = condition.reindex(base_leverage.index).fillna(False).astype(bool)
    lev = base_leverage.copy().astype(float)
    if action == "cap_1x":
        lev.loc[cond] = lev.loc[cond].clip(upper=1.0)
    elif action == "cap_2x":
        lev.loc[cond] = lev.loc[cond].clip(upper=2.0)
    elif action == "reduce_one_tier":
        lev.loc[cond] = lev.loc[cond].map({3.0: 2.0, 2.0: 1.0, 1.0: 1.0, 0.0: 0.0}).fillna(
            lev.loc[cond].clip(lower=0.0) - 1.0
        ).clip(lower=0.0)
    else:
        raise ValueError(f"Unknown overlay action: {action}")
    return lev


def build_overlay_specs(signals: pd.DataFrame) -> list[OverlaySpec]:
    specs: list[OverlaySpec] = []

    if "CAPE" in signals:
        for threshold in [25.0, 30.0, 35.0]:
            for action in ["cap_2x", "cap_1x", "reduce_one_tier"]:
                specs.append(
                    OverlaySpec(
                        "Valuation",
                        f"CAPE > {threshold:g} / {action}",
                        "CAPE",
                        f">{threshold:g}",
                        action,
                        lambda s, t=threshold: s["CAPE"] > t,
                        ("CAPE",),
                    )
                )
    if "EY_MINUS_10Y" in signals:
        for threshold in [0.00, 0.01]:
            specs.append(
                OverlaySpec(
                    "Valuation",
                    f"Earnings yield - 10Y < {threshold:.0%} / cap_1x",
                    "Earnings yield minus 10Y Treasury",
                    f"<{threshold:.0%}",
                    "cap_1x",
                    lambda s, t=threshold: s["EY_MINUS_10Y"] < t,
                    ("CAPE", "DGS10"),
                )
            )

    if "HY_OAS" in signals:
        for threshold in [0.05, 0.065, 0.08]:
            for action in ["cap_2x", "cap_1x", "reduce_one_tier"]:
                specs.append(
                    OverlaySpec(
                        "Credit",
                        f"HY OAS > {threshold:.1%} / {action}",
                        "High-yield OAS",
                        f">{threshold:.1%}",
                        action,
                        lambda s, t=threshold: s["HY_OAS"] > t,
                        ("HY_OAS",),
                    )
                )
        for change in [0.015, 0.025]:
            specs.append(
                OverlaySpec(
                    "Credit",
                    f"HY OAS 63d widening > {change:.1%} / cap_1x",
                    "High-yield OAS 63-session change",
                    f">{change:.1%}",
                    "cap_1x",
                    lambda s, t=change: s["HY_OAS"].diff(63) > t,
                    ("HY_OAS",),
                )
            )

    if "IG_OAS" in signals:
        for threshold in [0.015, 0.02, 0.025]:
            specs.append(
                OverlaySpec(
                    "Credit",
                    f"IG OAS > {threshold:.1%} / cap_1x",
                    "Investment-grade OAS",
                    f">{threshold:.1%}",
                    "cap_1x",
                    lambda s, t=threshold: s["IG_OAS"] > t,
                    ("IG_OAS",),
                )
            )

    if "T10Y3M" in signals:
        for action in ["cap_2x", "reduce_one_tier", "cap_1x"]:
            specs.append(
                OverlaySpec(
                    "Rates",
                    f"10Y-3M inverted / {action}",
                    "10Y minus 3M Treasury",
                    "<0%",
                    action,
                    lambda s: s["T10Y3M"] < 0.0,
                    ("T10Y3M",),
                )
            )
    if "T10Y2Y" in signals:
        specs.append(
            OverlaySpec(
                "Rates",
                "10Y-2Y inverted / cap_2x",
                "10Y minus 2Y Treasury",
                "<0%",
                "cap_2x",
                lambda s: s["T10Y2Y"] < 0.0,
                ("T10Y2Y",),
            )
        )
    if "DGS10" in signals:
        specs.append(
            OverlaySpec(
                "Rates",
                "10Y yield > 4% and rising / cap_2x",
                "10Y Treasury yield and 200-session trend",
                ">4% and above 200d average",
                "cap_2x",
                lambda s: (s["DGS10"] > 0.04) & (s["DGS10"] > s["DGS10"].rolling(200).mean()),
                ("DGS10",),
            )
        )

    if "RECPROUSM156N" in signals:
        for threshold in [0.20, 0.30]:
            specs.append(
                OverlaySpec(
                    "Recession/Labor",
                    f"Recession probability > {threshold:.0%} / cap_1x",
                    "Smoothed recession probability",
                    f">{threshold:.0%}",
                    "cap_1x",
                    lambda s, t=threshold: s["RECPROUSM156N"] > t,
                    ("RECPROUSM156N",),
                )
            )
    if "SAHM" in signals:
        specs.append(
            OverlaySpec(
                "Recession/Labor",
                "Sahm real-time >= 0.5 / cap_1x",
                "Real-time Sahm Rule",
                ">=0.5",
                "cap_1x",
                lambda s: s["SAHM"] >= 0.5,
                ("SAHM",),
            )
        )
    if "UNRATE" in signals:
        specs.append(
            OverlaySpec(
                "Recession/Labor",
                "Unemployment > 12m low + 0.5pp / cap_1x",
                "Unemployment trend",
                "> trailing 12m low + 0.5pp",
                "cap_1x",
                lambda s: s["UNRATE"] >= s["UNRATE"].rolling(252, min_periods=126).min() + 0.005,
                ("UNRATE",),
            )
        )
    if "USREC" in signals:
        specs.append(
            OverlaySpec(
                "Recession/Labor",
                "NBER recession flag / cap_1x",
                "Lagged NBER recession indicator",
                "==1",
                "cap_1x",
                lambda s: s["USREC"] >= 1.0,
                ("USREC",),
            )
        )

    return specs


def run_backtest(
    prices: pd.DataFrame,
    leverage: pd.Series,
    strategy: str,
    extra_counts: dict[str, float | int] | None = None,
) -> tuple[dict[str, float | int | str], pd.Series]:
    result = make_engine().run(prices, leverage, name=strategy)
    stats = comprehensive_stats(
        result.equity,
        result.daily_returns,
        trading_costs_total=result.trading_costs_total,
        turnover_notional=result.turnover_notional,
    )
    row: dict[str, float | int | str] = {
        "strategy": strategy,
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "sortino": stats["sortino"],
        "calmar": stats["calmar"],
        "max_drawdown": stats["max_drawdown"],
        "ulcer_index": stats["ulcer_index"],
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": result.rebalance_count,
        "trading_costs_total": result.trading_costs_total,
        "funding_costs_total": result.funding_costs_total,
        "pct_days_cash": float((result.leverage <= 0).mean() * 100.0),
        "pct_days_1x": float((result.leverage == 1.0).mean() * 100.0),
        "pct_days_2x": float((result.leverage == 2.0).mean() * 100.0),
        "pct_days_3x": float((result.leverage == 3.0).mean() * 100.0),
    }
    if extra_counts:
        row.update(extra_counts)
    return row, result.equity


def add_comparison_columns(df: pd.DataFrame, baseline: dict[str, float | int | str]) -> pd.DataFrame:
    out = df.copy()
    base_cagr = float(baseline["cagr"])
    base_dd = float(baseline["max_drawdown"])
    base_sharpe = float(baseline["sharpe"])
    out["cagr_delta_pp"] = (out["cagr"] - base_cagr) * 100.0
    out["cagr_retention_pct"] = out["cagr"] / base_cagr * 100.0
    out["max_dd_improvement_pp"] = (out["max_drawdown"] - base_dd) * 100.0
    out["sharpe_delta"] = out["sharpe"] - base_sharpe
    out["rank_score"] = (
        out["max_dd_improvement_pp"] * 2.0
        + out["sharpe_delta"] * 5.0
        + (out["cagr_retention_pct"] - 100.0) * 0.25
    )
    return out


def selected_annual_equity(equity_by_name: dict[str, pd.Series], selected_names: list[str]) -> pd.DataFrame:
    rows = []
    for name in selected_names:
        eq = equity_by_name[name].resample("YE").last()
        for dt, value in eq.items():
            rows.append({"year": int(dt.year), "strategy": name, "equity_$": float(value)})
    return pd.DataFrame(rows)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    base_lev, base_counts = baseline_leverage(prices)
    baseline_row, baseline_equity = run_backtest(
        prices,
        base_lev,
        str(BASELINE_SPEC["strategy"]),
        base_counts,
    )

    print(f"Loaded market data: {prices.index[0].date()} -> {prices.index[-1].date()} ({len(prices)} sessions)")
    print("Loading macro and fundamental signals...", flush=True)
    signals, availability = load_signal_data(prices)
    usable_columns = [c for c in signals.columns if signals[c].notna().any()]
    signals = signals[usable_columns]
    print(f"Usable signal columns: {', '.join(usable_columns) if usable_columns else 'none'}")

    specs = build_overlay_specs(signals)
    rows: list[dict[str, float | int | str]] = []
    equity_by_name = {str(BASELINE_SPEC["strategy"]): baseline_equity}

    for spec in specs:
        if not all(col in signals.columns for col in spec.data_series):
            continue
        condition = spec.condition(signals).reindex(prices.index).fillna(False).astype(bool)
        lev = apply_action(base_lev, condition, spec.action)
        active_days = int(condition.sum())
        if active_days == 0:
            continue
        row, equity = run_backtest(
            prices,
            lev,
            spec.name,
            {
                "category": spec.category,
                "signal": spec.signal,
                "threshold": spec.threshold,
                "action": spec.action,
                "overlay_active_days": active_days,
                "overlay_active_pct": float(active_days / len(prices) * 100.0),
                "avg_leverage": float(lev.mean()),
                "pct_leverage_changed": float((lev != base_lev).mean() * 100.0),
            },
        )
        rows.append(row)
        equity_by_name[spec.name] = equity

    if not rows:
        raise RuntimeError("No overlay candidates could be tested because no usable external signals loaded.")

    results = pd.DataFrame(rows)
    results = add_comparison_columns(results, baseline_row)
    results = results.sort_values(
        ["max_dd_improvement_pp", "sharpe", "cagr_retention_pct"],
        ascending=[False, False, False],
    )
    category_best = (
        results.sort_values(["category", "max_dd_improvement_pp", "sharpe"], ascending=[True, False, False])
        .groupby("category", as_index=False)
        .head(3)
    )
    top_ranked = results.sort_values(
        ["rank_score", "max_dd_improvement_pp", "sharpe"],
        ascending=[False, False, False],
    ).head(12)

    baseline_df = add_comparison_columns(pd.DataFrame([baseline_row]), baseline_row)
    baseline_df["category"] = "Baseline"
    baseline_df["signal"] = "Current default strategy"
    baseline_df["threshold"] = "n/a"
    baseline_df["action"] = "n/a"
    baseline_df["overlay_active_days"] = 0
    baseline_df["overlay_active_pct"] = 0.0
    baseline_df["avg_leverage"] = float(base_lev.mean())
    baseline_df["pct_leverage_changed"] = 0.0

    pd.concat([baseline_df, results], ignore_index=True).to_csv(RESULTS_CSV, index=False)
    category_best.to_csv(CATEGORY_BEST_CSV, index=False)
    top_ranked.to_csv(TOP_RANKED_CSV, index=False)

    selected_names = [str(BASELINE_SPEC["strategy"])] + list(top_ranked["strategy"].head(5))
    selected_annual_equity(equity_by_name, selected_names).to_csv(ANNUAL_EQUITY_CSV, index=False)

    metadata = {
        "market_source": "Yahoo Finance ^GSPC and ^IRX via project data_manager.load_backtest_data",
        "market_start": prices.index[0].date().isoformat(),
        "market_end": prices.index[-1].date().isoformat(),
        "sessions": int(len(prices)),
        "baseline": BASELINE_SPEC,
        "initial_capital": INITIAL_CAPITAL,
        "annual_inflow_usd": ANNUAL_INFLOW_USD,
        "trading_cost_pct": TRADING_COST_FROM_MID_PCT,
        "lag_policy": {
            "daily_fred": "forward-filled to market sessions, shifted one market session before use",
            "monthly_fred_and_shiller": "forward-filled to market sessions, shifted 21 market sessions before use",
        },
        "availability": availability,
        "tested_overlay_count": int(len(results)),
    }
    with METADATA_JSON.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    disp_cols = [
        "category",
        "strategy",
        "cagr",
        "cagr_retention_pct",
        "sharpe",
        "max_drawdown",
        "max_dd_improvement_pp",
        "overlay_active_pct",
    ]
    print("\nBaseline:")
    print(pd.DataFrame([baseline_row])[["strategy", "cagr", "sharpe", "max_drawdown", "end_$"]].to_string(index=False))
    print("\nTop overlays by max drawdown improvement:")
    print(results[disp_cols].head(12).to_string(index=False))
    print(f"\nWrote {RESULTS_CSV}")
    print(f"Wrote {CATEGORY_BEST_CSV}")
    print(f"Wrote {TOP_RANKED_CSV}")
    print(f"Wrote {ANNUAL_EQUITY_CSV}")
    print(f"Wrote {METADATA_JSON}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"Network/data access failed: {exc}", file=sys.stderr)
        raise
