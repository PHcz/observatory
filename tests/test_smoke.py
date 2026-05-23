"""Smoke test: verifies the test infrastructure is importable.

This minimal test ensures `pytest --collect-only` exits 0, confirming that
pytest, the test package, and conftest.py all load correctly.
"""


def test_infrastructure_importable() -> None:
    """Placeholder test confirming pytest infrastructure is working."""
    assert True
