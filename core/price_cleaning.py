"""Conservative single-day round-trip price-spike filter, shared by the backtest writers.

This mirrors ``update_static_market_data.clean_price_spikes`` (the live cron updater) exactly,
so the two code paths that fetch daily closes from Yahoo scrub the same class of bad upstream
ticks before they can reach a ``*_daily.csv`` or a ``*_site_data.json``:

  (a) the cron updater ``update_static_market_data.py`` (round-trip filter already applied), and
  (b) the per-asset backtest scripts (``backtest_guarded_assets.py`` and friends), which load
      via ``yfinance`` and previously had no spike guard.

A "spike" is a single close that jumps more than ``jump`` away from BOTH neighbours in the same
direction AND reverts on the next session (e.g. a 1x index printing +34% then snapping back). It
is replaced with the mean of its two neighbours. Sustained real moves -- a 3x ETP down ~53% in
the Brexit week and *staying* down, or MSCI World's non-reverting 2009 inception cliff -- do not
revert, so they are left untouched. Neighbours are always read from the ORIGINAL series, never
from already-cleaned values, so a short run of bad ticks cannot cascade.

Keep this in sync with the updater; ``test_price_cleaning.py`` asserts the two agree.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps this module pandas-free at import time
    import pandas as pd

# Same thresholds as update_static_market_data.clean_price_spikes.
DEFAULT_JUMP = 0.25
DEFAULT_REVERT = 0.20


def clean_spike_values(
    values: Sequence[float],
    *,
    jump: float = DEFAULT_JUMP,
    revert: float = DEFAULT_REVERT,
) -> list[float]:
    """Round-trip spike filter over a plain sequence of floats (standard library only).

    Returns a new ``list`` -- the input is not mutated. Interior points only; the first and last
    samples are never altered (they have no pair of neighbours to round-trip against).
    """
    out = [float(v) for v in values]
    n = len(out)
    if n < 3:
        return out
    original = list(out)
    for i in range(1, n - 1):
        prev = original[i - 1]
        cur = original[i]
        nxt = original[i + 1]
        if prev <= 0 or nxt <= 0:
            continue
        spike_up = cur > prev * (1 + jump) and cur > nxt * (1 + revert)
        spike_down = cur < prev * (1 - jump) and cur < nxt * (1 - revert)
        if spike_up or spike_down:
            out[i] = (prev + nxt) / 2.0
    return out


def clean_close_series(
    close: "pd.Series",
    *,
    jump: float = DEFAULT_JUMP,
    revert: float = DEFAULT_REVERT,
) -> "pd.Series":
    """pandas wrapper: scrub a Close-price Series, preserving its index and name.

    Used by the backtest ``download_*_panel`` loaders right after the panel is assembled, so the
    daily CSV and site JSON they emit cannot carry a re-introduced single-day Yahoo glitch.
    """
    import pandas as pd

    cleaned = clean_spike_values(close.to_numpy(dtype=float).tolist(), jump=jump, revert=revert)
    return pd.Series(cleaned, index=close.index, name=close.name)
