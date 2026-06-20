"""Build categorized Excel from sweep CSVs including DD Protection, DD Refinement, and Counter-Cyclical."""
import pandas as pd
from pathlib import Path
import traceback, sys

ROOT = Path(__file__).resolve().parent

def main():
    try:
        # --- Existing sweeps ---
        old = pd.read_csv(ROOT / 'output/spx_strategy_sweep/spx_sweep_results.csv')
        new = pd.read_csv(ROOT / 'output/spx_1x_sweep/spx_1x_sweep_results.csv')
        print(f'Old rows: {len(old)}, New rows: {len(new)}', flush=True)

        # Remove old 1x-only rows (covered by new sweep)
        old_1x_mask = (old['pct_days_2x'] == 0.0) & (old['pct_days_3x'] == 0.0)
        old_non_1x = old[~old_1x_mask].copy()
        print(f'Old non-1x rows: {len(old_non_1x)}', flush=True)

        all_df = pd.concat([new, old_non_1x], ignore_index=True)
        print(f'Combined: {len(all_df)}', flush=True)

        def categorize(row):
            has_2x = row['pct_days_2x'] > 0.5
            has_3x = row['pct_days_3x'] > 0.5
            if has_2x and has_3x:
                return 'Hybrid'
            elif has_3x:
                return '3x'
            elif has_2x:
                return '2x'
            else:
                return '1x'

        all_df['category'] = all_df.apply(categorize, axis=1)
        for cat in ['1x', '2x', '3x', 'Hybrid']:
            print(f'{cat}: {(all_df["category"] == cat).sum()}', flush=True)

        # --- DD Protection sweep ---
        dd_df = pd.read_csv(ROOT / 'output/spx_dd_protection_sweep/spx_dd_protection_results.csv', encoding='latin-1')
        print(f'DD Protection rows: {len(dd_df)}', flush=True)

        dd_threshold = -0.60
        dd_qual = (dd_df['max_drawdown'] >= dd_threshold).sum()
        dd_excl = (dd_df['max_drawdown'] < dd_threshold).sum()
        print(f'DD <= 60%: {dd_qual}, DD > 60% (excluded): {dd_excl}', flush=True)

        # --- DD Refinement sweep ---
        ref_df = pd.read_csv(ROOT / 'output/spx_dd_refinement/spx_dd_refinement_results.csv', encoding='latin-1')
        print(f'DD Refinement rows: {len(ref_df)}', flush=True)

        # --- Counter-Cyclical sweep ---
        cc_df = pd.read_csv(ROOT / 'output/spx_counter_cyclical/spx_counter_cyclical_results.csv', encoding='latin-1')
        print(f'Counter-Cyclical rows: {len(cc_df)}', flush=True)

        cc_qual = (cc_df['max_drawdown'] >= dd_threshold).sum()
        cc_excl = (cc_df['max_drawdown'] < dd_threshold).sum()
        print(f'CC DD <= 60%: {cc_qual}, CC DD > 60% (excluded): {cc_excl}', flush=True)

        # --- Pareto Optimization sweep ---
        pareto_df = pd.read_csv(ROOT / 'output/spx_pareto/spx_pareto_results.csv', encoding='latin-1')
        print(f'Pareto rows: {len(pareto_df)}', flush=True)

        pareto_qual = (pareto_df['max_drawdown'] >= dd_threshold).sum()
        pareto_excl = (pareto_df['max_drawdown'] < dd_threshold).sum()
        print(f'Pareto DD <= 60%: {pareto_qual}, Pareto DD > 60% (excluded): {pareto_excl}', flush=True)

        # --- SPX 3x Levered Tab ---
        spx3x_df = pd.read_csv(ROOT / 'output/spx_3x_levered/spx_3x_levered_comparison.csv')
        print(f'SPX 3x Levered rows: {len(spx3x_df)}', flush=True)

        out_dir = ROOT / 'Results'
        out_dir.mkdir(exist_ok=True)
        excel_path = out_dir / 'spx_strategy_sweep_categorized.xlsx'

        out_cols_map = {
            'strategy': 'Strategy', 'cagr': 'CAGR', 'ann_volatility': 'Ann Vol',
            'sharpe': 'Sharpe', 'max_drawdown': 'Max DD', 'sortino': 'Sortino',
            'calmar': 'Calmar', 'pct_days_cash': '% Cash', 'pct_days_1x': '% 1x',
            'pct_days_2x': '% 2x', 'pct_days_3x': '% 3x', 'end_value': 'End Value ($)',
            'rebalances': 'Rebal', 'turnover_notional': 'Turnover ($)',
            'win_rate': 'Win Rate', 'profit_factor': 'Profit Factor',
        }

        dd_cols_map = {
            'strategy': 'Strategy', 'leverage': 'Leverage', 'cagr': 'CAGR',
            'max_drawdown': 'Max DD', 'ann_volatility': 'Ann Vol',
            'sharpe': 'Sharpe', 'sortino': 'Sortino',
            'pct_cash': '% Cash', 'end_value': 'End Value ($)', 'trades': 'Trades',
        }

        ref_cols_map = {
            'strategy': 'Strategy', 'leverage': 'Leverage', 'cagr': 'CAGR',
            'max_drawdown': 'Max DD', 'ann_volatility': 'Ann Vol',
            'sharpe': 'Sharpe', 'sortino': 'Sortino',
            'pct_cash': '% Cash', 'end_value': 'End Value ($)', 'trades': 'Trades',
        }

        cc_cols_map = {
            'strategy': 'Strategy', 'cagr': 'CAGR',
            'max_drawdown': 'Max DD', 'ann_volatility': 'Ann Vol',
            'sharpe': 'Sharpe', 'sortino': 'Sortino',
            'pct_cash': '% Cash', 'end_value': 'End Value ($)', 'trades': 'Trades',
            'avg_leverage': 'Avg Leverage',
        }

        pareto_cols_map = {
            'strategy': 'Strategy', 'cagr': 'CAGR',
            'max_drawdown': 'Max DD', 'ann_volatility': 'Ann Vol',
            'sharpe': 'Sharpe', 'sortino': 'Sortino',
            'pct_cash': '% Cash', 'end_value': 'End Value ($)', 'trades': 'Trades',
            'avg_leverage': 'Avg Leverage',
        }

        spx3x_cols_map = {
            'strategy': 'Strategy', 'cagr': 'CAGR',
            'ann_volatility': 'Ann Vol', 'sharpe': 'Sharpe',
            'sortino': 'Sortino', 'max_drawdown': 'Max DD',
            'end_$': 'End Value ($)', 'total_trades': 'Trades',
            'pct_days_cash': '% Cash', 'avg_leverage': 'Avg Leverage',
        }

        def format_sheet(df_sheet, benchmarks):
            rows = []
            if benchmarks is not None and len(benchmarks):
                for _, b in benchmarks.iterrows():
                    r = b.to_dict()
                    r['Type'] = '★ BENCHMARK'
                    rows.append(r)
            strat_df = df_sheet.sort_values('cagr', ascending=False)
            for _, s in strat_df.iterrows():
                r = s.to_dict()
                r['Type'] = 'Strategy'
                rows.append(r)
            result = pd.DataFrame(rows)
            cols_present = [c for c in out_cols_map if c in result.columns]
            result = result[['Type'] + cols_present].rename(columns=out_cols_map)
            for col in ['CAGR', 'Ann Vol', 'Max DD', '% Cash', '% 1x', '% 2x', '% 3x', 'Win Rate']:
                if col in result.columns:
                    result[col] = (result[col] * 100).round(2)
            for col in ['Sharpe', 'Sortino', 'Calmar', 'Profit Factor']:
                if col in result.columns:
                    result[col] = result[col].round(3)
            for col in ['End Value ($)', 'Turnover ($)']:
                if col in result.columns:
                    result[col] = result[col].round(0).astype(int)
            return result

        def format_dd_sheet(df_dd, benchmarks):
            """Format DD Protection sheet: qualifying (DD <= 60%) full detail,
            excluded (DD > 60%) collapsed to Strategy + Max DD only."""
            dd_threshold = -0.60

            qualifying = df_dd[df_dd['max_drawdown'] >= dd_threshold].copy()
            excluded = df_dd[df_dd['max_drawdown'] < dd_threshold].copy()

            # --- Qualifying section (full detail, sorted by CAGR desc) ---
            q_rows = []
            if benchmarks is not None and len(benchmarks):
                for _, b in benchmarks.iterrows():
                    r = b.to_dict()
                    r['Type'] = '★ BENCHMARK'
                    q_rows.append(r)
            q_strat = qualifying.sort_values('cagr', ascending=False)
            for _, s in q_strat.iterrows():
                r = s.to_dict()
                r['Type'] = 'Strategy'
                q_rows.append(r)

            q_df = pd.DataFrame(q_rows)
            cols_present = [c for c in dd_cols_map if c in q_df.columns]
            q_df = q_df[['Type'] + cols_present].rename(columns=dd_cols_map)
            for col in ['CAGR', 'Ann Vol', 'Max DD', '% Cash']:
                if col in q_df.columns:
                    q_df[col] = (q_df[col] * 100).round(2)
            for col in ['Sharpe', 'Sortino']:
                if col in q_df.columns:
                    q_df[col] = q_df[col].round(3)
            for col in ['End Value ($)']:
                if col in q_df.columns:
                    q_df[col] = q_df[col].round(0).astype(int)
            if 'Leverage' in q_df.columns:
                q_df['Leverage'] = q_df['Leverage'].round(1)

            # --- Excluded section (collapsed: Strategy + Max DD only) ---
            excluded = excluded.sort_values('max_drawdown', ascending=True)
            ex_rows = []
            for _, s in excluded.iterrows():
                ex_rows.append({
                    'Strategy': s['strategy'],
                    'Max DD': round(s['max_drawdown'] * 100, 2),
                })
            ex_df = pd.DataFrame(ex_rows)

            return q_df, ex_df

        def format_ref_sheet(df_ref, benchmarks):
            """Format DD Refinement sheet: all strategies, benchmarks at top."""
            rows = []
            if benchmarks is not None and len(benchmarks):
                for _, b in benchmarks.iterrows():
                    r = b.to_dict()
                    r['Type'] = '★ BENCHMARK'
                    rows.append(r)
            strat_df = df_ref.sort_values('cagr', ascending=False)
            for _, s in strat_df.iterrows():
                r = s.to_dict()
                r['Type'] = 'Strategy'
                rows.append(r)
            result = pd.DataFrame(rows)
            cols_present = [c for c in ref_cols_map if c in result.columns]
            result = result[['Type'] + cols_present].rename(columns=ref_cols_map)
            for col in ['CAGR', 'Ann Vol', 'Max DD', '% Cash']:
                if col in result.columns:
                    result[col] = (result[col] * 100).round(2)
            for col in ['Sharpe', 'Sortino']:
                if col in result.columns:
                    result[col] = result[col].round(3)
            for col in ['End Value ($)']:
                if col in result.columns:
                    result[col] = result[col].round(0).astype(int)
            if 'Leverage' in result.columns:
                result['Leverage'] = result['Leverage'].round(1)
            return result

        def format_cc_sheet(df_cc, benchmarks):
            """Format Counter-Cyclical sheet: qualifying (DD <= 60%) full detail,
            excluded (DD > 60%) collapsed to Strategy + Max DD only."""
            dd_threshold = -0.60

            qualifying = df_cc[df_cc['max_drawdown'] >= dd_threshold].copy()
            excluded = df_cc[df_cc['max_drawdown'] < dd_threshold].copy()

            # --- Qualifying section (full detail, sorted by CAGR desc) ---
            q_rows = []
            if benchmarks is not None and len(benchmarks):
                for _, b in benchmarks.iterrows():
                    r = b.to_dict()
                    r['Type'] = '★ BENCHMARK'
                    q_rows.append(r)
            q_strat = qualifying.sort_values('cagr', ascending=False)
            for _, s in q_strat.iterrows():
                r = s.to_dict()
                r['Type'] = 'Strategy'
                q_rows.append(r)

            q_df = pd.DataFrame(q_rows)
            cols_present = [c for c in cc_cols_map if c in q_df.columns]
            q_df = q_df[['Type'] + cols_present].rename(columns=cc_cols_map)
            for col in ['CAGR', 'Ann Vol', 'Max DD', '% Cash']:
                if col in q_df.columns:
                    q_df[col] = (q_df[col] * 100).round(2)
            for col in ['Sharpe', 'Sortino']:
                if col in q_df.columns:
                    q_df[col] = q_df[col].round(3)
            for col in ['End Value ($)']:
                if col in q_df.columns:
                    q_df[col] = q_df[col].round(0).astype(int)
            if 'Avg Leverage' in q_df.columns:
                q_df['Avg Leverage'] = q_df['Avg Leverage'].round(1)

            # --- Excluded section (collapsed: Strategy + Max DD only) ---
            excluded = excluded.sort_values('max_drawdown', ascending=True)
            ex_rows = []
            for _, s in excluded.iterrows():
                ex_rows.append({
                    'Strategy': s['strategy'],
                    'Max DD': round(s['max_drawdown'] * 100, 2),
                })
            ex_df = pd.DataFrame(ex_rows)

            return q_df, ex_df

        def format_pareto_sheet(df_pareto, benchmarks):
            """Format Pareto Optimization sheet: qualifying (DD <= 60%) full detail,
            excluded (DD > 60%) collapsed to Strategy + Max DD only."""
            dd_threshold = -0.60

            qualifying = df_pareto[df_pareto['max_drawdown'] >= dd_threshold].copy()
            excluded = df_pareto[df_pareto['max_drawdown'] < dd_threshold].copy()

            # --- Qualifying section (full detail, sorted by CAGR desc) ---
            q_rows = []
            if benchmarks is not None and len(benchmarks):
                for _, b in benchmarks.iterrows():
                    r = b.to_dict()
                    r['Type'] = '★ BENCHMARK'
                    q_rows.append(r)
            q_strat = qualifying.sort_values('cagr', ascending=False)
            for _, s in q_strat.iterrows():
                r = s.to_dict()
                r['Type'] = 'Strategy'
                q_rows.append(r)

            q_df = pd.DataFrame(q_rows)
            cols_present = [c for c in pareto_cols_map if c in q_df.columns]
            q_df = q_df[['Type'] + cols_present].rename(columns=pareto_cols_map)
            for col in ['CAGR', 'Ann Vol', 'Max DD', '% Cash']:
                if col in q_df.columns:
                    q_df[col] = (q_df[col] * 100).round(2)
            for col in ['Sharpe', 'Sortino']:
                if col in q_df.columns:
                    q_df[col] = q_df[col].round(3)
            for col in ['End Value ($)']:
                if col in q_df.columns:
                    q_df[col] = q_df[col].round(0).astype(int)
            if 'Avg Leverage' in q_df.columns:
                q_df['Avg Leverage'] = q_df['Avg Leverage'].round(2)

            # --- Excluded section (collapsed: Strategy + Max DD only) ---
            excluded = excluded.sort_values('max_drawdown', ascending=True)
            ex_rows = []
            for _, s in excluded.iterrows():
                ex_rows.append({
                    'Strategy': s['strategy'],
                    'Max DD': round(s['max_drawdown'] * 100, 2),
                })
            ex_df = pd.DataFrame(ex_rows)

            return q_df, ex_df

        def format_spx3x_sheet(df_spx3x, benchmarks):
            """Format SPX 3x Levered Tab: benchmarks at top, all 9 strategies sorted by CAGR desc."""
            rows = []
            if benchmarks is not None and len(benchmarks):
                for _, b in benchmarks.iterrows():
                    r = b.to_dict()
                    r['Type'] = '★ BENCHMARK'
                    rows.append(r)
            strat_df = df_spx3x.sort_values('cagr', ascending=False)
            for _, s in strat_df.iterrows():
                r = s.to_dict()
                r['Type'] = 'Strategy'
                rows.append(r)
            result = pd.DataFrame(rows)
            cols_present = [c for c in spx3x_cols_map if c in result.columns]
            result = result[['Type'] + cols_present].rename(columns=spx3x_cols_map)
            for col in ['CAGR', 'Ann Vol', 'Max DD', '% Cash']:
                if col in result.columns:
                    result[col] = (result[col] * 100).round(2)
            for col in ['Sharpe', 'Sortino']:
                if col in result.columns:
                    result[col] = result[col].round(3)
            for col in ['End Value ($)']:
                if col in result.columns:
                    result[col] = result[col].round(0).astype(int)
            if 'Avg Leverage' in result.columns:
                result['Avg Leverage'] = result['Avg Leverage'].round(2)
            return result

        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            # --- Existing category sheets ---
            for cat, bh_names in [
                ('1x', ['Buy & Hold SPY 1x', 'Buy & Hold 60/40 SPY/T-bills']),
                ('2x', ['Buy & Hold 2x']),
                ('3x', ['Buy & Hold 3x']),
                ('Hybrid', ['Buy & Hold 1x', 'Buy & Hold 2x', 'Buy & Hold 3x']),
            ]:
                df_cat = all_df[all_df['category'] == cat]
                bh_rows = all_df[all_df['strategy'].isin(bh_names)]
                sheet = format_sheet(df_cat, bh_rows if len(bh_rows) else None)
                sheet.to_excel(writer, sheet_name=f'{cat} Strategies', index=False)
                print(f'Sheet {cat}: {len(sheet)} rows', flush=True)

            # --- DD Protection Sweep sheet ---
            bh_dd_names = ['Buy & Hold SPY 1x', 'Buy & Hold SSO 2x', 'Buy & Hold UPRO 3x']
            bh_dd = dd_df[dd_df['strategy'].isin(bh_dd_names)]
            q_df, ex_df = format_dd_sheet(dd_df, bh_dd if len(bh_dd) else None)

            q_df.to_excel(writer, sheet_name='DD Protection Sweep', index=False)
            sep_df = pd.DataFrame([{'Strategy': '--- DD > 60% (EXCLUDED) ---', 'Max DD': ''}])
            sep_start = len(q_df) + 2
            sep_df.to_excel(writer, sheet_name='DD Protection Sweep', index=False,
                           startrow=sep_start, header=False)
            ex_df.to_excel(writer, sheet_name='DD Protection Sweep', index=False,
                          startrow=sep_start + 1)
            print(f'Sheet DD Protection: {len(q_df)} qualifying + {len(ex_df)} excluded', flush=True)

            # --- DD Refinement sheet ---
            bh_ref_names = ['Buy & Hold SPY 1x', 'Buy & Hold SSO 2x', 'Buy & Hold UPRO 3x',
                           'SMA200 +-3% Band 2x (baseline)', 'SMA200 +-3% Band 3x (baseline)']
            bh_ref = ref_df[ref_df['strategy'].isin(bh_ref_names)]
            ref_sheet = format_ref_sheet(ref_df, bh_ref if len(bh_ref) else None)
            ref_sheet.to_excel(writer, sheet_name='DD Refinement', index=False)
            print(f'Sheet DD Refinement: {len(ref_sheet)} rows', flush=True)

            # --- Counter-Cyclical sheet ---
            bh_cc_names = ['Buy & Hold SPY 1x', 'Buy & Hold SSO 2x', 'Buy & Hold UPRO 3x',
                          'SMA200 +-3% Band + RSI>30 Exit 3x', 'SMA200 +-3% Band + RSI>30 Exit 2x']
            bh_cc = cc_df[cc_df['strategy'].isin(bh_cc_names)]
            cc_q_df, cc_ex_df = format_cc_sheet(cc_df, bh_cc if len(bh_cc) else None)

            cc_q_df.to_excel(writer, sheet_name='Counter-Cyclical', index=False)
            cc_sep_df = pd.DataFrame([{'Strategy': '--- DD > 60% (EXCLUDED) ---', 'Max DD': ''}])
            cc_sep_start = len(cc_q_df) + 2
            cc_sep_df.to_excel(writer, sheet_name='Counter-Cyclical', index=False,
                              startrow=cc_sep_start, header=False)
            cc_ex_df.to_excel(writer, sheet_name='Counter-Cyclical', index=False,
                            startrow=cc_sep_start + 1)
            print(f'Sheet Counter-Cyclical: {len(cc_q_df)} qualifying + {len(cc_ex_df)} excluded', flush=True)

            # --- Pareto Optimization sheet ---
            bh_pareto_names = ['Buy & Hold SPY 1x',
                              'B1: SMA200 \xb1 3% Band + RSI>30 Exit 3x',
                              'B2: SMA200 \xb1 3% Band + RSI>30 Exit 2x',
                              'B3: SMA200 \xb1 3% Band + RSI>30 Exit + RSI Scale 1-3x',
                              'B4: SMA200 \xb1 3% Band + RSI>30 Exit + VIX Scale 1-3x']
            bh_pareto = pareto_df[pareto_df['strategy'].isin(bh_pareto_names)]
            pareto_q_df, pareto_ex_df = format_pareto_sheet(pareto_df, bh_pareto if len(bh_pareto) else None)

            pareto_q_df.to_excel(writer, sheet_name='Pareto Optimization', index=False)
            pareto_sep_df = pd.DataFrame([{'Strategy': '--- DD > 60% (EXCLUDED) ---', 'Max DD': ''}])
            pareto_sep_start = len(pareto_q_df) + 2
            pareto_sep_df.to_excel(writer, sheet_name='Pareto Optimization', index=False,
                                   startrow=pareto_sep_start, header=False)
            pareto_ex_df.to_excel(writer, sheet_name='Pareto Optimization', index=False,
                                 startrow=pareto_sep_start + 1)
            print(f'Sheet Pareto Optimization: {len(pareto_q_df)} qualifying + {len(pareto_ex_df)} excluded', flush=True)

            # --- SPX 3x Levered Tab sheet ---
            bh_spx3x_names = ['Buy & Hold SPY 1x', 'Buy & Hold SSO 2x', 'Buy & Hold UPRO 3x']
            bh_spx3x = spx3x_df[spx3x_df['strategy'].isin(bh_spx3x_names)]
            spx3x_sheet = format_spx3x_sheet(spx3x_df, bh_spx3x if len(bh_spx3x) else None)
            spx3x_sheet.to_excel(writer, sheet_name='SPX 3x Levered Tab', index=False)
            print(f'Sheet SPX 3x Levered Tab: {len(spx3x_sheet)} rows', flush=True)

            # --- Summary Top 5 ---
            summary_rows = []
            for cat, bh_name in [
                ('1x', 'Buy & Hold SPY 1x'),
                ('2x', 'Buy & Hold 2x'),
                ('3x', 'Buy & Hold 3x'),
                ('Hybrid', 'Buy & Hold 3x'),
            ]:
                df_cat = all_df[all_df['category'] == cat]
                bh_row = df_cat[df_cat['strategy'] == bh_name]
                if len(bh_row):
                    bh = bh_row.iloc[0]
                    summary_rows.append({
                        'Category': cat, 'Rank': 'BH',
                        'Strategy': bh['strategy'],
                        'CAGR': bh['cagr'] * 100, 'Max DD': bh['max_drawdown'] * 100,
                        'Sharpe': bh['sharpe'], 'Sortino': bh['sortino'],
                        'End Value ($)': int(bh['end_value']),
                        '% Cash': bh['pct_days_cash'] * 100,
                    })
                top5 = df_cat.sort_values('cagr', ascending=False).head(5)
                for rank, (_, s) in enumerate(top5.iterrows(), 1):
                    summary_rows.append({
                        'Category': cat, 'Rank': rank,
                        'Strategy': s['strategy'],
                        'CAGR': s['cagr'] * 100, 'Max DD': s['max_drawdown'] * 100,
                        'Sharpe': s['sharpe'], 'Sortino': s['sortino'],
                        'End Value ($)': int(s['end_value']),
                        '% Cash': s['pct_days_cash'] * 100,
                    })

            # DD Protection summary rows
            dd_bh_name = 'Buy & Hold SPY 1x'
            dd_bh_row = dd_df[dd_df['strategy'] == dd_bh_name]
            if len(dd_bh_row):
                bh = dd_bh_row.iloc[0]
                summary_rows.append({
                    'Category': 'DD Protection', 'Rank': 'BH',
                    'Strategy': bh['strategy'],
                    'CAGR': bh['cagr'] * 100, 'Max DD': bh['max_drawdown'] * 100,
                    'Sharpe': bh['sharpe'], 'Sortino': bh['sortino'],
                    'End Value ($)': int(bh['end_value']),
                    '% Cash': bh['pct_cash'] * 100,
                })
            dd_qual_top = dd_df[dd_df['max_drawdown'] >= -0.60].sort_values('cagr', ascending=False).head(5)
            for rank, (_, s) in enumerate(dd_qual_top.iterrows(), 1):
                summary_rows.append({
                    'Category': 'DD Protection', 'Rank': rank,
                    'Strategy': s['strategy'],
                    'CAGR': s['cagr'] * 100, 'Max DD': s['max_drawdown'] * 100,
                    'Sharpe': s['sharpe'], 'Sortino': s['sortino'],
                    'End Value ($)': int(s['end_value']),
                    '% Cash': s['pct_cash'] * 100,
                })

            # DD Refinement summary rows
            ref_bh_name = 'SMA200 +-3% Band 3x (baseline)'
            ref_bh_row = ref_df[ref_df['strategy'] == ref_bh_name]
            if len(ref_bh_row):
                bh = ref_bh_row.iloc[0]
                summary_rows.append({
                    'Category': 'DD Refinement', 'Rank': 'BH',
                    'Strategy': bh['strategy'],
                    'CAGR': bh['cagr'] * 100, 'Max DD': bh['max_drawdown'] * 100,
                    'Sharpe': bh['sharpe'], 'Sortino': bh['sortino'],
                    'End Value ($)': int(bh['end_value']),
                    '% Cash': bh['pct_cash'] * 100,
                })
            ref_top = ref_df.sort_values('cagr', ascending=False).head(5)
            for rank, (_, s) in enumerate(ref_top.iterrows(), 1):
                summary_rows.append({
                    'Category': 'DD Refinement', 'Rank': rank,
                    'Strategy': s['strategy'],
                    'CAGR': s['cagr'] * 100, 'Max DD': s['max_drawdown'] * 100,
                    'Sharpe': s['sharpe'], 'Sortino': s['sortino'],
                    'End Value ($)': int(s['end_value']),
                    '% Cash': s['pct_cash'] * 100,
                })

            # Counter-Cyclical summary rows
            cc_bh_name = 'SMA200 +-3% Band + RSI>30 Exit 3x'
            cc_bh_row = cc_df[cc_df['strategy'] == cc_bh_name]
            if len(cc_bh_row):
                bh = cc_bh_row.iloc[0]
                summary_rows.append({
                    'Category': 'Counter-Cyclical', 'Rank': 'BH',
                    'Strategy': bh['strategy'],
                    'CAGR': bh['cagr'] * 100, 'Max DD': bh['max_drawdown'] * 100,
                    'Sharpe': bh['sharpe'], 'Sortino': bh['sortino'],
                    'End Value ($)': int(bh['end_value']),
                    '% Cash': bh['pct_cash'] * 100,
                })
            cc_qual_top = cc_df[cc_df['max_drawdown'] >= -0.60].sort_values('cagr', ascending=False).head(5)
            for rank, (_, s) in enumerate(cc_qual_top.iterrows(), 1):
                summary_rows.append({
                    'Category': 'Counter-Cyclical', 'Rank': rank,
                    'Strategy': s['strategy'],
                    'CAGR': s['cagr'] * 100, 'Max DD': s['max_drawdown'] * 100,
                    'Sharpe': s['sharpe'], 'Sortino': s['sortino'],
                    'End Value ($)': int(s['end_value']),
                    '% Cash': s['pct_cash'] * 100,
                })

            # Pareto Optimization summary rows
            pareto_bh_name = 'B1: SMA200 \xb1 3% Band + RSI>30 Exit 3x'
            pareto_bh_row = pareto_df[pareto_df['strategy'] == pareto_bh_name]
            if len(pareto_bh_row):
                bh = pareto_bh_row.iloc[0]
                summary_rows.append({
                    'Category': 'Pareto Optimization', 'Rank': 'BH',
                    'Strategy': bh['strategy'],
                    'CAGR': bh['cagr'] * 100, 'Max DD': bh['max_drawdown'] * 100,
                    'Sharpe': bh['sharpe'], 'Sortino': bh['sortino'],
                    'End Value ($)': int(bh['end_value']),
                    '% Cash': bh['pct_cash'] * 100,
                })
            pareto_qual_top = pareto_df[pareto_df['max_drawdown'] >= -0.60].sort_values('cagr', ascending=False).head(5)
            for rank, (_, s) in enumerate(pareto_qual_top.iterrows(), 1):
                summary_rows.append({
                    'Category': 'Pareto Optimization', 'Rank': rank,
                    'Strategy': s['strategy'],
                    'CAGR': s['cagr'] * 100, 'Max DD': s['max_drawdown'] * 100,
                    'Sharpe': s['sharpe'], 'Sortino': s['sortino'],
                    'End Value ($)': int(s['end_value']),
                    '% Cash': s['pct_cash'] * 100,
                })

            # SPX 3x Levered summary rows
            spx3x_bh_name = 'Buy & Hold UPRO 3x'
            spx3x_bh_row = spx3x_df[spx3x_df['strategy'] == spx3x_bh_name]
            if len(spx3x_bh_row):
                bh = spx3x_bh_row.iloc[0]
                summary_rows.append({
                    'Category': 'SPX 3x Levered', 'Rank': 'BH',
                    'Strategy': bh['strategy'],
                    'CAGR': bh['cagr'] * 100, 'Max DD': bh['max_drawdown'] * 100,
                    'Sharpe': bh['sharpe'], 'Sortino': bh['sortino'],
                    'End Value ($)': int(bh['end_$']),
                    '% Cash': bh['pct_days_cash'] * 100,
                })
            spx3x_top = spx3x_df.sort_values('cagr', ascending=False).head(5)
            for rank, (_, s) in enumerate(spx3x_top.iterrows(), 1):
                summary_rows.append({
                    'Category': 'SPX 3x Levered', 'Rank': rank,
                    'Strategy': s['strategy'],
                    'CAGR': s['cagr'] * 100, 'Max DD': s['max_drawdown'] * 100,
                    'Sharpe': s['sharpe'], 'Sortino': s['sortino'],
                    'End Value ($)': int(s['end_$']),
                    '% Cash': s['pct_days_cash'] * 100,
                })

            summary_df = pd.DataFrame(summary_rows)
            for col in ['CAGR', 'Max DD', '% Cash']:
                summary_df[col] = summary_df[col].round(2)
            for col in ['Sharpe', 'Sortino']:
                summary_df[col] = summary_df[col].round(3)
            summary_df.to_excel(writer, sheet_name='Summary Top 5', index=False)

        print(f'SUCCESS: {excel_path}', flush=True)
        print(f'Size: {excel_path.stat().st_size} bytes', flush=True)

    except Exception:
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
