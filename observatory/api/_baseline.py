"""%-of-baseline normalisation (Phase 13, MU2-06) — pure function, no DB.

Wave-0 RED skeleton: ``pct_of_baseline`` raises NotImplementedError. Wave 3
(plan 13-04) implements rolling-median normalisation (median over non-null
values; ``pct = 100 * value / baseline``; gaps pass through as None; empty -> []).
"""

from __future__ import annotations


def pct_of_baseline(values: list[float | None]) -> list[float | None]:
    """Normalise a series to % of its rolling-median baseline.

    Implemented in Wave 3 (plan 13-04).
    """
    raise NotImplementedError("pct_of_baseline is implemented in Wave 3 (plan 13-04)")
