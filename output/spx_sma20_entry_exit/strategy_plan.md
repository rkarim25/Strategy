# SPX SMA entry/exit sweep

## Question

Can a **low-turnover** price-vs-SMA rule beat default **Guarded A5/B25 SMA20 Lead**
on Sharpe and/or CAGR with materially fewer rebalances?

## Default baseline

| Metric | Value |
|--------|-------|
| Strategy | Guarded A5/B25 SMA20 Lead |
| CAGR | 37.23% |
| Sharpe | 3.132 |
| Max DD | -27.89% |
| End $ | $1,312,569 |
| Rebalances | 774 |

## Families tested (427 configs)

1. **Binary SMA** — invested at Lx when close > SMA(w), cash when below; sweep confirm days N∈{1,2,3,5}.
2. **Buffer hysteresis** — enter above SMA×(1+entry%), exit below SMA×(1−exit%); confirm=1d.
3. **SMA distance tiers** — 1x above SMA, 2x/3x when margin exceeds tier thresholds.

## Parameter grid (focused)

- SMA window: [10, 15, 20, 30, 50, 100, 200]
- Leverage (binary/buffer): [1.0, 2.0, 3.0]
- Entry buffer: ['0%', '0.5%', '1%', '2%']
- Exit buffer: ['0%', '0.5%', '1%', '2%']
- Confirm days (binary only): [1, 2, 3, 5]
- Tier margins: [(0.03, 0.1), (0.05, 0.15), (0.05, 0.2), (0.1, 0.25)]

## Ranking

- **Low turnover**: Sharpe among configs with rebalances ≤ 200
- **Pareto**: non-dominated on CAGR ↑, Sharpe ↑, rebalances ↓

## Engine

- SPX_ETP daily returns (`ret_1` / `ret_2` / `ret_3`)
- $100 start, $10/yr inflow, 1.0% rebalance cost
