"""Build comprehensive Strategy Results Excel workbook with Water/Octane classification.

Reads 11 CSV files from output/strategy_results/ and produces a formatted
Excel workbook at Results/strategy_results.xlsx with:
  - 1 Summary sheet
  - 20 detail sheets (10 assets x 2 classifications: Water + Octane)
"""

import pandas as pd
import openpyxl
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, NamedStyle, numbers
)
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from pathlib import Path
import os
import traceback
import sys

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
CSV_DIR = ROOT / 'output' / 'strategy_results'
RESULTS_DIR = ROOT / 'Results'
EXCEL_PATH = RESULTS_DIR / 'strategy_results.xlsx'

# ── Asset label mapping ───────────────────────────────────────────────────
ASSET_LABELS = {
    'spx':        'S&P 500',
    'spxew':      'S&P 500 EW',
    'ndx':        'Nasdaq 100',
    'rut':        'Russell 2000',
    'gold':       'Gold',
    'tlt':        '20Y+ Treasuries',
    'ftse250':    'FTSE 250',
    'dax':        'DAX',
    'msci_em':    'MSCI EM',
    'msci_world': 'MSCI World',
}

# Order for display
ASSET_ORDER = ['spx', 'spxew', 'ndx', 'rut', 'gold', 'tlt',
               'ftse250', 'dax', 'msci_em', 'msci_world']

# ── Column sets ───────────────────────────────────────────────────────────
# Full detail columns (Water/Octane expanded sections)
DETAIL_COLS = [
    'Strategy', 'Leverage_Max', 'CAGR_pct', 'Vol_pct', 'Sharpe', 'Sortino',
    'Calmar', 'MaxDD_pct', 'End_Value', 'Start_Date', 'End_Date', 'Years',
    'Pct_Cash_Time', 'Trades_Per_Year', 'Total_Trades', 'Avg_Leverage',
]

# Collapsed "Neither" columns
NEITHER_COLS = ['Strategy', 'MaxDD_pct']

# Summary columns
SUMMARY_COLS = [
    'Asset', 'Total_Strategies', 'Water_Count', 'Octane_Count',
    'Neither_Count', 'Best_Water_Strategy', 'Best_Water_CAGR',
    'Best_Octane_Strategy', 'Best_Octane_Calmar',
    'BH_1x_CAGR', 'BH_1x_MaxDD',
]

# ── Number format mapping ─────────────────────────────────────────────────
# (column_name, openpyxl number_format)
NUMBER_FORMATS = {
    'CAGR_pct':        '0.00%',
    'Vol_pct':         '0.00%',
    'MaxDD_pct':       '0.00%',
    'Pct_Cash_Time':   '0.00%',
    'Sharpe':          '0.000',
    'Sortino':         '0.000',
    'Calmar':          '0.000',
    'Avg_Leverage':    '0.000',
    'Trades_Per_Year': '0.000',
    'End_Value':       '$#,##0',
    'Total_Trades':    '0',
    'Years':           '0.0',
    'Leverage_Max':    '0.0',
    'BH_1x_CAGR':      '0.00%',
    'BH_1x_MaxDD':     '0.00%',
    'Best_Water_CAGR': '0.00%',
    'Best_Octane_Calmar': '0.000',
}

# ── Styles ─────────────────────────────────────────────────────────────────
HEADER_FILL = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
HEADER_FONT = Font(name='Calibri', size=11, bold=True, color='FFFFFF')
BH_FILL = PatternFill(start_color='BDD7EE', end_color='BDD7EE', fill_type='solid')  # light blue
BH_FONT = Font(name='Calibri', size=11, bold=True)
WATER_FILL = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')  # light green
OCTANE_FILL = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')  # light green
NEITHER_FILL = PatternFill(start_color='D9D9D9', end_color='D9D9D9', fill_type='solid')  # light gray
NEITHER_FONT = Font(name='Calibri', size=11, italic=True, color='808080')
NORMAL_FONT = Font(name='Calibri', size=11)
THIN_BORDER = Border(
    left=Side(style='thin', color='D0D0D0'),
    right=Side(style='thin', color='D0D0D0'),
    top=Side(style='thin', color='D0D0D0'),
    bottom=Side(style='thin', color='D0D0D0'),
)


