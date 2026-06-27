"""Comprehensive strategy sweep over the UST section (yields + steepeners + butterflies).
For each instrument, backtest the playbook strategy families across a param grid, pick the best by
Sharpe, and emit ust_strategies.json (consumed by the Charts 'Curve strategy leaderboard').
Yields: P&L = carry (rate/252 while long). Spreads/flies: P&L = position(+1/-1) x daily change in spread."""
import json, math, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
reg = json.load(open(os.path.join(ROOT, "price_assets.json")))
UST = [a for a in reg if a["klass"] in ("Rates", "Steepness", "Butterfly")]
TD = 252


def sma(a, n):
    o = [None] * len(a); s = 0.0
    for i in range(len(a)):
        s += a[i]
        if i >= n: s -= a[i - n]
        if i >= n - 1: o[i] = s / n
    return o

def ema(a, n):
    o = [None] * len(a); k = 2 / (n + 1); e = None
    for i in range(len(a)):
        e = a[i] if e is None else a[i] * k + e * (1 - k)
        if i >= n - 1: o[i] = e
    return o

def rsi(a, n):
    o = [None] * len(a); g = l = 0.0
    for i in range(1, len(a)):
        ch = a[i] - a[i - 1]; gg = max(ch, 0); ll = max(-ch, 0)
        if i <= n:
            g += gg; l += ll
            if i == n: g /= n; l /= n; o[i] = 100 - 100 / (1 + (1e9 if l == 0 else g / l))
        else:
            g = (g * (n - 1) + gg) / n; l = (l * (n - 1) + ll) / n; o[i] = 100 - 100 / (1 + (1e9 if l == 0 else g / l))
    return o

def macd(a, f=12, s=26, sig=9):
    ef = ema(a, f); es = ema(a, s)
    m = [None if (ef[i] is None or es[i] is None) else ef[i] - es[i] for i in range(len(a))]
    g = ema([0 if v is None else v for v in m], sig); g = [None if m[i] is None else g[i] for i in range(len(a))]
    return m, g

def rstd(a, n):
    o = [None] * len(a)
    for i in range(n - 1, len(a)):
        w = a[i - n + 1:i + 1]; m = sum(w) / n; o[i] = math.sqrt(sum((x - m) ** 2 for x in w) / n)
    return o

def rmax(a, n): return [None if i < n - 1 else max(a[i - n + 1:i + 1]) for i in range(len(a))]
def rmin(a, n): return [None if i < n - 1 else min(a[i - n + 1:i + 1]) for i in range(len(a))]

# position generators (0/1) matching the playbook
def p_trend(c, win): b = sma(c, win); return [1 if (b[i] is not None and c[i] >= b[i]) else 0 for i in range(len(c))]
def p_band(c, win, band):
    s = sma(c, win); st = 0; out = []
    for i in range(len(c)):
        if s[i] is not None:
            if c[i] > s[i] * (1 + band): st = 1
            elif c[i] < s[i] * (1 - band): st = 0
        out.append(st)
    return out
def p_gc(c, f, s): a = sma(c, f); b = sma(c, s); return [1 if (a[i] is not None and b[i] is not None and a[i] >= b[i]) else 0 for i in range(len(c))]
def p_ema(c, f, s): a = ema(c, f); b = ema(c, s); return [1 if (a[i] is not None and b[i] is not None and a[i] >= b[i]) else 0 for i in range(len(c))]
def p_macd(c): m, g = macd(c); return [1 if (m[i] is not None and g[i] is not None and m[i] >= g[i]) else 0 for i in range(len(c))]
def p_macdzero(c): m, _ = macd(c); return [1 if (m[i] is not None and m[i] >= 0) else 0 for i in range(len(c))]
def p_rsimom(c, p, lvl): r = rsi(c, p); return [1 if (r[i] is not None and r[i] >= lvl) else 0 for i in range(len(c))]
def p_rsirev(c, p, lo, hi):
    r = rsi(c, p); st = 0; out = []
    for i in range(len(c)):
        if r[i] is not None:
            if st == 0 and r[i] < lo: st = 1
            elif st == 1 and r[i] > hi: st = 0
        out.append(st)
    return out
def p_boll(c, w, m):
    mid = sma(c, w); sd = rstd(c, w); st = 0; out = []
    for i in range(len(c)):
        if mid[i] is not None:
            if st == 0 and c[i] < mid[i] - m * sd[i]: st = 1
            elif st == 1 and c[i] > mid[i]: st = 0
        out.append(st)
    return out
def p_donch(c, w):
    hi = rmax(c, w); lo = rmin(c, w); st = 0; out = []
    for i in range(len(c)):
        if i >= w:
            if c[i] >= hi[i - 1]: st = 1
            elif c[i] <= lo[i - 1]: st = 0
        out.append(st)
    return out

