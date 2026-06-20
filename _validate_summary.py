"""Extract all summary_data.json structure for validation."""
import json

with open(r"C:\Users\Reza Karim\OneDrive\Systematic_Backstester\summary_data.json") as f:
    d = json.load(f)

print("=== TOP-LEVEL KEYS ===")
print(list(d.keys()))
print(f"Generated: {d['generated']}")
print(f"Assets count: {len(d['assets'])}")

for a in d['assets']:
    print(f"\n=== ASSET: {a['key']} ({a['label']}) ===")
    print(f"  idx: {a['idx']}, real_lev: {a['real_lev']}")
    print(f"  tickers: {a.get('tickers', 'N/A')}")
    for reg in ['real', 'synth_era', 'synth_long']:
        r = a.get(reg)
        if r:
            print(f"  --- {reg} ---")
            print(f"    start={r['start']}, end={r['end']}, years={r['years']}, sessions={r['sessions']}")
            if 'cov' in r:
                print(f"    cov: {r['cov']}")
            strategies = list(r['rows'].keys())
            print(f"    strategies ({len(strategies)}):")
            for s in strategies:
                m = r['rows'][s]
                print(f"      {s}: cagr_r={m.get('cagr_r','?')}, dd_r={m.get('dd_r','?')}, vol={m.get('vol','?')}, sharpe={m.get('sharpe','?')}, sortino={m.get('sortino','?')}, calmar={m.get('calmar','?')}, cash={m.get('cash','?')}, trades_yr={m.get('trades_yr','?')}, end={m.get('end','?')}")
