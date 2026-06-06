"""Phase 6 — tests for astral_calc (Plan 06-01 RED/GREEN TDD)."""

from __future__ import annotations

import datetime

from observatory.api.astral_calc import compute_moon_illumination, get_astronomy


class TestComputeMoonIllumination:
    """Pure cosine formula helper: (1 - cos(2π * phase_days / 29.53)) / 2 * 100."""

    def test_new_moon_zero(self) -> None:
        result = compute_moon_illumination(0.0)
        assert abs(result - 0.0) < 0.01

    def test_full_moon_hundred(self) -> None:
        result = compute_moon_illumination(29.53 / 2)
        assert abs(result - 100.0) < 0.5

    def test_first_quarter_fifty(self) -> None:
        result = compute_moon_illumination(29.53 / 4)
        assert abs(result - 50.0) < 0.5


class TestGetAstronomy:
    """Integration tests using known moon-phase dates (UTC)."""

    LON = -0.1278  # London
    LAT = 51.5074

    def test_returns_all_keys(self) -> None:
        result = get_astronomy(self.LAT, self.LON, today=datetime.date(2024, 1, 11))
        assert set(result.keys()) == {
            "sunrise_ts",
            "sunset_ts",
            "moon_phase",
            "moon_illumination_pct",
            "moonrise_ts",
            "moonset_ts",
        }

    def test_types(self) -> None:
        result = get_astronomy(self.LAT, self.LON, today=datetime.date(2024, 1, 11))
        assert isinstance(result["sunrise_ts"], int)
        assert isinstance(result["sunset_ts"], int)
        assert isinstance(result["moon_phase"], float)
        assert isinstance(result["moon_illumination_pct"], float)

    def test_moonrise_moonset_present_as_int_or_none(self) -> None:
        result = get_astronomy(self.LAT, self.LON, today=datetime.date(2024, 1, 11))
        for key in ("moonrise_ts", "moonset_ts"):
            assert result[key] is None or isinstance(result[key], int)

    def test_moonrise_moonset_typical_day_are_ints(self) -> None:
        # London, 2026-06-03: both a moonrise and a moonset occur this UTC day.
        result = get_astronomy(self.LAT, self.LON, today=datetime.date(2026, 6, 3))
        assert isinstance(result["moonrise_ts"], int)
        assert isinstance(result["moonset_ts"], int)

    def test_moonrise_none_at_high_latitude(self) -> None:
        # Svalbard (78°N): the moon does not rise on this date -> None, no raise.
        result = get_astronomy(78.0, 15.0, today=datetime.date(2026, 6, 3))
        assert result["moonrise_ts"] is None

    def test_new_moon_illumination_near_zero(self) -> None:
        # 2024-01-11 was a new moon
        result = get_astronomy(self.LAT, self.LON, today=datetime.date(2024, 1, 11))
        assert result["moon_illumination_pct"] < 5.0

    def test_first_quarter_illumination_midrange(self) -> None:
        # 2024-01-18 was first quarter
        result = get_astronomy(self.LAT, self.LON, today=datetime.date(2024, 1, 18))
        assert 40.0 <= result["moon_illumination_pct"] <= 60.0

    def test_full_moon_illumination_near_hundred(self) -> None:
        # 2024-01-25 was full moon
        result = get_astronomy(self.LAT, self.LON, today=datetime.date(2024, 1, 25))
        assert result["moon_illumination_pct"] > 95.0

    def test_last_quarter_illumination_midrange(self) -> None:
        # 2024-02-04 was last quarter (astral phase ~22.4 days => ~48% illumination)
        result = get_astronomy(self.LAT, self.LON, today=datetime.date(2024, 2, 4))
        assert 40.0 <= result["moon_illumination_pct"] <= 60.0

    def test_moon_phase_in_range(self) -> None:
        result = get_astronomy(self.LAT, self.LON, today=datetime.date(2024, 1, 11))
        assert 0.0 <= result["moon_phase"] < 1.0

    def test_moon_illumination_in_range(self) -> None:
        result = get_astronomy(self.LAT, self.LON, today=datetime.date(2024, 1, 11))
        assert 0.0 <= result["moon_illumination_pct"] <= 100.0

    def test_moon_phase_always_in_range_multiple_dates(self) -> None:
        dates = [
            datetime.date(2024, 1, 11),
            datetime.date(2024, 1, 18),
            datetime.date(2024, 1, 25),
            datetime.date(2024, 2, 4),
        ]
        for d in dates:
            result = get_astronomy(self.LAT, self.LON, today=d)
            assert 0.0 <= result["moon_phase"] < 1.0, f"moon_phase out of range for {d}"
            assert 0.0 <= result["moon_illumination_pct"] <= 100.0, (
                f"moon_illumination_pct out of range for {d}"
            )

    def test_london_summer_solstice_sunrise_range(self) -> None:
        # London, 2024-06-21 (summer solstice), sunrise ~03:43 UTC per astral 3.2
        # astral returns 1718941413 (03:43:33 UTC); allow ±300s for floating-point variation
        result = get_astronomy(self.LAT, self.LON, today=datetime.date(2024, 6, 21))
        assert abs(result["sunrise_ts"] - 1718941413) < 300, (
            f"sunrise_ts {result['sunrise_ts']} not in expected range"
        )

    def test_sunrise_before_sunset(self) -> None:
        result = get_astronomy(self.LAT, self.LON, today=datetime.date(2024, 6, 21))
        assert result["sunrise_ts"] < result["sunset_ts"]
