"""Regression tests for the shared round-trip spike filter (price_cleaning).

Covers the three things that matter for data durability:
  1. It stays byte-for-byte equivalent to the live cron updater's clean_price_spikes.
  2. It removes a genuine single-day round-trip spike but leaves sustained moves alone.
  3. It is a no-op on every committed *_daily.csv (the current series are already clean).

Runs under pytest, or standalone: ``python test_price_cleaning.py``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from price_cleaning import clean_close_series, clean_spike_values

ROOT = Path(__file__).resolve().parent
DAILY_CSVS = sorted(ROOT.glob("*_daily.csv"))


def _spike_series():
    # A clean ramp with one +34% round-trip blip on day 3 and a sustained -53% step on day 7.
    base = [100.0, 101.0, 135.0, 102.0, 103.0, 104.0, 49.0, 48.5, 49.5, 50.0]
    return base


def test_matches_updater_clean_price_spikes():
    """clean_spike_values must agree with update_static_market_data.clean_price_spikes."""
    try:
        from update_static_market_data import clean_price_spikes
    except Exception as exc:  # pragma: no cover - env without zoneinfo/tzdata
        import pytest

        pytest.skip(f"could not import updater module: {exc}")

    samples = [
        _spike_series(),
        [100.0, 100.0, 100.0],
        [10.0, 200.0, 9.0, 9.5, 9.2],          # up spike that reverts
        [50.0, 5.0, 52.0, 51.0],               # down spike that reverts
        [100.0, 90.0, 47.0, 46.0, 46.5, 47.0], # sustained drop (Brexit-like), must be untouched
    ]
    for values in samples:
        rows = [{"date": f"2020-01-{i + 1:02d}", "close": v} for i, v in enumerate(values)]
        updater_out = [float(r["close"]) for r in clean_price_spikes(rows)]
        ours = clean_spike_values(values)
        assert ours == updater_out, (values, ours, updater_out)


def test_removes_roundtrip_spike_keeps_sustained_move():
    values = _spike_series()
    cleaned = clean_spike_values(values)
    # Day 3 round-trip blip (135 between 101 and 102) is replaced with the neighbour mean.
    assert cleaned[2] == (101.0 + 102.0) / 2.0
    # The sustained -53% step (104 -> 49 and staying ~49) does NOT revert, so it is preserved.
    assert cleaned[6] == 49.0
    assert cleaned[7] == 48.5
    # First/last samples are never touched.
    assert cleaned[0] == values[0]
    assert cleaned[-1] == values[-1]


def test_noop_on_committed_daily_csvs():
    assert DAILY_CSVS, "expected at least one *_daily.csv in the repo root"
    for path in DAILY_CSVS:
        df = pd.read_csv(path)
        close = df["Close"].astype(float)
        cleaned = clean_close_series(close)
        changed = (cleaned.to_numpy() != close.to_numpy()).sum()
        assert changed == 0, f"{path.name}: filter changed {changed} rows (expected a no-op)"


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except Exception as exc:  # noqa: BLE001 - surface any failure in the standalone runner
                failures += 1
                print(f"FAIL  {name}: {exc}")
    print(f"\n{'-' * 40}\n{'ALL PASSED' if not failures else f'{failures} FAILED'}")
    raise SystemExit(1 if failures else 0)