def load_all_data():
    """Load the combined CSV and return a DataFrame with Asset column."""
    csv_path = CSV_DIR / 'all_assets_combined.csv'
    if not csv_path.exists():
        # Fall back to reading individual CSVs and combining
        print("Combined CSV not found, building from individual CSVs...", flush=True)
        frames = []
        for asset_key in ASSET_ORDER:
            fpath = CSV_DIR / f'{asset_key}_results.csv'
            if fpath.exists():
                df = pd.read_csv(fpath)
                df.insert(0, 'Asset', asset_key)
                frames.append(df)
                print(f"  Loaded {asset_key}: {len(df)} rows", flush=True)
        if not frames:
            raise FileNotFoundError(f"No CSV files found in {CSV_DIR}")
        df = pd.concat(frames, ignore_index=True)
    else:
        df = pd.read_csv(csv_path)
        print(f"Loaded combined CSV: {len(df)} rows, {df['Asset'].nunique()} assets", flush=True)

    # Ensure numeric columns are numeric
    numeric_cols = ['Leverage_Max', 'CAGR_pct', 'Vol_pct', 'Sharpe', 'Sortino',
                    'Calmar', 'MaxDD_pct', 'End_Value', 'Years', 'Pct_Cash_Time',
                    'Trades_Per_Year', 'Total_Trades', 'Avg_Leverage',
                    'Beat_BH_Sharpe', 'Beat_BH_Calmar', 'Beat_BH_DD', 'Beat_BH_CAGR']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    return df


def is_bh_row(strategy_name):
    """Check if a row is a Buy & Hold benchmark."""
    return isinstance(strategy_name, str) and strategy_name.startswith('Buy & Hold')


def classify_strategy(row):
    """Classify a single strategy row as 'Water', 'Octane', or 'Neither'.

    Uses the pre-computed Beat_BH_* columns which already compare against
    the same-leverage B&H benchmark.

    Water (ALL 4):
      - Beat_BH_Sharpe == 1
      - Beat_BH_Calmar == 1
      - Beat_BH_DD == 1
      - Beat_BH_CAGR == 1

    Octane (ALL 3):
      - Beat_BH_Calmar == 1
      - MaxDD_pct >= -45.0
      - Trades_Per_Year <= 20

    If both qualify → Water (more prestigious).
    """
    if is_bh_row(row.get('Strategy', '')):
        return 'Benchmark'

    water = (int(row.get('Beat_BH_Sharpe', 0)) == 1
             and int(row.get('Beat_BH_Calmar', 0)) == 1
             and int(row.get('Beat_BH_DD', 0)) == 1
             and int(row.get('Beat_BH_CAGR', 0)) == 1)

    octane = (int(row.get('Beat_BH_Calmar', 0)) == 1
              and float(row.get('MaxDD_pct', -999)) >= -45.0
              and float(row.get('Trades_Per_Year', 999)) <= 20.0)

    if water:
        return 'Water'
    elif octane:
        return 'Octane'
    else:
        return 'Neither'


def classify_all(df):
    """Add classification column to dataframe."""
    df = df.copy()
    df['Classification'] = df.apply(classify_strategy, axis=1)
    return df


