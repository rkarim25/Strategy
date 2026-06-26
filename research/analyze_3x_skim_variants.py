"""3x-only + profit skim strategy variants for SPX and NDX.

Reuses the existing ETP/VIX-linked return model (``etp_leverage.py``) and the
Guarded A5/B25 arming logic (``test_guarded_balanced_candidate.py``).

Each variant is binary: sleeve is either 3x (3USL/LQQ3-equivalent) or 0x
(T-bills), and a separate "skim" cash bucket compounds at the T-bill rate.
Total wealth = sleeve + cash bucket; HWM and YTD baselines track total wealth.

Outputs written to ``output/guarded_3x_skim_variants/``.
"""

from __future__ import annotations
import sys as _s, pathlib as _p; _s.path.insert(0, str(_p.Path(__file__).resolve().parent.parent))  # repo root importable (moved into research/)

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from backtest_ndx_guarded import download_ndx_panel
from backtest_spx_guarded import download_spx_panel
from core.engine import (
    INITIAL_CAPITAL,
    TRADING_COST_FROM_MID_PCT,
    TRADING_DAYS,
)
from core.etp_leverage import (
    NDX_ETP,
    SPX_ETP,
    build_etp_return_panel,
    etp_coverage_summary,
)
from core.metrics import comprehensive_stats
from test_guarded_balanced_candidate import guarded_strategy_leverage
from test_tiered_dd_recovery_guarded import ANNUAL_INFLOW_USD

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output" / "guarded_3x_skim_variants"

SMA_LONG = 200
SMA_SHORT = 50
VOL_LOOKBACK = 21
# Sleeve trading cost on |delta-leverage| * sleeve (matches engine convention)
SIGNAL_SWITCH_COST_PCT = TRADING_COST_FROM_MID_PCT  # 1% of |delta_lev|*sleeve
# Conservative cost on internal skim/redeploy (spread + commission)
INTERNAL_TRANSFER_COST_PCT = 0.0005  # 5 bps of moved notional

GUARDED_SPEC = dict(
    trigger_a=0.05,
    trigger_b=0.25,
    lead_pct_below_sma20=0.0075,
    x_return=0.40,
    y_return=0.15,
)


# ---------------------------------------------------------------------------
# Signal helpers
# ---------------------------------------------------------------------------


def realized_vol_annualised(returns: pd.Series, window: int) -> pd.Series:
    return returns.rolling(window, min_periods=window).std() * np.sqrt(TRADING_DAYS)


def signal_trend_gated(prices: pd.DataFrame, etp_panel: pd.DataFrame) -> pd.Series:
    """Variant A signal: close > SMA200 AND SMA50 > SMA200."""
    close = prices["spx_close"].astype(float)
    sma200 = close.rolling(SMA_LONG, min_periods=SMA_LONG).mean()
    sma50 = close.rolling(SMA_SHORT, min_periods=SMA_SHORT).mean()
    sig = ((close > sma200) & (sma50 > sma200)).astype(float) * 3.0
    return sig.fillna(0.0)


def signal_vol_gated_hysteresis(
    prices: pd.DataFrame,
    etp_panel: pd.DataFrame,
) -> pd.Series:
    """Variant B signal: vol-gated with hysteresis (18%/22% vol, 20/25 VIX)."""
    close = prices["spx_close"].astype(float)
    ret = close.pct_change()
    vol = realized_vol_annualised(ret, VOL_LOOKBACK)
    vix = etp_panel["vix"].astype(float)

    sig = pd.Series(0.0, index=prices.index)
    state = False
    for dt in prices.index:
        v = float(vol.loc[dt]) if not pd.isna(vol.loc[dt]) else 1e9
        x = float(vix.loc[dt]) if not pd.isna(vix.loc[dt]) else 0.0
        if state:
            if v >= 0.22 or x >= 25.0:
                state = False
        else:
            if v < 0.18 or x < 20.0:
                state = True
        sig.loc[dt] = 3.0 if state else 0.0
    return sig


