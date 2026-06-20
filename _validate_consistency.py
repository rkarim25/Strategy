"""Comprehensive validation of summary_data.json internal consistency."""
import json, math, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open(r"C:\Users\Reza Karim\OneDrive\Systematic_Backstester\summary_data.json") as f:
    d = json.load(f)

issues = []
warnings = []

# 1. Calmar = CAGR / |Max DD|
print("=== 1. CALMAR CONSISTENCY (cagr_r / |dd_r| ~= calmar) ===")
calmar_errors = 0
for a in d['assets']:
    for reg in ['real', 'synth_era', 'synth_long']:
        r = a.get(reg)
        if not r: continue
        for sname, m in r['rows'].items():
            expected = m['cagr_r'] / abs(m['dd_r']) if m['dd_r'] != 0 else float('inf')
            actual = m['calmar']
            if abs(expected - actual) > 0.015 and abs(m['dd_r']) > 0.001:
                calmar_errors += 1
                if calmar_errors <= 10:
                    issues.append(f"CALMAR: {a['key']}/{reg}/{sname}: expected {expected:.3f}, got {actual:.3f} (cagr_r={m['cagr_r']:.4f}, dd_r={m['dd_r']:.4f})")
print(f"  Calmar discrepancies > 0.015: {calmar_errors}")

# 2. Cross-regime: synth_era == synth_long when same window
print("\n=== 2. CROSS-REGIME CONSISTENCY (synth_era vs synth_long) ===")
for a in d['assets']:
    se = a.get('synth_era')
    sl = a.get('synth_long')
    if not se or not sl: continue
    if se['start'] == sl['start'] and se['end'] == sl['end']:
        mismatches = 0
        for sname in se['rows']:
            for field in ['cagr_r', 'dd_r', 'vol', 'sharpe', 'sortino', 'calmar', 'end']:
                v_se = se['rows'][sname].get(field)
                v_sl = sl['rows'][sname].get(field)
                if v_se != v_sl:
                    mismatches += 1
                    if mismatches <= 5:
                        issues.append(f"REGIME-MISMATCH: {a['key']}/{sname}/{field}: synth_era={v_se}, synth_long={v_sl} (same window {se['start']}→{se['end']})")
        if mismatches == 0:
            print(f"  {a['key']}: synth_era == synth_long ✓ (same window {se['start']}→{se['end']})")
        else:
            print(f"  {a['key']}: {mismatches} MISMATCHES between synth_era and synth_long!")
            issues.append(f"REGIME-MISMATCH: {a['key']} has {mismatches} field mismatches between synth_era and synth_long despite identical date ranges")

# 3. Banner claim vs data: real_lev=false assets
print("\n=== 3. BANNER CLAIM CHECK (real_lev=false: 'Real' and 'Synthetic · same era' are identical) ===")
for a in d['assets']:
    if not a['real_lev']:
        real_r = a.get('real')
        synth_r = a.get('synth_era')
        if real_r and synth_r:
            # Check 1x B&H (should differ since real uses actual ETF)
            bh1_real = real_r['rows'].get('Buy & hold 1x', {})
            bh1_synth = synth_r['rows'].get('Buy & hold 1x', {})
            diff_pp = abs(bh1_real.get('cagr_r', 0) - bh1_synth.get('cagr_r', 0)) * 100
            if diff_pp > 0.1:
                warnings.append(f"BANNER-DIFF: {a['key']} ({a['label']}) real_lev=false: 1x CAGR real={bh1_real.get('cagr_r'):.4f}, synth_era={bh1_synth.get('cagr_r'):.4f} (diff={diff_pp:.1f}pp). Banner now shows the actual difference.")
            # Check 2x/3x B&H (should be identical since both synthetic)
            for lev in ['Buy & hold 2x', 'Buy & hold 3x']:
                r2 = real_r['rows'].get(lev, {})
                s2 = synth_r['rows'].get(lev, {})
                if r2.get('cagr_r') != s2.get('cagr_r'):
                    issues.append(f"BANNER-DATA: {a['key']} {lev} differs between real and synth_era despite both being synthetic: real={r2.get('cagr_r')}, synth={s2.get('cagr_r')}")

