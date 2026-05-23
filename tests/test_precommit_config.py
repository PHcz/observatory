"""QA-05 / SEC-01/02 / INFRA-04: .pre-commit-config.yaml contains expected hooks per stage."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG = REPO_ROOT / ".pre-commit-config.yaml"


def _config() -> dict[str, object]:
    return yaml.safe_load(CONFIG.read_text())


def _all_hooks_by_id() -> dict[str, dict[str, object]]:
    cfg = _config()
    out: dict[str, dict[str, object]] = {}
    for repo in cfg["repos"]:  # type: ignore[index]
        for h in repo["hooks"]:
            out[h["id"]] = h
    return out


def test_config_exists() -> None:
    assert CONFIG.is_file()


def test_fast_hooks_on_pre_commit_stage() -> None:
    hooks = _all_hooks_by_id()
    for hid in [
        "gitleaks",
        "ruff",
        "ruff-format",
        "trailing-whitespace",
        "end-of-file-fixer",
        "check-yaml",
        "check-toml",
    ]:
        assert hid in hooks, f"missing hook: {hid}"
        stages = hooks[hid].get("stages", [])
        assert "pre-commit" in stages, f"hook {hid} should be pre-commit, got {stages}"


def test_slow_hooks_on_pre_push_stage() -> None:
    hooks = _all_hooks_by_id()
    for hid in ["mypy", "bandit", "pip-audit", "pytest-collect"]:
        assert hid in hooks, f"missing hook: {hid}"
        stages = hooks[hid].get("stages", [])
        assert "pre-push" in stages, f"hook {hid} should be pre-push, got {stages}"


def test_mypy_runs_strict_on_observatory() -> None:
    hooks = _all_hooks_by_id()
    args = hooks["mypy"]["args"]
    assert "--strict" in args
    assert "observatory/" in args


def test_default_install_hook_types_includes_both() -> None:
    cfg = _config()
    types = cfg.get("default_install_hook_types", [])
    assert "pre-commit" in types
    assert "pre-push" in types


def test_config_is_valid_yaml() -> None:
    # Already implicit if other tests pass, but explicit assertion is cheap
    cfg = _config()
    assert isinstance(cfg, dict)
    assert "repos" in cfg
