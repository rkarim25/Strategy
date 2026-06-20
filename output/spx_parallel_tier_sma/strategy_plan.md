# Parallel tier SMA rotation (SPX)

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
4. **SMA and momentum** — greedy SMA pick AND momentum pick must agree; else cash. (Stricter.)
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
