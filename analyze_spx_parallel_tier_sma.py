"""
Parallel tier SMA rotation on S&P 500 (SPX_ETP benchmarks).

Instead of exiting recovery tiers at fixed +X%/+Y% from entry, each leverage sleeve
(1x / 2x / 3x ETP) is monitored on its own benchmark price with SMA20. Daily
exposure is chosen among cash, 1x, 2x, 3x based on which tier looks most attractive.

Writes output/spx_parallel_tier_sma/ (strategy_plan.md, comparison.csv, summary.json).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from backtest_spx_guarded import DEFAULT_SPEC, download_spx_panel, make_engine, run_strategy
from core.engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT
from core.etp_leverage import SPX_ETP, build_etp_return_panel, etp_coverage_summary
from core.metrics import comprehensive_stats, invested_vs_tbills_sessions
from test_guarded_balanced_candidate import guarded_strategy_leverage
from test_tiered_dd_recovery_guarded import BASE_SMA_WINDOW, sma_cash_leverage

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output" / "spx_parallel_tier_sma"

SMA_WINDOW = BASE_SMA_WINDOW
LEAD_PCT = DEFAULT_SPEC["lead_pct_below_sma20"]
TRIGGER_A = DEFAULT_SPEC["trigger_a"]
TRIGGER_B = DEFAULT_SPEC["trigger_b"]


def benchmark_prices_from_etp(etp_panel: pd.DataFrame) -> pd.DataFrame:
    """Cumulative ETP price levels (start 100) for 1x / 2x / 3x sleeves."""
    out = pd.DataFrame(index=etp_panel.index)
    for col, name in (("ret_1", "p_1x"), ("ret_2", "p_2x"), ("ret_3", "p_3x")):
        r = etp_panel[col].fillna(0.0).astype(float)
        out[name] = 100.0 * (1.0 + r).cumprod()
    return out


def tier_margins(bench: pd.DataFrame, window: int = SMA_WINDOW) -> pd.DataFrame:
    """Close / SMA20 - 1 for each tier benchmark."""
    margins = pd.DataFrame(index=bench.index)
    for tier, col in ((1, "p_1x"), (2, "p_2x"), (3, "p_3x")):
        px = bench[col].astype(float)
        sma = px.rolling(window, min_periods=window).mean()
        margins[f"m_{tier}x"] = px / sma - 1.0
        margins[f"above_{tier}x"] = px > sma
    return margins


def leverage_stats(lev: pd.Series) -> dict[str, float]:
    return {
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_days_1x": float((lev == 1.0).mean() * 100.0),
        "pct_days_2x": float((lev == 2.0).mean() * 100.0),
        "pct_days_3x": float((lev == 3.0).mean() * 100.0),
    }


def _pick_greedy_tier(
    margins: pd.DataFrame,
    *,
    max_lev: float = 3.0,
    min_margin: float = 0.0,
) -> pd.Series:
    """Highest tier above its own SMA (3 > 2 > 1), else cash."""
    lev = pd.Series(0.0, index=margins.index)
    for dt in margins.index:
        chosen = 0.0
        for tier in (3, 2, 1):
            if tier > max_lev:
                continue
            mcol = f"m_{tier}x"
            if mcol not in margins.columns:
                continue
            m = margins.loc[dt, mcol]
            if pd.notna(m) and float(m) >= min_margin:
                chosen = float(tier)
                break
        lev.loc[dt] = chosen
    return lev


def _pick_best_margin(
    margins: pd.DataFrame,
    *,
    max_lev: float = 3.0,
    min_margin: float = 0.0,
) -> pd.Series:
    """Tier with largest SMA margin; cash if all margins below threshold."""
    lev = pd.Series(0.0, index=margins.index)
    for dt in margins.index:
        best_tier = 0.0
        best_m = min_margin
        for tier in (1, 2, 3):
            if tier > max_lev:
                continue
            m = margins.loc[dt, f"m_{tier}x"]
            if pd.isna(m):
                continue
            m = float(m)
            if m > best_m:
                best_m = m
                best_tier = float(tier)
        lev.loc[dt] = best_tier
    return lev


def _pick_momentum_score(
    bench: pd.DataFrame,
    *,
    lookback: int = 20,
    max_lev: float = 3.0,
) -> pd.Series:
    """Argmax 20d return on each tier benchmark; cash if all negative."""
    lev = pd.Series(0.0, index=bench.index)
    mom = pd.DataFrame(index=bench.index)
    for tier, col in ((1, "p_1x"), (2, "p_2x"), (3, "p_3x")):
        px = bench[col].astype(float)
        mom[f"r_{tier}x"] = px / px.shift(lookback) - 1.0
    for dt in bench.index:
        scores = []
        for tier in (1, 2, 3):
            if tier > max_lev:
                scores.append((tier, -np.inf))
                continue
            r = mom.loc[dt, f"r_{tier}x"]
            scores.append((tier, float(r) if pd.notna(r) else -np.inf))
        best_tier, best_r = max(scores, key=lambda x: x[1])
        lev.loc[dt] = float(best_tier) if best_r > 0 else 0.0
    return lev


def _spx_dd_cap(prices: pd.DataFrame) -> pd.Series:
    """Max allowed leverage from SPX drawdown (Guarded arming, no recovery exit)."""
    close = prices["spx_close"].astype(float)
    dd = close / close.cummax() - 1.0
    cap = pd.Series(1.0, index=prices.index)
    cap.loc[dd <= -TRIGGER_A] = 2.0
    cap.loc[dd <= -TRIGGER_B] = 3.0
    return cap


def _spx_recovery_guard(prices: pd.DataFrame, lead_pct: float = LEAD_PCT) -> pd.Series:
    """SPX close within lead band below SMA20 (site default recovery guard)."""
    close = prices["spx_close"].astype(float)
    sma = close.rolling(SMA_WINDOW, min_periods=SMA_WINDOW).mean()
    return (close >= sma * (1.0 - lead_pct)).fillna(False)


def parallel_tier_leverage(
    prices: pd.DataFrame,
    bench: pd.DataFrame,
    *,
    mode: str,
    use_dd_cap: bool = False,
    use_spx_lead: bool = False,
    min_margin: float = 0.0,
) -> tuple[pd.Series, dict[str, float | int]]:
    margins = tier_margins(bench)
    dd_cap = _spx_dd_cap(prices) if use_dd_cap else pd.Series(3.0, index=prices.index)
    spx_ok = _spx_recovery_guard(prices) if use_spx_lead else pd.Series(True, index=prices.index)

    if mode == "greedy":
        raw = _pick_greedy_tier(margins, min_margin=min_margin)
    elif mode == "best_margin":
        raw = _pick_best_margin(margins, min_margin=min_margin)
    elif mode == "momentum":
        raw = _pick_momentum_score(bench)
    elif mode == "sma_and_momentum":
        sma_pick = _pick_greedy_tier(margins, min_margin=0.0)
        mom_pick = _pick_momentum_score(bench)
        raw = pd.Series(0.0, index=prices.index)
        for dt in prices.index:
            s, m = float(sma_pick.loc[dt]), float(mom_pick.loc[dt])
            if s <= 0 or m <= 0:
                raw.loc[dt] = 0.0
            else:
                raw.loc[dt] = min(s, m)
    else:
        raise ValueError(f"unknown mode: {mode}")

    lev = pd.Series(0.0, index=prices.index)
    capped_days = 0
    lead_blocked = 0
    for dt in prices.index:
        target = float(raw.loc[dt])
        cap = float(dd_cap.loc[dt])
        if not bool(spx_ok.loc[dt]):
            if target > 0:
                lead_blocked += 1
            lev.loc[dt] = 0.0
            continue
        if target > cap:
            capped_days += 1
            target = cap
        lev.loc[dt] = target

    stats = leverage_stats(lev)
    stats["dd_cap_days"] = capped_days
    stats["lead_blocked_days"] = lead_blocked
    return lev, stats


def run_leverage_row(
    prices: pd.DataFrame,
    lev: pd.Series,
    label: str,
    etp_panel: pd.DataFrame,
    extra: dict | None = None,
) -> dict:
    result = make_engine().run(prices, lev, name=label, etp_returns=etp_panel)
    stats = comprehensive_stats(result.equity, result.daily_returns)
    cash = invested_vs_tbills_sessions(result.leverage)
    row = {
        "strategy": label,
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "max_drawdown": stats["max_drawdown"],
        "calmar": stats.get("calmar"),
        "end_$": float(result.equity.iloc[-1]),
        "rebalances": result.rebalance_count,
        "trading_costs_total": result.trading_costs_total,
        "pct_cash": cash["pct_sessions_tbills"],
    }
    if extra:
        row.update(extra)
    return row


def write_strategy_plan(path: Path) -> None:
    path.write_text(
        """# Parallel tier SMA rotation (SPX)

