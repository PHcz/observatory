"""Phase 11 — GET /api/air-quality (OAQ-02 read half).

Serves the cached Open-Meteo air-quality snapshot from SQLite. LOCAL-FIRST:
this router NEVER touches any upstream API — only the poller
(``observatory.pollers.airquality``) makes the upstream call. The read side
reads the single ``air_quality`` snapshot row (id=1) plus ``air_quality_meta``
for the freshness anchor.

Empty-state contract (11-RESEARCH Pattern 4 — mirrors forecast, diverges from
the aurora/current 404 idiom): when no poll has run yet the endpoint returns a
valid 200 body with all values null so the panel renders its locked empty state
instead of an error.

Pollen-hidden contract (UI-SPEC): when ALL six pollen values are null the
response sets ``pollen`` to ``None`` so the panel hides the section entirely.
Any other column may be null and propagates through as ``None`` (the panel
renders a per-metric ``—``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from observatory.db.connection import get_conn

router = APIRouter()

_POLLEN_FIELDS = (
    "alder_pollen",
    "birch_pollen",
    "grass_pollen",
    "mugwort_pollen",
    "olive_pollen",
    "ragweed_pollen",
)

_EMPTY_STATE: dict[str, Any] = {
    "aqi": None,
    "pollutants": {
        "pm2_5": None,
        "pm10": None,
        "nitrogen_dioxide": None,
        "ozone": None,
        "sulphur_dioxide": None,
    },
    "pollen": None,
    "uv": None,
    "fetched_at": None,
}


@router.get("/air-quality")
def get_air_quality() -> dict[str, Any]:
    """Return the cached air-quality snapshot from SQLite.

    Response shape::

        {
            "aqi": float | null,             # raw european_aqi; panel maps to band
            "pollutants": {pm2_5, pm10, nitrogen_dioxide, ozone, sulphur_dioxide},
            "pollen": {6 *_pollen values} | null,  # null when all six are null
            "uv": float | null,
            "ts": int,
            "fetched_at": int | null
        }

    Empty cache (no poll yet) -> empty-state 200 body (NOT 404) so the panel
    shows its locked empty state. LOCAL-FIRST: SQLite only, never upstream.
    """
    with get_conn() as conn:
        meta = conn.execute("SELECT fetched_at FROM air_quality_meta WHERE id = 1").fetchone()
        if meta is None:
            # No poll has run yet -> empty-but-valid body (UI-SPEC empty state).
            return dict(_EMPTY_STATE)

        row = conn.execute(
            """
            SELECT ts, european_aqi, pm2_5, pm10, nitrogen_dioxide, ozone,
                   sulphur_dioxide, uv_index, alder_pollen, birch_pollen,
                   grass_pollen, mugwort_pollen, olive_pollen, ragweed_pollen,
                   fetched_at
            FROM air_quality
            WHERE id = 1
            """
        ).fetchone()

        if row is None:
            # Meta present but no snapshot row — treat as empty state.
            return dict(_EMPTY_STATE)

    data = dict(row)

    pollen = {f: data[f] for f in _POLLEN_FIELDS}
    # UI-SPEC pollen-hidden contract: all six null -> hide the section.
    if all(pollen[f] is None for f in _POLLEN_FIELDS):
        pollen_out: dict[str, Any] | None = None
    else:
        pollen_out = pollen

    return {
        "aqi": data["european_aqi"],
        "pollutants": {
            "pm2_5": data["pm2_5"],
            "pm10": data["pm10"],
            "nitrogen_dioxide": data["nitrogen_dioxide"],
            "ozone": data["ozone"],
            "sulphur_dioxide": data["sulphur_dioxide"],
        },
        "pollen": pollen_out,
        "uv": data["uv_index"],
        "ts": data["ts"],
        "fetched_at": meta["fetched_at"],
    }
