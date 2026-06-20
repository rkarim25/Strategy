# Strategic portfolio policy

Final five-sleeve book for UK / Interactive Investor. Rebalance **quarterly** (or when any sleeve drifts **>5 pp** from target). Follow each sleeve’s **daily signal** on the site.

## Portfolio table

| Sleeve | Weight | Strategy | Instrument (II) |
|--------|--------|----------|-------------------|
| **S&P 500** | **40%** | Guarded A5/B25 · X40/Y15 · lead 0.75% · **full 2x/3x** | **SPYL** (1x) · **XS2D** (2x) · **3USL** (3x) · cash when 0x |
| **Nasdaq 100** | **15%** | Guarded A5/B25 · X40/Y15 · lead 0.75% · **full 2x/3x** | **EQQQ** (1x) · **LQQ** (2x) · **LQQ3** (3x) · cash when 0x |
| **FTSE 250** | **16%** | Guarded A5/B25 · X40/Y15 · lead 0.75% · **max 1x** | **MIDD** · cash when 0x |
| **MSCI EM** | **14%** | Guarded A5/B25 · X40/Y15 · lead 0.75% · **max 1x** | **EIMI** · cash when 0x |
| **Gold** | **15%** | Guarded A5/B25 · X40/Y15 · lead 0.75% · **max 1x** | **SGLN** · cash when 0x |

**Total:** 100%. Bold tickers are the main recommendation per tier. Signals use `^GSPC`, `^NDX`, `^FTMC`, `EEM`, `GC=F` respectively.

**Alts:** CSP1 / VUAG (S&P 1x), CNDX (Nasdaq 1x), VMID (FTSE 250), VFEM (EM), PHGP (gold).

## Strategy detail (all sleeves)

- **A5 / B25** — 5% drawdown → 2x path; 25% → 3x path (US sleeves only)
- **X40 / Y15** — recovery targets from tier entry
- **0.75% lead** — SMA20 recovery guard
- **SMA20** — below trend → cash (with lead guard)

Do **not** use 2x/3x on FTSE 250, EM, or gold (no clean II 2x+3x pair in policy).

## Back-test (semi-annual rebalance)

Script: `analyze_five_sleeve_portfolio_rebalance.py`  
Output: `output/five_sleeve_portfolio_rebalance/`

| Portfolio | CAGR | Vol | Sharpe | Max DD | End $ (from $100) |
|-----------|------|-----|--------|--------|-------------------|
| **Hybrid + rebalance Jan/Jul** | **~37%** | **~18%** | **~1.80** | **~−12%** | **~$94,563** |
| Hybrid + drift (no rebalance) | ~57% | ~25% | ~1.87 | ~−23% | ~$1.57m |

Window: **2004-11-18 → 2026-05-22** (gold/GLD history limit). **43** rebalance dates.  
Assumptions: $100 start, **$10/yr** total inflow at **portfolio** level, 1% sleeve trade cost, **0.1%** on rebalance turnover. Returns use **equity.pct_change()** (not raw `port_ret`).

Letting weights **drift** raises CAGR in this period (US sleeves dominated); **semi-annual rebalance** keeps policy weights and **shallower** max DD.

Per-sleeve Guarded (engine equity, $10/yr each — matches site pages): S&P **~39%**, Nasdaq **~103%**, FTSE 250 **~18%**, EM **~34%**, Gold **~19%** (full US lev / 1x others).

## Account placement

| Wrapper | Role |
|---------|------|
| **Stocks & shares ISAs** | All five sleeves; active Guarded + US leverage |
| **Pension (SIPP / workplace)** | Same policy if holdings allow LSE ETPs |
| **Cash ISA** | Emergency / deployment cash — outside the 100% risk budget |
| **GIA (taxable)** | **No Guarded.** Passive **Acc** (e.g. S&P or World) + sterling MM; bed-and-ISA when possible |

## Site and signals

| Sleeve | Page | Signal file | Leverage in signal |
|--------|------|-------------|-------------------|
| S&P 500 | `index.html` | `latest_signal.json` | Full (no `maxLeverage` cap) |
| Nasdaq 100 | `ndx_guarded.html` | `latest_ndx_signal.json` | Full |
| FTSE 250 | `ftse250_guarded.html` | `latest_ftse250_signal.json` | `maxLeverage: 1` |
| MSCI EM | `msci_em_guarded.html` | `latest_msci_em_signal.json` | `maxLeverage: 1` |
| Gold | `gold_guarded.html` | `latest_gold_signal.json` | `maxLeverage: 1` |

## Risk notes

- **US sleeves at full leverage** dominate portfolio tail risk (~40% + ~15% weight in levered US).
- **FTSE 250 / EM / gold at 1x** stabilise turnover and avoid weak levered ETPs on those markets.
- Combined back-test (Guarded, static weights, 2004–2026, `analyze_five_sleeve_hybrid_portfolio.py`):

  | Policy | CAGR (sim) | Vol | Sharpe | Max DD |
  |--------|------------|-----|--------|--------|
  | **Hybrid (your policy)** | ~105% | ~18% | ~4.0 | **~−10%** |
  | All sleeves max 1x | ~57% | ~9% | ~4.8 | ~−5% |
  | All sleeves full 3x | ~160% | ~23% | ~4.3 | ~−13% |

  Absolute CAGR levels are inflated by the multi-sleeve return blend; use **relative** DD and Sharpe. Hybrid roughly **doubles** simulated return vs all-1x with **~2× deeper** portfolio DD.

## Excluded from policy

- MSCI World (US overlap)
- MSCI EAFE (not accretive vs this five-sleeve mix in portfolio tests)
- Standalone Australia / DAX / Euro Stoxx
- Engine **5% hard drawdown floor** (different problem from Guarded max DD)