## Motivation

Default **Guarded A5/B25** uses a single SPX SMA20 for the base rule and fixed recovery
exits (+40% from 2x entry, +15% from 3x entry). That forces tier exits on **index**
recovery, not on whether the **leveraged sleeve** (1x / 2x / 3x ETP) still looks attractive.

## Idea

Run three parallel benchmarks — cumulative **1x, 2x, 3x ETP** price paths (XS2D / 3USL
when listed, synthetic daily-reset pre-inception). Apply **SMA20 on each tier's own
benchmark**, then each day pick the most attractive exposure among **cash, 1x, 2x, 3x**.

Entry/exit is therefore **tier-native** (2x decisions use 2x SMA, 3x use 3x SMA), not
only SPX SMA.

## Benchmarks

| Sleeve | ETP (UK) | Signal input |
|--------|----------|--------------|
| 1x | SPY / 1x UCITS | `P_1x` = cumprod(1 + ret_1) |
| 2x | XS2D.L | `P_2x` = cumprod(1 + ret_2) |
| 3x | 3USL.L | `P_3x` = cumprod(1 + ret_3) |

Per tier: `margin_k = P_k / SMA20(P_k) - 1`, `bull_k = margin_k > 0`.

## Selection rules (backtested)

1. **Greedy tier** — highest k ∈ {3,2,1} with `bull_k`; else cash. (Favours leverage when multiple tiers trend.)
2. **Best margin** — argmax_k `margin_k` if max > 0; else cash. (Favours strongest relative trend.)
3. **20d momentum** — argmax_k 20-day return on `P_k` if positive; else cash.
4. **SMA ∧ momentum** — greedy SMA pick AND momentum pick must agree; else cash. (Stricter.)
5. **+ DD cap** — same as (1)/(2) but cap max leverage by SPX drawdown: ≤−5% → up to 2x, ≤−25% → up to 3x (arms tiers, no fixed +X% exit).
6. **+ SPX lead guard** — if SPX fails 0.75% SMA20 lead band, force cash (site recovery guard).

