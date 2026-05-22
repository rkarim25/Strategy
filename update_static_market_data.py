#!/usr/bin/env python3
"""Refresh static SPX data for the GitHub Pages dashboard."""

from __future__ import annotations

import csv
import html
import json
import math
import os
import re
import smtplib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree


WORKER_BASE = "https://spx-quote-proxy.rkarim88.workers.dev/"
WORKER_DAILY_URL = f"{WORKER_BASE}?mode=daily"
WORKER_QUOTE_URL = f"{WORKER_BASE}?mode=quote"
WORKER_DAILY_NDX_URL = f"{WORKER_BASE}?mode=daily&symbol=ndx"
WORKER_QUOTE_NDX_URL = f"{WORKER_BASE}?mode=quote&symbol=ndx"
WORKER_DAILY_GOLD_URL = f"{WORKER_BASE}?mode=daily&symbol=gold"
WORKER_QUOTE_GOLD_URL = f"{WORKER_BASE}?mode=quote&symbol=gold"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC"
YAHOO_NDX_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5ENDX"
YAHOO_GOLD_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC%3DF"
YAHOO_FTSE250_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EFTMC"
YAHOO_DAX_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGDAXI"
YAHOO_EM_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/EEM"
YAHOO_WORLD_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/SWDA.L"
ROOT = Path(__file__).resolve().parent
DAILY_CSV = ROOT / "spx_daily.csv"
LATEST_SIGNAL_JSON = ROOT / "latest_signal.json"
NDX_DAILY_CSV = ROOT / "ndx_daily.csv"
LATEST_NDX_SIGNAL_JSON = ROOT / "latest_ndx_signal.json"
GOLD_DAILY_CSV = ROOT / "gold_daily.csv"
LATEST_GOLD_SIGNAL_JSON = ROOT / "latest_gold_signal.json"
FTSE250_DAILY_CSV = ROOT / "ftse250_daily.csv"
LATEST_FTSE250_SIGNAL_JSON = ROOT / "latest_ftse250_signal.json"
EM_DAILY_CSV = ROOT / "msci_em_daily.csv"
LATEST_EM_SIGNAL_JSON = ROOT / "latest_msci_em_signal.json"
DAX_DAILY_CSV = ROOT / "dax_daily.csv"
LATEST_DAX_SIGNAL_JSON = ROOT / "latest_dax_signal.json"
WORLD_DAILY_CSV = ROOT / "msci_world_daily.csv"
LATEST_WORLD_SIGNAL_JSON = ROOT / "latest_msci_world_signal.json"
NEWS_SCORE_JSON = ROOT / "news_score.json"
TRADING_DAYS = 252
SITE_URL = "https://rkarim25.github.io/Strategy/"
DEFAULT_ALERT_EMAIL_TO = "rkarim88@gmail.com"
DEFAULT_GUARDED = {
    "triggerA": 0.05,
    "triggerB": 0.25,
    "hold2": 0.40,
    "hold3": 0.15,
    "leadPct": 0.0075,
}
NEWS_WINDOW_DAYS = 7
NEWS_FEEDS = [
    {
        "name": "Yahoo Finance S&P 500",
        "url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US",
    },
    {
        "name": "MarketWatch MarketPulse",
        "url": "https://feeds.content.dowjones.io/public/rss/mw_marketpulse",
    },
    {
        "name": "CNBC Markets",
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    },
    {
        "name": "Google News market query",
        "url": "https://news.google.com/rss/search?q=%28S%26P%20500%20OR%20stock%20market%20OR%20Wall%20Street%29%20when%3A7d&hl=en-US&gl=US&ceid=US%3Aen",
    },
]
BULLISH_TERMS = {
    "rally": 2.0,
    "rallies": 2.0,
    "record high": 2.0,
    "all-time high": 2.0,
    "gain": 1.0,
    "gains": 1.0,
    "higher": 1.0,
    "rise": 1.0,
    "rises": 1.0,
    "surge": 1.5,
    "jumps": 1.3,
    "rebounds": 1.2,
    "rebound": 1.2,
    "optimism": 1.2,
    "soft landing": 1.6,
    "earnings beat": 1.6,
    "beats": 1.0,
    "rate cut": 1.5,
    "rate cuts": 1.5,
    "cooling inflation": 1.6,
    "inflation cools": 1.6,
    "jobs growth": 1.0,
    "strong jobs": 1.0,
    "ai": 0.6,
    "buyback": 0.8,
}
BEARISH_TERMS = {
    "selloff": 2.0,
    "sell-off": 2.0,
    "plunge": 2.0,
    "falls": 1.2,
    "fall": 1.2,
    "drops": 1.2,
    "drop": 1.2,
    "slumps": 1.5,
    "losses": 1.0,
    "lower": 1.0,
    "recession": 2.0,
    "stagflation": 2.0,
    "tariff": 1.4,
    "tariffs": 1.4,
    "trade war": 1.8,
    "war": 1.5,
    "geopolitical": 1.2,
    "inflation": 0.9,
    "hot inflation": 1.7,
    "rate hike": 1.7,
    "rate hikes": 1.7,
    "higher yields": 1.5,
    "yield spike": 1.5,
    "earnings miss": 1.6,
    "misses": 1.0,
    "warning": 1.0,
    "warns": 1.0,
    "dangerous": 1.2,
    "left behind": 1.0,
    "extremes": 0.8,
    "masking": 0.8,
    "default": 1.8,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch_url(url: str, *, accept: str = "*/*", timeout: int = 30) -> tuple[int, str, dict[str, str]]:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": "Strategy static data updater/1.0 (+https://rkarim25.github.io/Strategy/)",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
        return response.status, body, dict(response.headers.items())


def source_result(url: str, ok: bool, status: int | None = None, error: str | None = None) -> dict[str, object]:
    out: dict[str, object] = {"url": url, "ok": ok}
    if status is not None:
        out["status"] = status
    if error:
        out["error"] = error
    return out


def parse_daily_csv(text: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise ValueError("daily CSV is missing a header")

    field_map = {name.strip().lower(): name for name in reader.fieldnames}
    date_field = field_map.get("date")
    close_field = field_map.get("close")
    if not date_field or not close_field:
        raise ValueError("daily CSV must include Date and Close columns")

    for row in reader:
        date = (row.get(date_field) or "").strip()
        close_text = (row.get(close_field) or "").strip()
        try:
            close = float(close_text)
        except ValueError:
            continue
        if date and math.isfinite(close) and close > 0:
            rows.append({"date": date[:10], "close": close})

    rows.sort(key=lambda item: str(item["date"]))
    deduped: dict[str, dict[str, object]] = {str(item["date"]): item for item in rows}
    return [deduped[key] for key in sorted(deduped)]


def fetch_worker_daily(
    sources: dict[str, object],
    *,
    worker_daily_url: str = WORKER_DAILY_URL,
    source_key: str = "daily_worker",
) -> list[dict[str, object]]:
    try:
        status, text, _headers = fetch_url(worker_daily_url, accept="text/csv,application/json")
        rows = parse_daily_csv(text)
        if len(rows) < 260:
            raise ValueError(f"worker daily returned only {len(rows)} rows")
        sources[source_key] = source_result(worker_daily_url, True, status)
        return rows
    except Exception as exc:
        sources[source_key] = source_result(worker_daily_url, False, error=str(exc))
        raise


def fetch_yahoo_daily(
    sources: dict[str, object],
    *,
    yahoo_chart_url: str = YAHOO_CHART_URL,
    source_key: str = "daily_yahoo",
) -> list[dict[str, object]]:
    period1 = 0
    period2 = int(time.time()) + 86400
    params = urllib.parse.urlencode(
        {
            "period1": period1,
            "period2": period2,
            "interval": "1d",
            "events": "history",
            "includeAdjustedClose": "true",
        }
    )
    url = f"{yahoo_chart_url}?{params}"
    try:
        status, text, _headers = fetch_url(url, accept="application/json")
        payload = json.loads(text)
        result = payload["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        rows = []
        for stamp, close in zip(timestamps, closes):
            if close is None:
                continue
            close_value = float(close)
            if math.isfinite(close_value) and close_value > 0:
                date = datetime.fromtimestamp(int(stamp), timezone.utc).date().isoformat()
                rows.append({"date": date, "close": close_value})
        if len(rows) < 260:
            raise ValueError(f"Yahoo chart returned only {len(rows)} rows")
        sources[source_key] = source_result(url, True, status)
        return rows
    except Exception as exc:
        sources[source_key] = source_result(url, False, error=str(exc))
        raise


def fetch_daily_rows(
    sources: dict[str, object],
    *,
    worker_daily_url: str = WORKER_DAILY_URL,
    yahoo_chart_url: str = YAHOO_CHART_URL,
    worker_source_key: str = "daily_worker",
    yahoo_source_key: str = "daily_yahoo",
) -> list[dict[str, object]]:
    try:
        return fetch_worker_daily(
            sources,
            worker_daily_url=worker_daily_url,
            source_key=worker_source_key,
        )
    except Exception:
        return fetch_yahoo_daily(
            sources,
            yahoo_chart_url=yahoo_chart_url,
            source_key=yahoo_source_key,
        )


def parse_quote_payload(text: str) -> dict[str, object]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        rows = parse_daily_csv(text)
        if not rows:
            raise ValueError("quote response was neither JSON nor CSV")
        latest = rows[-1]
        return {
            "quote_price": latest["close"],
            "quote_timestamp": latest["date"],
            "quote_source": "worker CSV fallback",
        }

    price = payload.get("price", payload.get("close", payload.get("last", payload.get("value"))))
    price_value = float(price)
    if not math.isfinite(price_value) or price_value <= 0:
        raise ValueError("quote JSON did not contain a positive price/close/last/value")

    timestamp = (
        payload.get("timestamp")
        or payload.get("time")
        or payload.get("asOf")
        or payload.get("asof")
        or payload.get("date")
    )
    return {
        "quote_price": price_value,
        "quote_timestamp": timestamp,
        "quote_source": payload.get("source") or "worker quote endpoint",
    }


def fetch_quote(
    sources: dict[str, object],
    *,
    worker_quote_url: str = WORKER_QUOTE_URL,
    source_key: str = "quote_worker",
) -> dict[str, object] | None:
    try:
        status, text, _headers = fetch_url(worker_quote_url, accept="application/json,text/csv")
        quote = parse_quote_payload(text)
        sources[source_key] = source_result(worker_quote_url, True, status)
        return quote
    except Exception as exc:
        sources[source_key] = source_result(worker_quote_url, False, error=str(exc))
        return None


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_text(element: ElementTree.Element, name: str) -> str:
    for child in element:
        if local_name(child.tag) == name:
            return "".join(child.itertext()).strip()
    return ""


def parse_feed_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_headline(value: str) -> str:
    normalized = re.sub(r"\s+", " ", html.unescape(value)).strip().lower()
    normalized = re.sub(r"\s+-\s+[^-]{2,80}$", "", normalized)
    return re.sub(r"[^a-z0-9 ]+", "", normalized)


def keyword_hits(text: str, terms: dict[str, float]) -> tuple[float, list[str]]:
    lowered = text.lower()
    score = 0.0
    hits: list[str] = []
    for term, weight in terms.items():
        if re.search(rf"\b{re.escape(term)}\b", lowered):
            score += weight
            hits.append(term)
    return score, hits


def score_news_text(title: str, summary: str) -> tuple[float, str, list[str]]:
    text = f"{title}. {summary}"
    bullish, bullish_hits = keyword_hits(text, BULLISH_TERMS)
    bearish, bearish_hits = keyword_hits(text, BEARISH_TERMS)
    net = bullish - bearish
    if net >= 1.0:
        tone = "bullish"
    elif net <= -1.0:
        tone = "bearish"
    else:
        tone = "neutral"
    return net, tone, bullish_hits[:3] + bearish_hits[:3]


def article_source(item: ElementTree.Element, fallback: str) -> str:
    source = child_text(item, "source")
    if source:
        return html.unescape(source)
    creator = child_text(item, "creator")
    return html.unescape(creator) if creator else fallback


def parse_rss_articles(feed: dict[str, str], text: str, now: datetime) -> list[dict[str, object]]:
    root = ElementTree.fromstring(text)
    cutoff = now - timedelta(days=NEWS_WINDOW_DAYS)
    articles: list[dict[str, object]] = []
    for item in root.iter():
        if local_name(item.tag) not in {"item", "entry"}:
            continue
        title = html.unescape(child_text(item, "title"))
        url = child_text(item, "link")
        if not url:
            for child in item:
                if local_name(child.tag) == "link":
                    url = child.attrib.get("href", "")
                    break
        published = (
            parse_feed_datetime(child_text(item, "pubdate"))
            or parse_feed_datetime(child_text(item, "published"))
            or parse_feed_datetime(child_text(item, "updated"))
        )
        if not title or not url or published is None or published < cutoff or published > now:
            continue
        summary = html.unescape(child_text(item, "description") or child_text(item, "summary"))
        raw_score, tone, matched_terms = score_news_text(title, summary)
        articles.append(
            {
                "title": re.sub(r"\s+", " ", title).strip(),
                "source": article_source(item, feed["name"]),
                "url": url,
                "published": iso_utc(published),
                "tone": tone,
                "_raw_score": raw_score,
                "_matched_terms": matched_terms,
            }
        )
    return articles


def fetch_news_articles() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    now = utc_now()
    articles: list[dict[str, object]] = []
    sources: list[dict[str, object]] = []
    seen: set[str] = set()
    for feed in NEWS_FEEDS:
        url = feed["url"]
        try:
            status, text, _headers = fetch_url(url, accept="application/rss+xml,application/xml,text/xml", timeout=20)
            parsed = parse_rss_articles(feed, text, now)
            added = 0
            for article in parsed:
                key = normalize_headline(str(article["title"]))
                if not key or key in seen:
                    continue
                seen.add(key)
                articles.append(article)
                added += 1
            sources.append(source_result(url, True, status) | {"name": feed["name"], "articles": added})
        except Exception as exc:
            sources.append(source_result(url, False, error=str(exc)) | {"name": feed["name"]})
    articles.sort(key=lambda item: str(item["published"]), reverse=True)
    return articles, sources


def news_label(score: int | None) -> str:
    if score is None:
        return "Unavailable"
    if score <= 3:
        return "Bearish"
    if score <= 6:
        return "Neutral"
    return "Bullish"


def concise_headline_list(articles: list[dict[str, object]], tone: str, limit: int = 2) -> list[str]:
    return [str(item["title"]) for item in articles if item.get("tone") == tone][:limit]


def build_news_explanation(articles: list[dict[str, object]], score: int) -> str:
    bullish = concise_headline_list(articles, "bullish")
    bearish = concise_headline_list(articles, "bearish")
    parts = [f"{score}/10 is {news_label(score).lower()} from a 7-day headline keyword scan."]
    if bullish:
        parts.append("Bullish drivers: " + "; ".join(bullish) + ".")
    if bearish:
        parts.append("Bearish offsets: " + "; ".join(bearish) + ".")
    if not bullish and not bearish:
        parts.append("Most recent headlines were mixed or did not hit strong market sentiment keywords.")
    return " ".join(parts)


def build_unavailable_news_payload(error: str) -> dict[str, object]:
    generated_at_utc = iso_utc(utc_now())
    return {
        "generated_at_utc": generated_at_utc,
        "window_days": NEWS_WINDOW_DAYS,
        "score": None,
        "label": "Unavailable",
        "explanation": "Headline score is unavailable because RSS feeds could not be fetched during the latest refresh.",
        "articles": [],
        "data_source": {
            "feeds": NEWS_FEEDS,
            "successful_feeds": 0,
            "errors": [error],
        },
        "limitations": [
            "Headline-based keyword heuristic, not investment advice.",
            "Not part of the mechanical default signal unless explicitly added later.",
            "Free RSS feeds can be incomplete and delayed.",
        ],
    }


def write_news_score_json() -> None:
    try:
        articles, sources = fetch_news_articles()
        if not articles:
            raise ValueError("No dated market/S&P headlines were available from RSS feeds.")
        raw_total = sum(float(article.get("_raw_score", 0.0)) for article in articles)
        normalizer = max(3.0, math.sqrt(len(articles)) * 2.8)
        score = int(round(max(1, min(10, 5.5 + raw_total / normalizer * 2.5))))
        selected = sorted(
            articles,
            key=lambda article: (abs(float(article.get("_raw_score", 0.0))), str(article["published"])),
            reverse=True,
        )[:5]
        payload_articles = [
            {key: article[key] for key in ("title", "source", "url", "published", "tone")}
            for article in selected
        ]
        payload = {
            "generated_at_utc": iso_utc(utc_now()),
            "window_days": NEWS_WINDOW_DAYS,
            "score": score,
            "label": news_label(score),
            "explanation": build_news_explanation(selected, score),
            "articles": payload_articles,
            "data_source": {
                "feeds": sources,
                "headline_count": len(articles),
                "method": "RSS headlines from the last 7 days scored with weighted bullish/bearish keyword lists.",
            },
            "limitations": [
                "Headline-based keyword heuristic, not investment advice.",
                "Not part of the mechanical default signal unless explicitly added later.",
                "Free RSS feeds can be incomplete and delayed.",
            ],
        }
        NEWS_SCORE_JSON.write_text(json.dumps(clean_for_json(payload), indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {NEWS_SCORE_JSON.name} with {len(articles)} headlines; score {score}/10")
    except Exception as exc:
        if NEWS_SCORE_JSON.exists():
            print(f"News score refresh failed; keeping existing {NEWS_SCORE_JSON.name}: {exc}", file=sys.stderr)
            return
        NEWS_SCORE_JSON.write_text(
            json.dumps(build_unavailable_news_payload(str(exc)), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote unavailable {NEWS_SCORE_JSON.name}: {exc}", file=sys.stderr)


def sma(values: list[float], end_index: int, window: int) -> float:
    if end_index + 1 < window:
        return math.nan
    return sum(values[end_index - window + 1 : end_index + 1]) / window


def compute_signal(rows: list[dict[str, object]], *, max_leverage: float | None = None) -> dict[str, object]:
    params = DEFAULT_GUARDED

    def cap_lev(lev: int) -> int:
        if max_leverage is None or max_leverage <= 0:
            return lev
        return int(min(lev, max_leverage))
    closes = [float(row["close"]) for row in rows]
    high_water = closes[0]
    high_water_date = str(rows[0]["date"])
    regime = "base"
    entry_close: float | None = None
    entry_date: str | None = None
    base_entry_close: float | None = None
    base_entry_date: str | None = None
    previous_target_leverage = 0
    target_leverage = 0
    explanation = ""

    def update_active_entry_tracking(close: float, date: str) -> None:
        nonlocal base_entry_close, base_entry_date, previous_target_leverage
        if target_leverage == 1 and previous_target_leverage != 1:
            base_entry_close = close
            base_entry_date = date
        elif target_leverage == 0:
            base_entry_close = None
            base_entry_date = None
        previous_target_leverage = target_leverage

    for i, row in enumerate(rows):
        close = closes[i]
        date = str(row["date"])
        avg20 = sma(closes, i, 20)
        if close >= high_water:
            high_water = close
            high_water_date = date

        dd = close / high_water - 1
        above_sma = math.isfinite(avg20) and close > avg20
        recovery_ok = math.isfinite(avg20) and close >= avg20 * (1 - params["leadPct"])
        base_lev = 1 if above_sma else 0

        if regime == "tier3":
            if entry_close is not None and close / entry_close - 1 >= params["hold3"]:
                regime = "base"
                entry_close = None
                entry_date = None
            else:
                target_leverage = cap_lev(3 if recovery_ok else base_lev)
                explanation = (
                    "Recovery tier3 armed at 1x max (lead guard passed)."
                    if recovery_ok and max_leverage == 1
                    else "3x recovery tier is active and price is inside the 0.75% SMA20 lead guard."
                    if recovery_ok
                    else "3x tier is armed, but lead guard failed; using base cash/1x rule."
                )
                update_active_entry_tracking(close, date)
                continue

        if regime == "tier2":
            if dd <= -params["triggerB"] and recovery_ok:
                regime = "tier3"
                entry_close = close
                entry_date = date
                target_leverage = cap_lev(3)
                explanation = (
                    "Drawdown hit B=-25%; tier3 armed at 1x max."
                    if max_leverage == 1
                    else "Drawdown hit B=-25% and lead guard passed; upgraded to 3x."
                )
                update_active_entry_tracking(close, date)
                continue
            if entry_close is not None and close / entry_close - 1 >= params["hold2"]:
                regime = "base"
                entry_close = None
                entry_date = None
            else:
                target_leverage = cap_lev(2 if recovery_ok else base_lev)
                explanation = (
                    "Recovery tier2 armed at 1x max (lead guard passed)."
                    if recovery_ok and max_leverage == 1
                    else "2x recovery tier is active and price is inside the 0.75% SMA20 lead guard."
                    if recovery_ok
                    else "2x tier is armed, but lead guard failed; using base cash/1x rule."
                )
                update_active_entry_tracking(close, date)
                continue

        if dd <= -params["triggerB"] and recovery_ok:
            regime = "tier3"
            entry_close = close
            entry_date = date
            target_leverage = cap_lev(3)
            explanation = (
                "Drawdown at/through -25%; tier3 armed at 1x max."
                if max_leverage == 1
                else "Drawdown is at/through -25% and price is inside the 0.75% SMA20 lead guard; enter 3x."
            )
        elif dd <= -params["triggerA"] and recovery_ok:
            regime = "tier2"
            entry_close = close
            entry_date = date
            target_leverage = cap_lev(2)
            explanation = (
                "Drawdown at/through -5%; tier2 armed at 1x max."
                if max_leverage == 1
                else "Drawdown is at/through -5% and price is inside the 0.75% SMA20 lead guard; enter 2x."
            )
        else:
            target_leverage = cap_lev(base_lev)
            explanation = (
                "No recovery tier active; base rule says 1x because close is above SMA20."
                if above_sma
                else "No recovery tier active; base rule says cash because close is below SMA20."
            )
        update_active_entry_tracking(close, date)

    latest_index = len(rows) - 1
    latest = rows[latest_index]
    latest_close = float(latest["close"])
    latest_sma = sma(closes, latest_index, 20)
    latest_dd = latest_close / high_water - 1
    recovery_target = None
    if entry_close is not None:
        recovery_target = entry_close * (1 + (params["hold3"] if regime == "tier3" else params["hold2"]))

    active_entry_close = None
    active_entry_date = None
    if target_leverage > 0:
        if target_leverage >= 2:
            active_entry_close = entry_close
            active_entry_date = entry_date
        else:
            active_entry_close = base_entry_close
            active_entry_date = base_entry_date

    return {
        "latest": {"date": latest["date"], "close": latest_close},
        "latestSma": latest_sma,
        "highWater": high_water,
        "highWaterDate": high_water_date,
        "latestDd": latest_dd,
        "regime": regime,
        "entryClose": entry_close,
        "entryDate": entry_date,
        "recoveryTarget": recovery_target,
        "aboveSma": latest_close > latest_sma if math.isfinite(latest_sma) else False,
        "recoveryOk": latest_close >= latest_sma * (1 - params["leadPct"]) if math.isfinite(latest_sma) else False,
        "targetLeverage": target_leverage,
        "activeEntryClose": active_entry_close,
        "activeEntryDate": active_entry_date,
        "activeEntryLeverage": target_leverage if active_entry_close is not None else None,
        "activeEntryPnl": latest_close / active_entry_close - 1 if active_entry_close else None,
        "explanation": explanation,
    }


def append_quote_row(rows: list[dict[str, object]], quote: dict[str, object]) -> list[dict[str, object]]:
    stamp = quote.get("quote_timestamp") or iso_utc(utc_now())
    out = list(rows)
    out.append({"date": str(stamp), "close": float(quote["quote_price"])})
    return out


def clean_for_json(value: object) -> object:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, dict):
        return {key: clean_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_for_json(item) for item in value]
    return value


def get_signal_target(payload: dict[str, object] | None) -> int | None:
    if not isinstance(payload, dict):
        return None

    alert_state = payload.get("trade_alert_state")
    if isinstance(alert_state, dict):
        target = alert_state.get("last_observed_target_leverage")
        if target is not None:
            try:
                return int(target)
            except (TypeError, ValueError):
                pass

    official_signal = payload.get("official_signal")
    if isinstance(official_signal, dict):
        target = official_signal.get("targetLeverage")
        if target is not None:
            try:
                return int(target)
            except (TypeError, ValueError):
                return None

    return None


def get_signal_asof(payload: dict[str, object] | None) -> str | None:
    if not isinstance(payload, dict):
        return None

    alert_state = payload.get("trade_alert_state")
    if isinstance(alert_state, dict):
        asof = alert_state.get("last_observed_asof")
        if asof:
            return str(asof)

    official_signal = payload.get("official_signal")
    if isinstance(official_signal, dict):
        latest = official_signal.get("latest")
        if isinstance(latest, dict) and latest.get("date"):
            return str(latest["date"])

    asof = payload.get("data_asof")
    return str(asof) if asof else None


def leverage_label(leverage: int | None) -> str:
    if leverage is None:
        return "unknown"
    if leverage == 0:
        return "cash"
    return f"{leverage}x"


def format_optional_number(value: object, *, pct: bool = False) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return "n/a"
    if pct:
        return f"{number:.2%}"
    return f"{number:,.2f}"


def format_signed_pct(value: object) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return "n/a"
    return f"{number:+.2%}"


def trade_action(old_leverage: int, new_leverage: int) -> str:
    if new_leverage == 0:
        return "SELL/REDUCE exposure and move the strategy allocation to cash/T-bills."
    if new_leverage > old_leverage:
        return f"BUY/ADD exposure, increasing the strategy allocation from {leverage_label(old_leverage)} to {leverage_label(new_leverage)}."
    if new_leverage < old_leverage:
        return f"SELL/REDUCE exposure, lowering the strategy allocation from {leverage_label(old_leverage)} to {leverage_label(new_leverage)}."
    return f"HOLD the current {leverage_label(new_leverage)} target exposure."


def build_trade_transition(
    previous_payload: dict[str, object] | None,
    official_signal: dict[str, object],
    generated_at_utc: str,
) -> dict[str, object] | None:
    previous_target = get_signal_target(previous_payload)
    current_target = int(official_signal["targetLeverage"])
    if previous_target is None or previous_target == current_target:
        return None

    latest = official_signal.get("latest") if isinstance(official_signal.get("latest"), dict) else {}
    transition_id = f"{get_signal_asof(previous_payload) or 'unknown'}:{previous_target}->{latest.get('date') or 'unknown'}:{current_target}"
    return {
        "id": transition_id,
        "detected_at_utc": generated_at_utc,
        "previous_asof": get_signal_asof(previous_payload),
        "current_asof": latest.get("date"),
        "old_target_leverage": previous_target,
        "new_target_leverage": current_target,
        "old_target_label": leverage_label(previous_target),
        "new_target_label": leverage_label(current_target),
    }


def build_alert_email_body(transition: dict[str, object], official_signal: dict[str, object]) -> str:
    latest = official_signal.get("latest") if isinstance(official_signal.get("latest"), dict) else {}
    old_leverage = int(transition["old_target_leverage"])
    new_leverage = int(transition["new_target_leverage"])
    close = latest.get("close")
    sma20 = official_signal.get("latestSma")
    close_vs_sma = None
    recovery_lead_level = None
    try:
        close_value = float(close)
        sma_value = float(sma20)
        if math.isfinite(close_value) and math.isfinite(sma_value) and sma_value > 0:
            close_vs_sma = close_value / sma_value - 1
            recovery_lead_level = sma_value * (1 - DEFAULT_GUARDED["leadPct"])
    except (TypeError, ValueError):
        pass

    lines = [
        "Strategy Trade Alert",
        "",
        f"Recommendation: {trade_action(old_leverage, new_leverage)}",
        f"Target leverage change: {transition['old_target_label']} -> {transition['new_target_label']}",
        f"Official signal as of: {latest.get('date', transition.get('current_asof', 'n/a'))}",
        "",
        "Signal details:",
        f"- SPX close: {format_optional_number(close)}",
        f"- SMA20: {format_optional_number(sma20)}",
        f"- Close vs SMA20: {format_signed_pct(close_vs_sma)}",
        f"- Drawdown from high: {format_optional_number(official_signal.get('latestDd'), pct=True)}",
        f"- Recovery lead level: {format_optional_number(recovery_lead_level)}",
        f"- Recovery target: {format_optional_number(official_signal.get('recoveryTarget'))}",
        f"- Regime: {official_signal.get('regime', 'n/a')}",
        f"- Above SMA20: {official_signal.get('aboveSma', 'n/a')}",
        f"- Recovery lead guard passed: {official_signal.get('recoveryOk', 'n/a')}",
        "",
        "Entry/P&L:",
        f"- Active entry date: {official_signal.get('activeEntryDate') or 'n/a'}",
        f"- Active entry level: {format_optional_number(official_signal.get('activeEntryClose'))}",
        f"- P&L from active entry: {format_optional_number(official_signal.get('activeEntryPnl'), pct=True)}",
        "",
        f"Rule reason: {official_signal.get('explanation', 'n/a')}",
        "",
        "Practical note: This is generated from the scheduled static refresh; verify execution level before trading.",
        f"Site: {SITE_URL}",
    ]
    return "\n".join(lines)


def smtp_config_from_env() -> dict[str, object]:
    return {
        "host": os.environ.get("SMTP_HOST", "").strip(),
        "port": int(os.environ.get("SMTP_PORT", "587") or "587"),
        "username": os.environ.get("SMTP_USERNAME", "").strip(),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "to": os.environ.get("ALERT_EMAIL_TO", DEFAULT_ALERT_EMAIL_TO).strip() or DEFAULT_ALERT_EMAIL_TO,
        "from": os.environ.get("ALERT_EMAIL_FROM", "").strip() or os.environ.get("SMTP_USERNAME", "").strip(),
    }


def send_trade_alert_email(transition: dict[str, object], official_signal: dict[str, object]) -> bool:
    config = smtp_config_from_env()
    missing = [key for key in ("host", "username", "password", "from") if not config.get(key)]
    if missing:
        print(
            "Trade alert detected, but email was skipped because SMTP configuration is incomplete "
            f"(missing: {', '.join(missing)})."
        )
        return False

    msg = EmailMessage()
    msg["Subject"] = (
        f"Strategy trade alert: {transition['old_target_label']} -> "
        f"{transition['new_target_label']} on {transition.get('current_asof', 'unknown date')}"
    )
    msg["From"] = str(config["from"])
    msg["To"] = str(config["to"])
    msg.set_content(build_alert_email_body(transition, official_signal))

    with smtplib.SMTP(str(config["host"]), int(config["port"]), timeout=30) as smtp:
        smtp.starttls()
        smtp.login(str(config["username"]), str(config["password"]))
        smtp.send_message(msg)

    print(f"Sent trade alert email to {config['to']}: {transition['old_target_label']} -> {transition['new_target_label']}")
    return True


def write_daily_csv(rows: list[dict[str, object]], path: Path = DAILY_CSV) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Date", "Close"])
        for row in rows:
            writer.writerow([row["date"], f"{float(row['close']):.12g}"])


def write_signal_json(
    rows: list[dict[str, object]],
    quote: dict[str, object] | None,
    sources: dict[str, object],
    previous_payload: dict[str, object] | None,
    *,
    output_path: Path = LATEST_SIGNAL_JSON,
    strategy_name: str = "Guarded A5/B25 SMA20 Lead Signal",
    send_trade_alerts: bool = True,
    max_leverage: float | None = None,
) -> None:
    generated_at_utc = iso_utc(utc_now())
    official_signal = compute_signal(rows, max_leverage=max_leverage)
    provisional_signal = (
        compute_signal(append_quote_row(rows, quote), max_leverage=max_leverage) if quote else None
    )
    transition = build_trade_transition(previous_payload, official_signal, generated_at_utc)
    email_sent = False
    email_error = None
    if transition and send_trade_alerts:
        try:
            email_sent = send_trade_alert_email(transition, official_signal)
        except Exception as exc:
            email_error = str(exc)
            print(f"Trade alert email failed: {exc}", file=sys.stderr)

    latest = official_signal.get("latest") if isinstance(official_signal.get("latest"), dict) else {}
    alert_state: dict[str, object] = {
        "last_observed_asof": latest.get("date"),
        "last_observed_target_leverage": official_signal["targetLeverage"],
        "last_observed_target_label": leverage_label(int(official_signal["targetLeverage"])),
        "last_checked_at_utc": generated_at_utc,
    }
    if transition:
        alert_state["last_transition"] = transition | {
            "email_sent": email_sent,
            "email_error": email_error,
        }
    elif isinstance(previous_payload, dict) and isinstance(previous_payload.get("trade_alert_state"), dict):
        previous_transition = previous_payload["trade_alert_state"].get("last_transition")
        if previous_transition:
            alert_state["last_transition"] = previous_transition

    strategy_params = dict(DEFAULT_GUARDED)
    if max_leverage is not None:
        strategy_params["maxLeverage"] = max_leverage

    payload = {
        "generated_at_utc": generated_at_utc,
        "data_asof": rows[-1]["date"],
        "daily_rows": len(rows),
        "quote_price": quote.get("quote_price") if quote else None,
        "quote_timestamp": quote.get("quote_timestamp") if quote else None,
        "quote_source": quote.get("quote_source") if quote else None,
        "sources": sources,
        "strategy": {
            "name": strategy_name,
            "parameters": strategy_params,
        },
        "official_signal": official_signal,
        "provisional_signal": provisional_signal,
        "trade_alert_state": alert_state,
    }
    output_path.write_text(json.dumps(clean_for_json(payload), indent=2) + "\n", encoding="utf-8")


def load_previous_signal_payload(path: Path = LATEST_SIGNAL_JSON) -> dict[str, object] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        print(f"Could not parse existing {path.name}; skipping trade-alert comparison: {exc}")
        return None


def yahoo_quote_from_rows(rows: list[dict[str, object]]) -> dict[str, object]:
    latest = rows[-1]
    return {
        "quote_price": latest["close"],
        "quote_timestamp": latest["date"],
        "quote_source": "Yahoo Finance chart endpoint",
    }


def refresh_yahoo_only(
    *,
    label: str,
    daily_csv: Path,
    signal_json: Path,
    yahoo_chart_url: str,
    strategy_name: str,
    max_leverage: float = 1.0,
) -> None:
    sources: dict[str, object] = {}
    rows = fetch_yahoo_daily(
        sources,
        yahoo_chart_url=yahoo_chart_url,
        source_key="daily_yahoo",
    )
    quote = yahoo_quote_from_rows(rows)
    write_daily_csv(rows, daily_csv)
    write_signal_json(
        rows,
        quote,
        sources,
        load_previous_signal_payload(signal_json),
        output_path=signal_json,
        strategy_name=strategy_name,
        send_trade_alerts=False,
        max_leverage=max_leverage,
    )
    print(f"[{label}] Wrote {daily_csv.name} with {len(rows)} rows through {rows[-1]['date']}")
    print(f"[{label}] Wrote {signal_json.name} with quote {quote['quote_price']}")


def refresh_gold_static_data() -> None:
    """Gold uses Yahoo GC=F; worker ?symbol=gold currently mirrors SPX and is not trusted."""
    sources: dict[str, object] = {}
    try:
        rows = fetch_yahoo_daily(
            sources,
            yahoo_chart_url=YAHOO_GOLD_CHART_URL,
            source_key="daily_yahoo_gold",
        )
    except Exception as exc:
        print(f"[Gold] Daily refresh failed; skipping signal JSON: {exc}", file=sys.stderr)
        return
    quote = fetch_quote(
        sources,
        worker_quote_url=WORKER_QUOTE_GOLD_URL,
        source_key="quote_worker_gold",
    )
    if quote and float(quote["quote_price"]) > 5000:
        sources["quote_worker_gold"] = source_result(
            WORKER_QUOTE_GOLD_URL,
            False,
            error="quote looked like SPX not gold; discarded",
        )
        quote = None
    write_daily_csv(rows, GOLD_DAILY_CSV)
    write_signal_json(
        rows,
        quote,
        sources,
        None,
        output_path=LATEST_GOLD_SIGNAL_JSON,
        strategy_name="Guarded A5/B25 SMA20 Lead (Gold, max 1x)",
        send_trade_alerts=False,
        max_leverage=1.0,
    )
    print(f"[Gold] Wrote {GOLD_DAILY_CSV.name} with {len(rows)} rows through {rows[-1]['date']}")
    if quote:
        print(f"[Gold] Wrote {LATEST_GOLD_SIGNAL_JSON.name} with quote {quote['quote_price']}")
    else:
        print(f"[Gold] Wrote {LATEST_GOLD_SIGNAL_JSON.name} without live quote")


def refresh_instrument(
    *,
    label: str,
    daily_csv: Path,
    signal_json: Path,
    worker_daily_url: str,
    worker_quote_url: str,
    yahoo_chart_url: str,
    strategy_name: str,
    send_trade_alerts: bool,
    max_leverage: float | None = None,
) -> None:
    sources: dict[str, object] = {}
    previous_payload = load_previous_signal_payload(signal_json) if send_trade_alerts else None
    rows = fetch_daily_rows(
        sources,
        worker_daily_url=worker_daily_url,
        yahoo_chart_url=yahoo_chart_url,
        worker_source_key="daily_worker",
        yahoo_source_key="daily_yahoo",
    )
    quote = fetch_quote(sources, worker_quote_url=worker_quote_url, source_key="quote_worker")
    write_daily_csv(rows, daily_csv)
    write_signal_json(
        rows,
        quote,
        sources,
        previous_payload,
        output_path=signal_json,
        strategy_name=strategy_name,
        send_trade_alerts=send_trade_alerts,
        max_leverage=max_leverage,
    )
    print(f"[{label}] Wrote {daily_csv.name} with {len(rows)} rows through {rows[-1]['date']}")
    if quote:
        print(
            f"[{label}] Wrote {signal_json.name} with quote {quote['quote_price']} "
            f"from {quote.get('quote_source')}"
        )
    else:
        print(f"[{label}] Wrote {signal_json.name} without live quote; quote endpoint unavailable")


def main() -> int:
    refresh_instrument(
        label="SPX",
        daily_csv=DAILY_CSV,
        signal_json=LATEST_SIGNAL_JSON,
        worker_daily_url=WORKER_DAILY_URL,
        worker_quote_url=WORKER_QUOTE_URL,
        yahoo_chart_url=YAHOO_CHART_URL,
        strategy_name="Guarded A5/B25 SMA20 Lead Signal",
        send_trade_alerts=True,
    )
    refresh_instrument(
        label="NDX",
        daily_csv=NDX_DAILY_CSV,
        signal_json=LATEST_NDX_SIGNAL_JSON,
        worker_daily_url=WORKER_DAILY_NDX_URL,
        worker_quote_url=WORKER_QUOTE_NDX_URL,
        yahoo_chart_url=YAHOO_NDX_CHART_URL,
        strategy_name="Guarded A5/B25 SMA20 Lead Signal (Nasdaq 100)",
        send_trade_alerts=False,
    )
    refresh_gold_static_data()
    for label, daily_csv, signal_json, yahoo_url, strategy_name in (
        (
            "FTSE250",
            FTSE250_DAILY_CSV,
            LATEST_FTSE250_SIGNAL_JSON,
            YAHOO_FTSE250_CHART_URL,
            "Guarded A5/B25 SMA20 Lead (FTSE 250, max 1x)",
        ),
        (
            "MSCI_EM",
            EM_DAILY_CSV,
            LATEST_EM_SIGNAL_JSON,
            YAHOO_EM_CHART_URL,
            "Guarded A5/B25 SMA20 Lead (MSCI EM, max 1x)",
        ),
        (
            "DAX",
            DAX_DAILY_CSV,
            LATEST_DAX_SIGNAL_JSON,
            YAHOO_DAX_CHART_URL,
            "Guarded A5/B25 SMA20 Lead (DAX, max 1x)",
        ),
        (
            "MSCI_WORLD",
            WORLD_DAILY_CSV,
            LATEST_WORLD_SIGNAL_JSON,
            YAHOO_WORLD_CHART_URL,
            "Guarded A5/B25 SMA20 Lead (MSCI World, max 1x)",
        ),
    ):
        try:
            refresh_yahoo_only(
                label=label,
                daily_csv=daily_csv,
                signal_json=signal_json,
                yahoo_chart_url=yahoo_url,
                strategy_name=strategy_name,
                max_leverage=1.0,
            )
        except Exception as exc:
            print(f"[{label}] refresh failed: {exc}", file=sys.stderr)
    write_news_score_json()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
        print(f"Static market data refresh failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
