# A3/B15 vs A5/B25 validation verdict

**Verdict:** DISCARD

Tests passed: 5/8  (Test 2/3/4 critical-pass: False)

## In-sample reference (NDX full history, ETP+VIX cost model)

| Config | CAGR | MaxDD | Calmar | End $ |
|---|---|---|---|---|
| Baseline A5/B25 | 89.95% | -35.51% | 2.53 | $22.57B |
| Candidate A3/B15 | 91.90% | -35.51% | 2.59 | $30.66B |

## Per-test pass/fail

| Test | Criterion | Result | Pass? |
|------|-----------|--------|-------|
| 1. Boundary | A3/B15 at/near CAGR max AND CAGR does not keep rising for A<3 | best A1/B8 CAGR=99.74% vs A3/B15 CAGR=91.90% | NO |
| 2. Walk-forward | A3/B15 (or train-fold equivalent) beats baseline on TEST in ≥3/4 folds | 4/4 folds pass | YES |
| 3. Cross-asset | A3/B15 strictly beats baseline (CAGR up, DD non-worse) in ≥4/7 assets | 1/7 assets pass | NO |
| 4. Bootstrap CI | win-rate>70% AND 95% CI of CAGR diff excludes 0 | win-rate=98.9%, 95% CI=[+0.60, +14.64]pp | YES |
| 5. Rolling 5-yr | A3/B15 wins in ≥60% of 5-yr windows, no catastrophic loss | win-rate=85.3% over 102 windows, worst Δ=-3.27pp | YES |
| 6. Crisis episodes | A3/B15 DD ≥ baseline in EVERY episode | no worse in any | YES |
| 7. Cost sensitivity | A3/B15 ranks ahead in ALL combos | 18/36 combos pass, worst Δ=-3.14pp | NO |
| 8. Monte Carlo | median CAGR dominates AND 5th-pctile end-$ not worse | median Δ=+7.27pp, 5th-pctile end cand=$12,282 vs base=$9,428 | YES |

## Recommendation

**DISCARD A3/B15. Keep A5/B25 as the default.**

The candidate failed at least one of the critical validation tests (walk-forward, cross-asset, or bootstrap CI), 
indicating its in-sample edge does not generalise reliably out of sample.

## Caveats

- All tests use the same ETP+VIX cost model and same data window the website already uses; 
  hidden costs (slippage, liquidity, FX hedge drag on UK/II tickers) are not modelled.
- Bootstrap of joint daily returns + signals preserves marginal distributions but breaks 
  cross-day autocorrelation beyond the 21-day block; very persistent regimes (e.g. multi-year 
  bull runs) are under-represented vs reality.
- A3/B15 mechanically arms tier-2/3 more often: realised trading frequency and tax-event drag 
  could erode the modelled CAGR edge in real client portfolios.