# strategy grid: (playbook_key, display, params_dict, position_fn) — families: trend / reversion / breakout
def build_grid():
    g = []
    for w in (50, 100, 150, 200): g.append(("trend", "Trend filter", {"win": w}, lambda c, w=w: p_trend(c, w), "trend"))
    for w in (100, 150, 200):
        for b in (0.02, 0.03): g.append(("bandtrend", "Band trend", {"win": w, "band": b * 100}, lambda c, w=w, b=b: p_band(c, w, b), "trend"))
    for f, s in ((20, 100), (50, 200)): g.append(("gc", "Golden Cross", {"fast": f, "slow": s}, lambda c, f=f, s=s: p_gc(c, f, s), "trend"))
    for f, s in ((12, 26), (50, 200)): g.append(("emacross", "EMA Cross", {"fast": f, "slow": s}, lambda c, f=f, s=s: p_ema(c, f, s), "trend"))
    g.append(("macd", "MACD", {"fast": 12, "slow": 26, "signal": 9}, p_macd, "trend"))
    g.append(("macdzero", "MACD zero-line", {"fast": 12, "slow": 26}, p_macdzero, "trend"))
    for lvl in (50, 55): g.append(("rsi", "RSI momentum", {"period": 14, "level": lvl}, lambda c, lvl=lvl: p_rsimom(c, 14, lvl), "trend"))
    for p, lo, hi in ((2, 25, 70), (14, 30, 70), (14, 25, 75)): g.append(("rsirev", "RSI reversion", {"period": p, "lower": lo, "upper": hi}, lambda c, p=p, lo=lo, hi=hi: p_rsirev(c, p, lo, hi), "reversion"))
    for m in (2, 2.5): g.append(("boll", "Bollinger reversion", {"win": 20, "mult": m}, lambda c, m=m: p_boll(c, 20, m), "reversion"))
    for w in (20, 50, 100): g.append(("donch", "Donchian breakout", {"win": w}, lambda c, w=w: p_donch(c, w), "breakout"))
    return g
GRID = build_grid()


def metr_carry(c, pos):
    eq = 1.0; peak = 1.0; mdd = 0.0; rets = []
    for i in range(len(c)):
        r = (pos[i - 1] if i else 0) * ((c[i - 1] if i else 0) / 100 / TD)
        eq *= 1 + r; rets.append(r)
        if eq > peak: peak = eq
        if eq / peak - 1 < mdd: mdd = eq / peak - 1
    n = len(c); yrs = n / TD; cagr = eq ** (1 / yrs) - 1
    m = sum(rets) / n; vol = math.sqrt(sum((x - m) ** 2 for x in rets) / (n - 1)) * math.sqrt(TD)
    return dict(primary=cagr, sharpe=(m * TD / vol if vol else 0), maxdd=mdd, pin=sum(1 for p in pos if p) / n, unit="cagr")

def metr_spread(c, pos):
    cum = 0.0; peak = 0.0; mdd = 0.0; hit = 0; pnl = []
    for i in range(1, len(c)):
        x = (1 if pos[i - 1] else -1) * (c[i] - c[i - 1]); pnl.append(x); cum += x
        if cum > peak: peak = cum
        if cum - peak < mdd: mdd = cum - peak
        if x > 0: hit += 1
    yrs = len(c) / TD; m = sum(pnl) / len(pnl); vol = math.sqrt(sum((x - m) ** 2 for x in pnl) / (len(pnl) - 1))
    return dict(primary=cum * 100, sharpe=(m / vol * math.sqrt(TD) if vol else 0), annbps=cum * 100 / yrs, maxddbps=mdd * 100, hit=hit / len(pnl), total=cum * 100, unit="bps")


out = []
for a in UST:
    d = json.load(open(os.path.join(ROOT, a["url"])))
    c = d["close"]; kind = a["kind"]
    if len(c) < 300:
        print(f"skip {a['id']} (short)"); continue
    rows = []
    for key, disp, params, fn, fam in GRID:
        try:
            pos = fn(c)
        except Exception:
            continue
        m = metr_spread(c, pos)  # directional/RV: P&L = pos x change-in-series (bps); long yield = long rates
        rows.append((key, disp, params, fam, m, pos))
    rows.sort(key=lambda r: -r[4]["sharpe"])
    best = rows[0]; fams = [r[3] for r in rows[:5]]
    win_fam = max(set(fams), key=fams.count)
    def explain():
        fam, nm, t, k = best[3], best[1], a["label"], a["klass"]
        if k == "Rates":
            s = f"Rates trend with the policy cycle, so directional momentum pays: {nm} goes long rates when the yield's own momentum turns up and long duration when it rolls over."
            return s + (" The belly (5Y/7Y) times the cleanest." if best[4]["sharpe"] > 0.7 else "")
        if k == "Steepness":
            if fam == "reversion":
                return f"The {t} oscillates around its range, so {nm} fades extremes — buy a flat curve, sell a steep one."
            return f"The {t} steepens in easing cycles and flattens in hiking cycles — long, persistent moves that {nm} follows (long the steepener when the slope's momentum is up)."
        return f"A butterfly is a pure relative-value trade with little directional drift, so it mean-reverts: {nm} fades a rich/cheap belly back to fair — the strongest risk-adjusted edge on the curve."
    on = 1 if best[5][-1] else 0
    siglabel = ("long rates" if on else "long duration") if kind == "yield" else \
               ("long the fly" if on else "short the fly") if a["klass"] == "Butterfly" else \
               ("long steepener" if on else "flattener")
    out.append({"id": a["id"], "label": a["label"], "klass": a["klass"], "kind": kind,
                "best": {"key": best[0], "name": best[1], "params": best[2], "family": best[3], "metrics": best[4],
                         "signalNow": on, "signalLabel": siglabel, "asof": d["dates"][-1]},
                "explain": explain(), "topFamily": win_fam, "rows": len(rows)})
    mm = best[4]
    print(f"{a['id']:10} {a['klass']:10} BEST {best[1]:18} {str(best[2]):34} | Sharpe {mm['sharpe']:.2f}  {mm['total']:.0f}bps total/{mm['annbps']:.0f}bps yr/DD {mm['maxddbps']:.0f}bps/hit {mm['hit']*100:.0f}%  [top family: {win_fam}]")

json.dump(out, open(os.path.join(ROOT, "ust_strategies.json"), "w"), indent=0)
print(f"\nwrote ust_strategies.json — {len(out)} UST instruments, {len(GRID)} strategies each")
