"""Fetch full-history daily OHLCV for the Charts page from Yahoo and write price_<id>.json each.
Config-driven registry: add a row to ASSETS (id, label, asset class, Yahoo ticker) to add an asset.
Output feeds KLineChart: parallel arrays dates / timestamp(ms) / open/high/low/close/volume.
Tickers are the live-quote symbols too (the quote-proxy worker fetches any Yahoo ticker)."""
import json, urllib.request, datetime as dt

# id, label, asset class, Yahoo ticker
ASSETS = [
    ("spx",     "S&P 500",          "Indices",     "^GSPC"),
    ("ndx",     "Nasdaq 100",       "Indices",     "^NDX"),
    ("ixic",    "Nasdaq Composite", "Indices",     "^IXIC"),
    ("ftse",    "FTSE 100",         "Indices",     "^FTSE"),
    ("dax",     "DAX",              "Indices",     "^GDAXI"),
    ("gold",    "Gold (front)",     "Commodities", "GC=F"),
    ("oil",     "WTI Crude (front)","Commodities", "CL=F"),
    ("btc",     "Bitcoin",          "Crypto",      "BTC-USD"),
    ("eth",     "Ethereum",         "Crypto",      "ETH-USD"),
    ("eurusd",  "EUR / USD",        "FX",          "EURUSD=X"),
    ("gbpusd",  "GBP / USD",        "FX",          "GBPUSD=X"),
]

EPOCH = dt.datetime(1970, 1, 1)
def ymd(t):  # handles pre-1970 (negative) timestamps on Windows
    return (EPOCH + dt.timedelta(seconds=int(t))).strftime("%Y-%m-%d")


def fetch(sym):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.request.quote(sym) + "?interval=1d&range=100y")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(req, timeout=60))
    r = d["chart"]["result"][0]
    ts = r["timestamp"]
    q = r["indicators"]["quote"][0]
    o, h, l, c, v = q["open"], q["high"], q["low"], q["close"], q.get("volume") or [None] * len(ts)
    dates, T, O, H, L, C, V = [], [], [], [], [], [], []
    for i, t in enumerate(ts):
        if None in (o[i], h[i], l[i], c[i]):
            continue
        if not (c[i] > 0 and h[i] >= l[i]):
            continue
        dates.append(ymd(t)); T.append(int(t) * 1000)
        O.append(round(o[i], 4)); H.append(round(h[i], 4)); L.append(round(l[i], 4)); C.append(round(c[i], 4))
        V.append(int(v[i]) if v[i] else 0)
    return dates, T, O, H, L, C, V


reg = []
for aid, label, klass, sym in ASSETS:
    out = f"price_{aid}.json"
    try:
        dates, T, O, H, L, C, V = fetch(sym)
    except Exception as e:
        print(f"!! {aid} ({sym}) FAILED: {e}")
        continue
    payload = {"id": aid, "ticker": sym, "asset_label": label, "klass": klass,
               "dates": dates, "timestamp": T, "open": O, "high": H, "low": L, "close": C, "volume": V}
    with open(out, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    reg.append({"id": aid, "label": label, "klass": klass, "ticker": sym, "url": out, "rows": len(dates),
                "from": dates[0] if dates else None, "to": dates[-1] if dates else None})
    print(f"{out}: {label} [{klass}] ({sym})  {len(dates)} rows  {dates[0]}..{dates[-1]}  last {C[-1]}")

with open("price_assets.json", "w") as f:
    json.dump([{k: r[k] for k in ("id", "label", "klass", "ticker", "url")} for r in reg], f, indent=0)
print(f"\nprice_assets.json: {len(reg)} assets")
