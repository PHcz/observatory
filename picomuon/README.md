# picomuon — PicoMuon offline analysis

A standalone, importable analysis library and offline CLI for the UKRAA
**PicoMuon** cosmic-ray detector (two-scintillator coincidence design, SiPM
readout via RP2040). It ingests one PicoMuon CSV log and produces a dead-time-
corrected muon flux, a coincidence-rate-over-time plot, a barometric-coefficient
fit, an ADC histogram, and a single self-contained HTML report.

The core (`parser`, `rates`, `pressure`, `histogram`) is a plain importable
library with no CLI or notebook dependency, so Phase 13 of the Observatory can
reuse it directly against the `muon_events` SQLite table.

## Install

The heavy analysis dependencies (polars, scipy, matplotlib, typer) ship as an
optional extra so the Pi `obs-api` runtime stays lean:

```sh
uv pip install -e ".[analysis]"
```

This installs the `picomuon` console script.

## Usage

```sh
picomuon summarise log.csv                 # aligned text table: flux, runtime, T/B/C, ratios
picomuon rate log.csv --bucket 10m         # rate over time + pressure overlay → rate.png
picomuon pressure log.csv                  # barometric fit → pressure.png
picomuon adc log.csv                       # ADC histogram → adc.png
picomuon report log.csv --out report.html  # self-contained HTML, all four plots inline
```

`summarise` prints a plain aligned text table (no `rich`). The plot commands
write a PNG; when `--out` is omitted the file lands in the **current working
directory** with a sensible default name (`rate.png`, `pressure.png`,
`adc.png`, `report.html`). The `report` HTML embeds its four plots as inline
base64 PNGs, so it opens on any device with **no running server**.

A malformed CSV (bad header, wrong column count) is reported as a one-line
error on stderr with a **non-zero exit code** — the parser never silently skips
rows or returns partial data.

## Limitations (v1)

- **ADC is uncalibrated** — values are raw pulse amplitude (0-1023). There is no
  ADC→MeV calibration in v1; the detector ships uncalibrated, so the histogram's
  modal bin is only a rough proxy for the MIP / Landau peak in raw ADC units.
- **RTC drift** — the detector's real-time clock drifts ~30 min/year, so there
  is no sub-second cross-file timestamp accuracy. Rates are computed from the
  detector's own `ElapsedTime`/`DeadTime` counters (internally consistent), not
  from wall-clock time, so **flux is unaffected** — only the absolute timestamp
  labels on the time axes drift.
- **Warm-BMP280 bias** — the BMP280 sensor sits inside the warm detector case,
  so the absolute pressure reading is slightly biased high. This is not
  corrected in v1.
- **Atmospheric-temperature limitation (MU2-02)** — v1 fits **only** the
  barometric (pressure) coefficient. The detector's internal BMP280 temperature
  is **not** the correct variable for a temperature-coefficient fit: it tracks
  the warm enclosure, not the atmosphere. No temperature coefficient is
  therefore reported.
- **One file in, one report out** — no multi-file merging across detector resets
  in v1.

## Notes on the data

- `ID` ∈ {T, B, C} — top scintillator, bottom scintillator, coincidence. When
  the detector is configured with `events_all=false`, **only C events** are
  logged; the tooling handles a C-only log gracefully (T:C and B:C ratios show
  `n/a`).
- `DeadTime(mS)` is cumulative per stream in some firmware versions and
  per-event in others. The shape is **auto-detected** by monotonicity; when in
  doubt the spec fallback treats the rightmost row's value as the file total.
- Active scintillator area is 25 cm² (50 × 50 mm), used for the flux
  calculation.
