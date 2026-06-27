"""Fetch full-history daily OHLC(V) for the Charts page from Yahoo and write price_<id>.json each.
Config-driven registry: add a row to ASSETS (id, label, asset class, Yahoo ticker, kind) to add an asset.
kind: 'price' (equities/commodities/crypto/FX) or 'yield' (UST rates — backtested with yield-as-PnL).
US 7Y has no Yahoo series, so it is synthesised by interpolating 5Y(^FVX) and 10Y(^TNX).
Output feeds KLineChart: parallel arrays dates / timestamp(ms) / open/high/low/close/volume."""
import json, urllib.request, datetime as dt
import numpy as np

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
# regression (beta) weighted flies: belly hedged by wings via full-sample OLS hedge ratios (RV residual)
FLIES_BETA = [
    ("f2s5s10sb",  "2s5s10s RW-fly",  "^FVX", "2YY=F", "^TNX"),
    ("f5s10s30sb", "5s10s30s RW-fly", "^TNX", "^FVX", "^TYX"),
]
ORDER = ([a[0] for a in ASSETS[:11]] + ["ust3m", "ust2y", "ust5y", "ust7y", "ust10y", "ust30y"]
         + [s[0] for s in SPREADS] + [f[0] for f in FLIES] + [f[0] for f in FLIES_BETA])

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

def build_fly_beta(aid, label, belly, w1, w2):
    # OUT-OF-SAMPLE: hedge betas from a ROLLING window (last WIN trading days) of past Δyields (lagged),
    # so the hedge ratio tracks regime drift; 50-50 fallback until MIN obs accumulate.
    B, A, Cc = cache.get(belly), cache.get(w1), cache.get(w2)
    if not (B and A and Cc):
        print(f"!! flyRW {aid}: missing leg"); return
    Bi = {d: i for i, d in enumerate(B[0])}; Ai = {d: i for i, d in enumerate(A[0])}; Ci = {d: i for i, d in enumerate(Cc[0])}
    common = [d for d in B[0] if d in Ai and d in Ci]
    if len(common) < 320:
        print(f"!! flyRW {aid}: short"); return
    yb = [B[5][Bi[d]] for d in common]; y1 = [A[5][Ai[d]] for d in common]; y2 = [Cc[5][Ci[d]] for d in common]
    MIN, WIN = 252, 756  # min obs to estimate; ~3y rolling window
    n = 0; s1 = s2 = sb = s11 = s22 = s12 = s1b = s2b = 0.0
    d1s = []; d2s = []; dbs = []; dropped = 0  # diff history for the rolling window
    b1 = b2 = 0.5; lb1 = lb2 = 0.5
    s = [[], [], [], [], [], [], []]
    for i, d in enumerate(common):
        if n >= MIN:
            S11 = s11 - s1 * s1 / n; S22 = s22 - s2 * s2 / n; S12 = s12 - s1 * s2 / n; S1b = s1b - s1 * sb / n; S2b = s2b - s2 * sb / n
            det = S11 * S22 - S12 * S12
            if abs(det) > 1e-12:
                b1 = (S22 * S1b - S12 * S2b) / det; b2 = (S11 * S2b - S12 * S1b) / det
        lb1, lb2 = b1, b2
        ib, ia, ic = Bi[d], Ai[d], Ci[d]
        o = h = lo = c = 0.0
        for leg, ii, w in [(B, ib, 1.0), (A, ia, -b1), (Cc, ic, -b2)]:
            o += w * leg[2][ii]; c += w * leg[5][ii]
            h += w * leg[3][ii] if w > 0 else w * leg[4][ii]
            lo += w * leg[4][ii] if w > 0 else w * leg[3][ii]
        s[0].append(d); s[1].append(B[1][ib]); s[2].append(round(o, 4)); s[3].append(round(h, 4)); s[4].append(round(lo, 4)); s[5].append(round(c, 4)); s[6].append(0)
        if i > 0:
            d1 = y1[i] - y1[i - 1]; d2 = y2[i] - y2[i - 1]; db = yb[i] - yb[i - 1]
            d1s.append(d1); d2s.append(d2); dbs.append(db)
            n += 1; s1 += d1; s2 += d2; sb += db; s11 += d1 * d1; s22 += d2 * d2; s12 += d1 * d2; s1b += d1 * db; s2b += d2 * db
            if n > WIN:  # drop the oldest diff so the window stays ~3y
                o1 = d1s[dropped]; o2 = d2s[dropped]; ob = dbs[dropped]
                s1 -= o1; s2 -= o2; sb -= ob; s11 -= o1 * o1; s22 -= o2 * o2; s12 -= o1 * o2; s1b -= o1 * ob; s2b -= o2 * ob
                n -= 1; dropped += 1
    write(aid, f"{label} (hedge ~{lb1:.2f}/{lb2:.2f})", "Butterfly", f"{belly}-rw-{w1}-{w2}", "spread", tuple(s),
          legs=[{"t": belly, "w": 1}, {"t": w1, "w": round(-lb1, 3)}, {"t": w2, "w": round(-lb2, 3)}])

