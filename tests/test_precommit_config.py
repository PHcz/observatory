"""QA-05 / SEC-01/02 / INFRA-04: .pre-commit-config.yaml contains expected hooks per stage."""

from __future__ import annotations

import secrets
import shutil
import string
import subprocess
import tomllib
from pathlib import Path
from typing import Any, cast

import pytest
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


# Hooks for tools that pyproject.toml also version-pins. Each one must take its
# version from the project venv, never from a second pin in this config.
_PROJECT_VENV_HOOKS = ("ruff", "ruff-format", "mypy", "bandit", "pip-audit")
_DUAL_PINNED_TOOLS = ("ruff", "mypy", "bandit", "pip-audit")


def test_tool_hooks_run_from_the_project_venv() -> None:
    """A hook and a local run of the same tool must be the same binary.

    Every one of these previously carried its own `rev:`, hand-synced against a
    floor in pyproject. They drifted: bandit sat at 1.8.3 against >=1.9.4, and
    pip-audit at v2.8.0 against >=2.10.1, while Dependabot moved the ruff floor
    without touching its rev because it cannot see the coupling. Two versions of
    one tool is the bug; running from the venv removes the second one.
    """
    hooks = _all_hooks_by_id()
    for hid in _PROJECT_VENV_HOOKS:
        assert hid in hooks, f"missing hook: {hid}"
        hook = hooks[hid]
        assert hook.get("language") == "system", (
            f"hook {hid} must run in the project venv (language: system), "
            f"got language={hook.get('language')!r}"
        )
        entry = str(hook.get("entry", ""))
        assert entry.startswith("uv run "), (
            f"hook {hid} must invoke the venv tool via `uv run`, got {entry!r}"
        )


def test_no_remote_repo_reintroduces_a_second_version_pin() -> None:
    """Guards the other direction: re-adding the upstream repo restores the pin."""
    offenders = [
        (repo["repo"], tool)
        for repo in _config()["repos"]
        if repo.get("repo") != "local"
        for tool in _DUAL_PINNED_TOOLS
        if tool in repo["repo"]
    ]
    assert not offenders, (
        f"these remote hook repos pin a tool pyproject also pins: {offenders}; "
        "use a local hook running `uv run <tool>` so there is only one version"
    )


def test_ruff_hooks_keep_force_exclude() -> None:
    """Without --force-exclude ruff ignores extend-exclude for explicit paths.

    pre-commit always passes explicit filenames, so dropping the flag silently
    starts linting frontend/, migrations/ and .venv (verified: the same file is
    skipped with the flag and reports 4 errors without it).
    """
    hooks = _all_hooks_by_id()
    for hid in ("ruff", "ruff-format"):
        entry = str(hooks[hid].get("entry", ""))
        assert "--force-exclude" in entry, (
            f"hook {hid} dropped --force-exclude; extend-exclude would be ignored"
        )


GITLEAKS_CONFIG = REPO_ROOT / ".gitleaks.toml"


def test_gitleaks_config_loads_the_default_ruleset() -> None:
    """A gitleaks config with only an [allowlist] loads ZERO rules.

    That was this repo's state from the day the hook was added until the
    2026-10-20 audit (M7): every "gitleaks ... Passed" meant nothing. The
    default ruleset must be extended explicitly.
    """
    cfg = tomllib.loads(GITLEAKS_CONFIG.read_text())
    assert cfg.get("extend", {}).get("useDefault") is True, (
        "add `[extend]\\nuseDefault = true` to .gitleaks.toml, or gitleaks loads no rules"
    )


@pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks binary not installed")
def test_gitleaks_with_repo_config_actually_detects_a_secret(tmp_path: Path) -> None:
    """Behavioural proof, not a config read: the repo config must catch a secret.

    The secret is generated at runtime so this file never contains a literal
    token -- otherwise, once real rules load, the hook would block this test.
    """
    alphabet = string.ascii_letters + string.digits
    token = "ghp_" + "".join(secrets.choice(alphabet) for _ in range(36))
    (tmp_path / "creds.txt").write_text(f'github_token = "{token}"\n')

    result = subprocess.run(
        [
            "gitleaks",
            "detect",
            "--no-git",
            "--no-banner",
            "--source",
            str(tmp_path),
            "--config",
            str(GITLEAKS_CONFIG),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, (
        "gitleaks with the repo config did not flag a synthetic GitHub token "
        f"(exit {result.returncode}); the hook is not enforcing anything.\n"
        f"{result.stdout}{result.stderr}"
    )


def test_blitzortung_probe_output_is_gitignored() -> None:
    """The manual network probe rewrote a committed doc on every run, which is
    how a host-specific CA failure became repo 'fact' (security audit M5)."""
    from tests.pollers.blitzortung import test_port_probe

    rel = test_port_probe.PROBE_DOC.relative_to(REPO_ROOT)
    result = subprocess.run(["git", "check-ignore", "-q", str(rel)], cwd=REPO_ROOT, check=False)
    assert result.returncode == 0, f"{rel} must be gitignored"
