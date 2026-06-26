"""Generate guarded asset HTML/JS pages from gold_guarded templates."""

from __future__ import annotations

import json
import re
from pathlib import Path

from core.guarded_asset_registry import ASSETS, GuardedAssetSpec

ROOT = Path(__file__).resolve().parent
GOLD_HTML = ROOT / "gold_guarded.html"
GOLD_JS = ROOT / "gold_guarded.js"


STRATEGIES_NAV = '<nav class="site-nav" aria-label="Strategies"></nav>'


def build_html(spec: GuardedAssetSpec) -> str:
    html = GOLD_HTML.read_text(encoding="utf-8")
    nav_pattern = re.compile(
        r'<nav class="site-nav" aria-label="Strategies">.*?</nav>',
        re.DOTALL,
    )
    html = nav_pattern.sub(STRATEGIES_NAV, html, count=1)

    replacements = [
        ("Strategy — Gold Guarded (max 1x)", f"Strategy — {spec.title_short} Guarded (max 1x)"),
        (
            "Guarded A5/B25 SMA20 Lead Signal (Gold, max 1x)",
            f"Guarded A5/B25 SMA20 Lead Signal ({spec.title_short}, max 1x)",
        ),
        (
            "Guarded <strong>A5/B25/X40/Y15 SMA20 Lead</strong> on <code>GC=F</code> (COMEX gold continuous futures). "
            "Recovery tiers still arm at -5% / -25%, but <strong>max leverage is capped at 1x</strong> on this tab "
            "(no 2x/3x exposure). Price history is a rolled futures series, not a spot ETF.",
            f"Guarded <strong>A5/B25/X40/Y15 SMA20 Lead</strong> on <code>{spec.yahoo_ticker}</code> ({spec.asset_label}). "
            "Recovery tiers still arm at -5% / -25%, but <strong>max leverage is capped at 1x</strong> on this tab "
            "(no 2x/3x exposure).",
        ),
        (
            "hold <strong>1x</strong> gold exposure only when the GC=F close is above the 20-day SMA",
            spec.hold_exposure_line,
        ),
        ("if gold is down", spec.drawdown_line),
        ("from its GC=F closing high-water mark", f"from its {spec.price_name} closing high-water mark"),
        ("after gold rises", spec.recovery_line),
        ("delayed gold quote", f"delayed {spec.price_name} quote"),
        ("Optional GC=F live", spec.manual_price_hint),
        ("manual gold level", f"manual {spec.price_name.lower()} level"),
        ("Gold (GC=F) Close vs 20-Day SMA", f"{spec.price_name} Close vs 20-Day SMA"),
        ('aria-label="GC=F close and 20-day SMA chart"', spec.chart_aria_price),
        (
            'aria-label="Gold buy and hold versus default strategy equity chart"',
            spec.chart_aria_equity,
        ),
        ("GC=F close", f"{spec.yahoo_ticker} close"),
        ("Gold return % (orange)", f"{spec.index_label} return % (orange)"),
        (
            "2x trigger (A)</th><td>-5% drawdown from GC=F high-water close",
            f"2x trigger (A)</th><td>-5% drawdown from {spec.price_name} high-water close",
        ),
        (
            "3x trigger (B)</th><td>-25% drawdown from GC=F high-water close",
            f"3x trigger (B)</th><td>-25% drawdown from {spec.price_name} high-water close",
        ),
        ("Gold vs Default Strategy Equity", spec.equity_compare_label),
        ("historical GC=F daily closes", f"historical {spec.yahoo_ticker} daily closes"),
        ("Gold buy-and-hold", f"{spec.index_label} buy-and-hold"),
        ("gold (GC=F) and T-bill", f"{spec.yahoo_ticker} and T-bill"),
        ("gold_guarded.js?v=20260522gold", f"{spec.slug}_guarded.js?v=20260523{spec.slug}"),
    ]
    for old, new in replacements:
        if old not in html:
            raise SystemExit(f"{spec.slug} HTML: missing pattern: {old!r}")
        html = html.replace(old, new)

    html = html.replace(
        "<li><strong>2x recovery tier (capped at 1x on site):</strong>",
        "<li><strong>2x recovery tier (capped at 1x on site):</strong>",
    )
    return html