for aid, label, belly, w1, w2 in FLIES_BETA:
    try:
        build_fly_beta(aid, label, belly, w1, w2)
    except Exception as e:
        print(f"!! flyRW {aid} FAILED: {e}")

# live curve snapshot: latest yield per tenor (+ approx modified-duration DV01 per $100)
TENORS = [("ust3m", 0.25, 0.25), ("ust2y", 2, 1.9), ("ust5y", 5, 4.7), ("ust7y", 7, 6.4), ("ust10y", 10, 8.6), ("ust30y", 30, 18.5)]
curve = [{"id": k, "years": yr, "dv01": dv, "yield": LATEST[k]["yield"], "date": LATEST[k]["date"]} for k, yr, dv in TENORS if k in LATEST]
# 3-month roll-down (yield pickup as the bond ages down the curve) + carry vs the 3M bill, in bps
pts = sorted((c["years"], c["yield"]) for c in curve)
def interp(t):
    if t <= pts[0][0]: return pts[0][1]
    if t >= pts[-1][0]: return pts[-1][1]
    for j in range(1, len(pts)):
        if pts[j][0] >= t:
            (x0, y0), (x1, y1) = pts[j - 1], pts[j]; return y0 + (y1 - y0) * (t - x0) / (x1 - x0)
    return pts[-1][1]
short = curve[0]["yield"]
for c in curve:
    c["roll3m"] = round((c["yield"] - interp(max(0.083, c["years"] - 0.25))) * 100, 1)
    c["carry3m"] = round((c["yield"] - short) * 0.25 * 100, 1)
json.dump(curve, open("ust_curve.json", "w"))

# Curve-inversion ranges (for the chart shading): union of 2s10s (^TNX-2YY=F, 2021+) and the
# longer-history 3m10y (^TNX-^IRX) inverted periods. ISO date strings sort lexically.
def inv_ranges(long_t, short_t):
    L, S = cache.get(long_t), cache.get(short_t)
    if not (L and S): return []
    Si = {d: i for i, d in enumerate(S[0])}; out = []; start = None; prev = None; cnt = 0
    for i, d in enumerate(L[0]):
        if d not in Si: continue
        sp = L[5][i] - S[5][Si[d]]
        if sp < 0:
            if start is None: start = d; cnt = 0
            cnt += 1
        elif start is not None:
            out.append([start, prev, cnt]); start = None
        prev = d
    if start is not None: out.append([start, prev, cnt])
    return out
def _days(a, b):
    return (dt.datetime.strptime(b, "%Y-%m-%d") - dt.datetime.strptime(a, "%Y-%m-%d")).days
def merge_ranges(rs):  # merge ranges within ~30 calendar days, then keep only sustained (>=5d) inversions
    out = []
    for a, b, n in sorted(rs):
        if out and _days(out[-1][1], a) <= 30:
            if b > out[-1][1]: out[-1][1] = b
            out[-1][2] += n
        else: out.append([a, b, n])
    return [[a, b] for a, b, n in out if n >= 5]
inv = merge_ranges(inv_ranges("^TNX", "2YY=F") + inv_ranges("^TNX", "^IRX"))
json.dump(inv, open("ust_inversions.json", "w"))
print(f"ust_inversions.json: {len(inv)} sustained inverted ranges (latest {inv[-1] if inv else '-'})")
print(f"ust_curve.json: {len(curve)} tenors")

reg.sort(key=lambda r: ORDER.index(r["id"]) if r["id"] in ORDER else 999)
with open("price_assets.json", "w") as f:
    json.dump([{k: r[k] for k in ("id", "label", "klass", "ticker", "kind", "url")} for r in reg], f, indent=0)
print(f"\nprice_assets.json: {len(reg)} assets")
