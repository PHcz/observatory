"""INFRA-01/02/06: bootstrap-pi.sh contains the required sections and uses idempotency markers."""

from __future__ import annotations

import re
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


def _uv_sync_line() -> str:
    lines = [
        ln
        for ln in _text().splitlines()
        if "uv sync" in ln and not ln.lstrip().startswith(("#", "log "))
    ]
    assert len(lines) == 1, f"expected exactly one uv sync invocation, got {lines}"
    return lines[0]


def test_production_sync_is_frozen_runtime_only() -> None:
    """The Pi must run exactly what uv.lock says, without dev tooling.

    Bootstrap used a plain `uv sync` and nothing re-synced afterwards, so by the
    2026-10-20 audit (M10) the Pi ran fastapi 0.136 / starlette 1.3 / uvicorn
    0.39 -- all below pyproject's security floors -- plus pytest, mypy, docker
    and testcontainers in production, while every dependency audit inspected
    the lockfile and reported "clean".
    """
    line = _uv_sync_line()
    for flag in ("--frozen", "--no-dev", "--extra analysis"):
        assert flag in line, f"uv sync on the Pi must pass {flag}: {line!r}"


def test_production_sync_keeps_temp_files_off_the_tmpfs() -> None:
    """/tmp is a 64 MB tmpfs; large wheels fail there with a misleading
    'network connectivity' error (polars-runtime is ~50 MB)."""
    assert "TMPDIR=" in _uv_sync_line()


def test_does_not_install_dev_hooks_on_the_pi() -> None:
    """Commits happen on the dev machine; the Pi has no dev tooling to run them."""
    assert ".venv/bin/pre-commit" not in _text()


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


def test_enables_unattended_security_upgrades() -> None:
    """A rebuilt Pi must patch itself (security audit 2026-10-20, F48).

    unattended-upgrades was never installed, and by the audit 48 security
    updates had piled up -- OpenSSL, GnuTLS, Kerberos, xz and the system
    Python 3.11 the venv runs on.
    """
    t = _text()
    assert "unattended-upgrades" in t
    assert 'APT::Periodic::Unattended-Upgrade "1"' in t


def test_disables_unneeded_root_daemons() -> None:
    """Bluetooth and ModemManager run as root with no purpose on this Pi, and
    ModemManager probes /dev/ttyACM* -- where the muon detector lives."""
    t = _text()
    assert "disable --now bluetooth.service ModemManager.service" in t


def test_mosquitto_config_installed_as_conf_d_drop_in() -> None:
    """Bootstrap overwrote the stock /etc/mosquitto/mosquitto.conf with the
    drop-in, contradicting deploy/mosquitto/README.md and the live Pi
    (security audit 2026-10-20, F22/F50/C6)."""
    t = _text()
    assert "/etc/mosquitto/conf.d/observatory.conf" in t
    assert 'deploy/mosquitto/mosquitto.conf" /etc/mosquitto/mosquitto.conf' not in t


def test_mosquitto_lan_ip_placeholder_is_rendered() -> None:
    """An unrendered `listener 1883 ${LAN_IP}` stops mosquitto from starting."""
    assert "${LAN_IP}" in _text() and "sed" in _text()
    assert re.search(r"sed [^\n]*\\\$\{LAN_IP\}", _text()), "bootstrap must render ${LAN_IP}"


def test_mosquitto_acl_is_installed() -> None:
    """mosquitto.conf names acl_file /etc/mosquitto/acl -- bootstrap never installed it."""
    assert 'deploy/mosquitto/acl.conf" /etc/mosquitto/acl' in _text()


def test_no_unused_mosquitto_admin_user() -> None:
    """Bootstrap created an `admin` user that no ACL entry or service uses."""
    assert "mosquitto_passwd -b /etc/mosquitto/passwords admin" not in _text()
