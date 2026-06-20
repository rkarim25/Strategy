"""Sweep gold Guarded sell buffer: exit on cross down through SMA20 * (1 + X).

Buy unchanged: 1x when close > SMA20 (same as site default).
Sell variant: while invested, exit to cash when close crosses below SMA20 + X% from above
             (prior close >= SMA20*(1+X), today's close < SMA20*(1+X)).
Baseline: exit to cash when close <= SMA20 (daily, stateless — site default).

Guarded A5/B25 SMA20 Lead max 1x on GC=F, ~30y, same engine as backtest_gold_guarded.py.
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
from test_tiered_dd_recovery_guarded import BASE_SMA_WINDOW

OUTPUT_DIR = Path("output") / "gold_sma_sell_buffer"


def build_x_grid() -> list[float | None]:
    """Dense sweep: baseline, negative in 0.1% steps, +0.1-4.9%, +5.0-15.0% in 0.1%."""
    xs: list[float] = []
    xs.extend(round(v, 4) for v in np.arange(-0.05, 0.0, 0.001))  # -5.0% .. -0.1%
    xs.append(0.0)
    xs.extend(round(v, 4) for v in np.arange(0.001, 0.05, 0.001))  # +0.1% .. +4.9%
    xs.extend(round(v, 4) for v in np.arange(0.05, 0.151, 0.001))  # +5.0% .. +15.0%
    unique = sorted(set(xs))
    return [None, *unique]


X_GRID = build_x_grid()


def crossed_down(
    px: float, prev_px: float, threshold: float, prev_threshold: float
) -> bool:
    if not all(np.isfinite(v) for v in (px, prev_px, threshold, prev_threshold)):
        return False
    return prev_px >= prev_threshold and px < threshold


def base_leverage_with_sell_buffer(
    px: float,
    sma: float,
    prev_px: float,
    prev_sma: float,
    *,
    in_position: bool,
    sell_buffer_x: float | None,
) -> tuple[float, bool]:
    if not np.isfinite(sma) or sma <= 0:
        return 0.0, False

    if sell_buffer_x is None:
        new_in = px > sma
        return (1.0 if new_in else 0.0), new_in

    threshold = sma * (1.0 + sell_buffer_x)
    prev_threshold = prev_sma * (1.0 + sell_buffer_x) if np.isfinite(prev_sma) else float("nan")

    if in_position:
        if crossed_down(px, prev_px, threshold, prev_threshold):
            return 0.0, False
        return 1.0, True

    if px > sma:
        return 1.0, True
    return 0.0, False


def guarded_lead_leverage_sell_buffer(
    prices: pd.DataFrame,
    *,
    sell_buffer_x: float | None,
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
    tier2_entries = 0
    tier3_entries = 0
    lead_only_days = 0
    guard_blocked_days = 0
    buffer_exits = 0

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

        base_lev, in_base_long = base_leverage_with_sell_buffer(
            px,
            sma,
            prev_px,
            prev_sma,
            in_position=in_base_long,
            sell_buffer_x=sell_buffer_x,
        )
        if sell_buffer_x is not None and prev_in_base and not in_base_long:
            buffer_exits += 1
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

    return lev, {
        "tier2_entries": tier2_entries,
        "tier3_entries": tier3_entries,
        "lead_only_days": lead_only_days,
        "guard_blocked_days": guard_blocked_days,
        "buffer_exits": buffer_exits,
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_days_1x": float((lev == 1.0).mean() * 100.0),
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
    if sell_x is None:
        label = "below_SMA20 (default)"
    elif sell_x >= 0:
        label = f"cross below SMA20+{sell_x:.2%}"
    else:
        label = f"cross below SMA20{sell_x:.2%}"
    row: dict[str, object] = {
        "strategy": strategy,
        "sell_buffer_x": sell_x,
        "sell_label": label,
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


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading gold panel (GC=F)...", flush=True)
    prices = download_gold_panel()
    print(
        f"  {len(prices)} sessions: {prices.index[0].date()} -> {prices.index[-1].date()}",
        flush=True,
    )

    rows: list[dict[str, object]] = []
    for sell_x in X_GRID:
        lev, counts = guarded_lead_leverage_sell_buffer(
            prices, sell_buffer_x=sell_x, max_leverage=1.0
        )
        rows.append(
            run_row(
                prices,
                strategy=f"Guarded max 1x (X={sell_x})",
                sell_x=sell_x,
                lev=lev,
                counts=counts,
            )
        )

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "guarded_sell_buffer_sweep.csv", index=False)

    pos_5_15 = df[(df["sell_buffer_x"] >= 0.05) & (df["sell_buffer_x"] <= 0.15)].copy()
    pos_5_15.to_csv(OUTPUT_DIR / "guarded_sell_buffer_5_to_15.csv", index=False)

    baseline = df[df["sell_buffer_x"].isna()].iloc[0]
    variants = df[df["sell_buffer_x"].notna()].copy()
    variants["delta_cagr_pp"] = (variants["cagr"] - baseline["cagr"]) * 100.0
    variants["delta_sharpe"] = variants["sharpe"] - baseline["sharpe"]
    variants["delta_max_dd_pp"] = (variants["max_drawdown"] - baseline["max_drawdown"]) * 100.0
    variants["delta_end_$"] = variants["end_$"] - baseline["end_$"]
    variants["beats_baseline"] = (
        (variants["cagr"] > baseline["cagr"])
        & (variants["sharpe"] > baseline["sharpe"])
        & (variants["max_drawdown"] >= baseline["max_drawdown"])
    )
    ranked = variants.sort_values(["sharpe", "cagr"], ascending=False)
    ranked.to_csv(OUTPUT_DIR / "guarded_sell_buffer_ranked.csv", index=False)

    best = ranked.iloc[0]
    best_cagr = variants.sort_values("cagr", ascending=False).iloc[0]
    best_calmar = variants.sort_values("calmar", ascending=False).iloc[0]
    winners = variants[variants["beats_baseline"]]
    near_neg = variants[(variants["sell_buffer_x"] >= -0.02) & (variants["sell_buffer_x"] <= 0)]
    near_neg_ranked = near_neg.sort_values(["sharpe", "cagr"], ascending=False)
    pos_5_15["delta_cagr_pp"] = (pos_5_15["cagr"] - baseline["cagr"]) * 100.0
    pos_5_15["delta_sharpe"] = pos_5_15["sharpe"] - baseline["sharpe"]
    pos_5_15["beats_baseline"] = (
        (pos_5_15["cagr"] > baseline["cagr"])
        & (pos_5_15["sharpe"] > baseline["sharpe"])
        & (pos_5_15["max_drawdown"] >= baseline["max_drawdown"])
    )
    pos_5_15_ranked = pos_5_15.sort_values(["sharpe", "cagr"], ascending=False)
    pos_5_15_ranked.to_csv(OUTPUT_DIR / "guarded_sell_buffer_5_to_15_ranked.csv", index=False)
    best_pos_5_15 = pos_5_15_ranked.iloc[0] if len(pos_5_15_ranked) else None
    best_pos_5_15_cagr = (
        pos_5_15.sort_values("cagr", ascending=False).iloc[0] if len(pos_5_15) else None
    )
    pos_5_15_winners = pos_5_15[pos_5_15["beats_baseline"]]

    summary = {
        "rule": {
            "buy": "Enter 1x when close > SMA20",
            "baseline_sell": "Exit when close <= SMA20",
            "variant_sell": "Exit on cross down through SMA20*(1+X) from above",
        },
        "baseline": {
            "cagr": float(baseline["cagr"]),
            "sharpe": float(baseline["sharpe"]),
            "max_drawdown": float(baseline["max_drawdown"]),
            "end_$": float(baseline["end_$"]),
            "pct_days_cash": float(baseline["pct_days_cash"]),
        },
        "best_by_sharpe": {
            "sell_label": str(best["sell_label"]),
            "cagr": float(best["cagr"]),
            "sharpe": float(best["sharpe"]),
            "max_drawdown": float(best["max_drawdown"]),
            "end_$": float(best["end_$"]),
            "delta_cagr_pp": float(best["delta_cagr_pp"]),
            "delta_sharpe": float(best["delta_sharpe"]),
            "buffer_exits": int(best.get("buffer_exits", 0)),
        },
        "best_by_cagr": {
            "sell_label": str(best_cagr["sell_label"]),
            "cagr": float(best_cagr["cagr"]),
            "sharpe": float(best_cagr["sharpe"]),
            "max_drawdown": float(best_cagr["max_drawdown"]),
            "calmar": float(best_cagr["calmar"]) if pd.notna(best_cagr["calmar"]) else None,
            "end_$": float(best_cagr["end_$"]),
            "delta_cagr_pp": float(best_cagr["delta_cagr_pp"]),
        },
        "best_by_calmar": {
            "sell_label": str(best_calmar["sell_label"]),
            "cagr": float(best_calmar["cagr"]),
            "sharpe": float(best_calmar["sharpe"]),
            "max_drawdown": float(best_calmar["max_drawdown"]),
            "calmar": float(best_calmar["calmar"]) if pd.notna(best_calmar["calmar"]) else None,
            "end_$": float(best_calmar["end_$"]),
        },
        "grid_size": len(X_GRID),
        "positive_5_to_15_count": int(len(pos_5_15)),
        "best_positive_5_to_15_by_sharpe": (
            {
                "sell_label": str(best_pos_5_15["sell_label"]),
                "sell_buffer_x": float(best_pos_5_15["sell_buffer_x"]),
                "cagr": float(best_pos_5_15["cagr"]),
                "sharpe": float(best_pos_5_15["sharpe"]),
                "max_drawdown": float(best_pos_5_15["max_drawdown"]),
                "end_$": float(best_pos_5_15["end_$"]),
                "pct_days_cash": float(best_pos_5_15["pct_days_cash"]),
                "buffer_exits": int(best_pos_5_15.get("buffer_exits", 0)),
            }
            if best_pos_5_15 is not None
            else None
        ),
        "best_positive_5_to_15_by_cagr": (
            {
                "sell_label": str(best_pos_5_15_cagr["sell_label"]),
                "sell_buffer_x": float(best_pos_5_15_cagr["sell_buffer_x"]),
                "cagr": float(best_pos_5_15_cagr["cagr"]),
                "sharpe": float(best_pos_5_15_cagr["sharpe"]),
                "max_drawdown": float(best_pos_5_15_cagr["max_drawdown"]),
                "end_$": float(best_pos_5_15_cagr["end_$"]),
            }
            if best_pos_5_15_cagr is not None
            else None
        ),
        "positive_5_to_15_beats_baseline_count": int(len(pos_5_15_winners)),
        "beats_baseline_count": int(len(winners)),
        "winners": [
            {
                "sell_label": str(r["sell_label"]),
                "cagr_pct": f"{r['cagr'] * 100:.2f}%",
                "sharpe": f"{r['sharpe']:.3f}",
                "max_dd_pct": f"{r['max_drawdown'] * 100:.2f}%",
                "delta_cagr_pp": f"{r['delta_cagr_pp']:+.2f}",
            }
            for _, r in winners.iterrows()
        ],
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print("\n=== Baseline (sell when close <= SMA20) ===")
    print(
        f"  CAGR {baseline['cagr'] * 100:.2f}%  Sharpe {baseline['sharpe']:.3f}  "
        f"MaxDD {baseline['max_drawdown'] * 100:.2f}%  End ${baseline['end_$']:,.0f}  "
        f"Cash {baseline['pct_days_cash']:.1f}%"
    )
    print("\n=== Best variant (cross below SMA20+X from above) ===")
    print(
        f"  {best['sell_label']}: CAGR {best['cagr'] * 100:.2f}%  Sharpe {best['sharpe']:.3f}  "
        f"MaxDD {best['max_drawdown'] * 100:.2f}%  End ${best['end_$']:,.0f}  "
        f"(dCAGR {best['delta_cagr_pp']:+.2f}pp  dSharpe {best['delta_sharpe']:+.3f}  "
        f"exits {int(best.get('buffer_exits', 0))})"
    )
    print(f"\n  Variants beating baseline (CAGR+Sharpe+MaxDD): {len(winners)}")
    print(f"  Grid size: {len(X_GRID)} values (incl. baseline)")

    print("\n=== Best by CAGR ===")
    print(
        f"  {best_cagr['sell_label']}: CAGR {best_cagr['cagr'] * 100:.2f}%  Sharpe {best_cagr['sharpe']:.3f}  "
        f"MaxDD {best_cagr['max_drawdown'] * 100:.2f}%  End ${best_cagr['end_$']:,.0f}  "
        f"(dCAGR {best_cagr['delta_cagr_pp']:+.2f}pp)"
    )

    print("\n=== Fine grid -2% to 0% (top 12 by Sharpe) ===")
    for _, r in near_neg_ranked.head(12).iterrows():
        print(
            f"  {str(r['sell_label']):<32} "
            f"CAGR {r['cagr'] * 100:6.2f}%  Sharpe {r['sharpe']:.3f}  "
            f"MaxDD {r['max_drawdown'] * 100:6.2f}%  "
            f"dCAGR {r['delta_cagr_pp']:+5.2f}pp  exits {int(r.get('buffer_exits', 0))}"
        )

    print("\n=== +5% to +15% band (top 15 by Sharpe) ===")
    for _, r in pos_5_15_ranked.head(15).iterrows():
        d_cagr = (r["cagr"] - baseline["cagr"]) * 100.0
        d_sh = r["sharpe"] - baseline["sharpe"]
        print(
            f"  {str(r['sell_label']):<32} "
            f"CAGR {r['cagr'] * 100:6.2f}%  Sharpe {r['sharpe']:.3f}  "
            f"MaxDD {r['max_drawdown'] * 100:6.2f}%  "
            f"dCAGR {d_cagr:+5.2f}pp  dSharpe {d_sh:+.3f}  "
            f"cash {r['pct_days_cash']:.1f}%  exits {int(r.get('buffer_exits', 0))}"
        )

    if best_pos_5_15 is not None:
        print("\n=== Best in +5%..+15% (by Sharpe) ===")
        print(
            f"  {best_pos_5_15['sell_label']}: CAGR {best_pos_5_15['cagr'] * 100:.2f}%  "
            f"Sharpe {best_pos_5_15['sharpe']:.3f}  MaxDD {best_pos_5_15['max_drawdown'] * 100:.2f}%  "
            f"End ${best_pos_5_15['end_$']:,.0f}  cash {best_pos_5_15['pct_days_cash']:.1f}%"
        )

    print("\n=== Top 10 overall by Sharpe ===")
    for _, r in ranked.head(10).iterrows():
        print(
            f"  {str(r['sell_label']):<32} "
            f"CAGR {r['cagr'] * 100:6.2f}%  Sharpe {r['sharpe']:.3f}  "
            f"MaxDD {r['max_drawdown'] * 100:6.2f}%  "
            f"dCAGR {r['delta_cagr_pp']:+5.2f}pp  exits {int(r.get('buffer_exits', 0))}"
        )

    print(f"\nWrote {OUTPUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
