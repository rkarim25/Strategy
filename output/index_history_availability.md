# Index / ETF history availability (Yahoo Finance)

Probe date: 2026-05-19
30-year backtest threshold: daily data on or before **1998-01-01**.

## Summary counts
- Usable for ~30y backtest: **12** tickers
- Has data but starts after 1998: **22**
- Empty / error: **6**

## Full ~30y (index or long history)
- `SPY` (etf): 1993-01-29 → 2026-05-19, 8383 rows — S&P 500 ETF
- `^BCOM` (index): 1991-01-02 → 2026-05-18, 8882 rows — Bloomberg Commodity
- `^DJI` (index): 1992-01-02 → 2026-05-19, 8656 rows — Dow Jones
- `^FVX` (index): 1962-01-02 → 2026-05-19, 16110 rows — 5Y yield
- `^GSPC` (index): 1927-12-30 → 2026-05-19, 24712 rows — S&P 500 baseline
- `^IRX` (index): 1960-01-04 → 2026-05-19, 16609 rows — 13-week T-bill yield
- `^IXIC` (index): 1971-02-05 → 2026-05-19, 13938 rows — Nasdaq Composite
- `^NDX` (index): 1985-10-01 → 2026-05-19, 10237 rows — Nasdaq 100
- `^RUT` (index): 1987-09-10 → 2026-05-19, 9746 rows — Russell 2000
- `^TNX` (index): 1962-01-02 → 2026-05-19, 16110 rows — 10Y yield
- `^TYX` (index): 1977-02-15 → 2026-05-19, 12340 rows — 30Y yield
- `^VIX` (index): 1990-01-02 → 2026-05-19, 9162 rows — VIX

## ETF / late inception (typical 2000s+)
- `IYR`: from **2000-06-19**, 6518 rows — REIT ETF
- `EFA`: from **2001-08-27**, 6218 rows — EAFE developed
- `TLT`: from **2002-07-30**, 5990 rows — 20+Y Treasury ETF
- `IEF`: from **2002-07-30**, 5990 rows — 7-10Y Treasury ETF
- `SHY`: from **2002-07-30**, 5990 rows — 1-3Y Treasury ETF
- `EEM`: from **2003-04-14**, 5812 rows — EM ETF
- `TIP`: from **2003-12-05**, 5648 rows — TIPS
- `VNQ`: from **2004-09-29**, 5444 rows — REIT ETF
- `GLD`: from **2004-11-18**, 5408 rows — Gold ETF
- `VGK`: from **2005-03-10**, 5332 rows — Europe
- `VWO`: from **2005-03-10**, 5332 rows — EM Vanguard
- `DBC`: from **2006-02-06**, 5103 rows — Broad commodities ETF
- `GSG`: from **2006-07-21**, 4988 rows — Commodities ETF
- `VEU`: from **2007-03-08**, 4831 rows — All world ex-US
- `ACWI`: from **2008-03-28**, 4565 rows — MSCI ACWI ETF
- `VT`: from **2008-06-26**, 4502 rows — Total world ETF
- `URTH`: from **2012-01-12**, 3608 rows — MSCI World ETF

## Indices with data but after 1998
- `^OVX`: from **2007-05-10** — Oil vol
- `^GVZ`: from **2008-06-03** — Gold vol

## No usable Yahoo daily history
- `^GOLD` (index): empty history
- `XAUUSD=X` (fx): empty history
- `XAU=X` (fx): empty history
- `^CRB` (index): empty history
- `GEISAC.FGI` (index): empty history
- `^MSCIEF` (index): empty history

## FTSE Global All Cap / world benchmark
- `GEISAC.FGI`: earliest N/A, rows=0, 30y=False, err=empty history
- `VT`: earliest 2008-06-26, rows=4502, 30y=False, err=
- `ACWI`: earliest 2008-03-28, rows=4565, 30y=False, err=
- `URTH`: earliest 2012-01-12, rows=3608, 30y=False, err=

## Notes
- **True indices** on Yahoo (e.g. `^GSPC`, `^NDX`, yield indices) often reach 1990s+.
- **ETFs** are fund NAV/share price; inception caps history (e.g. GLD 2004, TLT 2002).
- **Futures** (`GC=F`, `ZB=F`) have long OHLC but are continuous contracts, not investable index levels.
- **GEISAC.FGI** is not a reliable 30y daily series on Yahoo; use `^GSPC` + regional ETFs or external index data for global cap before ~2010.
- **BTC-USD** is short history vs 30y targets.


### Gold / commodities / global on Yahoo (30y reality)
| Asset class | ~30y index on Yahoo? | Best Yahoo substitute |
|-------------|----------------------|------------------------|
| US equity | Yes | ^GSPC, SPY (1993+) |
| Gold | **No** investable index | GC=F (~2000+), GLD (2004+) |
| Commodities | Partial | ^BCOM (1991+ index level) |
| Treasuries (levels) | Yields yes, TR no | ^TNX/^TYX/^FVX/^IRX; ETFs TLT/IEF/SHY (2002+) |
| World equity | **No** | EFA (2001+), VT/ACWI (2008+) |
| EM equity | **No** | EEM (2003+) |
| Vol | Yes (VIX) | ^VIX (1990+) |
| REITs | Index proxy weak | ^RUT is small-cap not REIT; IYR/VNQ 2000s+ |
| Bitcoin | No | BTC-USD (2014+) |

Full table: `output/index_history_availability.csv`