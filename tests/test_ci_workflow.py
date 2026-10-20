"""CI workflow guards (security audit 2026-10-20, M11).

Nothing used to run the test suite before code merged. These pin the properties
that make the workflow both useful and safe, not merely its existence.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"


def _wf() -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(WORKFLOW.read_text()))


def _steps() -> list[dict[str, Any]]:
    return [step for job in _wf()["jobs"].values() for step in job["steps"]]


def test_runs_the_real_suites_not_just_collection() -> None:
    runs = " ".join(str(s.get("run", "")) for s in _steps())
    assert "uv run pytest" in runs and "--collect-only" not in runs
    assert "npm run test:unit" in runs
    assert "uv run mypy" in runs


def test_third_party_actions_pinned_to_commit_shas() -> None:
    """A tag can be re-pointed at different code; a 40-hex SHA cannot."""
    for step in _steps():
        uses = step.get("uses")
        if uses:
            assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", uses), f"not SHA-pinned: {uses}"


def test_token_is_read_only() -> None:
    assert _wf()["permissions"] == {"contents": "read"}


def test_checkout_does_not_persist_credentials() -> None:
    for step in _steps():
        if str(step.get("uses", "")).startswith("actions/checkout@"):
            assert step.get("with", {}).get("persist-credentials") is False


def test_installs_from_lockfiles_only() -> None:
    runs = " ".join(str(s.get("run", "")) for s in _steps())
    assert "uv sync --frozen" in runs
    assert "npm ci" in runs
