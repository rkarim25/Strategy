"""Registry for Guarded asset pages (1x max) on the Strategy site."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GuardedAssetSpec:
    slug: str
    title_short: str
    nav_label: str
    index_label: str
    yahoo_ticker: str
    yahoo_chart_path: str
    asset_label: str
    price_name: str
    instruments_title: str
    instruments_blurb: str
    hold_exposure_line: str
    drawdown_line: str
    recovery_line: str
    chart_aria_price: str
    chart_aria_equity: str
    equity_compare_label: str
    manual_price_hint: str
    etf_1x: str
    # Earliest trustworthy date for the backtest/series; None = use the default 30-year window.
    # MSCI World (SWDA.L) has unreliable Yahoo inception data before 2009-12-01 (a non-reverting
    # ~39% cliff on 2009-11-05 that the round-trip spike filter cannot catch); skip it here.
    history_start: str | None = None


ASSETS: list[GuardedAssetSpec] = [
    GuardedAssetSpec(
        slug="ftse250",
        title_short="FTSE 250",
        nav_label="Guarded A5/B25 (FTSE 250, max 1x)",
        index_label="FTSE 250",
        yahoo_ticker="^FTMC",
        yahoo_chart_path="%5EFTMC",
        asset_label="FTSE 250 (^FTMC)",
        price_name="FTSE 250",
        instruments_title="FTSE 250 UCITS / ETP Instruments",
        instruments_blurb=(
            "Reference list of FTSE 250 trackers for UK / II investors. "
            "Back-test and signal use <code>^FTMC</code> index; listed ETFs track the index with fees and tracking difference."
        ),
        hold_exposure_line=(
            "hold <strong>1x</strong> FTSE 250 exposure only when the index close is above the 20-day SMA"
        ),
        drawdown_line="if the FTSE 250 is down",
        recovery_line="after the FTSE 250 rises",
        chart_aria_price='aria-label="FTSE 250 close and 20-day SMA chart"',
        chart_aria_equity='aria-label="FTSE 250 buy and hold versus default strategy equity chart"',
        equity_compare_label="FTSE 250 vs Default Strategy Equity",
        manual_price_hint="Optional FTSE 250 level",
        etf_1x="MIDD / VMID",
    ),
    GuardedAssetSpec(
        slug="msci_em",
        title_short="MSCI EM",
        nav_label="Guarded A5/B25 (MSCI EM, max 1x)",
        index_label="MSCI Emerging Markets",
        yahoo_ticker="EEM",
        yahoo_chart_path="EEM",
        asset_label="MSCI EM (EEM)",
        price_name="MSCI EM (EEM)",
        instruments_title="Emerging Markets UCITS / ETF Instruments",
        instruments_blurb=(
            "Reference list of emerging-market equity ETFs for UK / II investors. "
            "Back-test and signal use <code>EEM</code> (US-listed proxy); II lines include <code>EIMI</code> / <code>VFEM</code>."
        ),
        hold_exposure_line=(
            "hold <strong>1x</strong> MSCI EM exposure only when the EEM close is above the 20-day SMA"
        ),
        drawdown_line="if MSCI EM (EEM) is down",
        recovery_line="after MSCI EM rises",
        chart_aria_price='aria-label="MSCI EM close and 20-day SMA chart"',
        chart_aria_equity='aria-label="MSCI EM buy and hold versus default strategy equity chart"',
        equity_compare_label="MSCI EM vs Default Strategy Equity",
        manual_price_hint="Optional EEM level",
        etf_1x="EIMI / VFEM",
    ),
    GuardedAssetSpec(
        slug="dax",
        title_short="DAX",
        nav_label="Guarded A5/B25 (DAX, max 1x)",
        index_label="DAX",
        yahoo_ticker="^GDAXI",
        yahoo_chart_path="%5EGDAXI",
        asset_label="DAX (^GDAXI)",
        price_name="DAX",
        instruments_title="DAX UCITS / ETF Instruments",
        instruments_blurb=(
            "Reference list of German DAX trackers for UK / II investors. "
            "Back-test and signal use <code>^GDAXI</code>; listed ETFs such as <code>EXS1</code> / <code>XDAX</code> track the index."
        ),
        hold_exposure_line=(
            "hold <strong>1x</strong> DAX exposure only when the index close is above the 20-day SMA"
        ),
        drawdown_line="if the DAX is down",
        recovery_line="after the DAX rises",
        chart_aria_price='aria-label="DAX close and 20-day SMA chart"',
        chart_aria_equity='aria-label="DAX buy and hold versus default strategy equity chart"',
        equity_compare_label="DAX vs Default Strategy Equity",
        manual_price_hint="Optional DAX level",
        etf_1x="EXS1 / XDAX",
    ),
    GuardedAssetSpec(
        slug="msci_world",
        title_short="MSCI World",
        nav_label="Guarded A5/B25 (MSCI World, max 1x)",
        index_label="MSCI World",
        yahoo_ticker="SWDA.L",
        yahoo_chart_path="SWDA.L",
        asset_label="MSCI World (SWDA.L / IWDA)",
        price_name="MSCI World",
        instruments_title="MSCI World UCITS / ETF Instruments",
        instruments_blurb=(
            "Reference list of global equity trackers for UK / II investors. "
            "Back-test and signal use <code>SWDA.L</code> (iShares MSCI World); sibling <code>IWDA</code> is widely used on II."
        ),
        hold_exposure_line=(
            "hold <strong>1x</strong> MSCI World exposure only when the fund close is above the 20-day SMA"
        ),
        drawdown_line="if MSCI World is down",
        recovery_line="after MSCI World rises",
        chart_aria_price='aria-label="MSCI World close and 20-day SMA chart"',
        chart_aria_equity='aria-label="MSCI World buy and hold versus default strategy equity chart"',
        equity_compare_label="MSCI World vs Default Strategy Equity",
        manual_price_hint="Optional MSCI World level",
        etf_1x="IWDA / SWDA",
        history_start="2009-12-01",
    ),
    GuardedAssetSpec(
        slug="lqq3",
        title_short="LQQ3 3x Nasdaq",
        nav_label="Guarded A5/B25 (LQQ3 3x, max 1x)",
        index_label="LQQ3 3x ETP",
        yahoo_ticker="LQQ3.L",
        yahoo_chart_path="LQQ3.L",
        asset_label="LQQ3.L (WisdomTree 3x Daily Leveraged Nasdaq 100, GBX)",
        price_name="LQQ3",
        instruments_title="Nasdaq 100 Leveraged ETP Instruments",
        instruments_blurb=(
            "WisdomTree 3x Daily Leveraged Nasdaq 100 on London (<code>LQQ3.L</code>, GBX). "
            "Same ISIN as 3QQQ (IE00BLRPRL42). Back-test uses adjusted close from listing (2012-12-13). "
            "Max 1x on this tab = cash vs fully in the 3x ETP, not economic 1x Nasdaq beta."
        ),
        hold_exposure_line=(
            "toggle between <strong>cash (T-bills)</strong> and <strong>fully invested in LQQ3</strong> "
            "(3x daily Nasdaq ETP) when Guarded signals permit re-entry above the 20-day SMA"
        ),
        drawdown_line="if LQQ3 is down",
        recovery_line="after LQQ3 rises",
        chart_aria_price='aria-label="LQQ3 close and 20-day SMA chart"',
        chart_aria_equity='aria-label="LQQ3 buy and hold versus default strategy equity chart"',
        equity_compare_label="LQQ3 vs Default Strategy Equity",
        manual_price_hint="Optional LQQ3 level (GBX)",
        etf_1x="EQQQ (1x) / LQQ (2x) / LQQ3 (3x)",
    ),
]


def by_slug(slug: str) -> GuardedAssetSpec:
    for spec in ASSETS:
        if spec.slug == slug:
            return spec
    raise KeyError(slug)
