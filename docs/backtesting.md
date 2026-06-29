# Backtesting

Engine parameters, data sources, and how to regenerate outputs. For strategy definitions and
classification see [`strategies.md`](strategies.md); for module roles see [`architecture.md`](architecture.md).

> **Testing a NEW strategy or reproducing an old backtest?** Read
> [`strategy-lab.md`](strategy-lab.md) FIRST — it pins the canonical basis (the
> `load_asset_data` loader, NOT `download_spx_panel`) so your numbers are comparable to
> the workbook + website, and gives a reusable harness (`research/strategy_lab/`).

## Engine configuration (`sweep_all_assets_strategies.py`)

- **Signal delay:** 1 day (prevents look-ahead bias — a signal from bar T fills at T+1).
- **Trading cost:** per-asset (table below), charged from mid-price on each leverage change.
- **Annual inflow:** $10 absolute on $100 initial capital.
- **Drawdown protection:** none by default (`max_drawdown_limit=None`, `hard_drawdown_floor=False`).
- **Funding:** VIX-linked borrow spread (0.6% base + 30 bp per 10 pts above VIX 15, cap 2.6%, +20 bp at 3x).
- **ETP returns:** real listed ETP daily returns where available; synthetic daily-reset fallback pre-inception.
- **Defaults:** VIX 20.0 (pre-1990), T-bill 3% (pre-`^IRX`).

### Per-asset trading costs

| Asset | Cost | | Asset | Cost |
|-------|------|---|-------|------|
| S&P 500 | 0.10% | | FTSE 250 | 0.20% |
| S&P 500 EW | 0.12% | | DAX | 0.20% |
| Nasdaq 100 | 0.10% | | MSCI EM | 0.20% |
| Russell 2000 | 0.15% | | MSCI World | 0.15% |
| Gold | 0.15% | | 20Y+ Treasuries | 0.10% |

Real liquid-ETF half-spreads are ~0.01–0.05%; these include a 2–10× conservative buffer. **If you change a
cost, update it in BOTH `sweep_all_assets_strategies.py` AND `build_strategy_results_excel.py`
(`TRADING_COST_LABELS`).**

### ETP TER (embedded in real returns; subtracted daily in synthetic model)

1x = 0.30% (SPY, QQQ) · 2x = 0.60% (SSO, QLD) · 3x = 0.90% (UPRO, TQQQ).

### Time periods

S&P 500 from 1950-01-03 · Nasdaq 100 from 1985-10-01 · others from index/ETF inception
(MSCI World clamped to 2009-12-01 — Yahoo `SWDA.L` pre-2009 is unreliable).

## Data sources & cleaning

- **Source:** Yahoo Finance via `yfinance` (`data_manager.py`), tickers `^GSPC`, `^IRX`, `^VIX`, plus per-asset.
- **Cleaning:** `price_cleaning.py` runs a shared **round-trip spike filter**, kept in parity with the cron
  `clean_price_spikes` (covered by `test_price_cleaning.py`).
- **Two writers per daily CSV:** the cron writes full history at `.12g`; backtests write ~30y at `.9g`.
  Expect both to touch `{slug}_daily.csv`.
- **1950 history gotcha:** download `^GSPC` **alone**, then reindex `^IRX`/`^VIX` (ffill + defaults). Downloading
  all three together + `dropna(subset=["tbill_rate"])` truncates history to 1960.
- **Sharpe gotcha:** pass `risk_free=` (e.g. `avg_tbill`) to `comprehensive_stats()`, or Sharpe comes out wrong.

## Real vs synthetic ETP modelling

- Prefer **same-calendar US ETPs** (SSO/UPRO, QLD/TQQQ) over UCITS like `XS2D.L`/`LQQ.PA` — a calendar offset
  inflates daily-timed backtests.
- The synthetic daily-reset model **double-counts vol drag** (too pessimistic) vs real ETP data.
- A 1% rebalance cost destroys high-turnover SMA strategies — be deliberate about the cost level you quote.

## Regenerating outputs

```bash
python sweep_all_assets_strategies.py     # 1) ~35 strategies × 10 assets -> output/strategy_results/*.csv
python build_strategy_results_excel.py    # 2) CSVs -> Results/strategy_results.xlsx (Water/Octane/Stillwater)
python build_summary_excel_json.py        # 3) all_assets_combined.csv -> summary_excel.json (for summary.html)
```

**Always run the sweep before the Excel builder** (the builder reads the CSVs). When you change classification
logic, update the **Definitions sheet** in the Excel too.

## Key scripts (root)

| Pattern | Purpose |
|---------|---------|
| `sweep_*.py` | Parameter sweeps (`sweep_all_assets_strategies.py` is the master; `sweep_comprehensive_spx_ndx.py` adds C21 lever-up families) |
| `backtest_*.py` | Single-strategy/asset backtests (e.g. `backtest_spx_distance_scale.py` → the SPX Octane band+RSI data) |
| `build_*.py` | Output generators (Excel, summary JSON, asset pages) |
| `analyze_*.py` | Research/analysis (outputs land in `output/<name>/`) |
| `verify_*.py`, `validate_*.py`, `*_validate_*.py` | Consistency/sanity checks |
