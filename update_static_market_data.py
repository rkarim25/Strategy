#!/usr/bin/env python3
"""Refresh static SPX data for the GitHub Pages dashboard."""

from __future__ import annotations

import csv
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


WORKER_DAILY_URL = "https://spx-quote-proxy.rkarim88.workers.dev/?mode=daily"
WORKER_QUOTE_URL = "https://spx-quote-proxy.rkarim88.workers.dev/?mode=quote"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC"
ROOT = Path(__file__).resolve().parent
DAILY_CSV = ROOT / "spx_daily.csv"
LATEST_SIGNAL_JSON = ROOT / "latest_signal.json"
TRADING_DAYS = 252
DEFAULT_GUARDED = {
    "triggerA": 0.05,
    "triggerB": 0.25,
    "hold2": 0.40,
    "hold3": 0.15,
    "leadPct": 0.0075,
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


def fetch_worker_daily(sources: dict[str, object]) -> list[dict[str, object]]:
    try:
        status, text, _headers = fetch_url(WORKER_DAILY_URL, accept="text/csv,application/json")
        rows = parse_daily_csv(text)
        if len(rows) < 260:
            raise ValueError(f"worker daily returned only {len(rows)} rows")
        sources["daily_worker"] = source_result(WORKER_DAILY_URL, True, status)
        return rows
    except Exception as exc:
        sources["daily_worker"] = source_result(WORKER_DAILY_URL, False, error=str(exc))
        raise


def fetch_yahoo_daily(sources: dict[str, object]) -> list[dict[str, object]]:
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
    url = f"{YAHOO_CHART_URL}?{params}"
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
        sources["daily_yahoo"] = source_result(url, True, status)
        return rows
    except Exception as exc:
        sources["daily_yahoo"] = source_result(url, False, error=str(exc))
        raise


def fetch_daily_rows(sources: dict[str, object]) -> list[dict[str, object]]:
    try:
        return fetch_worker_daily(sources)
    except Exception:
        return fetch_yahoo_daily(sources)


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


def fetch_quote(sources: dict[str, object]) -> dict[str, object] | None:
    try:
        status, text, _headers = fetch_url(WORKER_QUOTE_URL, accept="application/json,text/csv")
        quote = parse_quote_payload(text)
        sources["quote_worker"] = source_result(WORKER_QUOTE_URL, True, status)
        return quote
    except Exception as exc:
        sources["quote_worker"] = source_result(WORKER_QUOTE_URL, False, error=str(exc))
        return None


def sma(values: list[float], end_index: int, window: int) -> float:
    if end_index + 1 < window:
        return math.nan
    return sum(values[end_index - window + 1 : end_index + 1]) / window


def compute_signal(rows: list[dict[str, object]]) -> dict[str, object]:
    params = DEFAULT_GUARDED
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
                target_leverage = 3 if recovery_ok else base_lev
                explanation = (
                    "3x recovery tier is active and price is inside the 0.75% SMA20 lead guard."
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
                target_leverage = 3
                explanation = "Drawdown hit B=-25% and lead guard passed; upgraded to 3x."
                update_active_entry_tracking(close, date)
                continue
            if entry_close is not None and close / entry_close - 1 >= params["hold2"]:
                regime = "base"
                entry_close = None
                entry_date = None
            else:
                target_leverage = 2 if recovery_ok else base_lev
                explanation = (
                    "2x recovery tier is active and price is inside the 0.75% SMA20 lead guard."
                    if recovery_ok
                    else "2x tier is armed, but lead guard failed; using base cash/1x rule."
                )
                update_active_entry_tracking(close, date)
                continue

        if dd <= -params["triggerB"] and recovery_ok:
            regime = "tier3"
            entry_close = close
            entry_date = date
            target_leverage = 3
            explanation = "Drawdown is at/through -25% and price is inside the 0.75% SMA20 lead guard; enter 3x."
        elif dd <= -params["triggerA"] and recovery_ok:
            regime = "tier2"
            entry_close = close
            entry_date = date
            target_leverage = 2
            explanation = "Drawdown is at/through -5% and price is inside the 0.75% SMA20 lead guard; enter 2x."
        else:
            target_leverage = base_lev
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


def write_daily_csv(rows: list[dict[str, object]]) -> None:
    with DAILY_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Date", "Close"])
        for row in rows:
            writer.writerow([row["date"], f"{float(row['close']):.12g}"])


def write_signal_json(rows: list[dict[str, object]], quote: dict[str, object] | None, sources: dict[str, object]) -> None:
    official_signal = compute_signal(rows)
    provisional_signal = compute_signal(append_quote_row(rows, quote)) if quote else None
    payload = {
        "generated_at_utc": iso_utc(utc_now()),
        "data_asof": rows[-1]["date"],
        "daily_rows": len(rows),
        "quote_price": quote.get("quote_price") if quote else None,
        "quote_timestamp": quote.get("quote_timestamp") if quote else None,
        "quote_source": quote.get("quote_source") if quote else None,
        "sources": sources,
        "strategy": {
            "name": "Guarded A5/B25 SMA20 Lead Signal",
            "parameters": DEFAULT_GUARDED,
        },
        "official_signal": official_signal,
        "provisional_signal": provisional_signal,
    }
    LATEST_SIGNAL_JSON.write_text(json.dumps(clean_for_json(payload), indent=2) + "\n", encoding="utf-8")


def main() -> int:
    sources: dict[str, object] = {}
    rows = fetch_daily_rows(sources)
    quote = fetch_quote(sources)
    write_daily_csv(rows)
    write_signal_json(rows, quote, sources)
    print(f"Wrote {DAILY_CSV.name} with {len(rows)} rows through {rows[-1]['date']}")
    if quote:
        print(f"Wrote {LATEST_SIGNAL_JSON.name} with quote {quote['quote_price']} from {quote.get('quote_source')}")
    else:
        print(f"Wrote {LATEST_SIGNAL_JSON.name} without live quote; quote endpoint unavailable")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
        print(f"Static market data refresh failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
