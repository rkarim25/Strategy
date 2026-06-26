"""Verify end-$ calculations for NDX 3x vs synthetic 3QQQ Guarded comparison."""

from __future__ import annotations
import sys as _s, pathlib as _p; _s.path.insert(0, str(_p.Path(__file__).resolve().parent.parent))  # repo root importable (moved into research/)

import pandas as pd

from analyze_cross_asset_guarded_1x import guarded_lead_leverage
from backtest_lqq3_synthetic_guarded import build_synthetic_lqq3_close, download_ndx_vix_tbill, panel_from_close
from backtest_ndx_guarded import DEFAULT_SPEC, make_engine
from core.engine import TRADING_COST_FROM_MID_PCT
from core.etp_leverage import NDX_ETP, build_etp_return_panel, daily_return_for_leverage
from core.metrics import comprehensive_stats
from test_guarded_balanced_candidate import guarded_strategy_leverage
from test_tiered_dd_recovery_guarded import BASE_SMA_WINDOW, sma_cash_leverage


def manual_sim(
    panel: pd.DataFrame,
    lev: pd.Series,
    *,
    etp: pd.DataFrame | None = None,
) -> tuple[float, float]:
    ret = panel["spx_close"].pct_change().fillna(0)
    tb = panel["tbill_rate"]
    aum = 100.0
    prev = 1.0  # engine default prev_lev before first bar
    prev_year = None
    tc = 0.0
    for i, dt in enumerate(panel.index):
        if prev_year is not None and dt.year != prev_year:
            aum += 10.0
        target = float(lev.iloc[i])
        if abs(target - prev) > 1e-9:
            cost = abs(target - prev) * aum * TRADING_COST_FROM_MID_PCT
            aum -= cost
            tc += cost
            prev = target
        if i > 0:
            tb_val = float(tb.iloc[i]) if not pd.isna(tb.iloc[i]) else 0.0
            idx_r = float(ret.iloc[i])
            if etp is not None:
                r = daily_return_for_leverage(target, idx_r, tb_val, etp.iloc[i])
            elif target <= 0:
                r = tb_val / 252
            else:
                r = idx_r
            aum *= 1.0 + r
        prev_year = dt.year
    return aum, tc


def main() -> int:
    ndx_vix = download_ndx_vix_tbill("1996-01-01")
    synth_close = build_synthetic_lqq3_close(ndx_vix)
    synth_panel = panel_from_close(synth_close, ndx_vix["tbill_rate"])
    ndx_panel = pd.DataFrame({"spx_close": ndx_vix["spx_close"], "tbill_rate": ndx_vix["tbill_rate"]})
    idx = synth_panel.index.intersection(ndx_panel.index)[BASE_SMA_WINDOW + 5 :]
    synth_panel = synth_panel.loc[idx]
    ndx_panel = ndx_panel.loc[idx]
    etp = build_etp_return_panel(ndx_panel, NDX_ETP)
    eng = make_engine()

    lev_def, _ = guarded_strategy_leverage(
        ndx_panel,
        trigger_a=DEFAULT_SPEC["trigger_a"],
        trigger_b=DEFAULT_SPEC["trigger_b"],
        lead_pct_below_sma20=DEFAULT_SPEC["lead_pct_below_sma20"],
        x_return=DEFAULT_SPEC["x_return"],
        y_return=DEFAULT_SPEC["y_return"],
    )
    lev_3x = lev_def.map(lambda x: 3.0 if float(x) > 0 else 0.0)
    lev_synth, _ = guarded_lead_leverage(synth_panel, max_leverage=1.0)

    configs = [
        ("NDX Guarded tiered (site default)", ndx_panel, lev_def, etp),
        ("NDX Guarded binary 3x/cash", ndx_panel, lev_3x, etp),
        ("NDX buy & hold 3x ETP", ndx_panel, pd.Series(3.0, index=ndx_panel.index), etp),
        ("Synthetic Guarded max 1x", synth_panel, lev_synth, None),
        ("Synthetic buy & hold", synth_panel, pd.Series(1.0, index=synth_panel.index), None),
        ("NDX SMA20 1x/cash", ndx_panel, sma_cash_leverage(ndx_panel, 20, 1.0), None),
    ]

    years = (idx[-1] - idx[0]).days / 365.25
    inflows = 10 * (idx[-1].year - idx[0].year)

    print(f"Window: {idx[0].date()} -> {idx[-1].date()} ({len(idx)} days, ~{years:.1f}y, ~${inflows} inflows)\n")
    print(f"{'Strategy':34} {'Engine end$':>16} {'Manual end$':>16} {'Match':>6} {'CAGR%':>8} {'MaxDD%':>8} {'%Inv':>6}")
    print("-" * 100)

    for name, panel, lev, etp_panel in configs:
        kw = {"etp_returns": etp_panel} if etp_panel is not None else {}
        res = eng.run(panel, lev, **kw)
        manual, _ = manual_sim(panel, lev, etp=etp_panel)
        stats = comprehensive_stats(res.equity, res.daily_returns)
        match = abs(res.equity.iloc[-1] - manual) / max(manual, 1) < 0.02
        pct_inv = float((lev > 0).mean() * 100)
        print(
            f"{name:34} {res.equity.iloc[-1]:16,.0f} {manual:16,.0f} "
            f"{'OK' if match else 'DIFF':>6} {stats['cagr']*100:8.2f} {stats['max_drawdown']*100:8.2f} {pct_inv:6.1f}"
        )

    print("\nSynthetic price: {:.2f} -> {:.2f} ({:.1f}x)".format(
        synth_panel["spx_close"].iloc[0],
        synth_panel["spx_close"].iloc[-1],
        synth_panel["spx_close"].iloc[-1] / synth_panel["spx_close"].iloc[0],
    ))
    print("NDX index: {:.0f} -> {:.0f} ({:.1f}x)".format(
        ndx_panel["spx_close"].iloc[0],
        ndx_panel["spx_close"].iloc[-1],
        ndx_panel["spx_close"].iloc[-1] / ndx_panel["spx_close"].iloc[0],
    ))

    ret_s = synth_panel["spx_close"].pct_change().fillna(0)
    invested_mult = float((1 + ret_s[lev_synth > 0]).prod())
    print(f"\nProduct of (1+r) on synthetic Guarded invested days only: {invested_mult:.3e}")
    print(f"Implied multiplier from $100 ignoring inflows/costs: {100 * invested_mult:.3e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
