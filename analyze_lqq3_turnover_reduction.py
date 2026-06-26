"""
LQQ3.L (real 3QQQ) turnover reduction sweep.

Tests ways to cut rebalances vs default SMA20 1x/cash and Guarded max 1x without
sacrificing CAGR or max drawdown on the listing window (2012+).

Families:
  1. SMA hysteresis — exit only when firmly below MA (exit buffer)
  2. Asymmetric entry/exit buffers + confirmation days
  3. Longer SMA windows
  4. Dual SMA — enter on fast SMA, exit only below slow SMA
  5. Min-hold days after entry
  6. Guarded max 1x with wider exit band / confirm on cash switches

Writes output/lqq3_turnover_reduction/
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from analyze_cross_asset_guarded_1x import DEFAULT_GUARDED, guarded_lead_leverage
from analyze_spx_sma20_entry_exit import pareto_3d, sma_entry_exit_leverage, strategy_label
from backtest_lqq3_guarded import LQQ3_START, LQQ3_TICKER, download_panel, make_engine
from core.engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT
from core.metrics import comprehensive_stats, invested_vs_tbills_sessions
from test_tiered_dd_recovery_guarded import BASE_SMA_WINDOW, sma_cash_leverage

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

OUTPUT_DIR = Path("output") / "lqq3_turnover_reduction"


def run_row(prices: pd.DataFrame, lev: pd.Series, label: str, **meta) -> dict:
    res = make_engine().run(prices, lev, name=label)
    stats = comprehensive_stats(res.equity, res.daily_returns)
    cash = invested_vs_tbills_sessions(res.leverage)
    return {
        "strategy": label,
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "max_drawdown": stats["max_drawdown"],
        "calmar": stats.get("calmar"),
        "end_$": float(res.equity.iloc[-1]),
        "rebalances": int(res.rebalance_count),
        "trading_costs_total": res.trading_costs_total,
        "pct_cash": cash["pct_sessions_tbills"],
        **meta,
    }


def dual_sma_leverage(
    prices: pd.DataFrame,
    *,
    fast: int = 20,
    slow: int = 50,
    confirm_days: int = 1,
) -> pd.Series:
    close = prices["spx_close"].astype(float)
    sma_f = close.rolling(fast, min_periods=fast).mean()
    sma_s = close.rolling(slow, min_periods=slow).mean()
    lev = pd.Series(0.0, index=prices.index)
    in_pos = False
    entry_streak = 0
    exit_streak = 0
    for dt in prices.index:
        px = float(close.loc[dt])
        sf = float(sma_f.loc[dt]) if pd.notna(sma_f.loc[dt]) else float("nan")
        ss = float(sma_s.loc[dt]) if pd.notna(sma_s.loc[dt]) else float("nan")
        if not np.isfinite(sf) or not np.isfinite(ss):
            lev.loc[dt] = 0.0
            in_pos = False
            continue
        if in_pos:
            if px < ss:
                exit_streak += 1
            else:
                exit_streak = 0
            if exit_streak >= confirm_days:
                in_pos = False
        else:
            if px > sf:
                entry_streak += 1
            else:
                entry_streak = 0
            if entry_streak >= confirm_days:
                in_pos = True
        lev.loc[dt] = 1.0 if in_pos else 0.0
    return lev


def min_hold_filter(raw: pd.Series, *, min_hold_days: int) -> pd.Series:
    lev = pd.Series(0.0, index=raw.index)
    in_pos = False
    hold_left = 0
    for dt in raw.index:
        target = float(raw.loc[dt]) > 0
        if in_pos:
            if not target and hold_left <= 0:
                in_pos = False
            elif target:
                hold_left = min_hold_days
            else:
                hold_left -= 1
        else:
            if target:
                in_pos = True
                hold_left = min_hold_days
        lev.loc[dt] = 1.0 if in_pos else 0.0
    return lev


def guarded_with_exit_buffer(
    prices: pd.DataFrame,
    *,
    exit_buffer: float = 0.0,
    entry_buffer: float = 0.0,
    confirm_days: int = 1,
    max_leverage: float = 1.0,
) -> tuple[pd.Series, dict]:
    """Guarded max 1x but base/recovery exit to cash needs close below SMA*(1-exit_buffer)."""
    close = prices["spx_close"].astype(float)
    sma20 = close.rolling(BASE_SMA_WINDOW, min_periods=BASE_SMA_WINDOW).mean()
    spx_dd = close / close.cummax() - 1.0
    lead = DEFAULT_GUARDED["lead_pct_below_sma20"]

    lev = pd.Series(0.0, index=prices.index)
    regime = "base"
    entry_close = 0.0
    in_market = False
    entry_streak = 0
    exit_streak = 0
    tier2 = tier3 = 0

    def want_invest(recovery_ok: bool, base_above: bool) -> bool:
        return recovery_ok and (base_above or regime != "base")

    for dt in prices.index:
        px = float(close.loc[dt])
        dd = float(spx_dd.loc[dt])
        s = float(sma20.loc[dt]) if pd.notna(sma20.loc[dt]) else float("nan")
        if not np.isfinite(s):
            lev.loc[dt] = 0.0
            in_market = False
            continue

        base_above = px > s * (1.0 + entry_buffer)
        recovery_ok = px >= s * (1.0 - lead)
        exit_line = px < s * (1.0 - exit_buffer)

        raw_target = 0.0
        if regime == "tier3":
            if px / entry_close - 1.0 >= DEFAULT_GUARDED["y_return"]:
                regime = "base"
            elif recovery_ok:
                raw_target = min(3.0, max_leverage)
        elif regime == "tier2":
            if dd <= -DEFAULT_GUARDED["trigger_b"] and recovery_ok:
                regime = "tier3"
                entry_close = px
                tier3 += 1
                raw_target = min(3.0, max_leverage)
            elif px / entry_close - 1.0 >= DEFAULT_GUARDED["x_return"]:
                regime = "base"
            elif recovery_ok:
                raw_target = min(2.0, max_leverage)
        else:
            if dd <= -DEFAULT_GUARDED["trigger_b"] and recovery_ok:
                regime = "tier3"
                entry_close = px
                tier3 += 1
                raw_target = min(3.0, max_leverage)
            elif dd <= -DEFAULT_GUARDED["trigger_a"] and recovery_ok:
                regime = "tier2"
                entry_close = px
                tier2 += 1
                raw_target = min(2.0, max_leverage)
            elif base_above:
                raw_target = 1.0

        target_in = raw_target > 0
        if in_market:
            if not target_in or exit_line:
                exit_streak += 1
            else:
                exit_streak = 0
            if exit_streak >= confirm_days:
                in_market = False
                entry_streak = 0
        else:
            if target_in and not exit_line:
                entry_streak += 1
            else:
                entry_streak = 0
            if entry_streak >= confirm_days:
                in_market = True
                exit_streak = 0

        lev.loc[dt] = min(raw_target, max_leverage) if in_market else 0.0

    counts = {
        "tier2_entries": tier2,
        "tier3_entries": tier3,
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
    }
    return lev, counts


def no_sacrifice_filter(df: pd.DataFrame, baseline: pd.Series) -> pd.DataFrame:
    """CAGR >= baseline and max DD no worse (more negative = worse)."""
    return df[
        (df["cagr"] >= baseline["cagr"] - 1e-9)
        & (df["max_drawdown"] >= baseline["max_drawdown"] - 1e-9)
    ].copy()


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Downloading LQQ3.L...", flush=True)
    prices = download_panel(LQQ3_TICKER, start=LQQ3_START)
    print(
        f"Sample: {prices.index[0].date()} -> {prices.index[-1].date()} ({len(prices)} days)",
        flush=True,
    )

    rows: list[dict] = []

    lev_bh = pd.Series(1.0, index=prices.index)
    rows.append(run_row(prices, lev_bh, "Buy & hold LQQ3", family="baseline"))

    lev_sma20 = sma_cash_leverage(prices, BASE_SMA_WINDOW, 1.0)
    rows.append(
        run_row(
            prices,
            lev_sma20,
            "SMA20 1x/cash (baseline)",
            family="baseline",
            sma_window=20,
        )
    )

    lev_guard, gcounts = guarded_lead_leverage(prices, max_leverage=1.0)
    rows.append(
        run_row(
            prices,
            lev_guard,
            "Guarded A5/B25 max 1x (baseline)",
            family="baseline",
            **gcounts,
        )
    )

    configs: list[tuple[str, pd.Series, dict]] = []

    # 1. Exit buffer only (firmly below MA to sell)
    for window, exit_b in product([20, 30, 50], [0.005, 0.01, 0.015, 0.02, 0.03, 0.05]):
        lev = sma_entry_exit_leverage(
            prices,
            window=window,
            leverage=1.0,
            entry_buffer=0.0,
            exit_buffer=exit_b,
            confirm_days=1,
        )
        label = f"SMA{window} 1x/cash exit-{exit_b*100:g}% below MA"
        configs.append((label, lev, {"family": "exit_buffer", "sma_window": window, "exit_buffer": exit_b}))

    # 2. Asymmetric buffers
    for window, entry_b, exit_b in product(
        [20, 30],
        [0.0, 0.005, 0.01],
        [0.01, 0.02, 0.03, 0.05],
    ):
        if entry_b == 0 and exit_b == 0:
            continue
        lev = sma_entry_exit_leverage(
            prices,
            window=window,
            leverage=1.0,
            entry_buffer=entry_b,
            exit_buffer=exit_b,
            confirm_days=1,
        )
        label = strategy_label(
            family="buffer",
            window=window,
            leverage=1.0,
            entry_buffer=entry_b,
            exit_buffer=exit_b,
        )
        configs.append(
            (
                label,
                lev,
                {
                    "family": "buffer",
                    "sma_window": window,
                    "entry_buffer": entry_b,
                    "exit_buffer": exit_b,
                },
            )
        )

    # 3. Confirmation days (SMA20)
    for confirm in (2, 3, 5):
        for exit_b in (0.0, 0.01, 0.02):
            lev = sma_entry_exit_leverage(
                prices,
                window=20,
                leverage=1.0,
                exit_buffer=exit_b,
                confirm_days=confirm,
            )
            label = f"SMA20 1x/cash out-{exit_b*100:g}% {confirm}d confirm"
            configs.append(
                (
                    label,
                    lev,
                    {"family": "confirm", "confirm_days": confirm, "exit_buffer": exit_b},
                )
            )

    # 4. Dual SMA
    for fast, slow in ((20, 50), (20, 100), (10, 50)):
        if fast >= slow:
            continue
        lev = dual_sma_leverage(prices, fast=fast, slow=slow, confirm_days=1)
        configs.append(
            (
                f"Dual SMA enter>{fast}d exit<{slow}d",
                lev,
                {"family": "dual_sma", "fast": fast, "slow": slow},
            )
        )

    # 5. Min hold after Guarded/SMA raw signal
    for min_hold in (5, 10, 20):
        lev = min_hold_filter(lev_sma20, min_hold_days=min_hold)
        configs.append(
            (
                f"SMA20 1x/cash + min hold {min_hold}d",
                lev,
                {"family": "min_hold", "min_hold_days": min_hold},
            )
        )
        lev = min_hold_filter(lev_guard, min_hold_days=min_hold)
        configs.append(
            (
                f"Guarded max 1x + min hold {min_hold}d",
                lev,
                {"family": "min_hold", "min_hold_days": min_hold},
            )
        )

    # 6. Guarded with exit buffer
    for exit_b, confirm in product([0.01, 0.02, 0.03, 0.05], [1, 2, 3]):
        lev, counts = guarded_with_exit_buffer(
            prices,
            exit_buffer=exit_b,
            confirm_days=confirm,
            max_leverage=1.0,
        )
        configs.append(
            (
                f"Guarded max 1x exit-{exit_b*100:g}% {confirm}d confirm",
                lev,
                {"family": "guarded_exit", "exit_buffer": exit_b, "confirm_days": confirm, **counts},
            )
        )

    print(f"Running {len(configs)} turnover-reduction configs...", flush=True)
    for i, (label, lev, meta) in enumerate(configs, 1):
        rows.append(run_row(prices, lev, label, **meta))
        if i % 40 == 0:
            print(f"  ... {i}/{len(configs)}", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "comparison.csv", index=False)

    sma_base = df[df["strategy"] == "SMA20 1x/cash (baseline)"].iloc[0]
    guard_base = df[df["strategy"] == "Guarded A5/B25 max 1x (baseline)"].iloc[0]
    sweep = df[~df["family"].isin(["baseline"])].copy()

    vs_sma = sweep[sweep["rebalances"] < sma_base["rebalances"]].sort_values("rebalances")
    vs_guard = sweep[sweep["rebalances"] < guard_base["rebalances"]].sort_values("rebalances")

    no_sac_sma = no_sacrifice_filter(vs_sma, sma_base).sort_values("rebalances")
    no_sac_guard = no_sacrifice_filter(vs_guard, guard_base).sort_values("rebalances")

    pareto_sma = pareto_3d(
        sweep.assign(
            rebalances=sweep["rebalances"],
        )
    )
    pareto_sma.to_csv(OUTPUT_DIR / "pareto_frontier.csv", index=False)

    no_sac_sma.to_csv(OUTPUT_DIR / "no_sacrifice_vs_sma20.csv", index=False)
    no_sac_guard.to_csv(OUTPUT_DIR / "no_sacrifice_vs_guarded.csv", index=False)
    vs_sma.sort_values("rebalances").head(30).to_csv(OUTPUT_DIR / "lowest_rebalances_vs_sma.csv", index=False)

    summary = {
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sample": {
            "start": prices.index[0].date().isoformat(),
            "end": prices.index[-1].date().isoformat(),
            "days": len(prices),
        },
        "assumptions": {
            "initial_capital": INITIAL_CAPITAL,
            "annual_inflow": 10,
            "trading_cost_pct": TRADING_COST_FROM_MID_PCT,
            "ticker": "LQQ3.L",
        },
        "baselines": {
            "sma20": sma_base.to_dict(),
            "guarded": guard_base.to_dict(),
        },
        "counts": {
            "configs": len(configs),
            "fewer_rebalances_than_sma20": int(len(vs_sma)),
            "fewer_rebalances_than_guarded": int(len(vs_guard)),
            "no_sacrifice_vs_sma20": int(len(no_sac_sma)),
            "no_sacrifice_vs_guarded": int(len(no_sac_guard)),
        },
        "best_no_sacrifice_sma20": no_sac_sma.head(10).to_dict(orient="records"),
        "best_no_sacrifice_guarded": no_sac_guard.head(10).to_dict(orient="records"),
        "lowest_rebalances_any": vs_sma.head(5).to_dict(orient="records"),
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

    def print_block(title: str, sub: pd.DataFrame, n: int = 8) -> None:
        print(f"\n=== {title} ===")
        if sub.empty:
            print("  (none)")
            return
        for _, r in sub.head(n).iterrows():
            print(
                f"  {str(r['strategy'])[:52]:52}  "
                f"CAGR {r['cagr']*100:6.2f}%  Sharpe {r['sharpe']:5.2f}  "
                f"MaxDD {r['max_drawdown']*100:6.2f}%  Rebals {int(r['rebalances']):4d}  "
                f"End ${r['end_$']:,.0f}"
            )

    print("\n--- Baselines ---")
    print_block("SMA20", pd.DataFrame([sma_base]), 1)
    print_block("Guarded", pd.DataFrame([guard_base]), 1)
    print_block(
        f"No sacrifice vs SMA20 ({len(no_sac_sma)} configs) — sorted by rebalances",
        no_sac_sma,
    )
    print_block(
        f"No sacrifice vs Guarded ({len(no_sac_guard)} configs)",
        no_sac_guard,
    )
    print_block("Lowest rebalances (any CAGR/DD tradeoff)", vs_sma)

    print(f"\nWrote {OUTPUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
