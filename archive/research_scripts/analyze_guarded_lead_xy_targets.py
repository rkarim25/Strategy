"""Assess X/Y recovery targets for the Guarded SMA20 lead-guard variant."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD

OUTPUT_DIR = Path("output") / "guarded_lead_xy_targets"
SWEEP_CSV = OUTPUT_DIR / "guarded_lead_xy_sweep.csv"
MC_SUMMARY_CSV = OUTPUT_DIR / "guarded_lead_xy_monte_carlo_summary.csv"
MC_PATHS_CSV = OUTPUT_DIR / "guarded_lead_xy_monte_carlo_paths.csv"
MC_METADATA_JSON = OUTPUT_DIR / "guarded_lead_xy_monte_carlo_metadata.json"

SMA_WINDOW = 20
TRIGGER_A = 0.10
TRIGGER_B = 0.20
LEAD_PCT_BELOW_SMA20 = 0.0075
BASELINE_X = 0.25
BASELINE_Y = 1.0 / 3.0

N_SIMS = 200
HORIZON_DAYS = 2520
BLOCK_DAYS = 21
SEED = 20260517


def make_engine() -> PortfolioEngine:
    return PortfolioEngine(
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
    )


def guarded_lead_leverage(
    prices: pd.DataFrame,
    *,
    lead_pct_below_sma20: float,
    x_return: float,
    y_return: float,
) -> tuple[pd.Series, dict[str, float | int]]:
    close = prices["spx_close"].astype(float)
    sma20 = close.rolling(SMA_WINDOW, min_periods=SMA_WINDOW).mean()
    base_guard = (close > sma20).fillna(False)
    recovery_guard = (close >= sma20 * (1.0 - lead_pct_below_sma20)).fillna(False)
    spx_dd = close / close.cummax() - 1.0

    lev = pd.Series(0.0, index=prices.index)
    regime = "base"
    entry_close = 0.0
    tier2_entries = 0
    tier3_entries = 0
    lead_only_days = 0
    guard_blocked_days = 0

    for dt in prices.index:
        px = float(close.loc[dt])
        dd = float(spx_dd.loc[dt])
        base_ok = bool(base_guard.loc[dt])
        recovery_ok = bool(recovery_guard.loc[dt])
        base_lev = 1.0 if base_ok else 0.0
        if recovery_ok and not base_ok:
            lead_only_days += 1

        if regime == "tier3":
            if px / entry_close - 1.0 >= y_return:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = 3.0
                continue
            else:
                guard_blocked_days += 1
                lev.loc[dt] = base_lev
                continue

        if regime == "tier2":
            if dd <= -TRIGGER_B and recovery_ok:
                regime = "tier3"
                entry_close = px
                tier3_entries += 1
                lev.loc[dt] = 3.0
                continue
            if px / entry_close - 1.0 >= x_return:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = 2.0
                continue
            else:
                guard_blocked_days += 1
                lev.loc[dt] = base_lev
                continue

        if dd <= -TRIGGER_B and recovery_ok:
            regime = "tier3"
            entry_close = px
            tier3_entries += 1
            lev.loc[dt] = 3.0
        elif dd <= -TRIGGER_A and recovery_ok:
            regime = "tier2"
            entry_close = px
            tier2_entries += 1
            lev.loc[dt] = 2.0
        else:
            if dd <= -TRIGGER_A and not recovery_ok:
                guard_blocked_days += 1
            lev.loc[dt] = base_lev

    return lev, {
        "tier2_entries": tier2_entries,
        "tier3_entries": tier3_entries,
        "lead_only_days": lead_only_days,
        "guard_blocked_days": guard_blocked_days,
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_days_1x": float((lev == 1.0).mean() * 100.0),
        "pct_days_2x": float((lev == 2.0).mean() * 100.0),
        "pct_days_3x": float((lev == 3.0).mean() * 100.0),
    }


def run_strategy(
    prices: pd.DataFrame,
    *,
    name: str,
    lead_pct_below_sma20: float,
    x_return: float,
    y_return: float,
) -> dict[str, float | int | str]:
    lev, counts = guarded_lead_leverage(
        prices,
        lead_pct_below_sma20=lead_pct_below_sma20,
        x_return=x_return,
        y_return=y_return,
    )
    result = make_engine().run(prices, lev, name=name)
    stats = comprehensive_stats(result.equity, result.daily_returns)
    return {
        "strategy": name,
        "lead_pct_below_sma20": lead_pct_below_sma20,
        "x_return": x_return,
        "y_return": y_return,
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "max_drawdown": stats["max_drawdown"],
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": result.rebalance_count,
        "trading_costs_total": result.trading_costs_total,
        "funding_costs_total": result.funding_costs_total,
        **counts,
    }


def xy_grid() -> tuple[list[float], list[float]]:
    x_values = sorted({round(x / 100.0, 6) for x in range(10, 61, 5)} | {BASELINE_X})
    y_values = sorted({round(y / 100.0, 6) for y in range(15, 81, 5)} | {round(BASELINE_Y, 6)})
    return x_values, y_values


def sweep_xy(prices: pd.DataFrame, baseline: dict[str, float | int | str]) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    x_values, y_values = xy_grid()
    for x_return in x_values:
        for y_return in y_values:
            row = run_strategy(
                prices,
                name=f"Lead 0.75 X{x_return:.2%} Y{y_return:.2%}",
                lead_pct_below_sma20=LEAD_PCT_BELOW_SMA20,
                x_return=x_return,
                y_return=y_return,
            )
            rows.append(row)
    df = pd.DataFrame(rows)
    df["cagr_delta_pp_vs_original"] = (df["cagr"] - float(baseline["cagr"])) * 100.0
    df["max_dd_delta_pp_vs_original"] = (df["max_drawdown"] - float(baseline["max_drawdown"])) * 100.0
    df["sharpe_delta_vs_original"] = df["sharpe"] - float(baseline["sharpe"])
    df["keeps_original_cagr"] = df["cagr"] >= float(baseline["cagr"])
    df["improves_original_drawdown"] = df["max_drawdown"] > float(baseline["max_drawdown"])
    df["improves_original_sharpe"] = df["sharpe"] > float(baseline["sharpe"])
    return df.sort_values(["keeps_original_cagr", "improves_original_drawdown", "sharpe"], ascending=[False, False, False])


def synthetic_market_paths(prices: pd.DataFrame) -> list[pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    spx_ret = prices["spx_close"].pct_change().fillna(0.0).to_numpy(dtype=float)
    tbill = prices["tbill_rate"].ffill().fillna(0.0).to_numpy(dtype=float)
    block_starts = np.arange(1, len(prices) - BLOCK_DAYS + 1)
    paths: list[pd.DataFrame] = []
    for _ in range(N_SIMS):
        sampled_idx: list[np.ndarray] = []
        while sum(len(x) for x in sampled_idx) < HORIZON_DAYS:
            start = int(rng.choice(block_starts))
            sampled_idx.append(np.arange(start, start + BLOCK_DAYS))
        idx = np.concatenate(sampled_idx)[:HORIZON_DAYS]
        returns = spx_ret[idx]
        index = pd.bdate_range("2000-01-03", periods=HORIZON_DAYS)
        paths.append(
            pd.DataFrame(
                {
                    "spx_close": 1000.0 * np.cumprod(1.0 + returns),
                    "tbill_rate": tbill[idx],
                },
                index=index,
            )
        )
    return paths


def summarize_mc(paths_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for strategy, g in paths_df.groupby("strategy"):
        rows.append(
            {
                "strategy": strategy,
                "median_cagr": float(g["cagr"].median()),
                "p10_cagr": float(g["cagr"].quantile(0.10)),
                "p90_cagr": float(g["cagr"].quantile(0.90)),
                "median_max_drawdown": float(g["max_drawdown"].median()),
                "p10_max_drawdown": float(g["max_drawdown"].quantile(0.10)),
                "p90_max_drawdown": float(g["max_drawdown"].quantile(0.90)),
                "median_sharpe": float(g["sharpe"].median()),
                "median_end_$": float(g["end_$"].median()),
                "prob_cagr_gt_original_full_sample": float((g["cagr"] > 0.2939).mean()),
                "prob_max_dd_worse_35pct": float((g["max_drawdown"] <= -0.35).mean()),
                "prob_max_dd_worse_40pct": float((g["max_drawdown"] <= -0.40).mean()),
                "prob_max_dd_worse_50pct": float((g["max_drawdown"] <= -0.50).mean()),
                "median_pct_days_2x": float(g["pct_days_2x"].median()),
                "median_pct_days_3x": float(g["pct_days_3x"].median()),
            }
        )
    return pd.DataFrame(rows)


def monte_carlo(prices: pd.DataFrame, candidate: dict[str, float | int | str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    specs = [
        ("Original strict SMA20", 0.0, BASELINE_X, BASELINE_Y),
        ("Lead 0.75 default X/Y", LEAD_PCT_BELOW_SMA20, BASELINE_X, BASELINE_Y),
        (
            "Lead 0.75 selected X/Y",
            LEAD_PCT_BELOW_SMA20,
            float(candidate["x_return"]),
            float(candidate["y_return"]),
        ),
    ]
    rows = []
    for sim, path in enumerate(synthetic_market_paths(prices)):
        if sim % 25 == 0:
            print(f"Monte Carlo path {sim + 1}/{N_SIMS}", flush=True)
        for name, lead_pct, x_return, y_return in specs:
            row = run_strategy(
                path,
                name=name,
                lead_pct_below_sma20=lead_pct,
                x_return=x_return,
                y_return=y_return,
            )
            row["simulation"] = sim
            rows.append(row)
    paths_df = pd.DataFrame(rows)
    return paths_df, summarize_mc(paths_df)


def print_table(df: pd.DataFrame, columns: list[str], n: int = 10) -> None:
    disp = df.head(n).copy()
    for col in ["cagr", "max_drawdown", "ann_volatility", "median_cagr", "median_max_drawdown"]:
        if col in disp:
            disp[col] = disp[col].map(lambda x: f"{x * 100:.2f}%")
    for col in ["x_return", "y_return", "lead_pct_below_sma20"]:
        if col in disp:
            disp[col] = disp[col].map(lambda x: f"{x * 100:.2f}%")
    if "sharpe" in disp:
        disp["sharpe"] = disp["sharpe"].map(lambda x: f"{x:.3f}")
    if "end_$" in disp:
        disp["end_$"] = disp["end_$"].map(lambda x: f"${x:,.0f}")
    print(disp[columns].to_string(index=False))


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prices = load_backtest_data()
    print(f"Loaded {len(prices)} sessions: {prices.index[0].date()} -> {prices.index[-1].date()}", flush=True)
    original = run_strategy(
        prices,
        name="Original strict SMA20",
        lead_pct_below_sma20=0.0,
        x_return=BASELINE_X,
        y_return=BASELINE_Y,
    )
    lead_default = run_strategy(
        prices,
        name="Lead 0.75 default X/Y",
        lead_pct_below_sma20=LEAD_PCT_BELOW_SMA20,
        x_return=BASELINE_X,
        y_return=BASELINE_Y,
    )
    print("Sweeping X/Y targets...", flush=True)
    sweep = sweep_xy(prices, original)
    sweep.to_csv(SWEEP_CSV, index=False)

    eligible = sweep[sweep["keeps_original_cagr"]].copy()
    better_dd = eligible[eligible["improves_original_drawdown"]].sort_values("cagr", ascending=False)
    better_sharpe = eligible[eligible["improves_original_sharpe"]].sort_values("cagr", ascending=False)
    if not better_dd.empty:
        selected = better_dd.iloc[0].to_dict()
        selected_reason = "highest CAGR while preserving original CAGR and improving max drawdown"
    elif not better_sharpe.empty:
        selected = better_sharpe.iloc[0].to_dict()
        selected_reason = "highest CAGR while preserving original CAGR and improving Sharpe"
    else:
        selected = eligible.sort_values("cagr", ascending=False).iloc[0].to_dict()
        selected_reason = "highest CAGR while preserving original CAGR; no risk metric improved"

    print(
        f"Running Monte Carlo for selected X={float(selected['x_return'])*100:.2f}%, "
        f"Y={float(selected['y_return'])*100:.2f}%...",
        flush=True,
    )
    mc_paths, mc_summary = monte_carlo(prices, selected)
    mc_paths.to_csv(MC_PATHS_CSV, index=False)
    mc_summary.to_csv(MC_SUMMARY_CSV, index=False)
    with MC_METADATA_JSON.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "source": "Yahoo Finance ^GSPC and ^IRX via project data loader",
                "market_history_start": prices.index[0].date().isoformat(),
                "market_history_end": prices.index[-1].date().isoformat(),
                "lead_pct_below_sma20": LEAD_PCT_BELOW_SMA20,
                "selected_reason": selected_reason,
                "selected_x_return": float(selected["x_return"]),
                "selected_y_return": float(selected["y_return"]),
                "n_sims": N_SIMS,
                "horizon_trading_days": HORIZON_DAYS,
                "horizon_years": HORIZON_DAYS / 252.0,
                "block_days": BLOCK_DAYS,
                "seed": SEED,
            },
            f,
            indent=2,
        )

    print(
        "Guarded lead X/Y target assessment | "
        f"${INITIAL_CAPITAL:.0f} start | ${ANNUAL_INFLOW_USD:.0f}/year fixed inflow | "
        f"{TRADING_COST_FROM_MID_PCT * 100:.1f}% rebalance cost"
    )
    print(f"Dates: {prices.index[0].date()} -> {prices.index[-1].date()} ({len(prices)} sessions)\n")
    print("Baselines:")
    print_table(pd.DataFrame([original, lead_default]), ["strategy", "lead_pct_below_sma20", "x_return", "y_return", "cagr", "sharpe", "max_drawdown", "end_$", "rebalances"], 2)
    print("\nBest X/Y rows that preserve original CAGR and improve original max drawdown:")
    print_table(better_dd.sort_values("cagr", ascending=False), ["x_return", "y_return", "cagr", "sharpe", "max_drawdown", "end_$", "rebalances"], 10)
    print("\nBest X/Y rows that preserve original CAGR and improve original Sharpe:")
    print_table(better_sharpe.sort_values("cagr", ascending=False), ["x_return", "y_return", "cagr", "sharpe", "max_drawdown", "end_$", "rebalances"], 10)
    print(f"\nSelected for Monte Carlo: X={float(selected['x_return'])*100:.2f}%, Y={float(selected['y_return'])*100:.2f}% ({selected_reason})")
    print("\nMonte Carlo summary:")
    mc_disp = mc_summary.copy()
    for col in ["median_cagr", "p10_cagr", "p90_cagr", "median_max_drawdown", "p10_max_drawdown", "p90_max_drawdown"]:
        mc_disp[col] = mc_disp[col].map(lambda x: f"{x * 100:.2f}%")
    mc_disp["median_sharpe"] = mc_disp["median_sharpe"].map(lambda x: f"{x:.3f}")
    mc_disp["median_end_$"] = mc_disp["median_end_$"].map(lambda x: f"${x:,.0f}")
    for col in ["prob_cagr_gt_original_full_sample", "prob_max_dd_worse_35pct", "prob_max_dd_worse_40pct", "prob_max_dd_worse_50pct"]:
        mc_disp[col] = mc_disp[col].map(lambda x: f"{x * 100:.1f}%")
    print(mc_disp.to_string(index=False))
    print(f"\nSweep CSV: {SWEEP_CSV}")
    print(f"Monte Carlo summary CSV: {MC_SUMMARY_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
