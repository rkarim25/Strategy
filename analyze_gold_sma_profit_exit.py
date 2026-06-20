"""Sweep gold Guarded base-rule exit: sell when price is X% above SMA20 (not below SMA20).

Buy signal unchanged: enter 1x when close > SMA20 (first entry).
After a profit exit: re-enter only on a cross from below SMA20 (prior close <= SMA20, now above).
Default (baseline): exit to cash when close <= SMA20 (stateless each day).

Tests the site default Guarded A5/B25 SMA20 Lead (max 1x) on GC=F, ~30y, same engine as backtest_gold_guarded.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from analyze_cross_asset_guarded_1x import DEFAULT_GUARDED
from backtest_gold_guarded import download_gold_panel, make_engine
from metrics import comprehensive_stats, invested_vs_tbills_sessions
from test_tiered_dd_recovery_guarded import BASE_SMA_WINDOW, sma_cash_leverage

OUTPUT_DIR = Path("output") / "gold_sma_profit_exit"

# X = sell when close >= SMA20 * (1 + X). None = default below-SMA exit.
X_GRID = [
    None,  # baseline: exit when close <= SMA20
    0.0,
    0.01,
    0.02,
    0.025,
    0.03,
    0.035,
    0.04,
    0.05,
    0.06,
    0.07,
    0.08,
    0.09,
    0.10,
    0.12,
    0.15,
    0.18,
    0.20,
    0.25,
    0.30,
    0.40,
    0.50,
    0.75,
    1.00,
]


def crossed_above_sma(px: float, sma: float, prev_px: float, prev_sma: float) -> bool:
    if not all(np.isfinite(v) for v in (px, sma, prev_px, prev_sma)):
        return False
    return prev_px <= prev_sma and px > sma


def base_leverage_stateful(
    px: float,
    sma: float,
    prev_px: float,
    prev_sma: float,
    *,
    in_position: bool,
    need_cross_reentry: bool,
    sell_pct_above_sma: float | None,
) -> tuple[float, bool, bool]:
    """Return (base_lev, in_position, need_cross_reentry)."""
    if not np.isfinite(sma) or sma <= 0:
        return 0.0, False, need_cross_reentry

    if sell_pct_above_sma is None:
        new_in = px > sma
        return (1.0 if new_in else 0.0), new_in, False

    if in_position:
        if px >= sma * (1.0 + sell_pct_above_sma):
            return 0.0, False, True
        return 1.0, True, False

    if need_cross_reentry:
        if crossed_above_sma(px, sma, prev_px, prev_sma):
            return 1.0, True, False
        return 0.0, False, True

    if px > sma:
        return 1.0, True, False
    return 0.0, False, False


def guarded_lead_leverage_profit_exit(
    prices: pd.DataFrame,
    *,
    sell_pct_above_sma: float | None,
    max_leverage: float = 1.0,
    trigger_a: float = DEFAULT_GUARDED["trigger_a"],
    trigger_b: float = DEFAULT_GUARDED["trigger_b"],
    lead_pct_below_sma20: float = DEFAULT_GUARDED["lead_pct_below_sma20"],
    x_return: float = DEFAULT_GUARDED["x_return"],
    y_return: float = DEFAULT_GUARDED["y_return"],
) -> tuple[pd.Series, dict[str, float | int]]:
    close = prices["spx_close"].astype(float)
    sma20 = close.rolling(BASE_SMA_WINDOW, min_periods=BASE_SMA_WINDOW).mean()
    recovery_guard = (close >= sma20 * (1.0 - lead_pct_below_sma20)).fillna(False)
    spx_dd = close / close.cummax() - 1.0

    lev = pd.Series(0.0, index=prices.index)
    regime = "base"
    entry_close = 0.0
    in_base_long = False
    need_cross_reentry = False
    tier2_entries = 0
    tier3_entries = 0
    lead_only_days = 0
    guard_blocked_days = 0
    profit_exits = 0
    cross_reentries = 0

    def cap(value: float) -> float:
        return float(min(max(value, 0.0), max_leverage))

    prev_px = float("nan")
    prev_sma = float("nan")
    prev_in_base = False

    for dt in prices.index:
        px = float(close.loc[dt])
        sma = float(sma20.loc[dt]) if pd.notna(sma20.loc[dt]) else float("nan")
        dd = float(spx_dd.loc[dt])
        recovery_ok = bool(recovery_guard.loc[dt])

        waiting_cross = need_cross_reentry and not in_base_long
        base_lev, in_base_long, need_cross_reentry = base_leverage_stateful(
            px,
            sma,
            prev_px,
            prev_sma,
            in_position=in_base_long,
            need_cross_reentry=need_cross_reentry,
            sell_pct_above_sma=sell_pct_above_sma,
        )
        if sell_pct_above_sma is not None and prev_in_base and not in_base_long:
            profit_exits += 1
        if sell_pct_above_sma is not None and waiting_cross and in_base_long:
            cross_reentries += 1
        prev_in_base = in_base_long
        prev_px = px
        prev_sma = sma

        base_ok = px > sma if np.isfinite(sma) else False
        if recovery_ok and not base_ok:
            lead_only_days += 1

        if regime == "tier3":
            if px / entry_close - 1.0 >= y_return:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = cap(3.0)
                continue
            else:
                guard_blocked_days += 1
                lev.loc[dt] = cap(base_lev)
                continue

        if regime == "tier2":
            if dd <= -trigger_b and recovery_ok:
                regime = "tier3"
                entry_close = px
                tier3_entries += 1
                lev.loc[dt] = cap(3.0)
                continue
            if px / entry_close - 1.0 >= x_return:
                regime = "base"
            elif recovery_ok:
                lev.loc[dt] = cap(2.0)
                continue
            else:
                guard_blocked_days += 1
                lev.loc[dt] = cap(base_lev)
                continue

        if dd <= -trigger_b and recovery_ok:
            regime = "tier3"
            entry_close = px
            tier3_entries += 1
            lev.loc[dt] = cap(3.0)
        elif dd <= -trigger_a and recovery_ok:
            regime = "tier2"
            entry_close = px
            tier2_entries += 1
            lev.loc[dt] = cap(2.0)
        else:
            if dd <= -trigger_a and not recovery_ok:
                guard_blocked_days += 1
            lev.loc[dt] = cap(base_lev)

    counts = {
        "tier2_entries": tier2_entries,
        "tier3_entries": tier3_entries,
        "lead_only_days": lead_only_days,
        "guard_blocked_days": guard_blocked_days,
        "profit_exits": profit_exits,
        "cross_reentries": cross_reentries,
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_days_1x": float((lev == 1.0).mean() * 100.0),
    }
    return lev, counts


def sma_cash_profit_exit(
    prices: pd.DataFrame,
    *,
    sell_pct_above_sma: float | None,
    leverage: float = 1.0,
    window: int = BASE_SMA_WINDOW,
) -> tuple[pd.Series, dict[str, int | float]]:
    close = prices["spx_close"].astype(float)
    sma = close.rolling(window, min_periods=window).mean()

    lev = pd.Series(0.0, index=prices.index)
    in_position = False
    need_cross_reentry = False
    profit_exits = 0
    cross_reentries = 0
    prev_in = False
    prev_px = float("nan")
    prev_sma = float("nan")

    for dt in prices.index:
        px = float(close.loc[dt])
        ma = float(sma.loc[dt]) if pd.notna(sma.loc[dt]) else float("nan")
        waiting_cross = need_cross_reentry and not in_position
        base_lev, in_position, need_cross_reentry = base_leverage_stateful(
            px,
            ma,
            prev_px,
            prev_sma,
            in_position=in_position,
            need_cross_reentry=need_cross_reentry,
            sell_pct_above_sma=sell_pct_above_sma,
        )
        if sell_pct_above_sma is not None and prev_in and not in_position:
            profit_exits += 1
        if sell_pct_above_sma is not None and waiting_cross and in_position:
            cross_reentries += 1
        prev_in = in_position
        prev_px = px
        prev_sma = ma
        lev.loc[dt] = leverage if base_lev > 0 else 0.0

    return lev, {
        "profit_exits": profit_exits,
        "cross_reentries": cross_reentries,
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
    }


def run_row(
    prices: pd.DataFrame,
    *,
    strategy: str,
    sell_x: float | None,
    lev: pd.Series,
    counts: dict[str, float | int] | None = None,
) -> dict[str, object]:
    result = make_engine().run(prices, lev, name=strategy)
    stats = comprehensive_stats(result.equity, result.daily_returns)
    cash = invested_vs_tbills_sessions(result.leverage)
    row: dict[str, object] = {
        "strategy": strategy,
        "sell_pct_above_sma20": sell_x,
        "sell_label": "below_SMA20 (default)" if sell_x is None else f"+{sell_x:.2%} above SMA20",
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "max_drawdown": stats["max_drawdown"],
        "calmar": stats.get("calmar"),
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": result.rebalance_count,
        "trading_costs_total": result.trading_costs_total,
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_cash_sessions": cash["pct_sessions_tbills"],
    }
    if counts:
        row.update(counts)
    return row


def x_label(sell_x: float | None) -> str:
    if sell_x is None:
        return "default_below_SMA"
    return f"x_{sell_x:.4f}".replace(".", "p")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading gold panel (GC=F)...", flush=True)
    prices = download_gold_panel()
    print(
        f"  {len(prices)} sessions: {prices.index[0].date()} -> {prices.index[-1].date()}",
        flush=True,
    )

    guarded_rows: list[dict[str, object]] = []
    sma_rows: list[dict[str, object]] = []

    for sell_x in X_GRID:
        label = x_label(sell_x)
        lev_g, counts_g = guarded_lead_leverage_profit_exit(
            prices, sell_pct_above_sma=sell_x, max_leverage=1.0
        )
        guarded_rows.append(
            run_row(
                prices,
                strategy=f"Guarded max 1x ({label})",
                sell_x=sell_x,
                lev=lev_g,
                counts=counts_g,
            )
        )

        lev_s, counts_s = sma_cash_profit_exit(prices, sell_pct_above_sma=sell_x)
        sma_rows.append(
            run_row(
                prices,
                strategy=f"SMA20 1x/cash ({label})",
                sell_x=sell_x,
                lev=lev_s,
                counts=counts_s,
            )
        )

    guarded_df = pd.DataFrame(guarded_rows)
    sma_df = pd.DataFrame(sma_rows)
    guarded_df.to_csv(OUTPUT_DIR / "guarded_profit_exit_sweep.csv", index=False)
    sma_df.to_csv(OUTPUT_DIR / "sma20_profit_exit_sweep.csv", index=False)

    baseline_g = guarded_df[guarded_df["sell_pct_above_sma20"].isna()].iloc[0]
    baseline_s = sma_df[sma_df["sell_pct_above_sma20"].isna()].iloc[0]

    def rank_vs_baseline(df: pd.DataFrame, baseline: pd.Series) -> pd.DataFrame:
        out = df[df["sell_pct_above_sma20"].notna()].copy()
        out["delta_cagr_pp"] = (out["cagr"] - baseline["cagr"]) * 100.0
        out["delta_max_dd_pp"] = (out["max_drawdown"] - baseline["max_drawdown"]) * 100.0
        out["delta_sharpe"] = out["sharpe"] - baseline["sharpe"]
        out["delta_end_$"] = out["end_$"] - baseline["end_$"]
        out["beats_baseline_cagr"] = out["cagr"] > baseline["cagr"]
        out["beats_baseline_sharpe"] = out["sharpe"] > baseline["sharpe"]
        out["beats_baseline_calmar"] = out["calmar"] > baseline["calmar"]
        out["better_risk_adj"] = (out["sharpe"] > baseline["sharpe"]) & (
            out["max_drawdown"] >= baseline["max_drawdown"]
        )
        return out.sort_values(["sharpe", "cagr"], ascending=False)

    guarded_ranked = rank_vs_baseline(guarded_df, baseline_g)
    sma_ranked = rank_vs_baseline(sma_df, baseline_s)
    guarded_ranked.to_csv(OUTPUT_DIR / "guarded_profit_exit_ranked.csv", index=False)
    sma_ranked.to_csv(OUTPUT_DIR / "sma20_profit_exit_ranked.csv", index=False)

    best_g = guarded_ranked.iloc[0] if len(guarded_ranked) else baseline_g
    best_s = sma_ranked.iloc[0] if len(sma_ranked) else baseline_s

    improved_g = guarded_ranked[
        (guarded_ranked["beats_baseline_cagr"])
        & (guarded_ranked["beats_baseline_sharpe"])
        & (guarded_ranked["max_drawdown"] >= baseline_g["max_drawdown"])
    ]

    summary = {
        "sample": {
            "ticker": "GC=F",
            "start": prices.index[0].date().isoformat(),
            "end": prices.index[-1].date().isoformat(),
            "days": len(prices),
        },
        "rule": {
            "buy": "Enter 1x when close > SMA20 (unchanged)",
            "default_sell": "Exit to cash when close <= SMA20",
            "variant_sell": "Exit to cash when close >= SMA20 * (1 + X)",
            "variant_reentry": "After profit exit, re-enter only on cross from below SMA20",
            "guarded": "Guarded A5/B25 SMA20 Lead max 1x; only base-rule exit modified",
        },
        "baseline_guarded": {
            k: (float(v) if isinstance(v, (float, np.floating)) else v)
            for k, v in baseline_g.items()
            if k in ("sell_label", "cagr", "sharpe", "max_drawdown", "calmar", "end_$", "pct_days_cash")
        },
        "baseline_sma20": {
            k: (float(v) if isinstance(v, (float, np.floating)) else v)
            for k, v in baseline_s.items()
            if k in ("sell_label", "cagr", "sharpe", "max_drawdown", "calmar", "end_$", "pct_days_cash")
        },
        "best_guarded_by_sharpe": {
            "sell_label": str(best_g["sell_label"]),
            "cagr": float(best_g["cagr"]),
            "sharpe": float(best_g["sharpe"]),
            "max_drawdown": float(best_g["max_drawdown"]),
            "calmar": float(best_g["calmar"]) if pd.notna(best_g["calmar"]) else None,
            "end_$": float(best_g["end_$"]),
            "delta_cagr_pp": float(best_g["delta_cagr_pp"]),
            "delta_sharpe": float(best_g["delta_sharpe"]),
        },
        "best_sma20_by_sharpe": {
            "sell_label": str(best_s["sell_label"]),
            "cagr": float(best_s["cagr"]),
            "sharpe": float(best_s["sharpe"]),
            "max_drawdown": float(best_s["max_drawdown"]),
            "end_$": float(best_s["end_$"]),
        },
        "guarded_beat_baseline_count": int(len(improved_g)),
        "guarded_improved_rows": [
            {
                "sell_label": str(r["sell_label"]),
                "cagr_pct": f"{r['cagr'] * 100:.2f}%",
                "sharpe": f"{r['sharpe']:.3f}",
                "max_dd_pct": f"{r['max_drawdown'] * 100:.2f}%",
                "delta_cagr_pp": f"{r['delta_cagr_pp']:+.2f}",
            }
            for _, r in improved_g.head(10).iterrows()
        ],
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print("\n=== Gold Guarded max 1x — baseline (default below-SMA exit) ===")
    print(
        f"  CAGR {baseline_g['cagr'] * 100:.2f}%  Sharpe {baseline_g['sharpe']:.3f}  "
        f"MaxDD {baseline_g['max_drawdown'] * 100:.2f}%  End ${baseline_g['end_$']:,.0f}  "
        f"Cash {baseline_g['pct_days_cash']:.1f}%"
    )
    print("\n=== Best Guarded variant by Sharpe (profit exit above SMA) ===")
    print(
        f"  {best_g['sell_label']}: CAGR {best_g['cagr'] * 100:.2f}%  Sharpe {best_g['sharpe']:.3f}  "
        f"MaxDD {best_g['max_drawdown'] * 100:.2f}%  End ${best_g['end_$']:,.0f}  "
        f"(dCAGR {best_g['delta_cagr_pp']:+.2f}pp  dSharpe {best_g['delta_sharpe']:+.3f})"
    )
    print(f"\n  Variants beating baseline on CAGR+Sharpe with equal/better MaxDD: {len(improved_g)}")

    print("\n=== Top 8 Guarded variants (by Sharpe) ===")
    for _, r in guarded_ranked.head(8).iterrows():
        print(
            f"  {str(r['sell_label']):<28} "
            f"CAGR {r['cagr'] * 100:6.2f}%  Sharpe {r['sharpe']:.3f}  "
            f"MaxDD {r['max_drawdown'] * 100:6.2f}%  "
            f"dCAGR {r['delta_cagr_pp']:+5.2f}pp"
        )

    print("\n=== SMA20 1x/cash reference — baseline vs best ===")
    print(
        f"  Baseline: CAGR {baseline_s['cagr'] * 100:.2f}%  Sharpe {baseline_s['sharpe']:.3f}  "
        f"MaxDD {baseline_s['max_drawdown'] * 100:.2f}%"
    )
    print(
        f"  Best:     {best_s['sell_label']}  CAGR {best_s['cagr'] * 100:.2f}%  "
        f"Sharpe {best_s['sharpe']:.3f}  MaxDD {best_s['max_drawdown'] * 100:.2f}%"
    )

    print(f"\nWrote {OUTPUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
