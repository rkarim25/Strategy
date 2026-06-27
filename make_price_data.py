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
    ("ust3m",   "US 3M yield",      "Rates",       "^IRX",     "yield"),
    ("ust2y",   "US 2Y yield",      "Rates",       "2YY=F",    "yield"),
    ("ust5y",   "US 5Y yield",      "Rates",       "^FVX",     "yield"),
    ("ust10y",  "US 10Y yield",     "Rates",       "^TNX",     "yield"),
    ("ust30y",  "US 30Y yield",     "Rates",       "^TYX",     "yield"),
]
# curve-steepness spreads (long-tenor minus short-tenor yield); kind 'spread' -> backtested as P&L = pos x change-in-spread
SPREADS = [
    ("s2s10s", "2s10s (10Y-2Y)", "^TNX", "2YY=F"),
    ("s3m10y", "3m10y (10Y-3M)", "^TNX", "^IRX"),
    ("s5s10s", "5s10s (10Y-5Y)", "^TNX", "^FVX"),
    ("s5s30s", "5s30s (30Y-5Y)", "^TYX", "^FVX"),
]
# curve butterflies (RV): 2*belly - wing_short - wing_long; kind 'spread' (P&L = pos x change-in-fly)
FLIES = [
    ("f2s5s10s",  "2s5s10s fly",  "^FVX", "2YY=F", "^TNX"),   # belly 5Y, wings 2Y/10Y
    ("f5s10s30s", "5s10s30s fly", "^TNX", "^FVX", "^TYX"),    # belly 10Y, wings 5Y/30Y (1977+)
]
ORDER = ([a[0] for a in ASSETS[:11]] + ["ust3m", "ust2y", "ust5y", "ust7y", "ust10y", "ust30y"]
         + [s[0] for s in SPREADS] + [f[0] for f in FLIES])

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


def write(aid, label, klass, ticker, kind, series, legs=None):
    dates, T, O, H, L, C, V = series
    out = f"price_{aid}.json"
    payload = {"id": aid, "ticker": ticker, "asset_label": label, "klass": klass, "kind": kind,
               "dates": dates, "timestamp": T, "open": O, "high": H, "low": L, "close": C, "volume": V}
    if legs: payload["legs"] = legs
    with open(out, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    r = {"id": aid, "label": label, "klass": klass, "ticker": ticker, "kind": kind, "url": out}
    if legs: r["legs"] = legs
    reg.append(r)
    if kind == "yield": LATEST[aid] = {"date": dates[-1], "yield": C[-1]}
    print(f"{out}: {label} [{klass}/{kind}] ({ticker})  {len(dates)} rows  {dates[0]}..{dates[-1]}  last {C[-1]}")


reg = []; cache = {}; LATEST = {}
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

# steepness spreads = long-tenor minus short-tenor, date-aligned (high = longHigh-shortLow, low = longLow-shortHigh)
def build_spread(aid, label, long_sym, short_sym):
    Lg, Sh = cache.get(long_sym), cache.get(short_sym)
    if not Lg or not Sh:
        print(f"!! spread {aid}: missing leg ({long_sym} or {short_sym})"); return
    Li = {d: i for i, d in enumerate(Lg[0])}; Si = {d: i for i, d in enumerate(Sh[0])}
    s = [[], [], [], [], [], [], []]
    for d in Lg[0]:
        j = Si.get(d)
        if j is None:
            continue
        i = Li[d]
        s[0].append(d); s[1].append(Lg[1][i])
        s[2].append(round(Lg[2][i] - Sh[2][j], 4))
        s[3].append(round(Lg[3][i] - Sh[4][j], 4))
        s[4].append(round(Lg[4][i] - Sh[3][j], 4))
        s[5].append(round(Lg[5][i] - Sh[5][j], 4))
        s[6].append(0)
    if len(s[0]) < 60:
        print(f"!! spread {aid}: too few aligned rows"); return
    write(aid, label, "Steepness", f"{long_sym}/{short_sym}", "spread", tuple(s),
          legs=[{"t": long_sym, "w": 1}, {"t": short_sym, "w": -1}])

for aid, label, lng, sht in SPREADS:
    try:
        build_spread(aid, label, lng, sht)
    except Exception as e:
        print(f"!! spread {aid} FAILED: {e}")

def build_fly(aid, label, belly, w1, w2):
    B, A, Cc = cache.get(belly), cache.get(w1), cache.get(w2)
    if not (B and A and Cc):
        print(f"!! fly {aid}: missing leg"); return
    Ai = {d: i for i, d in enumerate(A[0])}; Ci = {d: i for i, d in enumerate(Cc[0])}; Bi = {d: i for i, d in enumerate(B[0])}
    s = [[], [], [], [], [], [], []]
    for d in B[0]:
        j = Ai.get(d); k = Ci.get(d)
        if j is None or k is None:
            continue
        i = Bi[d]
        s[0].append(d); s[1].append(B[1][i])
        s[2].append(round(2 * B[2][i] - A[2][j] - Cc[2][k], 4))
        s[3].append(round(2 * B[3][i] - A[4][j] - Cc[4][k], 4))
        s[4].append(round(2 * B[4][i] - A[3][j] - Cc[3][k], 4))
        s[5].append(round(2 * B[5][i] - A[5][j] - Cc[5][k], 4))
        s[6].append(0)
    if len(s[0]) < 60:
        print(f"!! fly {aid}: too few rows"); return
    write(aid, label, "Butterfly", f"2*{belly}-{w1}-{w2}", "spread", tuple(s),
          legs=[{"t": belly, "w": 2}, {"t": w1, "w": -1}, {"t": w2, "w": -1}])

for aid, label, belly, w1, w2 in FLIES:
    try:
        build_fly(aid, label, belly, w1, w2)
    except Exception as e:
        print(f"!! fly {aid} FAILED: {e}")

# live curve snapshot: latest yield per tenor (+ approx modified-duration DV01 per $100)
TENORS = [("ust3m", 0.25, 0.25), ("ust2y", 2, 1.9), ("ust5y", 5, 4.7), ("ust7y", 7, 6.4), ("ust10y", 10, 8.6), ("ust30y", 30, 18.5)]
curve = [{"id": k, "years": yr, "dv01": dv, "yield": LATEST[k]["yield"], "date": LATEST[k]["date"]} for k, yr, dv in TENORS if k in LATEST]
json.dump(curve, open("ust_curve.json", "w"))
print(f"ust_curve.json: {len(curve)} tenors")

reg.sort(key=lambda r: ORDER.index(r["id"]) if r["id"] in ORDER else 999)
with open("price_assets.json", "w") as f:
    json.dump([{k: r[k] for k in ("id", "label", "klass", "ticker", "kind", "url")} for r in reg], f, indent=0)
print(f"\nprice_assets.json: {len(reg)} assets")
