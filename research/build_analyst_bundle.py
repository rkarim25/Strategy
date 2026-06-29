"""One-click Analyst — gather + validate ALL signal data into a single bundle.

This is the "download all the data and check the data" step behind the one-click
Analyst. It (1) refreshes the graded signal snapshot, (2) runs data-HEALTH checks
(freshness, gaps, NaN), and (3) bundles both assets' signals + the official
mechanical signals + news sentiment + benchmark into one ``analyst_bundle.json``.

That bundle is the single source of truth for every Analyst surface:
  * the Claude Code ``/analyst`` command (the oneclick-analyst skill reads it),
  * the website Analyst button's deterministic quant report,
  * the optional Cloudflare worker that calls the Claude API.

Run:  python research/build_analyst_bundle.py
No backtests are re-run — it re-reads the existing sweep via build_signal_dashboard.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any, Optional

import build_signal_dashboard  # refreshes signals_<asset>.json (same dir, on sys.path)
import signal_state            # live evaluators + composite (same as the in-browser dashboard)

REPO = Path(__file__).resolve().parents[1]
ASSETS = [("spx", "latest_signal.json"), ("ndx", "latest_ndx_signal.json")]
QUOTE = "https://spx-quote-proxy.rkarim88.workers.dev"
FRESH_WARN_DAYS = 5      # daily data older than this -> WARN
FRESH_FAIL_DAYS = 14     # ... older than this -> FAIL


def fetch_quote(sym: str) -> Optional[float]:
    """Latest price from the live quote worker (the same source the website uses)."""
    try:
        req = urllib.request.Request(f"{QUOTE}/?mode=quote&symbol={sym}",
                                     headers={"User-Agent": "Mozilla/5.0 (analyst-bundle)"})
        with urllib.request.urlopen(req, timeout=8) as r:
            q = json.loads(r.read().decode())
        return float(q["price"]) if q and q.get("price", 0) > 0 else None
    except Exception:
        return None


def live_recompute(asset: str, sj: dict[str, Any], live_price: Optional[float],
                   vix: Optional[float]) -> Optional[dict[str, Any]]:
    """Recompute the composite against the LIVE price + VIX, mirroring the dashboard."""
    try:
        close = signal_state.load_close(asset)
    except Exception:
        return None
    c = close.copy()
    if live_price:
        c.iloc[-1] = live_price
    month = datetime.now().month
    states = []
    for s in sj.get("signals", []):
        params = dict(s.get("params", {}))
        if s.get("data") == "vix":
            params["_vix"] = vix
        st = signal_state.evaluate(s["rule"], params, c, month)
        states.append({"kind": s["kind"], "reliability": s["reliability"], "state": st})
    comp = signal_state.composite(states)
    comp["price"] = round(float(c.iloc[-1]), 2)
    comp["vix"] = vix
    comp["asof"] = "live" if live_price else "snapshot"
    return comp


def _read(path: Path) -> Optional[dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _days_since(iso: Optional[str]) -> Optional[int]:
    if not iso:
        return None
    try:
        d = date.fromisoformat(str(iso)[:10])
        return (date.today() - d).days
    except Exception:
        return None


def _has_nan_token(path: Path) -> bool:
    try:
        txt = path.read_text(encoding="utf-8")
        return "NaN" in txt or "Infinity" in txt
    except Exception:
        return True


def _check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"check": name, "status": status, "detail": detail}


def health_checks(signals: dict[str, Any], officials: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for asset in ("spx", "ndx"):
        sj = signals.get(asset)
        # daily price freshness (from the daily CSV last row)
        try:
            df = (REPO / f"{asset}_daily.csv").read_text(encoding="utf-8").strip().splitlines()
            last_date = df[-1].split(",")[0]
            d = _days_since(last_date)
            st = "PASS" if (d is not None and d <= FRESH_WARN_DAYS) else ("WARN" if (d is not None and d <= FRESH_FAIL_DAYS) else "FAIL")
            out.append(_check(f"{asset} daily price freshness", st, f"last bar {last_date} ({d}d ago)"))
        except Exception as e:
            out.append(_check(f"{asset} daily price freshness", "FAIL", f"unreadable: {e}"))
        # signals file present + clean
        if not sj:
            out.append(_check(f"{asset} signals file", "FAIL", "signals_*.json missing or unreadable"))
        else:
            nan = _has_nan_token(REPO / f"signals_{asset}.json")
            out.append(_check(f"{asset} signals file", "FAIL" if nan else "PASS",
                              "contains NaN/Infinity (breaks browser parse)" if nan else f"{len(sj.get('signals', []))} graded signals, ok"))
            cur = sj.get("current", {})
            nstate = sum(1 for s in sj.get("signals", []) if s.get("state"))
            out.append(_check(f"{asset} live signal coverage", "PASS" if nstate else "WARN",
                              f"{nstate}/{len(sj.get('signals', []))} signals evaluated; composite {cur.get('label','?')} -> {cur.get('suggested_leverage','?')}x"))
        # official mechanical signal freshness
        oj = officials.get(asset)
        if not oj:
            out.append(_check(f"{asset} official signal", "WARN", "latest_*_signal.json missing"))
        else:
            d = _days_since(oj.get("data_asof"))
            st = "PASS" if (d is not None and d <= FRESH_WARN_DAYS) else "WARN"
            out.append(_check(f"{asset} official signal", st,
                              f"asof {oj.get('data_asof','?')} ({d}d); target {oj.get('official_signal',{}).get('targetLeverage','?')}x"))
    return out


def slim_signal(s: dict[str, Any]) -> dict[str, Any]:
    ev = s.get("evidence", {})
    return {
        "id": s["id"], "name": s["name"], "category": s["category"], "kind": s["kind"],
        "grade": s["grade"], "reliability": s["reliability"], "why": s["why"],
        "state": s.get("state"),
        "evidence": {k: ev.get(k) for k in ("sharpe", "calmar", "maxdd", "cagr", "beats_bh", "strategy_label", "sample")},
    }


def main() -> None:
    build_signal_dashboard.main()  # refresh signals_<asset>.json snapshots

    signals = {a: _read(REPO / f"signals_{a}.json") for a, _ in ASSETS}
    officials = {a: _read(REPO / f) for a, f in ASSETS}
    news = _read(REPO / "news_score.json") or {}

    # Pull LIVE quotes (same worker the website uses) so the read isn't the stale snapshot.
    vix = fetch_quote("vix")
    health = health_checks(signals, officials)
    health.append(_check("live VIX fetch", "PASS" if vix is not None else "WARN",
                         f"VIX {vix}" if vix is not None else "worker unreachable; using snapshot (no live VIX)"))

    bundle: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema": "analyst_bundle/1",
        "scope": ["spx", "ndx"],
        "data_health": health,
        "assets": {},
        "news": {k: news.get(k) for k in ("score", "label", "explanation", "window_days")},
    }
    for asset, _ in ASSETS:
        sj = signals.get(asset) or {}
        oj = officials.get(asset) or {}
        live_price = fetch_quote(asset)
        live = live_recompute(asset, sj, live_price, vix) if sj else None
        health.append(_check(f"{asset} live price fetch", "PASS" if live_price else "WARN",
                            f"{asset.upper()} {live_price}" if live_price else "worker unreachable; using snapshot close"))
        bundle["assets"][asset] = {
            "label": sj.get("asset_label", asset.upper()),
            "current": live or sj.get("current"),
            "current_snapshot": sj.get("current"),
            "benchmark": sj.get("benchmark"),
            "signals": [slim_signal(s) for s in sj.get("signals", [])],
            "official_signal": oj.get("official_signal", {}),
        }

    out = REPO / "analyst_bundle.json"
    out.write_text(json.dumps(bundle, indent=2, ensure_ascii=True), encoding="utf-8")

    worst = "PASS"
    for c in bundle["data_health"]:
        if c["status"] == "FAIL":
            worst = "FAIL"
        elif c["status"] == "WARN" and worst != "FAIL":
            worst = "WARN"
    print(f"analyst_bundle.json written | data health: {worst}")
    for c in bundle["data_health"]:
        if c["status"] != "PASS":
            print(f"  [{c['status']}] {c['check']}: {c['detail']}")
    for a in ("spx", "ndx"):
        cur = (bundle["assets"][a].get("current") or {})
        print(f"  {a.upper()}: {cur.get('label','?')} net {cur.get('net','?')} -> {cur.get('suggested_leverage','?')}x "
              f"| official {bundle['assets'][a]['official_signal'].get('targetLeverage','?')}x")


if __name__ == "__main__":
    main()
