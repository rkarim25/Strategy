# Tiered Guarded vs Binary 3x/Cash — Full Test Battery

Generated: 2026-06-01T20:08:45.895965+00:00

Runtime: 34.0s

## Test 1: Full-period comparison

| Asset | Strategy | CAGR | Max DD | End Value | Sharpe | %3x | Switches |
|-------|----------|------|--------|-----------|--------|-----|----------|
| NDX | Binary: any Guarded invested day → 3x | 114.85% | -47.94% | $908.07B | 3.29 | 68.7% | 807 |
| NDX | Binary: SMA20 on → 3x, else cash | 113.47% | -45.03% | $749.22B | 3.56 | 61.8% | 879 |
| NDX | Tiered ablation: skip 2x (1x→3x jump) | 103.48% | -47.94% | $177.71B | 3.20 | 63.5% | 820 |
| NDX | Binary: Guarded 2x/3x slots → 3x, else cash | 95.72% | -47.94% | $55.40B | 3.10 | 63.5% | 762 |
| NDX | Tiered Guarded A5/B25 (default) | 89.95% | -35.51% | $22.57B | 3.20 | 32.1% | 824 |
| NDX | Tiered ablation: cap at 2x (no 3x tier) | 73.38% | -28.42% | $1.46B | 3.37 | 0.0% | 820 |
| NDX | Tiered ablation: cap at 1x (no leverage) | 42.07% | -10.73% | $3.72M | 3.60 | 0.0% | 807 |
| NDX | Binary: DD≥5% + recovery → 3x | 35.50% | -71.58% | $897.2K | 2.43 | 41.0% | 658 |
| NDX | Binary: DD≥25% + recovery → 3x | 35.24% | -35.51% | $847.2K | 2.06 | 29.5% | 400 |
| NDX | Binary: SMA50>SMA200 trend → 3x | 29.81% | -75.73% | $247.8K | 0.99 | 67.6% | 127 |
| NDX | Always 3x (no cash filter) | 17.28% | -99.97% | $11.7K | 0.29 | 100.0% | 0 |
| NDX | Binary: low vol/VIX → 3x | 6.07% | -70.64% | $579 | 1.22 | 39.8% | 291 |
| SPX | Binary: any Guarded invested day → 3x | 45.09% | -48.07% | $6.99M | 3.40 | 71.2% | 763 |
| SPX | Tiered ablation: skip 2x (1x→3x jump) | 44.31% | -38.92% | $5.95M | 3.21 | 62.2% | 770 |
| SPX | Binary: Guarded 2x/3x slots → 3x, else cash | 43.48% | -38.89% | $5.00M | 3.06 | 62.2% | 623 |
| SPX | Tiered Guarded A5/B25 (default) | 37.09% | -27.89% | $1.27M | 3.13 | 13.6% | 773 |
| SPX | Tiered ablation: cap at 2x (no 3x tier) | 33.98% | -24.27% | $640.8K | 3.38 | 0.0% | 770 |
| SPX | Binary: SMA20 on → 3x, else cash | 32.96% | -62.59% | $508.5K | 3.74 | 63.0% | 867 |
| SPX | Binary: SMA50>SMA200 trend → 3x | 21.09% | -36.71% | $30.8K | 1.11 | 66.7% | 139 |
| SPX | Tiered ablation: cap at 1x (no leverage) | 20.77% | -17.62% | $28.5K | 3.68 | 0.0% | 763 |
| SPX | Binary: DD≥5% + recovery → 3x | 12.74% | -53.69% | $3.6K | 2.22 | 34.1% | 512 |
| SPX | Always 3x (no cash filter) | 12.29% | -98.41% | $3.2K | 0.29 | 100.0% | 0 |
| SPX | Binary: DD≥25% + recovery → 3x | 10.01% | -42.17% | $1.7K | 1.28 | 10.5% | 156 |
| SPX | Binary: low vol/VIX → 3x | 6.12% | -60.04% | $588 | 1.75 | 54.3% | 387 |

## Test 2: Tier decomposition (delta vs tiered default)

asset,variant,cagr_delta_vs_tiered,dd_delta_vs_tiered,end_ratio
SPX,tiered_cap_1x,-0.1631841407123968,0.1026786474819786,0.0223367650525649
SPX,tiered_cap_2x,-0.0310762136633602,0.0362487761958404,0.5026923896513974
SPX,tiered_skip_2x,0.0722200308581704,-0.1102963572327616,4.664442353013198
SPX,binary_guarded_any_invested,0.0800262144440964,-0.2018165790097079,5.483721099863234
NDX,tiered_cap_1x,-0.4787348617725735,0.2478507914652618,0.0001647999179278
NDX,tiered_cap_2x,-0.165666799044617,0.0709519826568493,0.0647424118959102
NDX,tiered_skip_2x,0.1352721705266293,-0.1243250502609883,7.873757941737927
NDX,binary_guarded_any_invested,0.2489865814845728,-0.1243250502845697,40.23446288509128


## Test 4: Bootstrap (NDX tiered vs best binary)

{
  "best_binary_key": "binary_guarded_any_invested",
  "tiered_wins_pct": 0.002,
  "mean_cagr_delta_tiered_minus_binary": -0.3351823436353338,
  "ci95_low": -0.612272112397667,
  "ci95_high": -0.11856586106722525
}

## Test 5: Rolling 5yr win rate

NDX tiered wins 4.0% of windows

SPX tiered wins 48.0% of windows


## Test 7: Cost sensitivity (NDX)

trading_cost_pct,tiered_cagr,binary_cagr,tiered_wins,cagr_delta
0.005,1.6566471861810943,2.243711891751496,False,-0.5870647055704015
0.01,0.8994780300934773,1.14846461157805,False,-0.2489865814845728
0.015,0.3530620712414489,0.4150605770024398,False,-0.0619985057609908
0.02,0.0243517177459877,0.0083881104660921,True,0.0159636072798956


## Test 8: Forward MC summary

{
  "tiered_median_cagr": 0.8664255143790068,
  "binary_median_cagr": 1.2337773700703765,
  "tiered_wins_pct": 0.02,
  "tiered_median_end": 40847.0194057022,
  "binary_median_end": 231310.2466370419
}

## Verdict scorecard

| Test | Pass? | Detail |
|------|-------|--------|
| Full-period NDX CAGR | NO | tiered 89.95% vs binary 114.85% |
| Full-period NDX end value | NO | $22.57B vs $908.07B |
| Full-period NDX max DD | YES | -35.51% vs -47.94% |
| Bootstrap tiered wins | NO | 0.2% of 500 resamples |
| Rolling 5yr NDX tiered wins | NO | 4.0% of windows |
| Walk-forward NDX | YES | tiered wins 4/4 folds on test |
| Cost sensitivity (all costs) | NO | tiered ahead at every cost level |
| MC forward median CAGR | NO | 86.64% vs 123.38% |

**Overall: 2/8 tests favour tiered → BINARY COMPETITIVE — REVIEW**