def build_summary_sheet(wb, df):
    """Build the Summary sheet with per-asset overview."""
    ws = wb.active
    ws.title = 'Summary'

    # Build summary data
    summary_rows = []
    for asset_key in ASSET_ORDER:
        asset_label = ASSET_LABELS[asset_key]
        asset_df = df[df['Asset'] == asset_key]

        # Exclude B&H rows from strategy counts
        strategies_df = asset_df[~asset_df['Strategy'].apply(is_bh_row)]
        total = len(strategies_df)
        water_count = (strategies_df['Classification'] == 'Water').sum()
        octane_count = (strategies_df['Classification'] == 'Octane').sum()
        neither_count = (strategies_df['Classification'] == 'Neither').sum()

        # Best Water strategy (by CAGR)
        water_df = strategies_df[strategies_df['Classification'] == 'Water']
        if len(water_df) > 0:
            best_water = water_df.loc[water_df['CAGR_pct'].idxmax()]
            best_water_name = best_water['Strategy']
            best_water_cagr = best_water['CAGR_pct']
        else:
            best_water_name = '—'
            best_water_cagr = None

        # Best Octane strategy (by Calmar, excluding Water)
        octane_df = strategies_df[strategies_df['Classification'] == 'Octane']
        if len(octane_df) > 0:
            best_octane = octane_df.loc[octane_df['Calmar'].idxmax()]
            best_octane_name = best_octane['Strategy']
            best_octane_calmar = best_octane['Calmar']
        else:
            best_octane_name = '—'
            best_octane_calmar = None

        # B&H 1x stats
        bh_1x = asset_df[asset_df['Strategy'] == 'Buy & Hold 1x']
        if len(bh_1x) > 0:
            bh_1x_cagr = bh_1x.iloc[0]['CAGR_pct']
            bh_1x_maxdd = bh_1x.iloc[0]['MaxDD_pct']
        else:
            bh_1x_cagr = None
            bh_1x_maxdd = None

        summary_rows.append({
            'Asset': asset_label,
            'Total_Strategies': total,
            'Water_Count': water_count,
            'Octane_Count': octane_count,
            'Neither_Count': neither_count,
            'Best_Water_Strategy': best_water_name,
            'Best_Water_CAGR': best_water_cagr,
            'Best_Octane_Strategy': best_octane_name,
            'Best_Octane_Calmar': best_octane_calmar,
            'BH_1x_CAGR': bh_1x_cagr,
            'BH_1x_MaxDD': bh_1x_maxdd,
        })

    # Write header
    for col_idx, col_name in enumerate(SUMMARY_COLS, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = THIN_BORDER

    # Write data
    for row_idx, row_data in enumerate(summary_rows, 2):
        for col_idx, col_name in enumerate(SUMMARY_COLS, 1):
            val = row_data.get(col_name)
            cell = ws.cell(row=row_idx, column=col_idx, value=val if val is not None else '')
            cell.font = NORMAL_FONT
            cell.border = THIN_BORDER
            cell.alignment = Alignment(horizontal='center' if col_idx > 1 else 'left')

            # Number formatting
            fmt = NUMBER_FORMATS.get(col_name)
            if fmt and val is not None:
                cell.number_format = fmt

    # Freeze panes
    ws.freeze_panes = 'A2'

    # Auto-fit column widths
    auto_fit_columns(ws)

    # Conditional formatting: highlight best values
    # Best Water CAGR (column 7)
    if len(summary_rows) > 1:
        last_data_row = len(summary_rows) + 1
        ws.conditional_formatting.add(
            f'G2:G{last_data_row}',
            FormulaRule(
                formula=[f'G2=MAX($G$2:$G${last_data_row})'],
                fill=PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid'),
                font=Font(bold=True)
            )
        )
        # Best Octane Calmar (column 9)
        ws.conditional_formatting.add(
            f'I2:I{last_data_row}',
            FormulaRule(
                formula=[f'I2=MAX($I$2:$I${last_data_row})'],
                fill=PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid'),
                font=Font(bold=True)
            )
        )

    print(f"  Summary sheet: {len(summary_rows)} assets", flush=True)
    return ws


def build_detail_sheet(wb, df, asset_key, classification):
    """Build a Water or Octane detail sheet for a single asset.

    Args:
        classification: 'Water' or 'Octane'
    """
    asset_label = ASSET_LABELS[asset_key]
    sheet_name = f'{asset_label} {classification}'
    # Truncate sheet name to 31 chars (Excel limit)
    if len(sheet_name) > 31:
        sheet_name = sheet_name[:31]

    ws = wb.create_sheet(title=sheet_name)

    asset_df = df[df['Asset'] == asset_key].copy()

    # Separate B&H rows, qualifying rows, and neither rows
    bh_rows = asset_df[asset_df['Strategy'].apply(is_bh_row)]
    strategies_df = asset_df[~asset_df['Strategy'].apply(is_bh_row)]

    if classification == 'Water':
        qualifying = strategies_df[strategies_df['Classification'] == 'Water']
        # Neither = everything not Water (including Octane and Neither)
        neither = strategies_df[strategies_df['Classification'] != 'Water']
        sort_col = 'Sharpe'
        sort_ascending = False
    else:  # Octane
        # Exclude strategies already classified as Water
        qualifying = strategies_df[strategies_df['Classification'] == 'Octane']
        neither = strategies_df[~strategies_df['Classification'].isin(['Water', 'Octane'])]
        sort_col = 'Calmar'
        sort_ascending = False

    # Sort qualifying strategies
    qualifying = qualifying.sort_values(sort_col, ascending=sort_ascending)
    # Sort neither by MaxDD (worst first = most negative first)
    neither = neither.sort_values('MaxDD_pct', ascending=True)

    current_row = 1

    # ── Section A header ──
    section_label = f'{asset_label} — {classification} Strategies'
    cell = ws.cell(row=current_row, column=1, value=section_label)
    cell.font = Font(name='Calibri', size=14, bold=True, color='1F4E79')
    ws.merge_cells(start_row=current_row, start_column=1,
                   end_row=current_row, end_column=len(DETAIL_COLS))
    current_row += 1

    # ── B&H benchmark rows ──
    cell = ws.cell(row=current_row, column=1, value='Benchmarks (Buy & Hold):')
    cell.font = Font(name='Calibri', size=11, bold=True, italic=True)
    ws.merge_cells(start_row=current_row, start_column=1,
                   end_row=current_row, end_column=len(DETAIL_COLS))
    current_row += 1

    # Write detail header
    for col_idx, col_name in enumerate(DETAIL_COLS, 1):
        cell = ws.cell(row=current_row, column=col_idx, value=col_name)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = THIN_BORDER
    current_row += 1

    # Write B&H rows
    bh_sorted = bh_rows.sort_values('Leverage_Max', ascending=True)
    for _, bh_row in bh_sorted.iterrows():
        for col_idx, col_name in enumerate(DETAIL_COLS, 1):
            val = bh_row.get(col_name)
            cell = ws.cell(row=current_row, column=col_idx, value=val if pd.notna(val) else '')
            cell.font = BH_FONT
            cell.fill = BH_FILL
            cell.border = THIN_BORDER
            fmt = NUMBER_FORMATS.get(col_name)
            if fmt and pd.notna(val):
                cell.number_format = fmt
        current_row += 1

    # ── Qualifying strategies ──
    current_row += 1  # blank separator row
    qual_label = f'{classification} Strategies ({len(qualifying)}):'
    cell = ws.cell(row=current_row, column=1, value=qual_label)
    cell.font = Font(name='Calibri', size=11, bold=True, color='375623')
    ws.merge_cells(start_row=current_row, start_column=1,
                   end_row=current_row, end_column=len(DETAIL_COLS))
    current_row += 1

    # Re-write header for qualifying section
    for col_idx, col_name in enumerate(DETAIL_COLS, 1):
        cell = ws.cell(row=current_row, column=col_idx, value=col_name)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = THIN_BORDER
    current_row += 1

    qual_start_row = current_row
    for _, q_row in qualifying.iterrows():
        for col_idx, col_name in enumerate(DETAIL_COLS, 1):
            val = q_row.get(col_name)
            cell = ws.cell(row=current_row, column=col_idx, value=val if pd.notna(val) else '')
            cell.font = NORMAL_FONT
            cell.fill = WATER_FILL if classification == 'Water' else OCTANE_FILL
            cell.border = THIN_BORDER
            fmt = NUMBER_FORMATS.get(col_name)
            if fmt and pd.notna(val):
                cell.number_format = fmt
        current_row += 1
    qual_end_row = current_row - 1

    # ── Neither strategies (collapsed) ──
    current_row += 1  # blank separator
    neither_label = f'Neither Strategies ({len(neither)}) — collapsed (Strategy + MaxDD only):'
    cell = ws.cell(row=current_row, column=1, value=neither_label)
    cell.font = Font(name='Calibri', size=11, bold=True, color='808080')
    ws.merge_cells(start_row=current_row, start_column=1,
                   end_row=current_row, end_column=len(NEITHER_COLS))
    current_row += 1

    # Neither header
    for col_idx, col_name in enumerate(NEITHER_COLS, 1):
        cell = ws.cell(row=current_row, column=col_idx, value=col_name)
        cell.font = Font(name='Calibri', size=11, bold=True, color='595959')
        cell.fill = PatternFill(start_color='BFBFBF', end_color='BFBFBF', fill_type='solid')
        cell.border = THIN_BORDER
    current_row += 1

    neither_start_row = current_row
    for _, n_row in neither.iterrows():
        for col_idx, col_name in enumerate(NEITHER_COLS, 1):
            val = n_row.get(col_name)
            cell = ws.cell(row=current_row, column=col_idx, value=val if pd.notna(val) else '')
            cell.font = NEITHER_FONT
            cell.fill = NEITHER_FILL
            cell.border = THIN_BORDER
            fmt = NUMBER_FORMATS.get(col_name)
            if fmt and pd.notna(val):
                cell.number_format = fmt
        current_row += 1
    neither_end_row = current_row - 1

    # Group/collapse neither rows using Excel outline
    if neither_end_row >= neither_start_row:
        ws.row_dimensions.group(neither_start_row, neither_end_row, outline_level=1)

    # ── Conditional formatting: highlight best in each metric column ──
    if qual_end_row >= qual_start_row:
        # Columns to highlight (1-based indices in DETAIL_COLS)
        # CAGR_pct=3, Vol_pct=4 (lower is better), Sharpe=5, Sortino=6,
        # Calmar=7, MaxDD_pct=8 (higher/less negative is better),
        # End_Value=9, Pct_Cash_Time=13 (lower is better),
        # Trades_Per_Year=14 (lower is better), Avg_Leverage=16
        highlight_cols_green = {
            3: 'max',   # CAGR — higher is better
            5: 'max',   # Sharpe — higher is better
            6: 'max',   # Sortino — higher is better
            7: 'max',   # Calmar — higher is better
            8: 'max',   # MaxDD — less negative is better
            9: 'max',   # End_Value — higher is better
        }
        highlight_cols_red = {
            4: 'min',   # Vol — lower is better
            13: 'min',  # Pct_Cash_Time — lower is better
            14: 'min',  # Trades_Per_Year — lower is better
        }

        for col_idx, mode in highlight_cols_green.items():
            col_letter = get_column_letter(col_idx)
            rng = f'{col_letter}{qual_start_row}:{col_letter}{qual_end_row}'
            if mode == 'max':
                ws.conditional_formatting.add(
                    rng,
                    FormulaRule(
                        formula=[f'{col_letter}{qual_start_row}=MAX(${col_letter}${qual_start_row}:${col_letter}${qual_end_row})'],
                        fill=PatternFill(start_color='00B050', end_color='00B050', fill_type='solid'),
                        font=Font(bold=True, color='FFFFFF')
                    )
                )
            else:
                ws.conditional_formatting.add(
                    rng,
                    FormulaRule(
                        formula=[f'{col_letter}{qual_start_row}=MIN(${col_letter}${qual_start_row}:${col_letter}${qual_end_row})'],
                        fill=PatternFill(start_color='00B050', end_color='00B050', fill_type='solid'),
                        font=Font(bold=True, color='FFFFFF')
                    )
                )

        for col_idx, mode in highlight_cols_red.items():
            col_letter = get_column_letter(col_idx)
            rng = f'{col_letter}{qual_start_row}:{col_letter}{qual_end_row}'
            if mode == 'min':
                ws.conditional_formatting.add(
                    rng,
                    FormulaRule(
                        formula=[f'{col_letter}{qual_start_row}=MIN(${col_letter}${qual_start_row}:${col_letter}${qual_end_row})'],
                        fill=PatternFill(start_color='FF4444', end_color='FF4444', fill_type='solid'),
                        font=Font(bold=True, color='FFFFFF')
                    )
                )
            else:
                ws.conditional_formatting.add(
                    rng,
                    FormulaRule(
                        formula=[f'{col_letter}{qual_start_row}=MAX(${col_letter}${qual_start_row}:${col_letter}${qual_end_row})'],
                        fill=PatternFill(start_color='FF4444', end_color='FF4444', fill_type='solid'),
                        font=Font(bold=True, color='FFFFFF')
                    )
                )

    # Freeze panes (row 4, after section header + B&H header)
    ws.freeze_panes = 'A4'

    # Auto-fit columns
    auto_fit_columns(ws)

    print(f"  Sheet '{sheet_name}': {len(qualifying)} {classification}, "
          f"{len(neither)} neither", flush=True)
    return ws


def auto_fit_columns(ws, min_width=8, max_width=40):
    """Auto-fit column widths based on content."""
    for col_cells in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col_cells[0].column)
        for cell in col_cells:
            if cell.value:
                # Estimate width: count characters, adjust for number formats
                val_str = str(cell.value)
                # Rough adjustment: each char ~1.1 units, add padding
                cell_len = len(val_str) * 1.1 + 2
                if cell_len > max_len:
                    max_len = cell_len
        adjusted = max(min_width, min(max_len, max_width))
        ws.column_dimensions[col_letter].width = adjusted


