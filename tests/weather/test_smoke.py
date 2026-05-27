"""Phase 3 Wave-0 smoke test — pytest --collect-only stays at exit 0."""

from __future__ import annotations

from collections.abc import Callable


def test_weather_package_importable() -> None:
    import observatory.weather  # noqa: F401


def test_fixtures_present(load_payload: Callable[[str], bytes]) -> None:
    assert load_payload("canonical_payload.json")
