# S&P 500 SMA-band variant sweep (Variants A / B / C)

Hunt for SMA-band strategies that beat the incumbent S&P **Water** (SMA200 ±3% 1x/cash)
and **Octane** (SMA200 ±3% + RSI>20 exit 2x). Added 2026-06-29.

## What it tests
~4,788 strategies over full S&P history (1950→2026), each through a numpy replica of
`core.engine` that is **validated to reproduce `backtest_spx_distance_scale.run_strategy`
to the penny** (`fast_engine.py`), then winners re-confirmed through the real
`PortfolioEngine` (`confirm.py`).

- **Variant A** — band entry & exit + fixed stop-loss. Two band directions: `conv`
  (enter above +upper, exit below −lower = incumbent) and `early` (enter rising through
  −lower, exit falling through +upper = the "early-in/early-out" rule). **A′** uses a
  trailing stop instead.
- **Variant B** — band entry, momentum exit. `decay` (premium falls ≥d from its trailing
  N-day max) and `accel` (no new band-high ≥step within N days of entry → cut).
- **Variant C** — RSI(14) / MACD(12,26,9) entry, band exit (+ optional stop).
- Grid: SMA {20,50,100,200} · leverage {1,2,3} · bands symmetric {1,2,3,5%} + asymmetric
  pairs · stop {none,0.5,1,1.5,2%}. Daily-close model.

## Result (only strategies that BEAT the incumbents)
The **variant-B "must-accelerate" exit** (cut a trade that fails to make a new +2% higher
band within 10–20 days) on the SMA200 ±3% entry is the only family that wins:
- **1x (Water):** `B-accel SMA200 e3% N10 s2%` → CAGR 10.01 / Sharpe 0.501 / Calmar 0.555 /
  DD −18.0% — a no-regret (Pareto) improvement on the incumbent Water (9.97 / 0.478 / 0.493 / −20.2).
- **2x (Octane):** same signal → Calmar 0.345 / Sharpe 0.505 / DD −39.1% vs incumbent (0.334 / −41.0).
- **3x:** 2 signals reached Octane-*class* but none beat the 2x incumbent; zero 3x Water —
  the −45% DD gate caps 3x (known structural fact).

Improvement is modest but consistent across N=10 and N=20.

## Where the winners landed
Added directly into the EXISTING `S&P 500 Water` (11→13) and `S&P 500 Octane` (11→14)
tabs of `Results/strategy_results.xlsx`, ranked among the incumbents:
- Water: `SMA200 +-3% Band + Accel-Exit N10/N20 1x/cash` (N10 is the new #1 by Sharpe, 0.538).
- Octane: `SMA200 +-3% Band + Accel-Exit N10/N20 2x` and `SMA200 +5%/-3% Band 2x`
  (new top-3 by Calmar, above the former #1 RSI>20 at 0.32).

`add_winners.py` is the integration step: it loads the 179-strategy source CSV
(`output/strategy_results/spx_results.csv`, the frozen source of the existing tabs),
recomputes the 5 winners on the SAME window (truncated to the CSV's 2026-06-24 end date,
plain-band-1x basis check = 10.48 = CSV), re-classifies with `classify_all`, and rewrites
the two tabs with `build_strategy_results_excel.build_detail_sheet`. All other tabs are
left byte-for-byte untouched. IMPORTANT: use the master sweep's `load_asset_data` loader
(NOT `backtest_spx_distance_scale.download_spx_panel`, which is a different/cleaner price
vintage and gives B&H 1x ≈ 9.3% vs the sheet's 9.99%).

## Reproduce
```bash
# from repo root, with research/spx_band_variant_sweep on PYTHONPATH
python research/spx_band_variant_sweep/sweep_driver.py output/spx_band_variant_sweep
python research/spx_band_variant_sweep/diagrams.py    output/spx_band_variant_sweep
python research/spx_band_variant_sweep/build_excel.py output/spx_band_variant_sweep <base.xlsx> <dest.xlsx>
```
Needs live `yfinance` for full 1950+ history (cached `spx_daily.csv` is only ~30y).