def signal_recovery_confirmed(
    prices: pd.DataFrame,
    etp_panel: pd.DataFrame,
) -> pd.Series:
    """Variant C signal: Guarded A5/B25 3x arm AND close > SMA50."""
    lev, _ = guarded_strategy_leverage(prices, **GUARDED_SPEC)
    close = prices["spx_close"].astype(float)
    sma50 = close.rolling(SMA_SHORT, min_periods=SMA_SHORT).mean()
    armed = lev >= 2.5
    above_sma50 = close > sma50
    return ((armed & above_sma50).astype(float) * 3.0).fillna(0.0)


def signal_pyramid(prices: pd.DataFrame, etp_panel: pd.DataFrame) -> pd.Series:
    """Variant D signal: composite trend + vol filter."""
    close = prices["spx_close"].astype(float)
    sma200 = close.rolling(SMA_LONG, min_periods=SMA_LONG).mean()
    sma50 = close.rolling(SMA_SHORT, min_periods=SMA_SHORT).mean()
    ret = close.pct_change()
    vol = realized_vol_annualised(ret, VOL_LOOKBACK)
    sig = ((close > sma200) & (sma50 > sma200) & (vol < 0.20)).astype(float) * 3.0
    return sig.fillna(0.0)


def signal_always_3x(prices: pd.DataFrame, etp_panel: pd.DataFrame) -> pd.Series:
    """Sanity check: always 3x."""
    return pd.Series(3.0, index=prices.index)


# ---------------------------------------------------------------------------
# Skim / redeploy callbacks (variant-specific state machines)
# ---------------------------------------------------------------------------


class NoSkim:
    """No skim, no redeploy."""

    def __init__(self) -> None:
        pass

    def __call__(self, st: dict) -> tuple[float, float]:
        return 0.0, 0.0


class HwmSkim:
    """Variant A: skim x% of new HWM gain to cash bucket."""

    def __init__(self, pct: float) -> None:
        self.pct = float(pct)
        self.prev_hwm: float | None = None

    def __call__(self, st: dict) -> tuple[float, float]:
        total = st["total"]
        if self.prev_hwm is None:
            self.prev_hwm = total
            return 0.0, 0.0
        if total > self.prev_hwm:
            gain = total - self.prev_hwm
            skim = self.pct * gain
            skim = min(skim, st["sleeve"])
            self.prev_hwm = total
            return skim, 0.0
        return 0.0, 0.0


