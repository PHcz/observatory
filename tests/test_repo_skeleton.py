"""Verify the Phase 1 repo skeleton exists.

Maps to INFRA-03 acceptance.
"""
from __future__ import annotations

import importlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_observatory_package_importable() -> None:
    for mod in [
        "observatory",
        "observatory.api",
        "observatory.muon",
        "observatory.db",
        "observatory.pollers",
        "observatory.pollers.usgs",
        "observatory.pollers.emsc",
        "observatory.pollers.bgs",
        "observatory.pollers.noaa",
        "observatory.pollers.blitzortung",
        "observatory.pollers.aurorawatch",
        "observatory.logging",
    ]:
        importlib.import_module(mod)


def test_deploy_directories_exist() -> None:
    for d in ["deploy/systemd", "deploy/udev", "deploy/mosquitto", "deploy/fstab"]:
        assert (REPO_ROOT / d).is_dir(), f"missing {d}"


def test_scripts_and_migrations_dirs_exist() -> None:
    assert (REPO_ROOT / "scripts").is_dir()
    assert (REPO_ROOT / "migrations").is_dir()


def test_frontend_dir_reserved() -> None:
    assert (REPO_ROOT / "frontend").is_dir()


def test_env_example_documents_all_required_keys() -> None:
    content = (REPO_ROOT / ".env.example").read_text()
    for key in ["HOME_LAT", "HOME_LON", "OBSERVATORY_DB_PATH", "MQTT_HOST", "MQTT_PORT"]:
        assert f"{key}=" in content, f".env.example missing key {key}"


def test_env_example_has_no_inline_comments_on_value_lines() -> None:
    """systemd EnvironmentFile passes inline comments as part of the value."""
    for line in (REPO_ROOT / ".env.example").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            # value side must not contain '#' (would break on Pi)
            assert "#" not in line.split("=", 1)[1], (
                f"Inline comment in .env.example value: {line!r}"
            )
