"""Charts and institutional reporting tables."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

from core.engine import (
    DEFAULT_MAX_DRAWDOWN,
    TRADING_COST_FROM_MID_PCT,
    BacktestResult,
    passes_drawdown_limit,
)
from core.metrics import comprehensive_stats
from core.strategies import BENCHMARK_RULES

BENCHMARK_LABEL = "Buy & Hold 1x SPX"


def _currency_k_m(x: float, _pos: int) -> str:
    if abs(x) >= 1_000_000:
        return f"${x / 1_000_000:.1f}M"
    if abs(x) >= 1_000:
        return f"${x / 1_000:.1f}K"
    return f"${x:.0f}"


def apply_chart_style(ax: plt.Axes) -> None:
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_currency_k_m))
    ax.grid(True, which="both", linestyle="--", alpha=0.35)


def build_stats_row(
    name: str,
    result: BacktestResult,
    benchmark_equity: pd.Series | None,
    max_dd_limit: float,
) -> dict:
    stats = comprehensive_stats(
        result.equity,
        result.daily_returns,
        benchmark_equity=benchmark_equity,
        trading_costs_total=result.trading_costs_total,
        turnover_notional=result.turnover_notional,
    )
    pct_levered = (result.leverage > 1.0).mean() * 100 if len(result.leverage) else 0.0
    pct_cash = (result.leverage <= 0.0).mean() * 100 if len(result.leverage) else 0.0
    within = passes_drawdown_limit(result.equity, max_dd_limit)
    return {
        "Strategy": name,
        **stats,
        "pct_days_levered": pct_levered,
        "pct_days_cash": pct_cash,
        "risk_off_days": result.risk_off_days,
        "rebalance_count": result.rebalance_count,
        "within_dd_limit": within,
    }


def build_stats_dataframe(
    results: dict[str, BacktestResult],
    max_dd_limit: float = DEFAULT_MAX_DRAWDOWN,
) -> pd.DataFrame:
    bench = results.get(BENCHMARK_LABEL)
    bench_eq = bench.equity if bench else None
    rows = []
    for name, result in results.items():
        rows.append(
            build_stats_row(
                name,
                result,
                bench_eq if name != BENCHMARK_LABEL else None,
                max_dd_limit,
            )
        )
    return pd.DataFrame(rows).set_index("Strategy")


def split_included_excluded(
    stats_df: pd.DataFrame,
    max_dd_limit: float = DEFAULT_MAX_DRAWDOWN,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Systematic strategies only; benchmark always in included for reference."""
    systematic = stats_df.drop(BENCHMARK_LABEL, errors="ignore")
    excluded = systematic[~systematic["within_dd_limit"]].copy()
    included_systematic = systematic[systematic["within_dd_limit"]].copy()
    if BENCHMARK_LABEL in stats_df.index:
        included = pd.concat([stats_df.loc[[BENCHMARK_LABEL]], included_systematic])
    else:
        included = included_systematic
    excluded["exclusion_reason"] = excluded.apply(
        lambda r: (
            f"Max drawdown {r['max_drawdown'] * 100:.2f}% exceeds "
            f"{max_dd_limit * 100:.0f}% portfolio limit"
        ),
        axis=1,
    )
    return included, excluded


def build_strategy_details_csv(
    strategies: list,
    max_dd_limit: float,
) -> pd.DataFrame:
    rows = []
    for s in strategies:
        row = s.rule_summary()
        row["max_portfolio_drawdown_limit"] = f"{max_dd_limit * 100:.0f}%"
        row["risk_overlay"] = (
            f"Hard floor at -{max_dd_limit * 100:.0f}% from peak; "
            "cash (T-Bill) when breached; early trigger at 85% of limit"
        )
        row["trading_cost"] = (
            f"{TRADING_COST_FROM_MID_PCT * 100:.1f}% of traded notional from mid "
            "on each leverage change"
        )
        row["annual_cash_inflow"] = "10% of AUM on first trading day each calendar year"
        row["starting_capital"] = "$100"
        rows.append(row)
    bench = BENCHMARK_RULES.copy()
    bench["max_portfolio_drawdown_limit"] = "None (unconstrained benchmark)"
    bench["risk_overlay"] = "None"
    bench["trading_cost"] = "None (buy-and-hold, no rebalances)"
    bench["annual_cash_inflow"] = "10% of AUM on first trading day each calendar year"
    bench["starting_capital"] = "$100"
    rows.insert(0, bench)
    return pd.DataFrame(rows)


