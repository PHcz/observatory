"""AuroraWatch UK XML parser — converts current-status.xml into (ts, status, detail).

Closes POLL-06 parse contract and resolves CONTEXT Open Question 4
(``detail`` column gets colon-joined ``project_id:site_id`` for traceability).

Two non-obvious choices made here, both mirroring Phase 4's BGS parser shape:

1. **defusedxml.ElementTree, not the stdlib equivalent.** Repo is public-bound;
   the billion-laughs / external-entity attack surface is closed at parse
   time. bandit B405/B314 cannot complain about defusedxml.
2. **Compact ``+0000`` timezone carve-out.** Live AuroraWatch payloads use the
   compact ``+0000`` form (no colon), which Python 3.11's
   :func:`datetime.fromisoformat` rejects (it requires ``+00:00`` with colon
   or ``Z``). We try strict ISO first (handles ``+00:00`` and ``Z`` directly),
   then fall back to :func:`email.utils.parsedate_to_datetime`, which is
   tolerant of both forms. The carve-out lives at parser level — the shared
   strict-ISO helper stays strict (same discipline as BGS's naive-pubDate
   handling).

Contract:
    ``parse_aurora(body) -> (ts, status, detail)``

Raises :class:`ValueError` on any structural or value-level failure (malformed
XML, missing ``<datetime>`` or ``<site_status>``, unknown ``status_id``,
unparseable datetime). The caller (``__main__``) catches and records a
``poller_runs.status='parse_fail'`` audit row + exit non-zero — the next
timer fire retries (ROADMAP criterion 2: parse failure causes retry log,
not a crash).
"""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import defusedxml.ElementTree as ET

VALID_STATUSES = frozenset({"green", "yellow", "amber", "red"})


def parse_aurora(body: bytes) -> tuple[int, str, str | None]:
    """Parse AuroraWatch current-status.xml into ``(ts, status, detail)``.

    Args:
        body: raw XML bytes from
            ``https://aurorawatch-api.lancs.ac.uk/0.2/status/current-status.xml``.

    Returns:
        ``(ts, status, detail)`` where ``ts`` is UTC unix epoch seconds,
        ``status`` is one of ``green | yellow | amber | red``, and ``detail``
        is the colon-joined ``project_id:site_id`` (or ``None`` if both are
        empty).

    Raises:
        ValueError: malformed XML, missing ``<datetime>`` or ``<site_status>``,
            unknown ``status_id``, or unparseable datetime.
    """
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ValueError(f"xml parse failure: {exc}") from exc

    dt_text = (root.findtext("./updated/datetime") or "").strip()
    if not dt_text:
        raise ValueError("missing <updated><datetime>")

    # Strict ISO first (handles +00:00 / Z); fall back to RFC 822 / email.utils
    # which tolerates the compact +0000 form AuroraWatch actually ships.
    try:
        dt = datetime.fromisoformat(dt_text)
    except ValueError:
        try:
            dt = parsedate_to_datetime(dt_text)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"unparseable datetime {dt_text!r}: {exc}") from exc
    if dt.tzinfo is None:
        # email.utils may yield naive on some inputs — treat as UTC
        # (mirrors BGS naive-pubDate carve-out).
        dt = dt.replace(tzinfo=UTC)
    ts = int(dt.astimezone(UTC).timestamp())

    site = root.find("./site_status")
    if site is None:
        raise ValueError("missing <site_status>")
    status = (site.get("status_id") or "").lower()
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status_id: {status!r}")

    project_id = site.get("project_id") or ""
    site_id = site.get("site_id") or ""
    detail = f"{project_id}:{site_id}".strip(":") or None
    return ts, status, detail
