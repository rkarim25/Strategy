"""
Guarded A5/B25 on major global equity indices — 1x for all II-investable benchmarks;
full 2x/3x recovery only where UK/II-listed daily 2x AND 3x ETPs exist (implementable).

Writes output/global_equity_guarded_ii/results.csv and summary.json for canvas.
"""

from __future__ import annotations
import sys as _s, pathlib as _p; _s.path.insert(0, str(_p.Path(__file__).resolve().parent.parent))  # repo root importable (moved into research/)

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from analyze_cross_asset_guarded_1x import (
    DEFAULT_GUARDED,
    build_world_equity_proxy_close,
    guarded_lead_leverage,
    run_row,
)
from test_tiered_dd_recovery_guarded import BASE_SMA_WINDOW, sma_cash_leverage

OUTPUT_DIR = Path("output") / "global_equity_guarded_ii"
TBILL = "^IRX"
YEARS = 30
MIN_ROWS = 252


@dataclass(frozen=True)
class IndexSpec:
    label: str
    yahoo: str
    region: str
    etf_1x: str
    etf_2x: str | None
    etf_3x: str | None
    ii_note: str

    @property
    def levered_implementable(self) -> bool:
        return bool(self.etf_2x and self.etf_3x)


# UK / II-accessible UCITS/ETPs (LSE unless noted). Full 2x+3x required for levered row.
II_UNIVERSE: list[IndexSpec] = [
    IndexSpec(
        "FTSE 100",
        "^FTSE",
        "UK",
        "ISF / VUKE / CUKX",
        "2UKL (WisdomTree 2x)",
        "3UKL (WisdomTree 3x)",
        "LSE daily-reset ETPs; ISA/SIPP eligible",
    ),
    IndexSpec(
        "FTSE 250",
        "^FTMC",
        "UK",
        "MIDD / VMID",
        "2MCL (WisdomTree 2x)",
        None,
        "2x only on II; no listed 3x FTSE 250 ETP — levered back-test omitted",
    ),
    IndexSpec(
        "S&P 500",
        "^GSPC",
        "US",
        "SPYL / CSP1 / VUAG",
        "XS2D / DBPG (Xtrackers 2x)",
        "3USL / 3LUS / 3SPY",
        "Core US sleeve; 2x/3x on LSE",
    ),
    IndexSpec(
        "Nasdaq 100",
        "^NDX",
        "US",
        "EQQQ / CNDX",
        "LQQ (Amundi 2x, Euronext)",
        "LQQ3 (WisdomTree 3x, LSE)",
        "2x primary listing Paris; 3x on LSE — both tradeable on II",
    ),
    IndexSpec(
        "Euro STOXX 50",
        "^STOXX50E",
        "Europe",
        "CS51 / SXRT",
        None,
        "3EUL (WisdomTree 3x, LSE)",
        "3x on II; no standard 2x Euro STOXX ETP found — levered omitted",
    ),
    IndexSpec(
        "DAX",
        "^GDAXI",
        "Europe",
        "EXS1 / XDAX",
        None,
        "3DEL (WisdomTree 3x, LSE)",
        "3x on II; no paired 2x DAX ETP — levered omitted",
    ),
    IndexSpec(
        "MSCI World",
        "SWDA.L",
        "Global",
        "IWDA / SWDA",
        None,
        None,
        "1x UCITS only; no daily 2x/3x world index ETP on II",
    ),
    IndexSpec(
        "MSCI ACWI",
        "ACWI",
        "Global",
        "SSAC / ISAC",
        None,
        None,
        "1x only",
    ),
    IndexSpec(
        "MSCI EM",
        "EEM",
        "EM",
        "EIMI / VFEM",
        None,
        None,
        "1x only; no UK 2x/3x EM index ETP",
    ),
    IndexSpec(
        "Developed ex-US",
        "EFA",
        "Intl",
        "IEFA / IEUX",
        None,
        None,
        "1x only",
    ),
    IndexSpec(
        "Japan (Nikkei 225)",
        "^N225",
        "Japan",
        "CNDX / XDJP",
        None,
        None,
        "1x trackers on II; no Nikkei 2x/3x index ETP",
    ),
    IndexSpec(
        "World (30y proxy)",
        "synthetic",
        "Global",
        "IWDA / VT",
        None,
        None,
        "Spliced SPY/EFA/VTI/VEU/VT for long history; 1x only",
    ),
]

PROXY_TICKERS = ["SPY", "EFA", "VTI", "VEU", "VT"]


def download_closes(years: int = YEARS) -> pd.DataFrame:
    end = datetime.today()
    start = end - timedelta(days=int(years * 365.25))
    tickers = list(
        {
            spec.yahoo
            for spec in II_UNIVERSE
            if spec.yahoo != "synthetic"
        }
        | set(PROXY_TICKERS)
        | {TBILL}
    )
    raw = yf.download(
        tickers,
        start=start.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )
    if raw.empty:
        raise ValueError("No data from yfinance")
    if isinstance(raw.columns, pd.MultiIndex):
        return raw["Close"].copy().sort_index().ffill()
    return raw.rename(columns={"Close": tickers[0]}).sort_index().ffill()