## Baselines

- Guarded A5/B25 SMA20 Lead (default, fixed recovery exits)
- SMA20 1x/cash on SPX only
- Buy & hold 1x / 2x / 3x ETP

## Implementation notes

- P&L uses `SPX_ETP` daily returns (`ret_1` / `ret_2` / `ret_3`) via `PortfolioEngine`.
- $100 start, $10/yr inflow, 1% rebalance cost (same as site).
- This script does **not** modify website assets until reviewed.
""",
        encoding="utf-8",
    )


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_strategy_plan(OUTPUT_DIR / "strategy_plan.md")

    print("Downloading SPX panel...", flush=True)
    prices = download_spx_panel()
    etp_panel = build_etp_return_panel(prices, SPX_ETP)
    bench = benchmark_prices_from_etp(etp_panel)
    cov = etp_coverage_summary(etp_panel)
    print(
        f"Sample: {prices.index[0].date()} -> {prices.index[-1].date()} "
        f"({len(prices)} days) | ETP real 2x/3x: {cov['pct_real_2x']}% / {cov['pct_real_3x']}%",
        flush=True,
    )

    variants: list[tuple[str, str, bool, bool, float]] = [
        ("Parallel greedy tier SMA", "greedy", False, False, 0.0),
        ("Parallel best SMA margin", "best_margin", False, False, 0.0),
        ("Parallel 20d momentum", "momentum", False, False, 0.0),
        ("Parallel SMA and momentum", "sma_and_momentum", False, False, 0.0),
        ("Parallel greedy + DD cap (A5/B25)", "greedy", True, False, 0.0),
        ("Parallel best margin + DD cap", "best_margin", True, False, 0.0),
        ("Parallel greedy + DD cap + SPX lead", "greedy", True, True, 0.0),
        ("Parallel best margin + DD cap + SPX lead", "best_margin", True, True, 0.0),
    ]

    rows: list[dict] = []

    # Baselines
    rows.append(
        run_strategy(prices, DEFAULT_SPEC, etp_returns=etp_panel)
        | {"family": "baseline"}
    )
    lev_sma = sma_cash_leverage(prices, SMA_WINDOW, 1.0)
    rows.append(
        run_leverage_row(
            prices,
            lev_sma,
            "SMA20 1x/cash (SPX)",
            etp_panel,
            {"family": "baseline", **leverage_stats(lev_sma)},
        )
    )
    for tier, label in ((1.0, "Buy & hold 1x ETP"), (2.0, "Buy & hold 2x ETP"), (3.0, "Buy & hold 3x ETP")):
        lev_bh = pd.Series(tier, index=prices.index)
        rows.append(
            run_leverage_row(prices, lev_bh, label, etp_panel, {"family": "baseline", **leverage_stats(lev_bh)})
        )

    for name, mode, dd_cap, spx_lead, min_m in variants:
        lev, counts = parallel_tier_leverage(
            prices,
            bench,
            mode=mode,
            use_dd_cap=dd_cap,
            use_spx_lead=spx_lead,
            min_margin=min_m,
        )
        rows.append(
            run_leverage_row(
                prices,
                lev,
                name,
                etp_panel,
                {"family": "parallel_tier_sma", **counts},
            )
        )

    df = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    df.to_csv(OUTPUT_DIR / "comparison.csv", index=False)

    parallel = df[df["family"] == "parallel_tier_sma"]
    baseline = df[df["family"] == "baseline"]
    best = parallel.iloc[0] if len(parallel) else None
    default = baseline[baseline["strategy"] == DEFAULT_SPEC["strategy"]].iloc[0]

    summary = {
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sample": {
            "start": prices.index[0].date().isoformat(),
            "end": prices.index[-1].date().isoformat(),
            "days": len(prices),
        },
        "etp_coverage": cov,
        "assumptions": {
            "initial_capital": INITIAL_CAPITAL,
            "trading_cost_pct": TRADING_COST_FROM_MID_PCT,
            "sma_window": SMA_WINDOW,
            "trigger_a": TRIGGER_A,
            "trigger_b": TRIGGER_B,
            "lead_pct_below_sma20": LEAD_PCT,
        },
        "default_guarded": default.to_dict(),
        "best_parallel_variant": best.to_dict() if best is not None else None,
        "all_results": rows,
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

    print("\n=== Top parallel tier SMA variants (by Sharpe) ===")
    for _, r in parallel.head(5).iterrows():
        print(
            f"  {r['strategy']:<42} CAGR {r['cagr']*100:6.2f}%  "
            f"Sharpe {r['sharpe']:5.2f}  MaxDD {r['max_drawdown']*100:6.2f}%  "
            f"End ${r['end_$']:,.0f}"
        )

    print("\n=== Default Guarded baseline ===")
    print(
        f"  {default['strategy']:<42} CAGR {default['cagr']*100:6.2f}%  "
        f"Sharpe {default['sharpe']:5.2f}  MaxDD {default['max_drawdown']*100:6.2f}%  "
        f"End ${default['end_$']:,.0f}"
    )

    if best is not None:
        print(
            f"\nBest parallel vs default: "
            f"CAGR {(best['cagr']-default['cagr'])*100:+.2f}pp  "
            f"Sharpe {best['sharpe']-default['sharpe']:+.2f}  "
            f"MaxDD {(best['max_drawdown']-default['max_drawdown'])*100:+.2f}pp"
        )

    print(f"\nWrote {OUTPUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
