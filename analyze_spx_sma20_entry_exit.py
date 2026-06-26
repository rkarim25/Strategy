"""
S&P 500 SMA entry/exit sweep vs default Guarded A5/B25 SMA20 Lead.

Tests price-vs-SMA rules on SPX with ETP P&L (SPX_ETP ret_1/2/3), same engine
assumptions ($100, $10/yr, 1% rebalance cost, ~30y from download_spx_panel).

Families:
  1. Binary SMA leverage — Lx when above SMA, cash when below
  2. Entry/exit buffer (hysteresis) — asymmetric bands around SMA
  3. Confirmation days — N consecutive closes before switching
  4. SMA distance tiers — 1x/2x/3x by margin above SMA

Writes output/spx_sma20_entry_exit/.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from backtest_spx_guarded import DEFAULT_SPEC, download_spx_panel, make_engine, run_strategy
from core.engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT
from core.etp_leverage import SPX_ETP, build_etp_return_panel, etp_coverage_summary
from core.metrics import comprehensive_stats, invested_vs_tbills_sessions
from test_tiered_dd_recovery_guarded import BASE_SMA_WINDOW, sma_cash_leverage

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output" / "spx_sma20_entry_exit"

SMA_WINDOWS = [10, 15, 20, 30, 50, 100, 200]
LEVERAGES = [1.0, 2.0, 3.0]
BUFFERS = [0.0, 0.005, 0.01, 0.02]
CONFIRM_DAYS = [1, 2, 3, 5]
TIER_MARGINS = [(0.03, 0.10), (0.05, 0.15), (0.05, 0.20), (0.10, 0.25)]

LOW_TURNOVER_REBAL_CAP = 200


def leverage_stats(lev: pd.Series) -> dict[str, float]:
    return {
        "pct_days_cash": float((lev <= 0).mean() * 100.0),
        "pct_days_1x": float((lev == 1.0).mean() * 100.0),
        "pct_days_2x": float((lev == 2.0).mean() * 100.0),
        "pct_days_3x": float((lev == 3.0).mean() * 100.0),
    }


def sma_entry_exit_leverage(
    prices: pd.DataFrame,
    *,
    window: int,
    leverage: float = 1.0,
    entry_buffer: float = 0.0,
    exit_buffer: float = 0.0,
    confirm_days: int = 1,
    mode: str = "binary",
    tier_margin_2x: float = 0.05,
    tier_margin_3x: float = 0.15,
) -> pd.Series:
    """Stateful SMA entry/exit with optional buffers, confirmation, and distance tiers."""
    if confirm_days < 1:
        raise ValueError("confirm_days must be >= 1")

    close = prices["spx_close"].astype(float)
    sma = close.rolling(window, min_periods=window).mean()

    lev = pd.Series(0.0, index=prices.index)
    in_position = False
    entry_streak = 0
    exit_streak = 0

    for dt in prices.index:
        px = float(close.loc[dt])
        s = float(sma.loc[dt]) if pd.notna(sma.loc[dt]) else float("nan")

        if not np.isfinite(s) or s <= 0:
            lev.loc[dt] = 0.0
            in_position = False
            entry_streak = 0
            exit_streak = 0
            continue

        entry_thresh = s * (1.0 + entry_buffer)
        exit_thresh = s * (1.0 - exit_buffer)

        if in_position:
            if px < exit_thresh:
                exit_streak += 1
            else:
                exit_streak = 0
            if exit_streak >= confirm_days:
                in_position = False
                entry_streak = 0
                exit_streak = 0
        else:
            if px > entry_thresh:
                entry_streak += 1
            else:
                entry_streak = 0
            if entry_streak >= confirm_days:
                in_position = True
                exit_streak = 0
                entry_streak = 0

        if in_position:
            if mode == "tier":
                margin = px / s - 1.0
                if margin >= tier_margin_3x:
                    lev.loc[dt] = 3.0
                elif margin >= tier_margin_2x:
                    lev.loc[dt] = 2.0
                else:
                    lev.loc[dt] = 1.0
            else:
                lev.loc[dt] = float(leverage)
        else:
            lev.loc[dt] = 0.0

    return lev


def format_buffer(pct: float) -> str:
    if pct == 0.0:
        return "0"
    return f"{pct * 100:.1f}".rstrip("0").rstrip(".")


def strategy_label(
    *,
    family: str,
    window: int,
    leverage: float | None = None,
    entry_buffer: float = 0.0,
    exit_buffer: float = 0.0,
    confirm_days: int = 1,
    tier_margin_2x: float | None = None,
    tier_margin_3x: float | None = None,
) -> str:
    if family == "tier":
        return (
            f"SMA{window} tier 1x/2x@{tier_margin_2x * 100:.0f}%/3x@{tier_margin_3x * 100:.0f}%"
        )
    lev = int(leverage) if leverage is not None and leverage == int(leverage) else leverage
    parts = [f"SMA{window} {lev}x/cash"]
    if entry_buffer > 0 or exit_buffer > 0:
        parts.append(f"in+{format_buffer(entry_buffer)}%/out-{format_buffer(exit_buffer)}%")
    if confirm_days > 1:
        parts.append(f"{confirm_days}d confirm")
    return " ".join(parts)


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
        "rebalances": int(result.rebalance_count),
        "trading_costs_total": result.trading_costs_total,
        "pct_cash": cash["pct_sessions_tbills"],
        **leverage_stats(lev),
    }
    if extra:
        row.update(extra)
    return row


def build_sweep_configs() -> list[dict]:
    configs: list[dict] = []

    for window, leverage, confirm in product(SMA_WINDOWS, LEVERAGES, CONFIRM_DAYS):
        configs.append(
            {
                "family": "binary",
                "sma_window": window,
                "leverage": leverage,
                "entry_buffer": 0.0,
                "exit_buffer": 0.0,
                "confirm_days": confirm,
            }
        )

    for window, leverage, entry_b, exit_b in product(SMA_WINDOWS, LEVERAGES, BUFFERS, BUFFERS):
        if entry_b == 0.0 and exit_b == 0.0:
            continue
        configs.append(
            {
                "family": "buffer",
                "sma_window": window,
                "leverage": leverage,
                "entry_buffer": entry_b,
                "exit_buffer": exit_b,
                "confirm_days": 1,
            }
        )

    for window, (m2, m3) in product(SMA_WINDOWS, TIER_MARGINS):
        configs.append(
            {
                "family": "tier",
                "sma_window": window,
                "leverage": None,
                "entry_buffer": 0.0,
                "exit_buffer": 0.0,
                "confirm_days": 1,
                "tier_margin_2x": m2,
                "tier_margin_3x": m3,
            }
        )

    return configs


def pareto_3d(df: pd.DataFrame) -> pd.DataFrame:
    """Non-dominated on CAGR↑, Sharpe↑, rebalances↓."""
    if df.empty:
        return df.copy()

    cols = ["cagr", "sharpe", "rebalances"]
    work = df.reset_index(drop=True)
    dominated = np.zeros(len(work), dtype=bool)

    cagr = work["cagr"].to_numpy()
    sharpe = work["sharpe"].to_numpy()
    rebals = work["rebalances"].to_numpy()

    for i in range(len(work)):
        if dominated[i]:
            continue
        for j in range(len(work)):
            if i == j or dominated[j]:
                continue
            ge = (
                cagr[j] >= cagr[i]
                and sharpe[j] >= sharpe[i]
                and rebals[j] <= rebals[i]
            )
            gt = (
                cagr[j] > cagr[i]
                or sharpe[j] > sharpe[i]
                or rebals[j] < rebals[i]
            )
            if ge and gt:
                dominated[i] = True
                break

    return work.loc[~dominated, cols + ["strategy", "family"]].sort_values(
        ["sharpe", "cagr"], ascending=[False, False]
    )


def write_strategy_plan(path: Path, *, n_configs: int, default: pd.Series) -> None:
    path.write_text(
        f"""# SPX SMA entry/exit sweep