def panel_for_close(close: pd.Series, tbill: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"spx_close": close.astype(float), "tbill_rate": tbill}).dropna(how="any")


def fmt_pct(x: float | None, digits: int = 1) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "—"
    return f"{100.0 * x:.{digits}f}%"


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Downloading market data...")
    closes = download_closes(YEARS)
    tbill = closes[TBILL] / 100.0

    rows: list[dict] = []

    for spec in II_UNIVERSE:
        if spec.yahoo == "synthetic":
            try:
                close = build_world_equity_proxy_close(closes)
            except Exception as exc:  # noqa: BLE001
                print(f"Skip {spec.label}: {exc}")
                continue
        else:
            col = spec.yahoo
            if col not in closes.columns:
                alt = col.replace(".L", "")
                if alt in closes.columns:
                    col = alt
                else:
                    print(f"Skip {spec.label}: missing {spec.yahoo}")
                    continue
            close = closes[col].dropna()

        panel = panel_for_close(close, tbill)
        if len(panel) < MIN_ROWS:
            print(f"Skip {spec.label}: only {len(panel)} rows")
            continue

        print(f"{spec.label}: {panel.index[0].date()} to {panel.index[-1].date()} ({len(panel)} days)")

        extra_base = {
            "region": spec.region,
            "yahoo": spec.yahoo,
            "etf_1x": spec.etf_1x,
            "etf_2x": spec.etf_2x or "",
            "etf_3x": spec.etf_3x or "",
            "ii_levered_ok": spec.levered_implementable,
            "ii_note": spec.ii_note,
        }

        lev_bh = pd.Series(1.0, index=panel.index)
        rows.append(run_row(spec.label, panel, "Buy & hold 1x", lev_bh, extra_base))

        lev_1x, counts_1x = guarded_lead_leverage(panel, max_leverage=1.0)
        rows.append(
            run_row(
                spec.label,
                panel,
                "Guarded max 1x",
                lev_1x,
                {**extra_base, **counts_1x},
            )
        )

        if spec.levered_implementable:
            lev_full, counts_full = guarded_lead_leverage(panel, max_leverage=3.0)
            rows.append(
                run_row(
                    spec.label,
                    panel,
                    "Guarded full 2x/3x",
                    lev_full,
                    {**extra_base, **counts_full},
                )
            )

    df = pd.DataFrame(rows)
    out_csv = OUTPUT_DIR / "results.csv"
    df.to_csv(out_csv, index=False)

    # Summary for canvas: one row per index, guarded 1x vs BH and optional levered
    summary: list[dict] = []
    for spec in II_UNIVERSE:
        sub = df[df["asset"] == spec.label]
        if sub.empty:
            continue
        bh = sub[sub["strategy"] == "Buy & hold 1x"].iloc[0]
        g1 = sub[sub["strategy"] == "Guarded max 1x"].iloc[0]
        entry = {
            "index": spec.label,
            "region": spec.region,
            "yahoo": spec.yahoo,
            "start": g1["start_date"],
            "end": g1["end_date"],
            "days": int(g1["trading_days"]),
            "etf_1x": spec.etf_1x,
            "etf_2x": spec.etf_2x,
            "etf_3x": spec.etf_3x,
            "levered_tested": spec.levered_implementable,
            "ii_note": spec.ii_note,
            "bh_cagr": bh["cagr"],
            "bh_max_dd": bh["max_drawdown"],
            "g1_cagr": g1["cagr"],
            "g1_max_dd": g1["max_drawdown"],
            "g1_sharpe": g1["sharpe"],
            "g1_end": g1["end_$"],
            "cagr_delta_1x": (g1["cagr"] - bh["cagr"]) if pd.notna(g1["cagr"]) and pd.notna(bh["cagr"]) else None,
            "dd_delta_1x": (g1["max_drawdown"] - bh["max_drawdown"]) if pd.notna(g1["max_drawdown"]) else None,
        }
        gl = sub[sub["strategy"] == "Guarded full 2x/3x"]
        if not gl.empty:
            g = gl.iloc[0]
            entry["glev_cagr"] = g["cagr"]
            entry["glev_max_dd"] = g["max_drawdown"]
            entry["glev_sharpe"] = g["sharpe"]
            entry["glev_end"] = g["end_$"]
            entry["cagr_delta_lev"] = g["cagr"] - bh["cagr"]
            entry["dd_delta_lev"] = g["max_drawdown"] - bh["max_drawdown"]
        summary.append(entry)

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "params": DEFAULT_GUARDED,
        "levered_rule": "Full 2x/3x back-test only when both ii_2x and ii_3x ETPs are listed for II.",
        "summary": summary,
    }
    summary_path = OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"\nWrote {out_csv} ({len(df)} rows)")
    print(f"Wrote {summary_path} ({len(summary)} indices)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
