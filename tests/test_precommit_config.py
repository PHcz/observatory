"""QA-05 / SEC-01/02 / INFRA-04: .pre-commit-config.yaml contains expected hooks per stage."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, cast

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG = REPO_ROOT / ".pre-commit-config.yaml"


def _config() -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(CONFIG.read_text()))


def _all_hooks_by_id() -> dict[str, dict[str, Any]]:
    cfg = _config()
    out: dict[str, dict[str, Any]] = {}
    for repo in cfg["repos"]:
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


def test_mypy_gate_scope_comes_from_pyproject_not_the_hook() -> None:
    """The mypy hook must not restate a narrower scope than pyproject declares.

    It used to pass `[--strict, observatory/]`, checking the package only, while
    [tool.mypy] claimed observatory + tests + scripts + picomuon. Three of the
    four trees were ungated and 20 type errors accumulated under tests/ unseen.
    Restating scope in the gate is what let it drift, so the hook now passes no
    path arguments and inherits them from the config.
    """
    hook = _all_hooks_by_id()["mypy"]
    args = hook.get("args", [])
    paths = [a for a in args if not a.startswith("-")]
    assert not paths, (
        f"mypy hook pins paths {paths}; scope must come from [tool.mypy] in "
        "pyproject.toml so the gate cannot be narrower than the config"
    )


def test_mypy_config_is_strict_over_every_source_tree() -> None:
    """Strictness and scope now live in pyproject, so assert them there."""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    mypy_cfg = pyproject["tool"]["mypy"]
    assert mypy_cfg.get("strict") is True, "mypy must run strict"
    files = mypy_cfg.get("files", [])
    for tree in ("observatory", "tests", "scripts", "picomuon"):
        assert tree in files, f"{tree} is not covered by [tool.mypy] files: {files}"


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
