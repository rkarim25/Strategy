"""Backtest pure news-score leverage strategies over the last five years.

The historical news score is built from free GDELT DOC API article samples.
It intentionally avoids fabricated headlines: if GDELT cannot provide enough
dated articles, the script writes diagnostic metadata instead of pretending a
five-year signal exists.
"""

from __future__ import annotations

import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from io import BytesIO, TextIOWrapper
from pathlib import Path
from typing import Any
import csv

import numpy as np
import pandas as pd

from data_manager import load_backtest_data
from engine import INITIAL_CAPITAL, TRADING_COST_FROM_MID_PCT, PortfolioEngine
from metrics import comprehensive_stats
from update_static_market_data import BEARISH_TERMS, BULLISH_TERMS, score_news_text

OUTPUT_DIR = Path("output") / "news_score_strategy"
HISTORICAL_SCORES_CSV = OUTPUT_DIR / "historical_news_scores.csv"
RESULTS_CSV = OUTPUT_DIR / "news_score_strategy_results.csv"
EQUITY_CSV = OUTPUT_DIR / "news_score_strategy_equity.csv"
METADATA_JSON = OUTPUT_DIR / "metadata.json"
SAMPLE_HEADLINES_JSON = OUTPUT_DIR / "sample_headlines.json"
GDELT_CACHE_JSONL = OUTPUT_DIR / "gdelt_weekly_cache.jsonl"
GDELT_GKG_CACHE_JSONL = OUTPUT_DIR / "gdelt_gkg_weekly_cache.jsonl"

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_QUERY = (
    '"S&P 500" OR "stock market" OR "Wall Street" OR "Federal Reserve" '
    'OR inflation OR recession'
)
YEARS = 5
WEEK_DAYS = 7
MAX_RECORDS_PER_WINDOW = 50
MIN_USABLE_WINDOWS = 180
ANNUAL_INFLOW_USD = 10.0
MARKET_FILTER_TERMS = (
    "ECON_STOCKMARKET",
    "STOCK MARKET",
    "WALL STREET",
    "S&P",
    "SP500",
    "FEDERAL_RESERVE",
    "FEDERAL RESERVE",
    "CENTRALBANK",
    "INTEREST_RATES",
    "INFLATION",
    "RECESSION",
)


def clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_json(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(clean_json(payload), indent=2) + "\n", encoding="utf-8")


def gdelt_datetime(dt: datetime) -> str:
    return dt.strftime("%Y%m%d%H%M%S")


def fetch_json(url: str, timeout: int = 12) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "news-score-backtest/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def gdelt_articles(start: datetime, end: datetime) -> tuple[list[dict[str, Any]], str | None]:
    params = {
        "query": GDELT_QUERY,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": str(MAX_RECORDS_PER_WINDOW),
        "sort": "hybridrel",
        "startdatetime": gdelt_datetime(start),
        "enddatetime": gdelt_datetime(end),
    }
    url = GDELT_DOC_URL + "?" + urllib.parse.urlencode(params)
    try:
        payload = fetch_json(url)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return [], str(exc)
    articles = payload.get("articles", [])
    if not isinstance(articles, list):
        return [], "GDELT response did not contain an article list"
    return [article for article in articles if isinstance(article, dict)], None


def load_gdelt_cache() -> dict[str, dict[str, Any]]:
    if not GDELT_CACHE_JSONL.exists():
        return {}
    cache: dict[str, dict[str, Any]] = {}
    for line in GDELT_CACHE_JSONL.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = str(row.get("key", ""))
        if key:
            cache[key] = row
    return cache


def append_gdelt_cache(row: dict[str, Any]) -> None:
    with GDELT_CACHE_JSONL.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(clean_json(row), separators=(",", ":")) + "\n")


def load_jsonl_cache(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    cache: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = str(row.get("key", ""))
        if key:
            cache[key] = row
    return cache


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(clean_json(row), separators=(",", ":")) + "\n")


def keyword_counts(scored_articles: list[dict[str, Any]], tone: str) -> str:
    counts: Counter[str] = Counter()
    for article in scored_articles:
        if article["tone"] == tone:
            counts.update(article["matched_terms"])
    return "; ".join(f"{term}:{count}" for term, count in counts.most_common(5))


