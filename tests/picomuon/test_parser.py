"""RED scaffolds for picomuon.parser (Wave 1 turns these GREEN)."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from picomuon.parser import Metadata, PicoMuonError, read_csv


def test_read_csv_header_and_typed_cols(full_csv: Path) -> None:
    meta, df = read_csv(full_csv)
    assert isinstance(meta, Metadata)
    assert meta.sw_version == "0.1.23"
    assert meta.detector_name == "V56/485"
    assert meta.threshold_t == 200
    assert meta.reset_t == 100
    assert meta.threshold_b == 200
    assert meta.reset_b == 100
    # Date + Time combined into a single datetime column
    assert "datetime" in df.columns
    assert df.schema["datetime"] == pl.Datetime
    # ID cast to categorical
    assert df.schema["ID"] == pl.Categorical
    assert set(df["ID"].unique().to_list()) <= {"T", "B", "C"}


def test_read_csv_malformed_bad_header(malformed_bad_header_csv: Path) -> None:
    with pytest.raises(PicoMuonError):
        read_csv(malformed_bad_header_csv)


def test_read_csv_malformed_col_count(malformed_col_count_csv: Path) -> None:
    with pytest.raises(PicoMuonError):
        read_csv(malformed_col_count_csv)


def test_read_csv_c_only(c_only_csv: Path) -> None:
    meta, df = read_csv(c_only_csv)
    assert isinstance(meta, Metadata)
    ids = set(df["ID"].unique().to_list())
    assert ids == {"C"}
    assert df.height > 0