def build_js(spec: GuardedAssetSpec) -> str:
    js = GOLD_JS.read_text(encoding="utf-8")
    signal_file = f"latest_{spec.slug}_signal.json"

    worker_refresh = """        setStatus(`${reason === "manual" ? "Manual refresh" : "Auto-refresh"}: fetching daily Gold (GC=F) data...`);
        const { text: csv } = await fetchTextWithDiagnostics(WORKER_DAILY_URL, "Daily Gold data");

        const rows = parseCsv(csv);
        if (rows.length < 260) throw new Error("Not enough daily data. Need at least ~260 rows.");
        const lastClose = rows[rows.length - 1]?.close;
        if (Number.isFinite(lastClose) && lastClose > 5000) {
          throw new Error("Live feed looks like SPX, not gold (GC=F). Using static gold_daily.csv instead.");
        }
        latestRows = rows;
        latestRowsSource = "live";
        const eodResult = computeSignal(rows);

        setStatus(`${reason === "manual" ? "Manual refresh" : "Auto-refresh"}: fetching live gold quote...`);
        let livePriceInfo = null;
        let quoteWarning = "";
        try {
          livePriceInfo = await getLivePrice({ allowManualOverride });
        } catch (quoteErr) {
          console.warn(quoteErr);
          quoteWarning = quoteErr.message || String(quoteErr);
        }

        const liveRows = livePriceInfo?.price == null ? rows : appendIntradayRow(rows, livePriceInfo.price);
        const liveResult = computeSignal(liveRows);
        if (livePriceInfo?.price == null) {
          liveResult.explanation = quoteWarning
            ? `Live quote unavailable; showing last completed close as placeholder. ${quoteWarning}`
            : "No intraday price provided; showing last completed close as placeholder.";
        }

        render(eodResult, liveResult);
        renderChart();
        renderSignalPnlChart();
        renderBacktestEquityChart();
        renderTopDrawdownsTable();
        updateRangeNudgeStates();
        const quoteStatus = livePriceInfo?.price == null
          ? `Live quote failed; using last completed close. ${quoteWarning}`
          : `Live quote loaded from ${livePriceInfo.source}.`;
        lastSuccessfulWorkerRefreshAt = new Date();
        setStatus(`Loaded ${rows.length} daily rows. Last completed close: ${eodResult.latest.date}. ${quoteStatus}`, livePriceInfo?.price == null);"""

    static_refresh = f"""        setStatus(`${{reason === "manual" ? "Manual refresh" : "Auto-refresh"}}: reloading static ${{ASSET_LABEL}} data...`);
        const {{ text: csv }} = await fetchTextWithDiagnostics(STATIC_DAILY_URL, "Daily ${{ASSET_LABEL}} CSV");
        const rows = parseCsv(csv);
        if (rows.length < 260) throw new Error("Not enough daily data. Need at least ~260 rows.");
        latestRows = rows;
        latestRowsSource = "static";
        const eodResult = computeSignal(rows);
        let livePriceInfo = null;
        let quoteWarning = "";
        try {{
          livePriceInfo = await getLivePrice({{ allowManualOverride }});
        }} catch (quoteErr) {{
          console.warn(quoteErr);
          quoteWarning = quoteErr.message || String(quoteErr);
        }}
        const liveRows = livePriceInfo?.price == null ? rows : appendIntradayRow(rows, livePriceInfo.price);
        const liveResult = computeSignal(liveRows);
        if (livePriceInfo?.price == null) {{
          liveResult.explanation = "Showing last completed close from static daily CSV. Use manual price + Refresh for intraday override.";
        }} else {{
          liveResult.explanation = `Live intraday quote applied (${{livePriceInfo.source}}).`;
        }}
        render(eodResult, liveResult);
        renderChart();
        renderSignalPnlChart();
        renderBacktestEquityChart();
        renderTopDrawdownsTable();
        updateRangeNudgeStates();
        setStatus(`Loaded ${{rows.length}} static daily rows through ${{eodResult.latest.date}}.${{quoteWarning ? " " + quoteWarning : ""}}`, !!quoteWarning);"""

    if worker_refresh not in js:
        raise SystemExit(f"{spec.slug} JS: worker refresh block not found")
    js = js.replace(worker_refresh, static_refresh)

    replacements = [
        (
            'const WORKER_DAILY_URL = "https://spx-quote-proxy.rkarim88.workers.dev/?mode=daily&symbol=gold";',
            "const USE_WORKER_LIVE = false;",
        ),
        (
            'const WORKER_QUOTE_URL = "https://spx-quote-proxy.rkarim88.workers.dev/?mode=quote&symbol=gold";',
            f'const WORKER_QUOTE_URL = "https://spx-quote-proxy.rkarim88.workers.dev/?mode=quote&symbol={spec.slug}";\n  const ASSET_LABEL = {json_escape(spec.price_name)};',
        ),
        ('const STATIC_DAILY_URL = "gold_daily.csv";', f'const STATIC_DAILY_URL = "{spec.slug}_daily.csv";'),
        (
            'const STATIC_SIGNAL_URL = "latest_gold_signal.json";',
            f'const STATIC_SIGNAL_URL = "{signal_file}";',
        ),
        (
            'const STATIC_SITE_DATA_URL = "gold_guarded_site_data.json";',
            f'const STATIC_SITE_DATA_URL = "{spec.slug}_guarded_site_data.json";',
        ),
        ("latest_gold_signal.json", signal_file),
        ("Enter a manual gold (GC=F) level", f"Enter a manual {spec.price_name} ({spec.yahoo_ticker}) level"),
        ('GC=F', spec.yahoo_ticker),
        ("Gold (GC=F)", spec.asset_label),
        ("Gold (GC=F) data", f"{spec.price_name} data"),
        ("daily Gold (GC=F) data", f"daily {spec.price_name} data"),
        ("Daily Gold data", f"Daily {spec.price_name} data"),
        ("live gold quote", f"live {spec.price_name} quote"),
        ("Intraday gold quote", f"Intraday {spec.price_name} quote"),
        ("gold_daily.csv", f"{spec.slug}_daily.csv"),
        ("not gold (GC=F)", f"not {spec.yahoo_ticker}"),
        ("Live feed looks like SPX, not gold", "Live feed rejected"),
        ("Enter a manual NDX level", f"Enter a manual {spec.price_name} level"),
        ("Gold return %", f"{spec.index_label} return %"),
        # Chart meta labels (gold_guarded.js master uses "vs Gold ..." / "vs Gold buy & hold ...").
        (
            "Strategy ${fmtSignedPct(windowReturn)} vs Gold ${fmtSignedPct(benchmarkReturn)}",
            f"Strategy ${{fmtSignedPct(windowReturn)}} vs {spec.title_short} ${{fmtSignedPct(benchmarkReturn)}}",
        ),
        (
            "vs Gold buy &amp; hold ${fmtSignedPct(last.spxReturn)}",
            f"vs {spec.title_short} buy &amp; hold ${{fmtSignedPct(last.spxReturn)}}",
        ),
    ]
    for old, new in replacements:
        js = js.replace(old, new)

    return js


def json_escape(s: str) -> str:
    return json.dumps(s)


def main() -> int:
    for spec in ASSETS:
        html_path = ROOT / f"{spec.slug}_guarded.html"
        js_path = ROOT / f"{spec.slug}_guarded.js"
        html_path.write_text(build_html(spec), encoding="utf-8")
        js_path.write_text(build_js(spec), encoding="utf-8")
        print(f"Wrote {html_path.name} ({len(html_path.read_text())} bytes)")
        print(f"Wrote {js_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
