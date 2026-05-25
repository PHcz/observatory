"""Smoke test so `pytest tests/muon/ --collect-only` exits 0 (not 5 = no tests).

Real parser/reader tests land in 02-02 and 02-03. Until then this placeholder
keeps the package collectable as part of the Wave-0 contract.
"""

from __future__ import annotations


def test_muon_package_importable() -> None:
    """Confirms tests/muon/ is a real importable package."""
    import tests.muon  # noqa: F401
