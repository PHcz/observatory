"""RED scaffolds for picomuon.cli (Wave 3 turns these GREEN)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from picomuon.cli import app

runner = CliRunner()


def test_summarise(full_csv: Path, c_only_csv: Path) -> None:
    result = runner.invoke(app, ["summarise", str(full_csv)])
    assert result.exit_code == 0
    out = result.stdout
    assert "flux" in out.lower()
    # T/B/C totals + ratios present
    assert "T:C" in out
    assert "B:C" in out
    # C-only: T:C ratio shows n/a (no T rows)
    result_c = runner.invoke(app, ["summarise", str(c_only_csv)])
    assert result_c.exit_code == 0
    assert "n/a" in result_c.stdout.lower()


def test_error_exit(malformed_bad_header_csv: Path) -> None:
    result = runner.invoke(app, ["summarise", str(malformed_bad_header_csv)])
    assert result.exit_code != 0
    # an error message is surfaced to the user
    assert result.output.strip() != ""


@pytest.mark.parametrize(
    ("command", "default_name"),
    [("rate", "rate.png"), ("pressure", "pressure.png"), ("adc", "adc.png")],
)
def test_default_out(
    full_csv: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str, default_name: str
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, [command, str(full_csv)])
    assert result.exit_code == 0
    assert (tmp_path / default_name).exists()


def test_report(full_csv: Path, tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    result = runner.invoke(app, ["report", str(full_csv), "--out", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    html = out.read_text()
    # four inline base64 PNGs + Hyborg accent
    assert html.count("data:image/png;base64,") == 4
    assert "#6b8e6b" in html


def test_plots_render(full_csv: Path, tmp_path: Path) -> None:
    # AC#4 smoke: all four plot/report paths render under Agg without raising.
    for command, name in (
        ("rate", "rate.png"),
        ("pressure", "pressure.png"),
        ("adc", "adc.png"),
        ("report", "report.html"),
    ):
        out = tmp_path / name
        result = runner.invoke(app, [command, str(full_csv), "--out", str(out)])
        assert result.exit_code == 0, result.output
        assert out.exists()
