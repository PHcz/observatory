"""INFRA-06 + MUON-01 + structural checks: Phase 1 deploy artifacts staged correctly."""

from __future__ import annotations

from pathlib import Path

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


def test_backup_fstab_template_has_uuid_placeholder() -> None:
    f = _read("deploy/fstab/observatory-backup.fstab.template")
    assert "UUID=XXXX-XXXX" in f
    assert "/mnt/backup" in f
    assert "nofail" in f
    assert "uid=observatory" in f


# === Phase 3: Weather Node Mosquitto bundle ===


def test_mosquitto_conf_sec03_directives() -> None:
    content = _read("deploy/mosquitto/mosquitto.conf")
    assert "listener 1883 ${LAN_IP}" in content, "SEC-03: must bind to LAN-IP, not 0.0.0.0"
    assert "allow_anonymous false" in content
    assert "acl_file /etc/mosquitto/acl" in content
    assert "password_file /etc/mosquitto/passwords" in content
    assert "persistence true" in content


def test_mosquitto_acl_two_users() -> None:
    content = _read("deploy/mosquitto/acl.conf")
    assert "user enviro-observatory-weather" in content
    assert "topic write enviro/observatory-weather" in content
    assert "user obs-api-subscriber" in content
    assert "topic read enviro/#" in content


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
