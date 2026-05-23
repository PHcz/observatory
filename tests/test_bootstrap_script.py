"""INFRA-01/02/06: bootstrap-pi.sh contains the required sections and uses idempotency markers."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "bootstrap-pi.sh"


def _text() -> str:
    return SCRIPT.read_text()


def test_script_is_executable() -> None:
    import os

    assert os.access(SCRIPT, os.X_OK), "bootstrap-pi.sh must be executable"


def test_uses_set_euo_pipefail() -> None:
    assert "set -euo pipefail" in _text()


def test_requires_root() -> None:
    t = _text()
    assert "EUID" in t
    assert "Must run as root" in t


def test_installs_chrony_with_makestep() -> None:
    t = _text()
    assert "apt-get install -y" in t
    assert "chrony" in t
    assert "makestep 1.0 3" in t
    assert "observatory-managed" in t  # idempotency marker for chrony.conf


def test_disables_systemd_timesyncd() -> None:
    assert "systemctl disable systemd-timesyncd" in _text()


def test_creates_observatory_user_with_dialout() -> None:
    t = _text()
    assert "id -u observatory" in t
    assert "useradd --system" in t
    assert "--groups dialout" in t
    assert "--shell /usr/sbin/nologin" in t


def test_creates_directories_with_correct_ownership() -> None:
    t = _text()
    assert "/var/lib/observatory" in t
    assert "/etc/observatory" in t
    assert "/mnt/backup" in t
    assert "-o observatory -g observatory" in t


def test_ssh_hardening_present() -> None:
    t = _text()
    assert "PasswordAuthentication no" in t
    assert "PermitRootLogin no" in t


def test_fstab_uses_idempotency_marker() -> None:
    t = _text()
    assert "observatory-tmpfs" in t
    # Must check grep marker BEFORE appending
    assert 'grep -q "# observatory-tmpfs" /etc/fstab' in t


def test_disables_swap() -> None:
    t = _text()
    assert "dphys-swapfile swapoff" in t
    assert "systemctl disable dphys-swapfile" in t


def test_uv_anchored_to_system_python() -> None:
    t = _text()
    assert "--python /usr/bin/python3.11" in t


def test_installs_pre_commit_hooks_both_stages() -> None:
    t = _text()
    assert "pre-commit" in t
    assert "install --hook-type pre-push" in t


def test_applies_yoyo_migrations() -> None:
    t = _text()
    assert "apply_migrations" in t


def test_enables_backup_timer_but_does_not_start_it() -> None:
    t = _text()
    assert "systemctl enable obs-backup.timer" in t
    # The script intentionally avoids actively starting the timer because the
    # USB UUID isn't filled in yet — but the start command IS mentioned in an
    # instructional comment. Strip comments before checking absence.
    non_comment_lines = [ln for ln in t.splitlines() if not ln.lstrip().startswith("#")]
    non_comment = "\n".join(non_comment_lines)
    assert "systemctl start obs-backup.timer" not in non_comment


def test_copies_deploy_artifacts() -> None:
    t = _text()
    assert "deploy/udev/99-picomuon.rules" in t
    assert "deploy/mosquitto/mosquitto.conf" in t
    assert "deploy/systemd/obs-backup.service" in t
    assert "deploy/systemd/obs-backup.timer" in t


def test_seeds_observatory_env() -> None:
    t = _text()
    assert "/etc/observatory/observatory.env" in t
    assert ".env.example" in t


def test_documents_operator_next_steps() -> None:
    t = _text()
    assert "Next steps for the operator" in t
    assert "blkid" in t
    assert "cold-boot" in t.lower()
