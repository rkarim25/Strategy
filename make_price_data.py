"""Fetch full-history daily OHLC for the Price page (S&P 500 ^GSPC, Nasdaq 100 ^NDX)
from Yahoo and write price_spx.json / price_ndx.json. Tickers match the quote-proxy
worker (spx->^GSPC, ndx->^NDX) so the live last-price overlay lines up."""
import json, urllib.request, datetime as dt

EPOCH = dt.datetime(1970, 1, 1)
def ymd(t):  # handles pre-1970 (negative) timestamps on Windows
    return (EPOCH + dt.timedelta(seconds=int(t))).strftime("%Y-%m-%d")

ASSETS = [
    ("^GSPC", "S&P 500", "price_spx.json"),
    ("^NDX", "Nasdaq 100", "price_ndx.json"),
]


def fetch(sym):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.request.quote(sym) + "?interval=1d&range=100y")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(req, timeout=60))
    r = d["chart"]["result"][0]
    ts = r["timestamp"]
    q = r["indicators"]["quote"][0]
    o, h, l, c = q["open"], q["high"], q["low"], q["close"]
    dates, O, H, L, C = [], [], [], [], []
    for i, t in enumerate(ts):
        if None in (o[i], h[i], l[i], c[i]):
            continue
        if not (c[i] > 0 and h[i] >= l[i]):
            continue
        dates.append(ymd(t))
        O.append(round(o[i], 2)); H.append(round(h[i], 2)); L.append(round(l[i], 2)); C.append(round(c[i], 2))
    return dates, O, H, L, C


for sym, label, out in ASSETS:
    dates, O, H, L, C = fetch(sym)
    payload = {"ticker": sym, "asset_label": label, "dates": dates, "open": O, "high": H, "low": L, "close": C}
    with open(out, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"{out}: {label} ({sym})  {len(dates)} rows  {dates[0]}..{dates[-1]}  last close {C[-1]}")
