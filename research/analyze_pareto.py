"""Quick Pareto analysis from saved CSV (encoding-safe, fixed vol logic)."""
import sys as _s, pathlib as _p; _s.path.insert(0, str(_p.Path(__file__).resolve().parent.parent))  # repo root importable (moved into research/)
import pandas as pd

df = pd.read_csv('output/spx_pareto/spx_pareto_results.csv', encoding='latin-1')

# Find baselines by partial match
def find_row(df, substr):
    matches = df[df['strategy'].str.contains(substr, na=False, regex=False)]
    if len(matches) == 0:
        raise ValueError(f"No match for '{substr}'")
    return matches.iloc[0]

bls = {
    'B1': find_row(df, 'B1:'),
    'B2': find_row(df, 'B2:'),
    'B3': find_row(df, 'B3:'),
    'B4': find_row(df, 'B4:'),
}

bl_names = set(bls[bl_key]['strategy'] for bl_key in bls)

EPS = 1e-9
# Metrics where higher numeric value = better
higher_better = ['cagr', 'sharpe', 'sortino', 'max_drawdown']  # DD is negative, less neg = higher = better
# Metrics where lower numeric value = better
lower_better = ['ann_volatility']  # positive, lower = better

with open('output/spx_pareto/pareto_analysis.txt', 'w', encoding='utf-8') as f:
    for bl_key, bl in bls.items():
        f.write(f'\n{"="*80}\n')
        f.write(f'PARETO ANALYSIS vs {bl_key}\n')
        f.write(f'Baseline: {bl["strategy"]}\n')
        f.write(f'CAGR={bl.cagr*100:.2f}% DD={bl.max_drawdown*100:.1f}% '
                f'Vol={bl.ann_volatility*100:.1f}% Sharpe={bl.sharpe:.3f} '
                f'Sortino={bl.sortino:.3f} AvgLev={bl.avg_leverage:.2f}\n')
        f.write(f'{"="*80}\n')

        candidates = df[~df['strategy'].isin(bl_names) &
                        ~df['strategy'].str.contains('Buy & Hold|plain', na=False, regex=True)]

        pareto = []
        closest = []

        for _, c in candidates.iterrows():
            lower_lev = c.avg_leverage < bl.avg_leverage - EPS
            improved = []
            worsened = []
            # Higher-is-better metrics
            for m in higher_better:
                if c[m] > bl[m] + EPS:
                    improved.append(m)
                elif c[m] < bl[m] - EPS:
                    worsened.append(m)
            # Lower-is-better metrics
            for m in lower_better:
                if c[m] < bl[m] - EPS:
                    improved.append(m)
                elif c[m] > bl[m] + EPS:
                    worsened.append(m)

            if lower_lev and improved and not worsened:
                pareto.append((c, improved))
            elif improved:
                closest.append((c, improved, worsened, lower_lev))

        if pareto:
            f.write(f'\nPARETO IMPROVEMENTS FOUND: {len(pareto)}\n')
            f.write(f'{"Strategy":<55} {"CAGR":>8} {"MaxDD":>8} {"AnnVol":>8} '
                    f'{"Sharpe":>7} {"Sortino":>7} {"AvgLev":>7} {"Improved":>30}\n')
            f.write('-' * 130 + '\n')
            for c, imps in sorted(pareto, key=lambda x: x[0].cagr, reverse=True):
                f.write(f'{c.strategy:<55} {c.cagr*100:>7.2f}% {c.max_drawdown*100:>7.1f}% '
                        f'{c.ann_volatility*100:>7.1f}% {c.sharpe:>7.3f} {c.sortino:>7.3f} '
                        f'{c.avg_leverage:>7.2f} {", ".join(imps):>30}\n')
        else:
            f.write('\nNO STRICT PARETO IMPROVEMENTS\n')

        if closest:
            closest.sort(key=lambda x: (len(x[1]), x[0].cagr), reverse=True)
            f.write(f'\nClosest strategies (improved some metrics but had trade-offs):\n')
            f.write(f'{"Strategy":<55} {"CAGR":>8} {"MaxDD":>8} {"AnnVol":>8} '
                    f'{"Sharpe":>7} {"Sortino":>7} {"AvgLev":>7} {"+":>20} {"-":>20} {"Lev<":>6}\n')
            f.write('-' * 140 + '\n')
            for c, imps, wors, ll in closest[:8]:
                f.write(f'{c.strategy:<55} {c.cagr*100:>7.2f}% {c.max_drawdown*100:>7.1f}% '
                        f'{c.ann_volatility*100:>7.1f}% {c.sharpe:>7.3f} {c.sortino:>7.3f} '
                        f'{c.avg_leverage:>7.2f} {", ".join(imps):>20} {", ".join(wors):>20} '
                        f'{"YES" if ll else "no":>6}\n')

print('Done. See output/spx_pareto/pareto_analysis.txt')