def score_week(date: datetime, articles: list[dict[str, Any]]) -> dict[str, Any]:
    scored: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for article in articles:
        title = re.sub(r"\s+", " ", str(article.get("title", ""))).strip()
        if not title:
            continue
        normalized = re.sub(r"[^a-z0-9 ]+", "", title.lower())
        if normalized in seen_titles:
            continue
        seen_titles.add(normalized)
        raw_score, tone, matched_terms = score_news_text(title, "")
        if matched_terms or abs(raw_score) > 0:
            scored.append(
                {
                    "title": title,
                    "url": article.get("url"),
                    "source": article.get("domain") or article.get("sourceCommonName"),
                    "seen_date": article.get("seendate"),
                    "raw_score": float(raw_score),
                    "tone": tone,
                    "matched_terms": matched_terms,
                }
            )

    raw_total = sum(float(article["raw_score"]) for article in scored)
    normalizer = max(3.0, math.sqrt(max(len(scored), 1)) * 2.8)
    score = int(round(max(1.0, min(10.0, 5.5 + raw_total / normalizer * 2.5))))
    top_positive = [a["title"] for a in sorted(scored, key=lambda a: a["raw_score"], reverse=True) if a["raw_score"] > 0][:3]
    top_negative = [a["title"] for a in sorted(scored, key=lambda a: a["raw_score"]) if a["raw_score"] < 0][:3]
    return {
        "date": date.date().isoformat(),
        "score": score,
        "article_count": len(articles),
        "scored_article_count": len(scored),
        "raw_total": raw_total,
        "avg_raw_score": raw_total / len(scored) if scored else 0.0,
        "positive_terms": keyword_counts(scored, "bullish"),
        "negative_terms": keyword_counts(scored, "bearish"),
        "top_positive_headlines": " | ".join(top_positive),
        "top_negative_headlines": " | ".join(top_negative),
        "_sample_articles": sorted(scored, key=lambda a: abs(float(a["raw_score"])), reverse=True)[:5],
    }


def gkg_snapshot_url(dt: datetime) -> str:
    return f"http://data.gdeltproject.org/gdeltv2/{dt.strftime('%Y%m%d%H%M%S')}.gkg.csv.zip"


def parse_tone(value: str) -> float:
    try:
        return float(value.split(",", 1)[0])
    except (AttributeError, ValueError):
        return 0.0


def market_relevant(row: list[str]) -> bool:
    text = " ".join(row[:18]).upper()
    return any(term in text for term in MARKET_FILTER_TERMS)


def fetch_gkg_snapshot(dt: datetime) -> tuple[list[dict[str, Any]], str | None]:
    url = gkg_snapshot_url(dt)
    try:
        raw = urllib.request.urlopen(url, timeout=30).read()
        archive = zipfile.ZipFile(BytesIO(raw))
        name = archive.namelist()[0]
        handle = TextIOWrapper(archive.open(name), encoding="utf-8", errors="replace", newline="")
        records: list[dict[str, Any]] = []
        for row in csv.reader(handle, delimiter="\t"):
            if len(row) < 16 or not market_relevant(row):
                continue
            title_proxy = " ".join([row[4], row[7], row[8], row[13], row[14]])
            keyword_raw, tone_label, matched_terms = score_news_text(title_proxy, "")
            gdelt_tone = parse_tone(row[15])
            composite = float(keyword_raw) + gdelt_tone * 0.25
            records.append(
                {
                    "date": row[1],
                    "source": row[3],
                    "url": row[4],
                    "themes": row[7],
                    "v2themes": row[8],
                    "tone": gdelt_tone,
                    "keyword_raw": float(keyword_raw),
                    "composite_raw": composite,
                    "tone_label": tone_label if abs(keyword_raw) >= 1 else ("bullish" if gdelt_tone > 1 else "bearish" if gdelt_tone < -1 else "neutral"),
                    "matched_terms": matched_terms,
                }
            )
        return records, None
    except (urllib.error.URLError, TimeoutError, zipfile.BadZipFile, IndexError, csv.Error) as exc:
        return [], str(exc)


