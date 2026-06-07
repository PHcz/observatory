"""NMDB / NEST ASCII parser (Phase 13, MU2-06).

Wave-0 RED skeleton: ``parse_nmdb`` raises NotImplementedError. Wave 3 (plan
13-04) implements the strict + per-row-tolerant parse against the pinned NEST
OULU fixture (counts/s absolute, UTC begin-of-interval epoch, ``null`` -> None +
failure-count, empty body -> ValueError).
"""

from __future__ import annotations

from observatory.pollers._types import NmdbCount


def parse_nmdb(body: bytes, station: str) -> tuple[list[NmdbCount], dict]:
    """Parse a NEST ASCII export into NMDB counts + a freshness/meta dict.

    Implemented in Wave 3 (plan 13-04). The Wave-0 skeleton raises so the symbol
    is importable for the RED scaffolds.
    """
    raise NotImplementedError("parse_nmdb is implemented in Wave 3 (plan 13-04)")