## Question

Can a **low-turnover** price-vs-SMA rule beat default **Guarded A5/B25 SMA20 Lead**
on Sharpe and/or CAGR with materially fewer rebalances?

## Default baseline

| Metric | Value |
|--------|-------|
| Strategy | {default['strategy']} |
| CAGR | {default['cagr'] * 100:.2f}% |
| Sharpe | {default['sharpe']:.3f} |
| Max DD | {default['max_drawdown'] * 100:.2f}% |
| End $ | ${default['end_$']:,.0f} |
| Rebalances | {int(default['rebalances'])} |

## Families tested ({n_configs} configs)

1. **Binary SMA** — invested at Lx when close > SMA(w), cash when below; sweep confirm days N∈{{1,2,3,5}}.
2. **Buffer hysteresis** — enter above SMA×(1+entry%), exit below SMA×(1−exit%); confirm=1d.
3. **SMA distance tiers** — 1x above SMA, 2x/3x when margin exceeds tier thresholds.

## Parameter grid (focused)

- SMA window: {SMA_WINDOWS}
- Leverage (binary/buffer): {LEVERAGES}
- Entry buffer: {[f'{b*100:g}%' for b in BUFFERS]}
- Exit buffer: {[f'{b*100:g}%' for b in BUFFERS]}
- Confirm days (binary only): {CONFIRM_DAYS}
- Tier margins: {TIER_MARGINS}