def theme_counts(records: list[dict[str, Any]], *, positive: bool) -> str:
    counts: Counter[str] = Counter()
    for record in records:
        tone = float(record.get("tone", 0.0))
        composite = float(record.get("composite_raw", 0.0))
        if positive and max(tone, composite) <= 0:
            continue
        if not positive and min(tone, composite) >= 0:
            continue
        themes = str(record.get("themes", "")).split(";") + [
            item.split(",", 1)[0] for item in str(record.get("v2themes", "")).split(";")
        ]
        counts.update(theme for theme in themes if theme and any(key in theme for key in ("ECON", "EPU", "WB_442", "STOCK", "INFLATION", "RECESSION")))
    return "; ".join(f"{theme}:{count}" for theme, count in counts.most_common(6))


def score_gkg_snapshot(score_date: datetime, records: list[dict[str, Any]]) -> dict[str, Any]:
    raw_values = [float(record["composite_raw"]) for record in records]
    avg_raw = float(np.mean(raw_values)) if raw_values else 0.0
    avg_tone = float(np.mean([float(record["tone"]) for record in records])) if records else 0.0
    score = int(round(max(1.0, min(10.0, 5.5 + avg_raw * 0.85))))
    positive = sorted(records, key=lambda r: float(r["composite_raw"]), reverse=True)[:5]
    negative = sorted(records, key=lambda r: float(r["composite_raw"]))[:5]
    return {
        "date": score_date.date().isoformat(),
        "score": score,
        "article_count": len(records),
        "scored_article_count": len(records),
        "raw_total": float(sum(raw_values)),
        "avg_raw_score": avg_raw,
        "avg_gdelt_tone": avg_tone,
        "positive_terms": theme_counts(records, positive=True),
        "negative_terms": theme_counts(records, positive=False),
        "top_positive_headlines": " | ".join(str(record.get("url", "")) for record in positive[:3]),
        "top_negative_headlines": " | ".join(str(record.get("url", "")) for record in negative[:3]),
        "_sample_articles": [
            {
                "score_date": score_date.date().isoformat(),
                "source": record.get("source"),
                "url": record.get("url"),
                "tone": record.get("tone"),
                "composite_raw": record.get("composite_raw"),
                "themes": record.get("themes"),
                "v2themes": record.get("v2themes"),
                "matched_terms": record.get("matched_terms"),
            }
            for record in sorted(records, key=lambda r: abs(float(r["composite_raw"])), reverse=True)[:5]
        ],
    }


