"""INFRA-06 + MUON-01 + structural checks: Phase 1 deploy artifacts staged correctly."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _read(p: str) -> str:
    return (REPO_ROOT / p).read_text()


def test_backup_service_runs_backup_py_as_observatory() -> None:
    s = _read("deploy/systemd/obs-backup.service")
    assert "User=observatory" in s
    assert "ExecStart=/opt/observatory/.venv/bin/python /opt/observatory/scripts/backup.py" in s
    assert "Type=oneshot" in s
    assert "EnvironmentFile=/etc/observatory/observatory.env" in s
    assert "ConditionPathIsMountPoint=/mnt/backup" in s


def test_backup_timer_is_daily_at_03_with_randomized_delay() -> None:
    t = _read("deploy/systemd/obs-backup.timer")
    assert "OnCalendar=*-*-* 03:00:00" in t
    assert "Persistent=true" in t
    assert "RandomizedDelaySec=300" in t
    assert "WantedBy=timers.target" in t


def test_udev_rule_targets_picomuon_vid_with_placeholder_pid() -> None:
    r = _read("deploy/udev/99-picomuon.rules")
    assert 'ATTRS{idVendor}=="2e8a"' in r
    assert 'ATTRS{idProduct}=="XXXX"' in r
    assert 'SYMLINK+="picomuon"' in r
    assert 'GROUP="dialout"' in r
    assert "udevadm info --name=/dev/ttyACM0" in r


def test_mosquitto_conf_anon_off_and_persistence_on() -> None:
    m = _read("deploy/mosquitto/mosquitto.conf")
    assert "allow_anonymous false" in m
    assert "persistence true" in m
    assert "password_file /etc/mosquitto/passwords" in m


def test_tmpfs_fstab_snippet_has_both_mounts() -> None:
    f = _read("deploy/fstab/observatory-tmpfs.fstab")
    assert "# observatory-tmpfs" in f
    assert "tmpfs /tmp     tmpfs" in f
    assert "tmpfs /var/log tmpfs" in f
    assert "noatime" in f


def test_backup_fstab_template_does_not_block_boot() -> None:
    f = _read("deploy/fstab/observatory-backup.fstab.template")
    assert "/mnt/backup" in f
    assert "nofail" in f  # a missing stick must never stop the Pi booting


# === Phase 3: Weather Node Mosquitto bundle ===


def test_mosquitto_conf_sec03_directives() -> None:
    content = _read("deploy/mosquitto/mosquitto.conf")
    assert "listener 1883 ${LAN_IP}" in content, "SEC-03: must bind to LAN-IP, not 0.0.0.0"
    assert "allow_anonymous false" in content
    assert "acl_file /etc/mosquitto/acl" in content
    assert "password_file /etc/mosquitto/passwords" in content
    assert "persistence true" in content


# ACL coverage moved to tests/test_mqtt_acl.py (derives needs from code + firmware).


def test_mosquitto_passwords_example_exists_not_real() -> None:
    assert (REPO_ROOT / "deploy/mosquitto/passwords.example").is_file()
    assert not (REPO_ROOT / "deploy/mosquitto/passwords").is_file(), (
        "Real passwords file must not be committed (gitignored)"
    )


def test_mosquitto_readme_documents_passwd() -> None:
    p = REPO_ROOT / "deploy/mosquitto/README.md"
    assert p.is_file()
    content = p.read_text()
    assert "mosquitto_passwd" in content
    assert "enviro-observatory-weather" in content
    assert "obs-api-subscriber" in content
    assert "ss -tlnp" in content


# --- Backup confidentiality (security audit 2026-10-20, F11/F52) -------------
# Backups were 0644 on an ext4 stick mounted without nosuid/nodev/noexec: every
# local account could read months of home sensor history.


@pytest.mark.parametrize("unit", ["obs-backup.service", "obs-backup-verify.service"])
def test_backup_units_write_group_private_files(unit: str) -> None:
    assert "UMask=0027" in _read(f"deploy/systemd/{unit}")


_HARDENED_MOUNT = ("nosuid", "nodev", "noexec")


def test_backup_fstab_template_matches_the_live_ext4_label_mount() -> None:
    t = _read("deploy/fstab/observatory-backup.fstab.template")
    line = next(ln for ln in t.splitlines() if "/mnt/backup" in ln and not ln.startswith("#"))
    assert line.startswith("LABEL=OBS_BACKUP /mnt/backup ext4 ")
    for opt in _HARDENED_MOUNT:
        assert opt in line, f"backup mount must use {opt}: {line!r}"


def test_operations_doc_fstab_line_is_hardened() -> None:
    doc = _read("docs/OPERATIONS.md")
    line = next(ln for ln in doc.splitlines() if ln.strip().startswith("LABEL=OBS_BACKUP"))
    for opt in _HARDENED_MOUNT:
        assert opt in line, f"documented backup mount must use {opt}: {line!r}"


def test_journald_limits_apply_to_the_volatile_journal() -> None:
    """The Pi runs Storage=volatile (journal in RAM, sparing the SD card), where
    System* limits are ignored and journald defaulted to ~10% of /run: about
    43 hours of logs, broker auth logs included (security audit F49)."""
    conf = _read("deploy/journald/observatory.conf")
    assert "RuntimeMaxUse=120M" in conf
    assert "RuntimeKeepFree=" in conf


def test_bootstrap_stops_avahi_publishing_the_workstation_record() -> None:
    """publish-workstation advertises the hostname plus the MAC address to the
    whole LAN; observatory.local resolution does not need it."""
    boot = _read("scripts/bootstrap-pi.sh")
    assert "publish-workstation=no" in boot
