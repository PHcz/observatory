"""Every obs-* service runs sandboxed (security audit 2026-10-20, F45/F44/M8).

`systemd-analyze security` rated every unit 9.2 "UNSAFE": a compromised poller
could rewrite its own code, read any home directory, and open the indoor
node's USB serial port (the account was in `dialout`). Each service now gets a
common sandbox; only obs-muon may open serial devices and only obs-api may
reach the VideoCore mailbox (vcgencmd, for the Pi temperature).
"""

from __future__ import annotations

import configparser
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
UNITS = sorted((REPO_ROOT / "deploy" / "systemd").glob("obs-*.service"))
BOOTSTRAP = (REPO_ROOT / "scripts" / "bootstrap-pi.sh").read_text()

COMMON = {
    "NoNewPrivileges": "yes",
    "CapabilityBoundingSet": "",
    "ProtectSystem": "strict",
    "ProtectHome": "yes",
    "PrivateTmp": "yes",
    "ProtectKernelTunables": "yes",
    "ProtectKernelModules": "yes",
    "ProtectKernelLogs": "yes",
    "ProtectControlGroups": "yes",
    "ProtectClock": "yes",
    "ProtectHostname": "yes",
    "RestrictSUIDSGID": "yes",
    "RestrictRealtime": "yes",
    "RestrictNamespaces": "yes",
    "LockPersonality": "yes",
    "SystemCallArchitectures": "native",
    "RestrictAddressFamilies": "AF_UNIX AF_INET AF_INET6",
    "UMask": "0027",
}


def _service(unit: Path) -> dict[str, str]:
    cp = configparser.ConfigParser(strict=False, interpolation=None, delimiters=("=",))
    cp.optionxform = str  # type: ignore[assignment,method-assign]
    cp.read_string(unit.read_text())
    return dict(cp["Service"])


def test_units_found() -> None:
    assert len(UNITS) >= 15


@pytest.mark.parametrize("unit", UNITS, ids=lambda p: p.name)
def test_common_sandbox(unit: Path) -> None:
    svc = _service(unit)
    for key, value in COMMON.items():
        assert svc.get(key) == value, f"{unit.name}: {key}={svc.get(key)!r}, want {value!r}"
    assert "/var/lib/observatory" in svc.get("ReadWritePaths", "").split()
    assert svc.get("User") == "observatory" and svc.get("Group") == "observatory"


@pytest.mark.parametrize(
    "unit",
    [u for u in UNITS if u.name not in ("obs-muon.service", "obs-api.service")],
    ids=lambda p: p.name,
)
def test_no_device_access_by_default(unit: Path) -> None:
    assert _service(unit).get("PrivateDevices") == "yes"
    assert "SupplementaryGroups" not in _service(unit)


def test_only_muon_reaches_serial_ports() -> None:
    svc = _service(REPO_ROOT / "deploy/systemd/obs-muon.service")
    assert svc["SupplementaryGroups"] == "dialout"
    assert svc["DevicePolicy"] == "closed"
    assert svc["DeviceAllow"] == "char-ttyACM rw"


def test_api_reaches_only_the_videocore_mailbox() -> None:
    svc = _service(REPO_ROOT / "deploy/systemd/obs-api.service")
    assert svc["SupplementaryGroups"] == "video"
    assert svc["DevicePolicy"] == "closed"
    assert svc["DeviceAllow"] == "/dev/vcio rw"


def test_backup_units_may_write_the_backup_mount() -> None:
    for name in ("obs-backup.service", "obs-backup-verify.service"):
        assert "/mnt/backup" in _service(REPO_ROOT / "deploy/systemd" / name)["ReadWritePaths"]


def test_vuln_check_keeps_tool_state_outside_the_hidden_home() -> None:
    """ProtectHome hides /home. uv probes ~/.cache and ~/.local/share/uv/python,
    pip-audit probes ~/.pip-audit-cache via Path.home() -- so HOME itself moves
    to the unit's writable CacheDirectory."""
    svc = _service(REPO_ROOT / "deploy/systemd/obs-vuln-check.service")
    assert svc["CacheDirectory"] == "obs-vuln-check"
    env = svc["Environment"].split()
    assert "HOME=/var/cache/obs-vuln-check" in env
    assert "UV_PYTHON_PREFERENCE=only-system" in env