def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    print("=" * 70, flush=True)
    print("BUILDING STRATEGY RESULTS EXCEL WORKBOOK", flush=True)
    print("=" * 70, flush=True)

    # ── Step 1: Load data ──
    print("\n[1/5] Loading CSV data...", flush=True)
    df = load_all_data()
    print(f"  Total rows: {len(df)}", flush=True)
    print(f"  Assets: {sorted(df['Asset'].unique())}", flush=True)

    # ── Step 2: Classify ──
    print("\n[2/5] Classifying strategies (Water / Octane / Neither)...", flush=True)
    df = classify_all(df)

    # Print classification summary
    for asset_key in ASSET_ORDER:
        asset_df = df[df['Asset'] == asset_key]
        strats = asset_df[~asset_df['Strategy'].apply(is_bh_row)]
        w = (strats['Classification'] == 'Water').sum()
        o = (strats['Classification'] == 'Octane').sum()
        n = (strats['Classification'] == 'Neither').sum()
        print(f"  {ASSET_LABELS[asset_key]:20s}: {len(strats):2d} strategies -> "
              f"Water={w}, Octane={o}, Neither={n}", flush=True)

    # ── Step 3: Create workbook ──
    print("\n[3/5] Creating Excel workbook...", flush=True)
    wb = openpyxl.Workbook()

    # ── Step 4: Build sheets ──
    print("\n[4/5] Building sheets...", flush=True)

    # Summary sheet
    print("  Building Summary sheet...", flush=True)
    build_summary_sheet(wb, df)

    # Detail sheets (Water + Octane per asset)
    for asset_key in ASSET_ORDER:
        for classification in ['Water', 'Octane']:
            build_detail_sheet(wb, df, asset_key, classification)

    # ── Step 5: Save ──
    print("\n[5/5] Saving workbook...", flush=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    wb.save(EXCEL_PATH)
    print(f"  Saved to: {EXCEL_PATH}", flush=True)
    print(f"  File size: {EXCEL_PATH.stat().st_size:,} bytes", flush=True)
    print(f"  Sheets: {len(wb.sheetnames)}", flush=True)

    # ── Final report ──
    print("\n" + "=" * 70, flush=True)
    print("BUILD COMPLETE", flush=True)
    print("=" * 70, flush=True)

    # Summary statistics
    strategies_df = df[~df['Strategy'].apply(is_bh_row)]
    total_strategies = len(strategies_df)
    total_water = (strategies_df['Classification'] == 'Water').sum()
    total_octane = (strategies_df['Classification'] == 'Octane').sum()
    total_neither = (strategies_df['Classification'] == 'Neither').sum()

    print(f"\nOverall Statistics:")
    print(f"  Total strategies (excl. B&H): {total_strategies}")
    print(f"  Water:  {total_water}")
    print(f"  Octane: {total_octane}")
    print(f"  Neither: {total_neither}")
    print(f"  Sheets: {len(wb.sheetnames)} (1 Summary + 20 detail)")

    # Top Water strategies overall
    water_df = strategies_df[strategies_df['Classification'] == 'Water']
    if len(water_df) > 0:
        print(f"\nTop 5 Water Strategies (by Sharpe):")
        top_water = water_df.nlargest(5, 'Sharpe')
        for _, r in top_water.iterrows():
            print(f"  {r['Asset']:10s} | {r['Strategy']:45s} | "
                  f"Sharpe={r['Sharpe']:.3f} | CAGR={r['CAGR_pct']:.2f}% | "
                  f"MaxDD={r['MaxDD_pct']:.2f}%")

    # Top Octane strategies overall
    octane_df = strategies_df[strategies_df['Classification'] == 'Octane']
    if len(octane_df) > 0:
        print(f"\nTop 5 Octane Strategies (by Calmar):")
        top_octane = octane_df.nlargest(5, 'Calmar')
        for _, r in top_octane.iterrows():
            print(f"  {r['Asset']:10s} | {r['Strategy']:45s} | "
                  f"Calmar={r['Calmar']:.3f} | CAGR={r['CAGR_pct']:.2f}% | "
                  f"MaxDD={r['MaxDD_pct']:.2f}%")

    print(f"\nExcel location: {EXCEL_PATH}")
    print("Done.", flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)
