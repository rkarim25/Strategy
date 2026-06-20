import csv
from datetime import datetime
from pathlib import Path

import yfinance as yf

TARGET_START = datetime(1998, 1, 1)
OUT_DIR = Path("output")
OUT_DIR.mkdir(exist_ok=True)

# ticker, kind, notes
TICKERS = [
    ("^GSPC", "index", "S&P 500 baseline"),
    ("GLD", "etf", "Gold ETF"),
    ("GC=F", "futures", "Gold futures"),
    ("^GOLD", "index", "Gold index proxy"),
    ("XAUUSD=X", "fx", "Gold USD spot"),
    ("XAU=X", "fx", "Gold spot alt"),
    ("DBC", "etf", "Broad commodities ETF"),
    ("GSG", "etf", "Commodities ETF"),
    ("^CRB", "index", "CRB index"),
    ("^BCOM", "index", "Bloomberg Commodity"),
    ("^TNX", "index", "10Y yield"),
    ("^TYX", "index", "30Y yield"),
    ("^FVX", "index", "5Y yield"),
    ("TLT", "etf", "20+Y Treasury ETF"),
    ("IEF", "etf", "7-10Y Treasury ETF"),
    ("SHY", "etf", "1-3Y Treasury ETF"),
    ("ZB=F", "futures", "30Y bond futures"),
    ("VT", "etf", "Total world ETF"),
    ("ACWI", "etf", "MSCI ACWI ETF"),
    ("URTH", "etf", "MSCI World ETF"),
    ("EFA", "etf", "EAFE developed"),
    ("VEU", "etf", "All world ex-US"),
    ("GEISAC.FGI", "index", "FTSE Global All Cap"),
    ("^NDX", "index", "Nasdaq 100"),
    ("^VIX", "index", "VIX"),
    ("^RUT", "index", "Russell 2000"),
    ("VNQ", "etf", "REIT ETF"),
    ("IYR", "etf", "REIT ETF"),
    ("EEM", "etf", "EM ETF"),
    ("^MSCIEF", "index", "MSCI EM index"),
    ("BTC-USD", "crypto", "Bitcoin"),
    ("^DJI", "index", "Dow Jones"),
    ("^IXIC", "index", "Nasdaq Composite"),
    ("SPY", "etf", "S&P 500 ETF"),
    ("VGK", "etf", "Europe"),
    ("VWO", "etf", "EM Vanguard"),
    ("TIP", "etf", "TIPS"),
    ("^IRX", "index", "13-week T-bill yield"),
    ("^GVZ", "index", "Gold vol"),
    ("^OVX", "index", "Oil vol"),
]

rows = []
for ticker, kind, notes in TICKERS:
    rec = {
        "ticker": ticker,
        "kind": kind,
        "notes": notes,
        "earliest": "",
        "latest": "",
        "row_count": 0,
        "usable_30y": False,
        "error": "",
    }
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="max", auto_adjust=True)
        if hist is None or hist.empty:
            rec["error"] = "empty history"
        else:
            hist = hist.dropna(how="all")
            if hist.empty:
                rec["error"] = "all NaN"
            else:
                earliest = hist.index.min().to_pydatetime().replace(tzinfo=None)
                latest = hist.index.max().to_pydatetime().replace(tzinfo=None)
                rec["earliest"] = earliest.strftime("%Y-%m-%d")
                rec["latest"] = latest.strftime("%Y-%m-%d")
                rec["row_count"] = len(hist)
                rec["usable_30y"] = earliest <= TARGET_START
    except Exception as e:
        rec["error"] = str(e)[:200]
    rows.append(rec)
    status = "OK" if not rec["error"] else rec["error"][:40]
    print(f"{ticker:14} {rec['earliest'] or '---':10} rows={rec['row_count']:5} 30y={rec['usable_30y']} {status}")

csv_path = OUT_DIR / "index_history_availability.csv"
with csv_path.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["ticker", "kind", "notes", "earliest", "latest", "row_count", "usable_30y", "error"])
    w.writeheader()
    w.writerows(rows)

# markdown summary
full30 = [r for r in rows if r["usable_30y"] and not r["error"]]
etf_late = [r for r in rows if r["kind"] == "etf" and r["row_count"] and not r["usable_30y"] and not r["error"]]
index_late = [r for r in rows if r["kind"] in ("index", "fx") and r["row_count"] and not r["usable_30y"] and not r["error"]]
failed = [r for r in rows if r["error"] or r["row_count"] == 0]

lines = [
    "# Index / ETF history availability (Yahoo Finance)",
    "",
    f"Probe date: {datetime.now().strftime('%Y-%m-%d')}",
    f"30-year backtest threshold: daily data on or before **{TARGET_START.date()}**.",
    "",
    "## Summary counts",
    f"- Usable for ~30y backtest: **{len(full30)}** tickers",
    f"- Has data but starts after 1998: **{len([r for r in rows if r['row_count'] and not r['usable_30y'] and not r['error']])}**",
    f"- Empty / error: **{len(failed)}**",
    "",
    "## Full ~30y (index or long history)",
]
for r in sorted(full30, key=lambda x: x["ticker"]):
    lines.append(f"- `{r['ticker']}` ({r['kind']}): {r['earliest']} → {r['latest']}, {r['row_count']} rows — {r['notes']}")

lines += ["", "## ETF / late inception (typical 2000s+)"]
for r in sorted(etf_late, key=lambda x: x["earliest"]):
    lines.append(f"- `{r['ticker']}`: from **{r['earliest']}**, {r['row_count']} rows — {r['notes']}")

lines += ["", "## Indices with data but after 1998"]
for r in sorted(index_late, key=lambda x: x["earliest"]):
    lines.append(f"- `{r['ticker']}`: from **{r['earliest']}** — {r['notes']}")

lines += ["", "## No usable Yahoo daily history"]
for r in failed:
    lines.append(f"- `{r['ticker']}` ({r['kind']}): {r['error'] or 'no rows'}")

lines += [
    "",
    "## FTSE Global All Cap / world benchmark",
]
gei = next((r for r in rows if r["ticker"] == "GEISAC.FGI"), None)
vt = next((r for r in rows if r["ticker"] == "VT"), None)
acwi = next((r for r in rows if r["ticker"] == "ACWI"), None)
for r in [gei, vt, acwi, next((x for x in rows if x["ticker"] == "URTH"), None)]:
    if r:
        lines.append(f"- `{r['ticker']}`: earliest {r['earliest'] or 'N/A'}, rows={r['row_count']}, 30y={r['usable_30y']}, err={r['error']}")

lines += [
    "",
    "## Notes",
    "- **True indices** on Yahoo (e.g. `^GSPC`, `^NDX`, yield indices) often reach 1990s+.",
    "- **ETFs** are fund NAV/share price; inception caps history (e.g. GLD 2004, TLT 2002).",
    "- **Futures** (`GC=F`, `ZB=F`) have long OHLC but are continuous contracts, not investable index levels.",
    "- **GEISAC.FGI** is not a reliable 30y daily series on Yahoo; use `^GSPC` + regional ETFs or external index data for global cap before ~2010.",
    "- **BTC-USD** is short history vs 30y targets.",
    "",
    f"Full table: `{csv_path.as_posix()}`",
]

md_path = OUT_DIR / "index_history_availability.md"
md_path.write_text("\n".join(lines), encoding="utf-8")
print(f"\nWrote {csv_path} and {md_path}")
