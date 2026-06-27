"""Fetch full-history daily OHLC(V) for the Charts page from Yahoo and write price_<id>.json each.
Config-driven registry: add a row to ASSETS (id, label, asset class, Yahoo ticker, kind) to add an asset.
kind: 'price' (equities/commodities/crypto/FX) or 'yield' (UST rates — backtested with yield-as-PnL).
US 7Y has no Yahoo series, so it is synthesised by interpolating 5Y(^FVX) and 10Y(^TNX).
Output feeds KLineChart: parallel arrays dates / timestamp(ms) / open/high/low/close/volume."""
import json, urllib.request, datetime as dt

# id, label, asset class, Yahoo ticker, kind
ASSETS = [
    ("spx",     "S&P 500",          "Indices",     "^GSPC",    "price"),
    ("ndx",     "Nasdaq 100",       "Indices",     "^NDX",     "price"),
    ("ixic",    "Nasdaq Composite", "Indices",     "^IXIC",    "price"),
    ("ftse",    "FTSE 100",         "Indices",     "^FTSE",    "price"),
    ("dax",     "DAX",              "Indices",     "^GDAXI",   "price"),
    ("gold",    "Gold (front)",     "Commodities", "GC=F",     "price"),
    ("oil",     "WTI Crude (front)","Commodities", "CL=F",     "price"),
    ("btc",     "Bitcoin",          "Crypto",      "BTC-USD",  "price"),
    ("eth",     "Ethereum",         "Crypto",      "ETH-USD",  "price"),
    ("eurusd",  "EUR / USD",        "FX",          "EURUSD=X", "price"),
    ("gbpusd",  "GBP / USD",        "FX",          "GBPUSD=X", "price"),
    ("ust2y",   "US 2Y yield",      "Rates",       "2YY=F",    "yield"),
    ("ust5y",   "US 5Y yield",      "Rates",       "^FVX",     "yield"),
    ("ust10y",  "US 10Y yield",     "Rates",       "^TNX",     "yield"),
    ("ust30y",  "US 30Y yield",     "Rates",       "^TYX",     "yield"),
]
ORDER = [a[0] for a in ASSETS[:11]] + ["ust2y", "ust5y", "ust7y", "ust10y", "ust30y"]

EPOCH = dt.datetime(1970, 1, 1)
def ymd(t):  # handles pre-1970 (negative) timestamps on Windows
    return (EPOCH + dt.timedelta(seconds=int(t))).strftime("%Y-%m-%d")


def fetch(sym):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.request.quote(sym) + "?interval=1d&range=100y")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(req, timeout=60))
    r = d["chart"]["result"][0]
    ts = r["timestamp"]; q = r["indicators"]["quote"][0]
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


def write(aid, label, klass, ticker, kind, series):
    dates, T, O, H, L, C, V = series
    out = f"price_{aid}.json"
    payload = {"id": aid, "ticker": ticker, "asset_label": label, "klass": klass, "kind": kind,
               "dates": dates, "timestamp": T, "open": O, "high": H, "low": L, "close": C, "volume": V}
    with open(out, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    reg.append({"id": aid, "label": label, "klass": klass, "ticker": ticker, "kind": kind, "url": out})
    print(f"{out}: {label} [{klass}/{kind}] ({ticker})  {len(dates)} rows  {dates[0]}..{dates[-1]}  last {C[-1]}")


reg = []; cache = {}
for aid, label, klass, sym, kind in ASSETS:
    try:
        cache[sym] = fetch(sym)
    except Exception as e:
        print(f"!! {aid} ({sym}) FAILED: {e}"); continue
    write(aid, label, klass, sym, kind, cache[sym])

# synthesise US 7Y = 5Y + 0.4*(10Y-5Y), date-aligned (linear in maturity 5y->10y)
try:
    f5, t10 = cache.get("^FVX"), cache.get("^TNX")
    if f5 and t10:
        idx5 = {d: i for i, d in enumerate(f5[0])}; idx10 = {d: i for i, d in enumerate(t10[0])}
        common = [d for d in f5[0] if d in idx10]; w = 0.4
        s = [[], [], [], [], [], [], []]
        for d in common:
            i, j = idx5[d], idx10[d]
            s[0].append(d); s[1].append(f5[1][i])
            for col in (2, 3, 4, 5):
                s[col].append(round(f5[col][i] + w * (t10[col][j] - f5[col][i]), 4))
            s[6].append(0)
        write("ust7y", "US 7Y yield (interp)", "Rates", "^FVX+^TNX", "yield", tuple(s))
except Exception as e:
    print(f"!! ust7y interp FAILED: {e}")

reg.sort(key=lambda r: ORDER.index(r["id"]) if r["id"] in ORDER else 999)
with open("price_assets.json", "w") as f:
    json.dump([{k: r[k] for k in ("id", "label", "klass", "ticker", "kind", "url")} for r in reg], f, indent=0)
print(f"\nprice_assets.json: {len(reg)} assets")
