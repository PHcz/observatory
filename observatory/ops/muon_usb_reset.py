"""Reset a stalled PicoMuon USB device (obs-muon-usb-reset.timer, root).

On 2026-11-11 the PicoMuon's USB serial output stalled: the board stayed
enumerated and the detector kept counting, but /dev/picomuon delivered 0 bytes
for 3.5 days. obs-muon reopens the port after 60 s of silence, which cannot
clear this. A USB reset of that single device did: USBDEVFS_RESET, then
de-/re-authorize when the tty does not come back by itself.

obs-muon (correctly) has no access to USB device nodes, so this check runs as a
separate small root job every few minutes. It only ever resets the device with
the PicoMuon's USB id (2e8a:000a), never another device and never the hub, and at
most once per MIN_INTERVAL_SEC. If resets do not help, the StaleMuonRule
Telegram alert reports the outage.

Exit code is always 0 (a timer job; the outcome is in the journal).
"""

from __future__ import annotations

import fcntl
import os
import sqlite3
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import structlog

from observatory.config import settings
from observatory.logging import configure_logging

log = structlog.get_logger(__name__)

PICO_VENDOR = "2e8a"
PICO_PRODUCT = "000a"
TTY_LINK = Path("/dev/picomuon")
# systemd creates /var/lib/obs-muon-usb-reset from StateDirectory= in the unit.
STATE_FILE = Path("/var/lib/obs-muon-usb-reset/last_reset")

# obs-muon reopens after 60 s of silence; give it three tries before a reset.
RESET_AFTER_SEC = 180
# A reset re-enumerates the board; leave room for it to recover before another.
MIN_INTERVAL_SEC = 900

_USBDEVFS_RESET = 0x5514  # _IO('U', 20)


def decide(
    age_sec: float | None,
    last_reset: float | None,
    now: float,
    reader_active: bool,
) -> str:
    """Return "ok", "no_data", "reader_stopped", "rate_limited" or "reset"."""
    if age_sec is None:
        return "no_data"
    if age_sec < RESET_AFTER_SEC:
        return "ok"
    if not reader_active:
        # Operator stopped obs-muon on purpose (e.g. to flash the Pico): hands off.
        return "reader_stopped"
    if last_reset is not None and now - last_reset < MIN_INTERVAL_SEC:
        return "rate_limited"
    return "reset"


def find_usb_device(sys_root: Path = Path("/sys")) -> Path | None:
    """The sysfs directory of the PicoMuon (matched by USB id), or None."""
    for dev in sorted((sys_root / "bus" / "usb" / "devices").glob("*")):
        try:
            vendor = (dev / "idVendor").read_text().strip()
            product = (dev / "idProduct").read_text().strip()
        except OSError:
            continue
        if (vendor, product) == (PICO_VENDOR, PICO_PRODUCT):
            return dev
    return None


def _ioctl_reset(path: str) -> None:
    fd = os.open(path, os.O_WRONLY)
    try:
        fcntl.ioctl(fd, _USBDEVFS_RESET, 0)
    finally:
        os.close(fd)


def _write_authorized(path: Path, value: str) -> None:
    path.write_text(value)


def reset_device(
    dev: Path,
    *,
    usb_reset: Callable[[str], None] = _ioctl_reset,
    tty_present: Callable[[], bool] = TTY_LINK.exists,
    sleep: Callable[[float], None] = time.sleep,
    write_authorized: Callable[[Path, str], None] = _write_authorized,
) -> str:
    """Reset one USB device; return which steps were needed."""
    bus = int((dev / "busnum").read_text())
    num = int((dev / "devnum").read_text())
    usb_reset(f"/dev/bus/usb/{bus:03d}/{num:03d}")
    sleep(5)
    if tty_present():
        return "ioctl"
    # The ioctl alone left the board unconfigured on 2026-11-14; a logical
    # disconnect/reconnect made the kernel configure it again.
    write_authorized(dev / "authorized", "0")
    sleep(2)
    write_authorized(dev / "authorized", "1")
    sleep(5)
    return "ioctl+reauthorize" if tty_present() else "failed"


def _last_event_age(db_path: str, now: float) -> float | None:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    try:
        row = conn.execute("SELECT MAX(ts) FROM muon_events").fetchone()
    finally:
        conn.close()
    return None if row is None or row[0] is None else now - float(row[0])


def _reader_active() -> bool:
    return (
        subprocess.run(
            ["/usr/bin/systemctl", "is-active", "--quiet", "obs-muon.service"], check=False
        ).returncode
        == 0
    )


def main() -> int:
    configure_logging()
    now = time.time()
    state = STATE_FILE
    try:
        last_reset: float | None = float(state.read_text())
    except (OSError, ValueError):
        last_reset = None

    age = _last_event_age(settings.observatory_db_path, now)
    action = decide(age, last_reset, now, _reader_active())
    if action != "reset":
        log.info("muon_usb_check", action=action, age_sec=None if age is None else int(age))
        return 0

    dev = find_usb_device()
    if dev is None:
        log.warning("muon_usb_reset_skipped", reason="PicoMuon not on USB", age_sec=int(age or 0))
        return 0
    state.write_text(f"{now:.0f}")
    result = reset_device(dev)
    log.warning("muon_usb_reset", device=dev.name, result=result, silent_sec=int(age or 0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
