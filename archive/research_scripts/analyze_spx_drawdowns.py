"""S&P 500 drawdown distribution and forward selloff probabilities."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from data_manager import load_backtest_data

OUTPUT_DIR = Path("output") / "spx_drawdown_analysis"

THRESHOLDS_PCT = [3, 5, 7, 10, 15, 20, 25, 30, 35, 40]
HORIZONS = {
    "1d": 1,
    "1w": 5,
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "1y": 252,
}


def drawdown_episodes(close: pd.Series) -> pd.DataFrame:
    peak = close.cummax()
    dd = close / peak - 1.0

    episodes: list[dict] = []
    in_episode = False
    start_date = peak_date = trough_date = None
    start_peak = trough_value = np.nan

    current_peak_date = close.index[0]
    current_peak_value = float(close.iloc[0])

    for dt, price in close.items():
        price = float(price)
        if price >= current_peak_value:
            if in_episode:
                recovery_days = (dt - start_date).days
                trading_days = int(close.loc[start_date:dt].shape[0] - 1)
                episodes.append(
                    {
                        "start_date": start_date.date().isoformat(),
                        "peak_date": peak_date.date().isoformat(),
                        "trough_date": trough_date.date().isoformat(),
                        "recovery_date": dt.date().isoformat(),
                        "depth": trough_value / start_peak - 1.0,
                        "calendar_days_to_recovery": recovery_days,
                        "trading_days_to_recovery": trading_days,
                    }
                )
                in_episode = False

            current_peak_date = dt
            current_peak_value = price
            continue

        if not in_episode:
            in_episode = True
            start_date = dt
            peak_date = current_peak_date
            start_peak = current_peak_value
            trough_date = dt
            trough_value = price
        elif price < trough_value:
            trough_date = dt
            trough_value = price

    if in_episode:
        last_dt = close.index[-1]
        trading_days = int(close.loc[start_date:last_dt].shape[0] - 1)
        episodes.append(
            {
                "start_date": start_date.date().isoformat(),
                "peak_date": peak_date.date().isoformat(),
                "trough_date": trough_date.date().isoformat(),
                "recovery_date": None,
                "depth": trough_value / start_peak - 1.0,
                "calendar_days_to_recovery": None,
                "trading_days_to_recovery": trading_days,
            }
        )

    return pd.DataFrame(episodes)


def forward_selloff_matrix(close: pd.Series) -> pd.DataFrame:
    rows = []
    n = len(close)
    values = close.to_numpy(dtype=float)

    for label, horizon in HORIZONS.items():
        max_selloffs = np.full(n, np.nan)
        for i in range(n - horizon):
            future_min = float(values[i + 1 : i + horizon + 1].min())
            max_selloffs[i] = future_min / values[i] - 1.0

        valid = pd.Series(max_selloffs, index=close.index).dropna()
        for threshold_pct in THRESHOLDS_PCT:
            threshold = threshold_pct / 100.0
            hit = valid <= -threshold
            rows.append(
                {
                    "horizon": label,
                    "trading_days": horizon,
                    "selloff_threshold_pct": threshold_pct,
                    "probability": float(hit.mean()),
                    "observations": int(len(valid)),
                    "events": int(hit.sum()),
                    "median_worst_selloff": float(valid.median()),
                    "p95_worst_selloff": float(valid.quantile(0.05)),
                    "p99_worst_selloff": float(valid.quantile(0.01)),
                }
            )

    return pd.DataFrame(rows)


def state_conditional_probabilities(close: pd.Series) -> pd.DataFrame:
    peak = close.cummax()
    trailing_dd = close / peak - 1.0
    values = close.to_numpy(dtype=float)
    horizon = 21

    max_selloffs = np.full(len(close), np.nan)
    for i in range(len(close) - horizon):
        future_min = float(values[i + 1 : i + horizon + 1].min())
        max_selloffs[i] = future_min / values[i] - 1.0

    states = [
        ("Near high (0 to -2%)", trailing_dd >= -0.02),
        ("Pullback (-2% to -5%)", (trailing_dd < -0.02) & (trailing_dd >= -0.05)),
        ("Dip (-5% to -10%)", (trailing_dd < -0.05) & (trailing_dd >= -0.10)),
        ("Correction (-10% to -20%)", (trailing_dd < -0.10) & (trailing_dd >= -0.20)),
        ("Bear drawdown (< -20%)", trailing_dd < -0.20),
    ]

    rows = []
    s = pd.Series(max_selloffs, index=close.index)
    for state_name, mask in states:
        sample = s[mask].dropna()
        if sample.empty:
            continue
        for threshold_pct in [3, 5, 7, 10, 15, 20]:
            threshold = threshold_pct / 100.0
            rows.append(
                {
                    "starting_state": state_name,
                    "horizon": "1m",
                    "selloff_threshold_pct": threshold_pct,
                    "probability": float((sample <= -threshold).mean()),
                    "observations": int(len(sample)),
                }
            )
    return pd.DataFrame(rows)


def daily_drawdown_distribution(close: pd.Series) -> dict:
    dd = close / close.cummax() - 1.0
    thresholds = [0, 2, 5, 10, 15, 20, 30, 40]
    time_below = {
        f"below_{t}pct": float((dd <= -t / 100.0).mean()) for t in thresholds if t > 0
    }
    return {
        "max_drawdown": float(dd.min()),
        "avg_drawdown_when_underwater": float(dd[dd < 0].mean()),
        "median_drawdown_when_underwater": float(dd[dd < 0].median()),
        "pct_days_at_new_high": float((dd == 0).mean()),
        "pct_days_underwater": float((dd < 0).mean()),
        **time_below,
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data = load_backtest_data(years=30)
    close = data["spx_close"].dropna()

    episodes = drawdown_episodes(close)
    forward = forward_selloff_matrix(close)
    state_probs = state_conditional_probabilities(close)
    dist = daily_drawdown_distribution(close)

    episodes.to_csv(OUTPUT_DIR / "spx_drawdown_episodes.csv", index=False)
    forward.to_csv(OUTPUT_DIR / "spx_forward_selloff_probabilities.csv", index=False)
    state_probs.to_csv(OUTPUT_DIR / "spx_state_conditional_1m_selloff_probabilities.csv", index=False)

    recovered = episodes[episodes["recovery_date"].notna()]
    summary = {
        "source": "Yahoo Finance ^GSPC via data_manager.load_backtest_data(years=30)",
        "start_date": close.index[0].date().isoformat(),
        "end_date": close.index[-1].date().isoformat(),
        "trading_days": int(len(close)),
        "close_start": float(close.iloc[0]),
        "close_end": float(close.iloc[-1]),
        "daily_drawdown_distribution": dist,
        "episode_count": int(len(episodes)),
        "recovered_episode_count": int(len(recovered)),
        "episode_depth_quantiles": {
            "median": float(episodes["depth"].median()),
            "p75": float(episodes["depth"].quantile(0.25)),
            "p90": float(episodes["depth"].quantile(0.10)),
            "p95": float(episodes["depth"].quantile(0.05)),
        },
        "top_10_episodes": episodes.sort_values("depth").head(10).to_dict("records"),
        "forward_probability_rows": forward.to_dict("records"),
        "state_conditional_rows": state_probs.to_dict("records"),
    }

    with (OUTPUT_DIR / "spx_drawdown_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(
        f"S&P 500 drawdown analysis: {summary['start_date']} -> {summary['end_date']} "
        f"({summary['trading_days']} trading days)"
    )
    print(f"Max drawdown: {dist['max_drawdown'] * 100:.2f}%")
    print(f"Days underwater: {dist['pct_days_underwater'] * 100:.1f}%")
    print(f"Episodes: {summary['episode_count']} ({summary['recovered_episode_count']} recovered)")
    print(f"Output: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