class QuarterlySkim:
    """Variant B: skim x% of positive quarterly P&L on sleeve."""

    def __init__(self, pct: float) -> None:
        self.pct = float(pct)
        self.q_start_sleeve: float | None = None
        self.q_key: tuple[int, int] | None = None

    @staticmethod
    def _quarter_key(dt) -> tuple[int, int]:
        return (dt.year, (dt.month - 1) // 3)

    def __call__(self, st: dict) -> tuple[float, float]:
        dt = st["dt"]
        sleeve = st["sleeve"]
        key = self._quarter_key(dt)

        if self.q_start_sleeve is None:
            self.q_start_sleeve = sleeve
            self.q_key = key
            return 0.0, 0.0

        if key != self.q_key:
            pnl = sleeve - self.q_start_sleeve
            skim = max(0.0, self.pct * pnl)
            skim = min(skim, sleeve)
            self.q_start_sleeve = sleeve - skim
            self.q_key = key
            return skim, 0.0
        return 0.0, 0.0


class RecoveryConfirmedSkim:
    """Variant C: skim 30% of YTD return above 20%; redeploy 50% of cash
    at every additional -10% drawdown from HWM."""

    def __init__(self) -> None:
        self.ytd_baseline: float | None = None
        self.ytd_skim_done: float = 0.0
        self.current_year: int | None = None
        self.hwm: float | None = None
        self.dd_redeploy_step: int = 0  # number of -10% thresholds crossed

    def __call__(self, st: dict) -> tuple[float, float]:
        dt = st["dt"]
        total = st["total"]
        sleeve = st["sleeve"]
        cash = st["cash"]

        if self.current_year != dt.year:
            self.ytd_baseline = total
            self.ytd_skim_done = 0.0
            self.current_year = dt.year

        if self.hwm is None or total > self.hwm:
            self.hwm = total
            self.dd_redeploy_step = 0

        skim = 0.0
        threshold = self.ytd_baseline * 1.20
        if total > threshold:
            excess = total - threshold
            target_skim = 0.30 * excess
            extra = target_skim - self.ytd_skim_done
            if extra > 0:
                skim = min(extra, sleeve)
                self.ytd_skim_done += skim

        redeploy = 0.0
        dd = (total - self.hwm) / self.hwm if self.hwm > 0 else 0.0
        needed_step = int(np.floor(-dd / 0.10)) if dd < 0 else 0
        if needed_step > self.dd_redeploy_step and cash > 1e-9:
            redeploy = 0.5 * cash
            self.dd_redeploy_step += 1

        return skim, redeploy


class PyramidSkim:
    """Variant D: skim 50% of gain when total wealth doubles from baseline."""

    def __init__(self) -> None:
        self.baseline: float | None = None

    def __call__(self, st: dict) -> tuple[float, float]:
        total = st["total"]
        sleeve = st["sleeve"]
        if self.baseline is None:
            self.baseline = total
            return 0.0, 0.0
        if total >= 2.0 * self.baseline:
            gain = total - self.baseline
            skim = 0.5 * gain
            skim = min(skim, sleeve)
            self.baseline = total - skim
            return skim, 0.0
        return 0.0, 0.0


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------


def simulate_skim_variant(
    prices: pd.DataFrame,
    etp_panel: pd.DataFrame,
    signal: pd.Series,
    callback_factory: Callable[[], object],
    *,
    initial: float = INITIAL_CAPITAL,
    inflow: float = ANNUAL_INFLOW_USD,
    name: str = "variant",
) -> dict:
    index = prices.index
    ret_0 = etp_panel["ret_0"]
    ret_3 = etp_panel["ret_3"]

    callback = callback_factory()

    sleeve = initial
    cash = 0.0
    prev_lev = 0.0  # start in cash; first signal will switch in

    equity = pd.Series(index=index, dtype=float)
    sleeve_s = pd.Series(index=index, dtype=float)
    cash_s = pd.Series(index=index, dtype=float)
    lev_s = pd.Series(index=index, dtype=float)
    daily_ret_s = pd.Series(0.0, index=index)

    prev_year: int | None = None
    n_switches = 0
    n_skim = 0
    n_redeploy = 0
    total_skim_amount = 0.0
    total_redeploy_amount = 0.0
    sleeve_trading_costs = 0.0
    days_3x = 0

    sig = signal.reindex(index).fillna(0.0)

    for i, dt in enumerate(index):
        prev_total = sleeve + cash if i > 0 else initial

        if prev_year is not None and dt.year != prev_year:
            sleeve += inflow
        prev_year = dt.year

        target_lev = float(sig.iloc[i])

        if abs(target_lev - prev_lev) > 1e-9:
            traded = abs(target_lev - prev_lev) * sleeve
            cost = traded * SIGNAL_SWITCH_COST_PCT
            sleeve -= cost
            sleeve_trading_costs += cost
            n_switches += 1
            prev_lev = target_lev

        if i > 0:
            r_cash = float(ret_0.iloc[i]) if not pd.isna(ret_0.iloc[i]) else 0.0
            cash *= 1.0 + r_cash
            if target_lev >= 2.5:
                r_sleeve = float(ret_3.iloc[i]) if not pd.isna(ret_3.iloc[i]) else 0.0
            else:
                r_sleeve = r_cash
            sleeve *= 1.0 + r_sleeve

        total = sleeve + cash

        state = {
            "dt": dt,
            "sleeve": sleeve,
            "cash": cash,
            "total": total,
            "prev_lev": prev_lev,
        }
        skim, redeploy = callback(state)

        if skim > 0:
            skim = min(skim, sleeve)
            cost = skim * INTERNAL_TRANSFER_COST_PCT
            sleeve -= skim
            sleeve_trading_costs += cost
            cash += skim - cost
            n_skim += 1
            total_skim_amount += skim

        if redeploy > 0:
            redeploy = min(redeploy, cash)
            cost = redeploy * INTERNAL_TRANSFER_COST_PCT
            cash -= redeploy
            sleeve_trading_costs += cost
            sleeve += redeploy - cost
            n_redeploy += 1
            total_redeploy_amount += redeploy

        new_total = sleeve + cash
        if i > 0 and prev_total > 0:
            daily_ret_s.iloc[i] = new_total / prev_total - 1.0

        equity.iloc[i] = new_total
        sleeve_s.iloc[i] = sleeve
        cash_s.iloc[i] = cash
        lev_s.iloc[i] = target_lev
        if target_lev >= 2.5:
            days_3x += 1

    equity.name = name
    stats = comprehensive_stats(equity, daily_ret_s)
    n = len(index)
    return {
        "name": name,
        "equity": equity,
        "sleeve": sleeve_s,
        "cash": cash_s,
        "leverage": lev_s,
        "daily_returns": daily_ret_s,
        "stats": stats,
        "n_switches": n_switches,
        "n_skim": n_skim,
        "n_redeploy": n_redeploy,
        "total_skim_amount": total_skim_amount,
        "total_redeploy_amount": total_redeploy_amount,
        "sleeve_trading_costs": sleeve_trading_costs,
        "pct_time_3x": 100.0 * days_3x / n,
        "end_sleeve": float(sleeve_s.iloc[-1]),
        "end_cash": float(cash_s.iloc[-1]),
        "end_total": float(equity.iloc[-1]),
        "cash_bucket_final_pct": (
            100.0 * float(cash_s.iloc[-1]) / float(equity.iloc[-1])
            if float(equity.iloc[-1]) > 0
            else 0.0
        ),
        "start_date": index[0].date().isoformat(),
        "end_date": index[-1].date().isoformat(),
        "years": (index[-1] - index[0]).days / 365.25,
    }


# ---------------------------------------------------------------------------
# Variant catalogue
# ---------------------------------------------------------------------------


def variant_catalogue() -> list[dict]:
    """Returns list of variant dicts: name, params, signal_fn, callback_factory."""
    out: list[dict] = []

    for pct in (0.10, 0.20, 0.30, 0.40):
        out.append(
            {
                "variant": "A_trend_hwm_skim",
                "params": f"skim={int(pct*100)}%",
                "signal_fn": signal_trend_gated,
                "callback_factory": (lambda p=pct: HwmSkim(p)),
            }
        )

    for pct in (0.20, 0.30):
        out.append(
            {
                "variant": "B_vol_quarterly_skim",
                "params": f"skim={int(pct*100)}%",
                "signal_fn": signal_vol_gated_hysteresis,
                "callback_factory": (lambda p=pct: QuarterlySkim(p)),
            }
        )

    out.append(
        {
            "variant": "C_guarded_recovery",
            "params": "skim=30%_above_YTD20%; redeploy=50%/10%dd",
            "signal_fn": signal_recovery_confirmed,
            "callback_factory": lambda: RecoveryConfirmedSkim(),
        }
    )

    out.append(
        {
            "variant": "D_pyramid_skim",
            "params": "skim=50%_on_double",
            "signal_fn": signal_pyramid,
            "callback_factory": lambda: PyramidSkim(),
        }
    )

    return out


# ---------------------------------------------------------------------------
# Reference benchmark loaders
# ---------------------------------------------------------------------------


def _row_to_bench(row: dict, asset: str, name: str) -> dict:
    return {
        "asset": asset,
        "variant": name,
        "params": "",
        "start_date": "",
        "end_date": "",
        "years": None,
        "cagr": float(row["cagr"]),
        "max_dd": float(row["max_drawdown"]),
        "end_value": float(row["end_$"]),
        "sharpe": float(row["sharpe"]),
        "pct_time_3x": (
            100.0 - float(row.get("pct_days_cash") or 0.0)
            if "pct_days_cash" in row
            else None
        ),
        "num_switches": int(row.get("rebalances") or 0),
        "cash_bucket_final_pct": None,
        "benchmark": True,
    }


def load_benchmarks() -> list[dict]:
    rows: list[dict] = []
    for asset, csv_path, key_names in (
        (
            "SPX",
            ROOT / "output" / "spx_guarded" / "spx_guarded_comparison.csv",
            ["Buy & hold 1x", "Buy & hold 3x", "Guarded A5/B25 SMA20 Lead"],
        ),
        (
            "NDX",
            ROOT / "output" / "ndx_guarded" / "ndx_guarded_comparison.csv",
            ["Buy & hold 1x", "Buy & hold 3x", "Guarded A5/B25 SMA20 Lead"],
        ),
    ):
        if not csv_path.exists():
            print(f"WARN: missing benchmark csv {csv_path}")
            continue
        df = pd.read_csv(csv_path)
        for key in key_names:
            match = df[df["strategy"] == key]
            if match.empty:
                continue
            row = match.iloc[0].to_dict()
            label = {
                "Buy & hold 1x": "Buy-hold 1x (benchmark)",
                "Buy & hold 3x": "Buy-hold 3x (benchmark)",
                "Guarded A5/B25 SMA20 Lead": "Guarded A5/B25 ETP+VIX (benchmark)",
            }[key]
            rows.append(_row_to_bench(row, asset, label))
    return rows


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def pct_str(x: float | None, digits: int = 2) -> str:
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "n/a"
    return f"{100.0 * float(x):.{digits}f}%"


def money_str(x: float | None) -> str:
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "n/a"
    v = float(x)
    if abs(v) >= 1e9:
        return f"${v / 1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"${v / 1e6:.2f}M"
    if abs(v) >= 1e3:
        return f"${v / 1e3:.1f}K"
    return f"${v:,.0f}"


def build_markdown_table(rows: list[dict]) -> str:
    headers = [
        "Asset",
        "Strategy",
        "CAGR",
        "Max DD",
        "End Value",
        "Sharpe",
        "Time in 3x",
        "Cash Bucket Final",
    ]
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for r in rows:
        label = r["variant"] + (f" ({r['params']})" if r.get("params") else "")
        lines.append(
            "| "
            + " | ".join(
                [
                    r["asset"],
                    label,
                    pct_str(r.get("cagr"), 2),
                    pct_str(r.get("max_dd"), 1),
                    money_str(r.get("end_value")),
                    f"{r.get('sharpe'):.2f}" if r.get("sharpe") is not None and not np.isnan(r.get("sharpe")) else "n/a",
                    (
                        f"{r.get('pct_time_3x'):.1f}%"
                        if r.get("pct_time_3x") is not None
                        else "n/a"
                    ),
                    (
                        f"{r.get('cash_bucket_final_pct'):.1f}%"
                        if r.get("cash_bucket_final_pct") is not None
                        else "n/a"
                    ),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_asset(
    asset_label: str,
    prices: pd.DataFrame,
    etp_panel: pd.DataFrame,
) -> tuple[list[dict], dict[str, dict]]:
    rows: list[dict] = []
    runs: dict[str, dict] = {}

    sanity = simulate_skim_variant(
        prices,
        etp_panel,
        signal_always_3x(prices, etp_panel),
        lambda: NoSkim(),
        name=f"{asset_label}_always_3x_baseline",
    )
    rows.append(
        {
            "asset": asset_label,
            "variant": "_sanity_always_3x",
            "params": "always_on_no_skim",
            "start_date": sanity["start_date"],
            "end_date": sanity["end_date"],
            "years": sanity["years"],
            "cagr": sanity["stats"]["cagr"],
            "max_dd": sanity["stats"]["max_drawdown"],
            "end_value": sanity["end_total"],
            "sharpe": sanity["stats"]["sharpe"],
            "pct_time_3x": sanity["pct_time_3x"],
            "num_switches": sanity["n_switches"],
            "cash_bucket_final_pct": sanity["cash_bucket_final_pct"],
            "n_skim": 0,
            "n_redeploy": 0,
            "sleeve_trading_costs": sanity["sleeve_trading_costs"],
            "benchmark": False,
        }
    )
    runs["_sanity_always_3x"] = sanity

    for spec in variant_catalogue():
        sig = spec["signal_fn"](prices, etp_panel)
        run = simulate_skim_variant(
            prices,
            etp_panel,
            sig,
            spec["callback_factory"],
            name=f"{asset_label}_{spec['variant']}_{spec['params']}",
        )
        key = f"{spec['variant']}|{spec['params']}"
        runs[key] = run
        rows.append(
            {
                "asset": asset_label,
                "variant": spec["variant"],
                "params": spec["params"],
                "start_date": run["start_date"],
                "end_date": run["end_date"],
                "years": run["years"],
                "cagr": run["stats"]["cagr"],
                "max_dd": run["stats"]["max_drawdown"],
                "end_value": run["end_total"],
                "sharpe": run["stats"]["sharpe"],
                "pct_time_3x": run["pct_time_3x"],
                "num_switches": run["n_switches"],
                "cash_bucket_final_pct": run["cash_bucket_final_pct"],
                "n_skim": run["n_skim"],
                "n_redeploy": run["n_redeploy"],
                "sleeve_trading_costs": run["sleeve_trading_costs"],
                "benchmark": False,
            }
        )
    return rows, runs


def write_equity_curves(asset_label: str, runs: dict[str, dict]) -> None:
    for key, run in runs.items():
        slug = (
            key.replace("|", "_")
            .replace("=", "")
            .replace("%", "pct")
            .replace(" ", "")
            .replace(";", "_")
            .replace("/", "p")
        )
        path = OUTPUT_DIR / f"equity_{asset_label}_{slug}.csv"
        df = pd.DataFrame(
            {
                "sleeve_value": run["sleeve"],
                "cash_bucket": run["cash"],
                "total_equity": run["equity"],
                "leverage_state": run["leverage"],
            }
        )
        df.index.name = "date"
        df.to_csv(path)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Downloading SPX panel...", flush=True)
    spx_prices = download_spx_panel()
    print(
        f"  SPX: {len(spx_prices)} sessions "
        f"{spx_prices.index[0].date()} -> {spx_prices.index[-1].date()}",
        flush=True,
    )

    print("Downloading NDX panel...", flush=True)
    ndx_prices = download_ndx_panel()
    print(
        f"  NDX: {len(ndx_prices)} sessions "
        f"{ndx_prices.index[0].date()} -> {ndx_prices.index[-1].date()}",
        flush=True,
    )

    print("Building ETP return panels...", flush=True)
    spx_etp = build_etp_return_panel(spx_prices, SPX_ETP)
    ndx_etp = build_etp_return_panel(ndx_prices, NDX_ETP)
    print(f"  SPX ETP coverage: {etp_coverage_summary(spx_etp)}")
    print(f"  NDX ETP coverage: {etp_coverage_summary(ndx_etp)}")

    print("Running SPX variants...", flush=True)
    spx_rows, spx_runs = run_asset("SPX", spx_prices, spx_etp)
    print("Running NDX variants...", flush=True)
    ndx_rows, ndx_runs = run_asset("NDX", ndx_prices, ndx_etp)

    all_rows = spx_rows + ndx_rows
    results_df = pd.DataFrame(all_rows)
    results_csv = OUTPUT_DIR / "results.csv"
    results_df.to_csv(results_csv, index=False)
    print(f"\nWrote {results_csv}")

    bench_rows = load_benchmarks()

    summary_rows: list[dict] = []
    for asset in ("SPX", "NDX"):
        asset_rows = [r for r in all_rows if r["asset"] == asset and r["variant"] != "_sanity_always_3x"]
        asset_rows = sorted(asset_rows, key=lambda r: r["cagr"], reverse=True)
        summary_rows.extend(asset_rows)
    summary_df = pd.DataFrame(summary_rows)
    summary_csv = OUTPUT_DIR / "summary.csv"
    summary_df.to_csv(summary_csv, index=False)
    print(f"Wrote {summary_csv}")

    write_equity_curves("SPX", spx_runs)
    write_equity_curves("NDX", ndx_runs)
    print(f"Wrote per-variant equity curves to {OUTPUT_DIR}")

    site_payload = {
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "model": {
            "initial_capital": INITIAL_CAPITAL,
            "annual_inflow_usd": ANNUAL_INFLOW_USD,
            "signal_switch_cost_pct": SIGNAL_SWITCH_COST_PCT,
            "internal_transfer_cost_pct": INTERNAL_TRANSFER_COST_PCT,
            "sleeve_pnl_model": (
                "Listed 2x/3x ETP daily returns (XS2D/3USL / LQQ/LQQ3); "
                "VIX-linked synthetic daily-reset before ETP inception. "
                "Cash bucket compounds at 13-week T-bill rate."
            ),
        },
        "assets": {
            "SPX": {
                "sample": {
                    "start_date": spx_prices.index[0].date().isoformat(),
                    "end_date": spx_prices.index[-1].date().isoformat(),
                    "trading_days": len(spx_prices),
                },
                "etp_coverage": etp_coverage_summary(spx_etp),
            },
            "NDX": {
                "sample": {
                    "start_date": ndx_prices.index[0].date().isoformat(),
                    "end_date": ndx_prices.index[-1].date().isoformat(),
                    "trading_days": len(ndx_prices),
                },
                "etp_coverage": etp_coverage_summary(ndx_etp),
            },
        },
        "variants": [
            {
                "asset": r["asset"],
                "variant": r["variant"],
                "params": r["params"],
                "cagr": r["cagr"],
                "cagr_pct": pct_str(r["cagr"]),
                "max_drawdown": r["max_dd"],
                "max_drawdown_pct": pct_str(r["max_dd"], 1),
                "end_value": r["end_value"],
                "end_value_fmt": money_str(r["end_value"]),
                "sharpe": r["sharpe"],
                "pct_time_3x": r["pct_time_3x"],
                "cash_bucket_final_pct": r["cash_bucket_final_pct"],
                "num_switches": r["num_switches"],
                "n_skim_events": r["n_skim"],
                "n_redeploy_events": r["n_redeploy"],
            }
            for r in all_rows
        ],
        "benchmarks": [
            {
                "asset": r["asset"],
                "name": r["variant"],
                "cagr": r["cagr"],
                "cagr_pct": pct_str(r["cagr"]),
                "max_drawdown": r["max_dd"],
                "max_drawdown_pct": pct_str(r["max_dd"], 1),
                "end_value": r["end_value"],
                "end_value_fmt": money_str(r["end_value"]),
                "sharpe": r["sharpe"],
            }
            for r in bench_rows
        ],
    }
    site_json = OUTPUT_DIR / "site_data.json"
    site_json.write_text(json.dumps(site_payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {site_json}")

    # ---------------- Markdown comparison table ----------------
    md_rows: list[dict] = []
    for asset in ("SPX", "NDX"):
        for b in bench_rows:
            if b["asset"] == asset:
                md_rows.append(b)
        sanity_row = next(
            r
            for r in all_rows
            if r["asset"] == asset and r["variant"] == "_sanity_always_3x"
        )
        md_rows.append(
            {
                "asset": asset,
                "variant": "Always-3x sanity (no skim)",
                "params": "",
                "cagr": sanity_row["cagr"],
                "max_dd": sanity_row["max_dd"],
                "end_value": sanity_row["end_value"],
                "sharpe": sanity_row["sharpe"],
                "pct_time_3x": sanity_row["pct_time_3x"],
                "cash_bucket_final_pct": sanity_row["cash_bucket_final_pct"],
            }
        )
        variant_rows = [
            r
            for r in all_rows
            if r["asset"] == asset and r["variant"] != "_sanity_always_3x"
        ]
        for r in variant_rows:
            md_rows.append(r)

    table = build_markdown_table(md_rows)
    md_path = OUTPUT_DIR / "comparison_table.md"
    md_path.write_text(table + "\n", encoding="utf-8")
    print(f"\nWrote {md_path}")

    print("\n=== 3x + Skim Variants vs Guarded benchmarks ===\n")
    print(table)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