## Ranking

- **Low turnover**: Sharpe among configs with rebalances ≤ {LOW_TURNOVER_REBAL_CAP}
- **Pareto**: non-dominated on CAGR ↑, Sharpe ↑, rebalances ↓

## Engine

- SPX_ETP daily returns (`ret_1` / `ret_2` / `ret_3`)
- ${INITIAL_CAPITAL:.0f} start, $10/yr inflow, {TRADING_COST_FROM_MID_PCT * 100:.1f}% rebalance cost
""",
        encoding="utf-8",
    )


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Downloading SPX panel...", flush=True)
    prices = download_spx_panel()
    etp_panel = build_etp_return_panel(prices, SPX_ETP)
    cov = etp_coverage_summary(etp_panel)
    print(
        f"Sample: {prices.index[0].date()} -> {prices.index[-1].date()} "
        f"({len(prices)} days) | ETP real 2x/3x: {cov['pct_real_2x']}% / {cov['pct_real_3x']}%",
        flush=True,
    )

    rows: list[dict] = []

    rows.append(run_strategy(prices, DEFAULT_SPEC, etp_returns=etp_panel) | {"family": "baseline"})
    lev_sma20 = sma_cash_leverage(prices, BASE_SMA_WINDOW, 1.0)
    rows.append(
        run_leverage_row(
            prices,
            lev_sma20,
            "SMA20 1x/cash (SPX)",
            etp_panel,
            {"family": "baseline", "sma_window": BASE_SMA_WINDOW, "leverage": 1.0},
        )
    )
    lev_bh = pd.Series(1.0, index=prices.index)
    rows.append(
        run_leverage_row(
            prices,
            lev_bh,
            "Buy & hold 1x ETP",
            etp_panel,
            {"family": "baseline", "leverage": 1.0},
        )
    )

    configs = build_sweep_configs()
    print(f"Running {len(configs)} SMA entry/exit configs...", flush=True)

    for i, cfg in enumerate(configs, 1):
        kw = {
            "window": cfg["sma_window"],
            "entry_buffer": cfg["entry_buffer"],
            "exit_buffer": cfg["exit_buffer"],
            "confirm_days": cfg["confirm_days"],
        }
        if cfg["family"] == "tier":
            kw["mode"] = "tier"
            kw["tier_margin_2x"] = cfg["tier_margin_2x"]
            kw["tier_margin_3x"] = cfg["tier_margin_3x"]
            label = strategy_label(
                family="tier",
                window=cfg["sma_window"],
                tier_margin_2x=cfg["tier_margin_2x"],
                tier_margin_3x=cfg["tier_margin_3x"],
            )
        else:
            kw["mode"] = "binary"
            kw["leverage"] = cfg["leverage"]
            label = strategy_label(
                family=cfg["family"],
                window=cfg["sma_window"],
                leverage=cfg["leverage"],
                entry_buffer=cfg["entry_buffer"],
                exit_buffer=cfg["exit_buffer"],
                confirm_days=cfg["confirm_days"],
            )

        lev = sma_entry_exit_leverage(prices, **kw)
        rows.append(
            run_leverage_row(
                prices,
                lev,
                label,
                etp_panel,
                extra={**cfg, "family": cfg["family"]},
            )
        )
        if i % 100 == 0:
            print(f"  ... {i}/{len(configs)}", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "comparison.csv", index=False)

    sweep = df[~df["family"].isin(["baseline"])].copy()
    low_turn = sweep[sweep["rebalances"] <= LOW_TURNOVER_REBAL_CAP].sort_values(
        "sharpe", ascending=False
    )
    low_turn.to_csv(OUTPUT_DIR / "ranked_low_turnover.csv", index=False)

    ranked_cagr = sweep.sort_values("cagr", ascending=False)
    ranked_cagr.to_csv(OUTPUT_DIR / "ranked_cagr.csv", index=False)

    pareto = pareto_3d(sweep)
    pareto.to_csv(OUTPUT_DIR / "pareto_frontier.csv", index=False)

    default = df[df["strategy"] == DEFAULT_SPEC["strategy"]].iloc[0]
    write_strategy_plan(OUTPUT_DIR / "strategy_plan.md", n_configs=len(configs), default=default)

    reb_q25 = float(sweep["rebalances"].quantile(0.25))
    low_q = sweep[sweep["rebalances"] <= reb_q25].sort_values("sharpe", ascending=False)

    def beats_default(row: pd.Series) -> dict:
        return {
            "beats_sharpe": bool(row["sharpe"] > default["sharpe"]),
            "beats_cagr": bool(row["cagr"] > default["cagr"]),
            "fewer_rebalances": bool(row["rebalances"] < default["rebalances"]),
            "sharpe_delta": float(row["sharpe"] - default["sharpe"]),
            "cagr_delta_pp": float((row["cagr"] - default["cagr"]) * 100.0),
            "rebalances_delta": int(row["rebalances"] - default["rebalances"]),
        }

    best_low_sharpe = low_turn.iloc[0] if len(low_turn) else None
    best_low_cagr = (
        low_turn.sort_values("cagr", ascending=False).iloc[0] if len(low_turn) else None
    )
    dual_winners = low_turn[
        (low_turn["sharpe"] > default["sharpe"]) | (low_turn["cagr"] > default["cagr"])
    ].sort_values("sharpe", ascending=False)

    summary = {
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sample": {
            "start": prices.index[0].date().isoformat(),
            "end": prices.index[-1].date().isoformat(),
            "days": len(prices),
        },
        "etp_coverage": cov,
        "n_configs": len(configs),
        "default_guarded": default.to_dict(),
        "rebalances_quartile_threshold": reb_q25,
        "best_low_turnover_sharpe": (
            {**best_low_sharpe.to_dict(), **beats_default(best_low_sharpe)}
            if best_low_sharpe is not None
            else None
        ),
        "best_low_turnover_cagr": (
            {**best_low_cagr.to_dict(), **beats_default(best_low_cagr)}
            if best_low_cagr is not None
            else None
        ),
        "low_turnover_beats_default_count": int(len(dual_winners)),
        "top10_low_turnover": low_turn.head(10).to_dict(orient="records"),
        "pareto_frontier_count": len(pareto),
        "verdict": None,
    }

    if best_low_sharpe is not None:
        b = beats_default(best_low_sharpe)
        if b["beats_sharpe"] and b["beats_cagr"] and b["fewer_rebalances"]:
            summary["verdict"] = (
                "YES — at least one low-turnover config beats default on both Sharpe and CAGR "
                f"with fewer rebalances ({int(best_low_sharpe['rebalances'])} vs "
                f"{int(default['rebalances'])})."
            )
        elif b["beats_sharpe"] and b["fewer_rebalances"]:
            summary["verdict"] = (
                "PARTIAL — best low-turnover config beats default Sharpe with fewer rebalances; "
                "CAGR does not beat default."
            )
        elif b["beats_cagr"] and b["fewer_rebalances"]:
            summary["verdict"] = (
                "PARTIAL — best low-turnover config beats default CAGR with fewer rebalances; "
                "Sharpe does not beat default."
            )
        else:
            summary["verdict"] = (
                "NO — no config with rebalances <= "
                f"{LOW_TURNOVER_REBAL_CAP} beats default on Sharpe or CAGR with fewer rebalances."
            )

    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8"
    )

    cols = ["strategy", "cagr", "sharpe", "max_drawdown", "end_$", "rebalances"]
    print("\n=== Default Guarded ===")
    _print_row(default)
    print(f"\n=== Top 10 low-turnover (rebalances <= {LOW_TURNOVER_REBAL_CAP}, by Sharpe) ===")
    for _, r in low_turn.head(10).iterrows():
        _print_row(r)
    print(f"\nBottom-quartile rebalances threshold: {reb_q25:.0f}")
    if len(low_q):
        print("Best Sharpe in bottom quartile rebalances:")
        _print_row(low_q.iloc[0])
    print(f"\n{summary['verdict']}")
    print(f"\nWrote {OUTPUT_DIR}/")
    return 0


def _print_row(r: pd.Series) -> None:
    print(
        f"  {str(r['strategy'])[:48]:<48}  "
        f"CAGR {r['cagr'] * 100:6.2f}%  Sharpe {r['sharpe']:5.2f}  "
        f"MaxDD {r['max_drawdown'] * 100:6.2f}%  "
        f"End ${r['end_$']:,.0f}  Rebals {int(r['rebalances'])}"
    )


if __name__ == "__main__":
    sys.exit(main())
