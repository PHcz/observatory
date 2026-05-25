"""One-shot probe: does BGS support https for the feeds endpoint?

Run manually:

    uv run pytest tests/pollers/bgs/test_https_probe.py -m network -s

The result is committed to ``tests/pollers/bgs/HTTPS_PROBE_RESULT.md`` so
future maintainers can see the SEC-05 carve-out justification
(04-RESEARCH Open Question 2).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import httpx
import pytest

RESULT_FILE = Path(__file__).parent / "HTTPS_PROBE_RESULT.md"
HTTPS_URL = "https://earthquakes.bgs.ac.uk/feeds/MhSeismology.xml"


@pytest.mark.network
def test_bgs_https_probe() -> None:
    today = dt.date.today().isoformat()
    try:
        r = httpx.head(HTTPS_URL, timeout=10.0, follow_redirects=False)
        status = r.status_code
        if 200 <= status < 400:
            recommendation = "switch settings default to https"
        else:
            recommendation = f"https returned {status}; keep http and document the carve-out"
        note = f"HTTPS HEAD returned {status}"
    except httpx.HTTPError as exc:
        status = -1
        recommendation = "https unreachable; keep http and document the carve-out"
        note = f"HTTPS HEAD raised {type(exc).__name__}: {exc}"
    RESULT_FILE.write_text(
        "# BGS https probe result\n\n"
        f"- Probed: {today}\n"
        f"- URL: {HTTPS_URL}\n"
        f"- Status: {status}\n"
        f"- Note: {note}\n"
        f"- Recommendation: {recommendation}\n"
    )
    assert True