def test_service_account_is_in_no_device_groups() -> None:
    assert not re.search(r"useradd[^\n]*--groups", BOOTSTRAP)
    assert "usermod -aG dialout" not in BOOTSTRAP


def test_code_tree_is_root_owned() -> None:
    """The service account must not be able to rewrite the code it runs."""
    assert 'chown -R observatory:observatory "$REPO_ROOT"' not in BOOTSTRAP
    assert 'chown -R root:root "$REPO_ROOT"' in BOOTSTRAP
    deploy = (REPO_ROOT / "scripts" / "deploy-frontend.sh").read_text()
    assert "chown -R observatory:observatory" not in deploy
    assert "chown -R root:root" in deploy


def test_venv_is_synced_as_root() -> None:
    sync = [ln for ln in BOOTSTRAP.splitlines() if "uv sync" in ln and "--frozen" in ln]
    assert sync and not any("sudo -u observatory" in ln for ln in sync)


@pytest.mark.parametrize(
    "bad", ["/", "/etc", "/opt/observatory", "/opt/observatory/../etc", "relative/path"]
)
def test_deploy_frontend_refuses_unsafe_remote_dirs(bad: str) -> None:
    """It runs a root `rsync --delete` + `chown -R` into this path (audit F51)."""
    import os
    import subprocess

    script = REPO_ROOT / "scripts" / "deploy-frontend.sh"
    env = {**os.environ, "OBS_REMOTE_BUNDLE_DIR": bad, "OBS_SSH_TARGET": "nobody@invalid.invalid"}
    proc = subprocess.run(
        ["bash", str(script)], env=env, capture_output=True, text=True, timeout=30, check=False
    )
    assert proc.returncode != 0
    assert "refusing" in (proc.stdout + proc.stderr).lower()


def test_github_token_is_readable_by_the_vuln_check_only() -> None:
    """Every unit loads observatory.env, so a token kept there reached every
    service (security audit F46). It lives in a root-only file that only
    obs-vuln-check loads; systemd reads it as root before dropping privileges."""
    env_files = [
        line.split("=", 1)[1]
        for line in (REPO_ROOT / "deploy/systemd/obs-vuln-check.service").read_text().splitlines()
        if line.startswith("EnvironmentFile=")
    ]
    assert env_files[-1] == "-/etc/observatory/vuln-check.env"  # last one wins
    for unit in UNITS:
        if unit.name != "obs-vuln-check.service":
            assert "vuln-check.env" not in unit.read_text(), unit.name
    example = (REPO_ROOT / ".env.example").read_text()
    assert "/etc/observatory/vuln-check.env" in example


TELEGRAM_SENDERS = {"obs-api.service", "obs-enviro-heartbeat.service", "obs-vuln-check.service"}


def _env_files(unit: Path) -> list[str]:
    return [
        line.split("=", 1)[1]
        for line in unit.read_text().splitlines()
        if line.startswith("EnvironmentFile=")
    ]


def test_telegram_token_is_readable_by_the_senders_only() -> None:
    """The bot token sat in observatory.env, so every poller, the muon reader and
    the backup jobs carried it (security audit F46). Only the three services
    that send Telegram messages load the root-only telegram.env."""
    for unit in UNITS:
        files = _env_files(unit)
        if unit.name in TELEGRAM_SENDERS:
            assert "-/etc/observatory/telegram.env" in files, unit.name
            assert files.index("-/etc/observatory/telegram.env") > files.index(
                "/etc/observatory/observatory.env"
            ), f"{unit.name}: telegram.env must load after observatory.env"
        else:
            assert "-/etc/observatory/telegram.env" not in files, unit.name
    assert "/etc/observatory/telegram.env" in (REPO_ROOT / ".env.example").read_text()