# 4. Negative CAGR but positive Sharpe/Sortino
print("\n=== 4. NEGATIVE CAGR WITH POSITIVE SHARPE ===")
for a in d['assets']:
    for reg in ['real', 'synth_era', 'synth_long']:
        r = a.get(reg)
        if not r: continue
        for sname, m in r['rows'].items():
            if m['cagr_r'] < 0 and (m['sharpe'] is not None and m['sharpe'] > 0.05):
                warnings.append(f"NEG-CAGR-POS-SHARPE: {a['key']}/{reg}/{sname}: cagr_r={m['cagr_r']:.4f}, sharpe={m['sharpe']:.3f} (possible if rf < 0)")

# 5. Exactly zero Sharpe/Sortino
print("\n=== 5. ZERO SHARPE/SORTINO ===")
for a in d['assets']:
    for reg in ['real', 'synth_era', 'synth_long']:
        r = a.get(reg)
        if not r: continue
        for sname, m in r['rows'].items():
            if m['sharpe'] is None or m['sortino'] is None:
                warnings.append(f"NULL-METRIC: {a['key']}/{reg}/{sname}: sharpe={m['sharpe']}, sortino={m['sortino']}, cagr_r={m['cagr_r']:.4f} (genuinely undefined — excess returns near zero)")
            elif m['sharpe'] == 0.0 or m['sortino'] == 0.0:
                warnings.append(f"ZERO-METRIC: {a['key']}/{reg}/{sname}: sharpe={m['sharpe']}, sortino={m['sortino']}, cagr_r={m['cagr_r']:.4f}")

# 6. Unusually high Sharpe (>1.5)
print("\n=== 6. UNUSUALLY HIGH SHARPE (>1.5) ===")
for a in d['assets']:
    for reg in ['real', 'synth_era', 'synth_long']:
        r = a.get(reg)
        if not r: continue
        for sname, m in r['rows'].items():
            if m['sharpe'] is not None and m['sharpe'] > 1.5:
                warnings.append(f"HIGH-SHARPE: {a['key']}/{reg}/{sname}: sharpe={m['sharpe']:.2f}, cagr_r={m['cagr_r']:.4f}, vol={m['vol']:.4f}, dd_r={m['dd_r']:.4f}")

# 7. End value sanity: $100 start + $10/yr inflow
print("\n=== 7. END VALUE ROUGH CONSISTENCY ===")
for a in d['assets']:
    for reg in ['real', 'synth_era', 'synth_long']:
        r = a.get(reg)
        if not r: continue
        years = r['years']
        for sname, m in r['rows'].items():
            cagr = m['cagr_r']
            end = m['end']
            # Rough estimate: 100*(1+cagr)^years + 10*((1+cagr)^years-1)/cagr
            if cagr > 0.001:
                g = 1 + cagr
                approx = 100 * (g**years) + 10 * ((g**years - 1) / cagr)
                ratio = end / approx if approx > 0 else 0
                if ratio < 0.5 or ratio > 2.0:
                    issues.append(f"END-VALUE: {a['key']}/{reg}/{sname}: end={end:.0f}, approx={approx:.0f}, ratio={ratio:.2f} (cagr={cagr:.4f}, yrs={years})")

# 8. Check for strategies with identical dd_r across different leverage levels (suspicious)
print("\n=== 8. IDENTICAL DD ACROSS LEVERAGE LEVELS ===")
for a in d['assets']:
    for reg in ['real', 'synth_era', 'synth_long']:
        r = a.get(reg)
        if not r: continue
        rows = r['rows']
        # Check Golden 2x volguard vs Golden 3x volguard vs Buy & hold 2x
        for group in [('Golden 2x volguard', 'Buy & hold 2x'), ('Golden 3x volguard', 'Buy & hold 3x'), ('Golden 50/200 2x', 'Buy & hold 2x')]:
            s1, s2 = group
            if s1 in rows and s2 in rows:
                if rows[s1]['dd_r'] == rows[s2]['dd_r']:
                    warnings.append(f"IDENTICAL-DD: {a['key']}/{reg}: {s1} dd_r={rows[s1]['dd_r']:.4f} == {s2} dd_r={rows[s2]['dd_r']:.4f}")

# Summary
print("\n\n========== VALIDATION SUMMARY ==========")
print(f"ISSUES: {len(issues)}")
for i in issues:
    print(f"  ❌ {i}")
print(f"\nWARNINGS: {len(warnings)}")
for w in warnings:
    print(f"  ⚠️ {w}")
