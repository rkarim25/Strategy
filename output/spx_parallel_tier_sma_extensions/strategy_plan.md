# Parallel tier SMA extensions (SPX)

## 1. Hybrid (latched Guarded arming + parallel pick)

SPX drawdown **arms** max allowed tier (latched until DD recovers):
- Base: max 1x
- DD <= -5% (A): arms tier-2 cap (max 2x) until DD > -5%
- DD <= -25% (B): arms tier-3 cap (max 3x) until DD > -25% (or -5% for full disarm)

**No fixed +40% / +15% recovery exit.** Within the cap, pick tier via parallel
SMA on 1x/2x/3x ETP benchmarks (greedy or best margin). Optional SPX 0.75% lead guard.

## 2. Risk cap

Parallel greedy / best-margin pick, but **hard cap at 2x** unless SPX DD <= -25%
(only then allow 3x).

## 3. Hysteresis

Raw parallel greedy or best-margin signal must persist **2 or 3 consecutive days**
before switching tier (reduces whipsaw / rebalance count).

## 4. Score blend

Greedy pick on `score_k = margin_k - lambda * vol_k` where `vol_k` is 20-day
rolling stdev of tier benchmark daily returns. Test lambda in {0.5, 1.0, 2.0};
tier chosen only if score > 0.

## Baselines (same window)

- Guarded A5/B25 SMA20 Lead (default)
- Parallel greedy / best margin (uncapped)
- 3x tier-native lead (3x benchmark >= SMA20 - 0.75%)

Assumptions: SPX_ETP P&L, $100 start, $10/yr inflow, 1% rebalance cost.
