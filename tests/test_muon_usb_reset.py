"""Automatic USB reset of a stalled PicoMuon (2026-11-14).

On 2026-11-11 the PicoMuon's USB serial output stalled: the board stayed
enumerated, the detector kept counting, but the port delivered 0 bytes for 3.5
days. obs-muon's own reopen-after-60-s-silence cannot clear that. A USB reset
of that single device (USBDEVFS_RESET, then de-/re-authorize if the tty does not
come back) did. obs-muon-usb-reset.timer runs this check as a small root job,
because obs-muon itself (correctly) has no access to USB device nodes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from observatory.ops import muon_usb_reset as m

NOW = 1_800_000_000.0


@pytest.mark.parametrize(
    ("age", "last_reset", "reader_active", "expected"),
    [
        (5, None, True, "ok"),  # events flowing
        (m.RESET_AFTER_SEC - 1, None, True, "ok"),
        (None, None, True, "no_data"),  # fresh install: nothing to compare
        (3600, None, False, "reader_stopped"),  # operator stopped obs-muon (e.g. flashing)
        (3600, NOW - 60, True, "rate_limited"),  # reset 1 min ago: give it time
        (3600, None, True, "reset"),
        (3600, NOW - m.MIN_INTERVAL_SEC - 1, True, "reset"),
    ],
)
def test_decide(
    age: float | None, last_reset: float | None, reader_active: bool, expected: str
) -> None:
    assert m.decide(age, last_reset, NOW, reader_active) == expected


def _fake_usb_tree(root: Path) -> Path:
    dev = root / "bus" / "usb" / "devices" / "1-1.3"
    (dev / "1-1.3:1.0").mkdir(parents=True)
    (dev / "idVendor").write_text("2e8a\n")
    (dev / "idProduct").write_text("000a\n")
    (dev / "busnum").write_text("1\n")
    (dev / "devnum").write_text("4\n")
    (dev / "authorized").write_text("1\n")
    other = root / "bus" / "usb" / "devices" / "1-1.4"
    other.mkdir(parents=True)
    (other / "idVendor").write_text("303a\n")  # ESP32-S2 indoor node: must never be picked
    (other / "idProduct").write_text("0002\n")
    return dev


def test_finds_the_pico_and_never_another_device(tmp_path: Path) -> None:
    dev = _fake_usb_tree(tmp_path)
    assert m.find_usb_device(sys_root=tmp_path) == dev


def test_no_pico_present(tmp_path: Path) -> None:
    (tmp_path / "bus" / "usb" / "devices").mkdir(parents=True)
    assert m.find_usb_device(sys_root=tmp_path) is None


def test_reset_stops_after_the_ioctl_when_the_tty_returns(tmp_path: Path) -> None:
    dev = _fake_usb_tree(tmp_path)
    calls: list[str] = []
    result = m.reset_device(
        dev,
        usb_reset=lambda path: calls.append(f"ioctl {path}"),
        tty_present=lambda: True,
        sleep=lambda s: None,
    )
    assert calls == ["ioctl /dev/bus/usb/001/004"]
    assert result == "ioctl"
    assert (dev / "authorized").read_text() == "1\n"  # untouched


def test_reset_reauthorizes_when_the_tty_stays_missing(tmp_path: Path) -> None:
    """2026-11-14: the ioctl alone left the board unconfigured; de-/re-authorize fixed it."""
    dev = _fake_usb_tree(tmp_path)
    writes: list[str] = []
    state = {"tty": False}

    def write_authorized(path: Path, value: str) -> None:
        writes.append(value)
        if value == "1":
            state["tty"] = True

    result = m.reset_device(
        dev,
        usb_reset=lambda path: None,
        tty_present=lambda: state["tty"],
        sleep=lambda s: None,
        write_authorized=write_authorized,
    )
    assert writes == ["0", "1"]
    assert result == "ioctl+reauthorize"