def format_stats_for_display(df: pd.DataFrame) -> pd.DataFrame:
    pct_cols = [
        "cagr", "total_return", "max_drawdown", "avg_drawdown",
        "volatility", "downside_volatility", "win_rate",
        "best_day", "worst_day", "best_month", "worst_month",
        "pct_days_levered", "pct_days_cash", "cost_drag_pct",
    ]
    out = df.copy()
    for col in pct_cols:
        if col in out.columns:
            out[col] = out[col].map(lambda x: f"{x * 100:.2f}%" if pd.notna(x) else "n/a")
    for col in ("sharpe", "sortino", "calmar", "profit_factor", "beta", "alpha", "information_ratio"):
        if col in out.columns:
            out[col] = out[col].map(lambda x: f"{x:.2f}" if pd.notna(x) else "n/a")
    if "final_value" in out.columns:
        out["final_value"] = out["final_value"].map(lambda x: f"${x:,.2f}")
    if "within_dd_limit" in out.columns:
        out["within_dd_limit"] = out["within_dd_limit"].map(lambda x: "Yes" if x else "No")
    return out


def print_stats_table(df: pd.DataFrame, title: str = "PORTFOLIO CHARACTERISTICS") -> None:
    key_cols = [
        "cagr", "max_drawdown", "sharpe", "sortino", "calmar",
        "volatility", "max_dd_duration_days", "ulcer_index",
        "profit_factor", "win_rate", "beta", "alpha",
        "final_value", "total_trading_costs", "within_dd_limit",
    ]
    display_cols = [c for c in key_cols if c in df.columns]
    display = format_stats_for_display(df[display_cols])
    print("\n" + "=" * 110)
    print(title)
    print("=" * 110)
    print(display.to_string())
    print("=" * 110 + "\n")


def plot_all_strategies(
    equities: dict[str, pd.Series],
    output_path: str | Path,
    title: str | None = None,
) -> None:
    fig, ax = plt.subplots(figsize=(14, 8))
    bench = equities.get(BENCHMARK_LABEL)

    for name, equity in equities.items():
        if name == BENCHMARK_LABEL:
            continue
        ax.plot(equity.index, equity.values, label=name, linewidth=0.9, alpha=0.8)

    if bench is not None:
        ax.plot(
            bench.index, bench.values,
            label=BENCHMARK_LABEL, linewidth=2.5, color="black", linestyle="--",
        )

    ax.set_yscale("log")
    apply_chart_style(ax)
    ax.set_title(title or "Approved Strategies vs Buy & Hold (Log Scale)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Portfolio Value")
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(output_path, format="pdf")
    plt.close(fig)


def plot_strategy_vs_benchmark(
    strategy_equity: pd.Series,
    benchmark_equity: pd.Series,
    strategy_name: str,
    output_path: str | Path,
) -> None:
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(strategy_equity.index, strategy_equity.values, label=strategy_name, linewidth=1.5)
    ax.plot(
        benchmark_equity.index, benchmark_equity.values,
        label=BENCHMARK_LABEL, linewidth=1.5, linestyle="--", color="black",
    )
    ax.set_yscale("log")
    apply_chart_style(ax)
    ax.set_title(f"{strategy_name} vs {BENCHMARK_LABEL}")
    ax.set_xlabel("Date")
    ax.set_ylabel("Portfolio Value")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(output_path, format="pdf")
    plt.close(fig)
