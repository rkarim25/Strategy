# Parallel tier SMA + risk cap sweep (SPX)

## Goal

Find parameter sets where **parallel tier SMA picking under a drawdown risk cap**
beats or matches default **Guarded A5/B25** on Sharpe and/or CAGR without
materially worse drawdown.

## Cap families

1. **Flat cap** — default max leverage (1x or 2x); allow 3x only when SPX DD <= threshold.
2. **Tiered cap** — default cap, then 2x when DD <= trigger_a, 3x when DD <= trigger_b
   (Guarded-style arming as a hard ceiling, not latched).

## Pick modes (all subject to cap + optional SPX 0.75% lead guard)

- greedy tier SMA
- best SMA margin
- 20d momentum
- score blend: margin_k - lambda * vol_k (under cap)

## Baselines

Guarded A5/B25, uncapped parallel greedy/best margin, prior best flat cap (2x / DD<=-25%).

Assumptions: SPX_ETP, $100 + $10/yr, 1% rebalance cost, 1996+ window.
