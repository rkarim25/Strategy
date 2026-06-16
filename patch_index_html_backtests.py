"""
Update hardcoded backtest tables in index.html from regenerated CSV/JSON outputs.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
INDEX_HTML = ROOT / "index.html"
SPX_SITE = ROOT / "spx_guarded_site_data.json"
MC_SUMMARY = ROOT / "output" / "guarded_balanced_candidate" / "guarded_balanced_candidate_monte_carlo_summary.csv"
MOMENTUM_CSV = ROOT / "output" / "momentum_leverage_strategies" / "momentum_leverage_results.csv"
LONG_HOLD_CSV = ROOT / "output" / "long_hold_momentum_strategies" / "long_hold_momentum_results.csv"
TIERED_CSV = ROOT / "output" / "guarded_tiered_sma20_50_200" / "guarded_tiered_sma20_50_200_results.csv"


def pct(x: float) -> str:
    return f"{100.0 * float(x):.2f}%"


def _pct_days(x: float) -> str:
    v = float(x)
    if v > 1.0:
        v /= 100.0
    return f"{v * 100:.2f}%"


def money(x: float) -> str:
    return f"${float(x):,.0f}"


def replace_tbody(html: str, marker_before: str, new_rows: str) -> str:
    """Replace tbody rows in the section after marker_before (unique heading text)."""
    pos = html.find(marker_before)
    if pos < 0:
        raise ValueError(f"Marker not found: {marker_before!r}")
    tbody_start = html.find("<tbody", pos)
    if tbody_start < 0:
        raise ValueError(f"No tbody after {marker_before!r}")
    open_end = html.find(">", tbody_start) + 1
    tbody_end = html.find("</tbody>", open_end)
    return html[:open_end] + "\n" + new_rows + "\n          " + html[tbody_end:]


def row_full_sample(r: pd.Series, bold: bool = False) -> str:
    b = "<strong>" if bold else ""
    be = "</strong>" if bold else ""
    cash = r.get("pct_days_cash")
    cash_s = pct(cash / 100.0) if pd.notna(cash) and cash > 1 else pct(cash) if pd.notna(cash) else "-"
    return (
        f"            <tr><td>{b}{r['strategy']}{be}</td>"
        f"<td>{b}{pct(r['cagr'])}{be}</td>"
        f"<td>{pct(r['ann_volatility']) if pd.notna(r.get('ann_volatility')) else '-'}</td>"
        f"<td>{float(r['sharpe']):.3f}</td>"
        f"<td>{pct(r['max_drawdown'])}</td>"
        f"<td>{b}{money(r['end_$'])}{be}</td>"
        f"<td>{int(r.get('rebalances', 0))}</td>"
        f"<td>{cash_s}</td></tr>"
    )


def row_tiered(r: pd.Series) -> str:
    t2 = int(r.get("tier2_entries", 0))
    t3 = int(r.get("tier3_entries", 0))
    entries = f"{t2} / {t3}" if t2 or t3 else "-"
    return (
        f"            <tr><td>{r['strategy']}</td>"
        f"<td>{pct(r['cagr'])}</td>"
        f"<td>{float(r['sharpe']):.3f}</td>"
        f"<td>{pct(r['max_drawdown'])}</td>"
        f"<td>{money(r['end_$'])}</td>"
        f"<td>{_pct_days(r['pct_days_cash'])}</td>"
        f"<td>{_pct_days(r['pct_days_1x'])}</td>"
        f"<td>{_pct_days(r['pct_days_2x'])}</td>"
        f"<td>{_pct_days(r['pct_days_3x'])}</td>"
        f"<td>{entries}</td></tr>"
    )


def row_momentum(r: pd.Series) -> str:
    return (
        f"              <tr><td>{r['strategy']}</td>"
        f"<td>{pct(r['cagr'])}</td>"
        f"<td>{pct(r['ann_volatility'])}</td>"
        f"<td>{float(r['sharpe']):.3f}</td>"
        f"<td>{pct(r['max_drawdown'])}</td>"
        f"<td>{money(r['end_$'])}</td>"
        f"<td>{int(r.get('rebalances', 0))}</td>"
        f"<td>{_pct_days(r['pct_days_cash'])}</td>"
        f"<td>{_pct_days(r['pct_days_1x'])}</td>"
        f"<td>{_pct_days(r['pct_days_2x'])}</td>"
        f"<td>{_pct_days(r['pct_days_3x'])}</td></tr>"
    )


def main() -> int:
    html = INDEX_HTML.read_text(encoding="utf-8")
    site = json.loads(SPX_SITE.read_text(encoding="utf-8"))
    comp = pd.read_csv(ROOT / "output" / "spx_guarded" / "spx_guarded_comparison.csv")
    default_name = site["default_backtest"]["strategy"]
    full_rows = "\n".join(
        row_full_sample(r, bold=(r["strategy"] == default_name)) for _, r in comp.iterrows()
    )
    html = replace_tbody(html, "<h2>Full-Sample Strategy Comparison</h2>", full_rows)

    tiered = pd.read_csv(TIERED_CSV)
    tiered = tiered[tiered["strategy"].str.contains("Guarded A10/B20", na=False)]
    legacy_rows = "\n".join(row_tiered(r) for _, r in tiered.iterrows())
    html = replace_tbody(html, "<h2>Legacy Guard SMA Sensitivity</h2>", legacy_rows)

    mom = pd.read_csv(MOMENTUM_CSV)
    mom_main = mom[mom["group"] == "Momentum trigger"].sort_values("cagr", ascending=False)
    mom_rows = "\n".join(row_momentum(r) for _, r in mom_main.iterrows())
    html = replace_tbody(html, "<h2>Daily Momentum Trigger Backtests</h2>", mom_rows)

    lh = pd.read_csv(LONG_HOLD_CSV)
    lh_main = lh[lh["group"] == "Long-hold momentum"].sort_values("cagr", ascending=False)
    lh_rows = "\n".join(row_momentum(r) for _, r in lh_main.iterrows())
    html = replace_tbody(html, "<h2>Long-Hold Momentum Backtests</h2>", lh_rows)

    # KPI cards
    bt = site["default_backtest"]
    orig = site.get("original_guarded") or {}
    mc = site["monte_carlo"]
    html = re.sub(
        r'(<div class="metric-card"><span class="small">Default CAGR</span><strong id="kpiDefaultCagr">)[^<]*(</strong></div>)',
        rf"\g<1>{bt['cagr_pct']}\g<2>",
        html,
        count=1,
    )
    html = re.sub(
        r'(<div class="metric-card"><span class="small">Default max DD</span><strong id="kpiDefaultMaxDd">)[^<]*(</strong></div>)',
        rf"\g<1>{bt['max_drawdown_pct']}\g<2>",
        html,
        count=1,
    )
    html = re.sub(
        r'(<div class="metric-card"><span class="small">Default Sharpe</span><strong id="kpiDefaultSharpe">)[^<]*(</strong></div>)',
        rf"\g<1>{bt['sharpe_fmt']}\g<2>",
        html,
        count=1,
    )
    html = re.sub(
        r'(<div class="metric-card"><span class="small">Annual volatility</span><strong id="kpiDefaultVol">)[^<]*(</strong></div>)',
        rf"\g<1>{bt['ann_volatility_pct']}\g<2>",
        html,
        count=1,
    )
    html = re.sub(
        r'(<div class="metric-card"><span class="small">Calmar ratio</span><strong id="kpiDefaultCalmar">)[^<]*(</strong></div>)',
        rf"\g<1>{bt.get('calmar_fmt', '-')}\g<2>",
        html,
        count=1,
    )
    html = re.sub(
        r'(<div class="metric-card"><span class="small">Default end value</span><strong id="kpiDefaultEnd">)[^<]*(</strong></div>)',
        rf"\g<1>{bt['end_value_fmt']}\g<2>",
        html,
        count=1,
    )
    html = re.sub(
        r'(<div class="metric-card"><span class="small">Median CAGR</span><strong id="mcMedianCagr">)[^<]*(</strong></div>)',
        rf"\g<1>{mc['median_cagr_pct']}\g<2>",
        html,
        count=1,
    )
    html = re.sub(
        r'(<div class="metric-card"><span class="small">Median max DD</span><strong id="mcMedianMaxDd">)[^<]*(</strong></div>)',
        rf"\g<1>{mc['median_max_drawdown_pct']}\g<2>",
        html,
        count=1,
    )
    html = re.sub(
        r'(<tr><td>Probability max drawdown is worse than -35%</td><td id="mcProbDd35">)[^<]*(</td></tr>)',
        rf"\g<1>{mc['prob_max_dd_worse_35pct_fmt']}\g<2>",
        html,
        count=1,
    )
    html = re.sub(
        r'(<tr><td>Probability max drawdown is worse than -40%</td><td id="mcProbDd40">)[^<]*(</td></tr>)',
        rf"\g<1>{mc['prob_max_dd_worse_40pct_fmt']}\g<2>",
        html,
        count=1,
    )
    html = re.sub(
        r'(<tr><td>Probability max drawdown is worse than -50%</td><td id="mcProbDd50">)[^<]*(</td></tr>)',
        rf"\g<1>{mc['prob_max_dd_worse_50pct_fmt']}\g<2>",
        html,
        count=1,
    )
    html = re.sub(
        r'(<tr><td>Probability ending below starting capital</td><td id="mcProbBelowStart">)[^<]*(</td></tr>)',
        rf"\g<1>{mc['prob_end_below_start_fmt']}\g<2>",
        html,
        count=1,
    )

    if orig:
        cagr_dir = "rose" if bt["cagr"] >= orig["cagr"] else "fell"
        # max_drawdown is negative; less negative = shallower (better)
        dd_dir = "narrowed" if bt["max_drawdown"] >= orig["max_drawdown"] else "deepened"
        callout = (
            "Versus the original strict A10/B20 version, "
            f"CAGR {cagr_dir} from {pct(orig['cagr'])} to {bt['cagr_pct']}, while max drawdown "
            f"{dd_dir} from {pct(orig['max_drawdown'])} to {bt['max_drawdown_pct']}. "
            "2x/3x P&amp;L uses listed same-calendar US ETP daily returns when history exists; the deep "
            "drawdowns come from 3x exposure in the synthetic pre-inception bear markets (dot-com, GFC)."
        )
        html = re.sub(
            r"<p id=\"backtestCallout\" class=\"callout\">[\s\S]*?</p>",
            f"<p id=\"backtestCallout\" class=\"callout\">\n        {callout}\n      </p>",
            html,
            count=1,
        )

    if MC_SUMMARY.exists():
        mc_df = pd.read_csv(MC_SUMMARY)
        mc_rows = ""
        for _, r in mc_df.iterrows():
            bold = "Lead 0.75 A5/B25" in r["strategy"]
            b, be = ("<strong>", "</strong>") if bold else ("", "")
            mc_rows += (
                f"            <tr><td>{b}{r['strategy']}{be}</td>"
                f"<td>{b}{pct(r['median_cagr'])}{be}</td>"
                f"<td>{pct(r['p10_cagr'])} / {pct(r['p90_cagr'])}</td>"
                f"<td>{b}{pct(r['median_max_drawdown'])}{be}</td>"
                f"<td>{pct(r['p10_max_drawdown'])} / {pct(r['p90_max_drawdown'])}</td>"
                f"<td>{float(r['median_sharpe']):.3f}</td>"
                f"<td>{b}{money(r['median_end_$'])}{be}</td>"
                f"<td>{pct(r['prob_max_dd_worse_40pct'])}</td></tr>\n"
            )
        html = replace_tbody(html, "<h2>Monte Carlo Comparison</h2>", mc_rows.rstrip())

    overview_note = (
        "These results use the project backtest engine with "
        "<strong>listed 2x/3x ETP daily returns</strong> (SPYL/XS2D/3USL) when available, "
        "synthetic daily-reset fill before ETP inception, $100 starting capital, "
        "$10 fixed annual inflows, and 1.0% rebalance cost on leverage changes."
    )
    html = re.sub(
        r"These results use the project backtest engine over[\s\S]*?2x/3x exposure can start when price is within 0\.75% below SMA20\.",
        overview_note,
        html,
        count=1,
    )

    def cagr_for(name: str, df: pd.DataFrame) -> str:
        row = df[df["strategy"] == name]
        if row.empty:
            return ""
        return pct(float(row.iloc[0]["cagr"]))

    sma3_cagr = cagr_for("SMA20 3x/cash", comp)
    guarded_cagr = cagr_for("Guarded A10/B20 SMA20", comp)
    if sma3_cagr:
        html = re.sub(
            r'(<div class="bar-row"><span>SMA20 3x/cash reference</span>[\s\S]*?<strong>)[^<]+(</strong></div>)',
            rf"\g<1>{sma3_cagr}\g<2>",
            html,
            count=1,
        )
    if guarded_cagr:
        html = re.sub(
            r'(<div class="bar-row"><span>Guarded A10/B20 reference</span>[\s\S]*?<strong>)[^<]+(</strong></div>)',
            rf"\g<1>{guarded_cagr}\g<2>",
            html,
            count=1,
        )

    ref_rows = comp[comp["strategy"].isin(["SMA20 3x/cash", "Guarded A10/B20 SMA20"])]
    if len(ref_rows) == 2:
        ref_html = "\n".join(
            "              " + row_momentum(r).strip() for _, r in ref_rows.iterrows()
        )
        html = replace_tbody(
            html,
            "<p class=\"small\">These rules were built specifically to remain in 2x/3x longer",
            ref_html,
        )

    bt_row = site["default_backtest"]
    diag = (
        f"            <tr><td>Cash days</td><td>{bt_row['pct_days_cash']:.2f}%</td>"
        f"<td>1x days</td><td>{bt_row['pct_days_1x']:.2f}%</td></tr>\n"
        f"            <tr><td>2x days</td><td>{bt_row['pct_days_2x']:.2f}%</td>"
        f"<td>3x days</td><td>{bt_row['pct_days_3x']:.2f}%</td></tr>\n"
        f"            <tr><td>2x entries</td><td>{bt_row['tier2_entries']}</td>"
        f"<td>3x entries</td><td>{bt_row['tier3_entries']}</td></tr>\n"
        f"            <tr><td>Lead-only days</td><td>{bt_row['lead_only_days']}</td>"
        f"<td>Rebalances</td><td>{bt_row['rebalances']}</td></tr>\n"
        f"            <tr><td>Total trading costs</td><td>${bt_row['trading_costs_total']:,.0f}</td>"
        f"<td>Funding (in ETP)</td><td>embedded in ETP returns</td></tr>"
    )
    html = replace_tbody(html, "<h2>Default Strategy Diagnostics</h2>", diag.rstrip())

    INDEX_HTML.write_text(html, encoding="utf-8")
    print(f"Updated {INDEX_HTML.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