def fetch_historical_gkg_scores(start: datetime, end: datetime) -> tuple[pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    cache = load_jsonl_cache(GDELT_GKG_CACHE_JSONL)
    window_start = start
    window_number = 0
    windows_requested = max(1, math.ceil((end - start).days / WEEK_DAYS))
    while window_start < end:
        window_end = min(window_start + timedelta(days=WEEK_DAYS), end)
        window_number += 1
        # Use a fixed midday UTC snapshot per week to keep free static-file downloads bounded.
        snapshot_dt = window_start.replace(hour=12, minute=0, second=0, microsecond=0)
        key = snapshot_dt.strftime("%Y%m%d%H%M%S")
        if key in cache:
            records = cache[key].get("records", [])
            error = cache[key].get("error")
            if not isinstance(records, list):
                records = []
        else:
            records, error = fetch_gkg_snapshot(snapshot_dt)
            append_jsonl(
                GDELT_GKG_CACHE_JSONL,
                {
                    "key": key,
                    "snapshot": snapshot_dt.isoformat(),
                    "error": error,
                    "records": records,
                },
            )
            print(
                f"GDELT GKG snapshot {window_number}/{windows_requested}: "
                f"{snapshot_dt.date()} 12:00 UTC | {len(records)} market records",
                flush=True,
            )
        if error:
            errors.append(
                {
                    "snapshot": snapshot_dt.isoformat(),
                    "error": str(error),
                }
            )
        row = score_gkg_snapshot(window_end, records)
        samples.extend(row.pop("_sample_articles"))
        rows.append(row)
        window_start = window_end
        if key not in cache:
            time.sleep(0.02)
    scores = pd.DataFrame(rows)
    metadata = {
        "source": "GDELT 2.1 GKG static 15-minute files sampled weekly at 12:00 UTC",
        "filter_terms": MARKET_FILTER_TERMS,
        "window_days": WEEK_DAYS,
        "errors": errors[:20],
        "error_count": len(errors),
        "windows_requested": len(rows),
        "cache_path": str(GDELT_GKG_CACHE_JSONL),
    }
    return scores, samples[:250], metadata


def fetch_historical_news_scores(start: datetime, end: datetime) -> tuple[pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    cache = load_gdelt_cache()
    windows_requested = max(1, math.ceil((end - start).days / WEEK_DAYS))
    window_start = start
    window_number = 0
    while window_start < end:
        window_end = min(window_start + timedelta(days=WEEK_DAYS), end)
        window_number += 1
        key = f"{window_start.date().isoformat()}_{window_end.date().isoformat()}"
        if key in cache:
            articles = cache[key].get("articles", [])
            error = cache[key].get("error")
            if not isinstance(articles, list):
                articles = []
        else:
            articles, error = gdelt_articles(window_start, window_end)
            append_gdelt_cache(
                {
                    "key": key,
                    "start": window_start.date().isoformat(),
                    "end": window_end.date().isoformat(),
                    "error": error,
                    "articles": articles,
                }
            )
            print(
                f"GDELT window {window_number}/{windows_requested}: "
                f"{window_start.date()} -> {window_end.date()} | {len(articles)} articles",
                flush=True,
            )
        if error:
            errors.append(
                {
                    "start": window_start.date().isoformat(),
                    "end": window_end.date().isoformat(),
                    "error": error,
                }
            )
        row = score_week(window_end, articles)
        samples.extend(
            {
                "score_date": row["date"],
                **article,
            }
            for article in row.pop("_sample_articles")
        )
        rows.append(row)
        window_start = window_end
        if key not in cache:
            time.sleep(0.03)

    scores = pd.DataFrame(rows)
    metadata = {
        "source": "GDELT 2.1 DOC API ArtList weekly samples",
        "query": GDELT_QUERY,
        "window_days": WEEK_DAYS,
        "max_records_per_window": MAX_RECORDS_PER_WINDOW,
        "errors": errors[:20],
        "error_count": len(errors),
        "windows_requested": len(rows),
        "cache_path": str(GDELT_CACHE_JSONL),
    }
    return scores, samples[:250], metadata


def load_or_fetch_scores(start: datetime, end: datetime) -> tuple[pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    if HISTORICAL_SCORES_CSV.exists() and SAMPLE_HEADLINES_JSON.exists():
        scores = pd.read_csv(HISTORICAL_SCORES_CSV)
        samples = json.loads(SAMPLE_HEADLINES_JSON.read_text(encoding="utf-8"))
        return scores, samples, {"source": "existing cached output", "cache_reused": True}
    return fetch_historical_gkg_scores(start, end)


def load_last_five_year_prices() -> pd.DataFrame:
    prices = load_backtest_data(years=YEARS + 1)
    prices = prices.sort_index()
    end = prices.index[-1]
    start = end - pd.DateOffset(years=YEARS)
    prices = prices.loc[prices.index >= start].copy()
    if len(prices) < 1000:
        raise ValueError(f"Insufficient market data for a five-year test: {len(prices)} rows")
    return prices


def make_engine() -> PortfolioEngine:
    return PortfolioEngine(
        initial_capital=INITIAL_CAPITAL,
        annual_inflow_pct=0.0,
        annual_inflow_abs=ANNUAL_INFLOW_USD,
        max_drawdown_limit=None,
        hard_drawdown_floor=False,
        trading_cost_pct=TRADING_COST_FROM_MID_PCT,
    )


def map_aggressive(score: float) -> float:
    if score <= 3:
        return 0.0
    if score <= 5:
        return 1.0
    if score <= 7:
        return 2.0
    return 3.0


def map_conservative(score: float) -> float:
    if score <= 4:
        return 0.0
    if score <= 6:
        return 1.0
    if score <= 7:
        return 2.0
    return 3.0


def map_binary(score: float) -> float:
    return 3.0 if score >= 7 else 0.0


def daily_news_scores(scores: pd.DataFrame, trading_index: pd.DatetimeIndex) -> pd.Series:
    weekly = scores.copy()
    weekly["date"] = pd.to_datetime(weekly["date"])
    weekly = weekly.sort_values("date").set_index("date")
    scored = weekly["score"].astype(float)
    aligned = scored.reindex(scored.index.union(trading_index)).sort_index().ffill().reindex(trading_index)
    return aligned


def exposure_mix(leverage: pd.Series) -> dict[str, float]:
    return {
        "pct_days_cash": float((leverage <= 0).mean() * 100.0),
        "pct_days_1x": float((leverage == 1.0).mean() * 100.0),
        "pct_days_2x": float((leverage == 2.0).mean() * 100.0),
        "pct_days_3x": float((leverage == 3.0).mean() * 100.0),
    }


def evaluate_strategy(
    prices: pd.DataFrame,
    benchmark_equity: pd.Series | None,
    name: str,
    detail: str,
    leverage: pd.Series | float,
) -> tuple[dict[str, Any], pd.Series, pd.Series]:
    result = make_engine().run(prices, leverage, name=name)
    stats = comprehensive_stats(
        result.equity,
        result.daily_returns,
        benchmark_equity=benchmark_equity,
        trading_costs_total=result.trading_costs_total,
        turnover_notional=result.turnover_notional,
    )
    lev = result.leverage
    row = {
        "strategy": name,
        "detail": detail,
        "cagr": stats["cagr"],
        "ann_volatility": stats["volatility"],
        "sharpe": stats["sharpe"],
        "sortino": stats["sortino"],
        "calmar": stats["calmar"],
        "max_drawdown": stats["max_drawdown"],
        "ending_value": stats["final_value"],
        "trades": result.rebalance_count,
        "trading_costs_total": result.trading_costs_total,
        "funding_costs_total": result.funding_costs_total,
        "turnover_notional": result.turnover_notional,
        "avg_leverage": float(lev.mean()),
        **exposure_mix(lev),
    }
    return row, result.equity, lev


def build_strategy_leverage(scores: pd.Series) -> dict[str, tuple[str, pd.Series]]:
    score_delta = scores.diff().fillna(0.0)
    smooth_5 = scores.rolling(5, min_periods=1).mean()
    smooth_10 = scores.rolling(10, min_periods=1).mean()
    rising = pd.Series(0.0, index=scores.index)
    rising.loc[(scores >= 8) & (score_delta > 0)] = 3.0
    rising.loc[(scores >= 7) & (scores < 8) & (score_delta > 0)] = 2.0
    rising.loc[(scores >= 6) & ~(score_delta > 0)] = 1.0
    return {
        "news aggressive tiers": (
            "Score <=3 cash, 4-5 1x, 6-7 2x, >=8 3x",
            scores.map(map_aggressive),
        ),
        "news conservative tiers": (
            "Score <=4 cash, 5-6 1x, 7 2x, >=8 3x",
            scores.map(map_conservative),
        ),
        "news high-conviction 3x/cash": (
            "3x only when score >=7; otherwise cash",
            scores.map(map_binary),
        ),
        "news rising-score tiers": (
            "2x/3x only when score is >=7 and rising; 1x when bullish but not rising",
            rising,
        ),
        "news 5-day smoothed tiers": (
            "Aggressive thresholds applied to 5-trading-day average score",
            smooth_5.map(map_aggressive),
        ),
        "news 10-day smoothed tiers": (
            "Conservative thresholds applied to 10-trading-day average score",
            smooth_10.map(map_conservative),
        ),
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading last five years of market data...", flush=True)
    prices = load_last_five_year_prices()
    print(
        f"Market data loaded: {prices.index[0].date()} -> {prices.index[-1].date()} "
        f"({len(prices)} trading days)",
        flush=True,
    )
    news_start = prices.index[0].to_pydatetime().replace(tzinfo=timezone.utc) - timedelta(days=WEEK_DAYS)
    news_end = prices.index[-1].to_pydatetime().replace(tzinfo=timezone.utc) + timedelta(days=1)
    print("Fetching/scoring historical GDELT GKG news snapshots...", flush=True)
    scores, samples, score_metadata = load_or_fetch_scores(news_start, news_end)
    scores.to_csv(HISTORICAL_SCORES_CSV, index=False)
    write_json(SAMPLE_HEADLINES_JSON, samples)

    usable_scores = scores[(scores["article_count"] > 0) & (scores["scored_article_count"] > 0)].copy()
    if len(usable_scores) < MIN_USABLE_WINDOWS:
        metadata = {
            "status": "insufficient_historical_news_data",
            "reason": (
                f"Only {len(usable_scores)} weekly windows had scored GDELT headlines; "
                f"{MIN_USABLE_WINDOWS} were required for a credible five-year backtest."
            ),
            "market_start": prices.index[0].date().isoformat(),
            "market_end": prices.index[-1].date().isoformat(),
            "score_metadata": score_metadata,
        }
        write_json(METADATA_JSON, metadata)
        print(metadata["reason"])
        return 2

    signal = daily_news_scores(usable_scores, prices.index)
    prices = prices.loc[signal.dropna().index].copy()
    signal = signal.reindex(prices.index).ffill()
    benchmark_row, benchmark_equity, benchmark_lev = evaluate_strategy(
        prices,
        None,
        "buy and hold 1x",
        "Always 1x SPX exposure",
        1.0,
    )

    rows = [benchmark_row]
    equity_curves = pd.DataFrame({"date": prices.index, "buy and hold 1x": benchmark_equity.values})
    leverage_curves = {"buy and hold 1x": benchmark_lev}
    for name, (detail, leverage) in build_strategy_leverage(signal).items():
        row, equity, applied_lev = evaluate_strategy(prices, benchmark_equity, name, detail, leverage)
        row["cagr_delta_pp_vs_buy_hold"] = (row["cagr"] - benchmark_row["cagr"]) * 100.0
        row["ending_value_delta_vs_buy_hold"] = row["ending_value"] - benchmark_row["ending_value"]
        rows.append(row)
        equity_curves[name] = equity.values
        leverage_curves[name] = applied_lev

    results = pd.DataFrame(rows)
    results["cagr_delta_pp_vs_buy_hold"] = results.get("cagr_delta_pp_vs_buy_hold", 0.0).fillna(0.0)
    results["ending_value_delta_vs_buy_hold"] = results.get("ending_value_delta_vs_buy_hold", 0.0).fillna(0.0)
    results = results.sort_values(["ending_value", "sharpe"], ascending=[False, False])
    results.to_csv(RESULTS_CSV, index=False)
    equity_curves.to_csv(EQUITY_CSV, index=False)

    best_news = results[results["strategy"] != "buy and hold 1x"].iloc[0]
    metadata = {
        "status": "success",
        "market_start": prices.index[0].date().isoformat(),
        "market_end": prices.index[-1].date().isoformat(),
        "trading_days": len(prices),
        "assumptions": {
            "initial_capital": INITIAL_CAPITAL,
            "annual_inflow_usd": ANNUAL_INFLOW_USD,
            "trading_cost_pct": TRADING_COST_FROM_MID_PCT,
            "cash_return": "13-week T-Bill rate from yfinance via engine",
            "leverage_funding": "engine funding model: T-Bill + 0.6% spread on leverage above 1x",
            "lookahead": "weekly GDELT windows are timestamped at window end and forward-filled to later trading days",
        },
        "score_coverage": {
            "weekly_windows": int(len(scores)),
            "usable_weekly_windows": int(len(usable_scores)),
            "median_articles_per_window": float(usable_scores["article_count"].median()),
            "median_scored_articles_per_window": float(usable_scores["scored_article_count"].median()),
            "mean_score": float(usable_scores["score"].mean()),
        },
        "best_news_strategy": best_news.to_dict(),
        "buy_and_hold": benchmark_row,
        "outperformed_buy_hold": bool(best_news["ending_value"] > benchmark_row["ending_value"]),
        "score_metadata": score_metadata,
        "limitations": [
            "GDELT article samples are not a point-in-time paid market news archive and can miss paywalled/vendor headlines.",
            "The keyword score is transparent but crude; it does not understand sarcasm, article context, or duplicate story clusters perfectly.",
            "Weekly sampling reduces API load but can dilute daily news timing.",
        ],
    }
    write_json(METADATA_JSON, metadata)

    print(
        f"Historical GDELT score windows: {len(usable_scores)}/{len(scores)} usable; "
        f"{prices.index[0].date()} -> {prices.index[-1].date()}"
    )
    print(results[["strategy", "cagr", "sharpe", "max_drawdown", "ending_value", "trades"]].to_string(index=False))
    print(
        f"Best news-only strategy: {best_news['strategy']} ending ${best_news['ending_value']:.2f} "
        f"vs buy-and-hold ${benchmark_row['ending_value']:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
