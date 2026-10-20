"""Secrets in Settings are SecretStr (security audit 2026-10-20, F37).

As plain ``str`` they appeared in ``repr(settings)``, in any log line or
traceback that rendered the settings object, and in pydantic error output.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from observatory.config import Settings

SECRET_FIELDS = (
    "mqtt_password",
    "alert_ntfy_token",
    "alert_telegram_bot_token",
    "vuln_check_github_token",
    "observatory_ingest_basic_auth_password",
)
CANARY = "canary-Zq8vX2mN4pL7"
HOME = {"home_lat": 51.5, "home_lon": -0.1}


@pytest.mark.parametrize("field", SECRET_FIELDS)
def test_secret_is_hidden_from_repr_and_dump(field: str) -> None:
    s = Settings(**HOME, **{field: CANARY})  # type: ignore[arg-type]
    assert CANARY not in repr(s)
    assert CANARY not in str(s.model_dump())
    value = getattr(s, field)
    assert isinstance(value, SecretStr)
    assert value.get_secret_value() == CANARY


@pytest.mark.parametrize("field", SECRET_FIELDS)
def test_secret_defaults_to_empty(field: str) -> None:
    assert getattr(Settings(**HOME), field).get_secret_value() == ""  # type: ignore[arg-type]


def test_startup_validation_error_does_not_echo_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bad setting at startup lands in the journal; pydantic's error text
    included the whole input -- every secret from the env file with it."""
    monkeypatch.setenv("ALERT_TELEGRAM_BOT_TOKEN", CANARY)
    monkeypatch.setenv("HOME_LAT", "not-a-number")
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert CANARY not in str(exc_info.value)
