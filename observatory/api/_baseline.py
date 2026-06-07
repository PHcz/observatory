"""%-of-baseline normalisation (Phase 13, MU2-06) — pure function, no DB.

Normalises a series to a percentage of its own baseline so that two series with
very different absolute scales (NMDB neutron counts/s vs local muon wall-clock
rate/min) line up on a shared axis: a Forbush dip then appears as the same
downward excursion in both.

Baseline = the **median over the non-null values** of the window. Median (not
mean) is robust to the local detector's Poisson spikes and to NMDB gaps. ``pct =
100 * value / baseline``; ``None`` (gap) passes through as ``None`` so the
dashboard line breaks; an empty list returns ``[]``.

``BASELINE_WINDOW_DAYS`` is a config constant documenting a v1 simplification: the
canonical Forbush baseline is a ~27-day (one solar rotation) climatology, but the
home DB will not have 27 days of muon data for a long time and the dashboard
window is 7 days. A trailing 7-day median is a defensible, computable
approximation that still makes a Forbush dip legible; grow this once data
accumulates.
"""

from __future__ import annotations

import statistics
from typing import Final

# v1 simplification of the canonical 27-day Forbush baseline (research §%-of-baseline).
BASELINE_WINDOW_DAYS: Final[int] = 7


def pct_of_baseline(values: list[float | None]) -> list[float | None]:
    """Normalise a series to % of its median baseline.

    Args:
        values: the series, with ``None`` for gaps.

    Returns:
        A list the same length as ``values`` where each present value is
        ``100 * value / median(non-null values)`` and each gap stays ``None``.
        An empty input returns ``[]``; an all-``None`` input returns all
        ``None`` (no baseline computable).
    """
    present = [v for v in values if v is not None]
    if not present:
        return [None for _ in values]
    baseline = statistics.median(present)
    if baseline == 0:
        return [None for _ in values]
    return [None if v is None else 100.0 * v / baseline for v in values]
