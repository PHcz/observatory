"""The pre-commit sensitive-data gate (security audit F61/F76/F63/C8).

It silently did nothing when the local pattern file was missing (every fresh
clone) and grepped the working tree rather than what is actually staged.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check-sensitive.sh"
CANARY = "canary-home-51.123456"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "1+x@users.noreply.github.com")
    _git(tmp_path, "config", "user.name", "x")
    shutil.copy(SCRIPT, tmp_path / "check.sh")
    return tmp_path


def _run(repo: Path, *files: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "check.sh", *files], cwd=repo, capture_output=True, text=True, check=False
    )


def test_fails_loudly_without_the_local_pattern_file(repo: Path) -> None:
    (repo / "a.txt").write_text("hello\n")
    _git(repo, "add", "a.txt")
    proc = _run(repo, "a.txt")
    assert proc.returncode != 0
    assert ".git-sensitive-patterns" in proc.stdout + proc.stderr


def test_checks_the_staged_content_not_the_working_tree(repo: Path) -> None:
    (repo / ".git-sensitive-patterns").write_text(CANARY.replace(".", r"\.") + "\n")
    (repo / "a.txt").write_text(f"lat = {CANARY}\n")
    _git(repo, "add", "a.txt")
    (repo / "a.txt").write_text("lat = redacted\n")  # tree is clean, index is not
    assert _run(repo, "a.txt").returncode != 0


def test_clean_staged_content_passes(repo: Path) -> None:
    (repo / ".git-sensitive-patterns").write_text(CANARY + "\n")
    (repo / "a.txt").write_text("nothing to see\n")
    _git(repo, "add", "a.txt")
    proc = _run(repo, "a.txt")
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.parametrize(
    "path",
    [
        "x.log",
        ".coverage",
        "htmlcov/index.html",
        "coverage/lcov.info",
        "test-results/r.xml",
        ".superpowers/notes.md",
    ],
)
def test_local_noise_is_gitignored(path: str) -> None:
    proc = subprocess.run(["git", "check-ignore", "-q", path], cwd=REPO_ROOT, check=False)
    assert proc.returncode == 0, f"{path} should be gitignored"
