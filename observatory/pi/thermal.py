"""Pi thermal monitoring via vcgencmd. Plan 05-01 implements RED-first."""

from __future__ import annotations

from typing import Any, Literal

PiStatus = Literal["healthy", "warning", "critical"]


class ThermalReadError(RuntimeError):
    """vcgencmd failed or output was unparseable."""


def read_temp_c(binary: str | None = None) -> float:
    raise NotImplementedError("Plan 05-01")


def read_throttled(binary: str | None = None) -> str:
    raise NotImplementedError("Plan 05-01")


def derive_status(temp_c: float, throttled_hex: str) -> tuple[PiStatus, list[str]]:
    raise NotImplementedError("Plan 05-01")


class ThermalWarningEmitter:
    """Stub — Plan 05-01 GREEN replaces with state-tracking transition detector."""

    def __init__(self, rate_limit_sec: int | None = None, clock: Any = None) -> None:
        raise NotImplementedError("Plan 05-01")

    def observe(self, status: PiStatus, warnings: list[str]) -> list[str]:
        raise NotImplementedError("Plan 05-01")
