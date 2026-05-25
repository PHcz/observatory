# Pinned fixtures

Per-phase pinned upstream captures. **Pinned** = committed once and only refreshed when a
parser test fails because upstream shape changed. Do NOT auto-refresh from CI. The fail-loud
contract is: upstream format drift breaks tests, we update the fixture + parser together.

`tests/fixtures/` is excluded from EOF + trailing-whitespace pre-commit hooks so wire-format
captures stay byte-perfect (Phase 4 decision).

## Phase 4 (earthquakes)

See [earthquakes/README.md](earthquakes/README.md). Recapture: `bash scripts/capture-earthquake-fixtures.sh`.

## Phase 5 fixtures

Captured 2026-05-25 via `scripts/capture-phase5-fixtures.sh`.

| File | Source | Shape | Notes |
|------|--------|-------|-------|
| noaa/kp_sample.json | services.swpc.noaa.gov | list[dict] | `time_tag` is NAIVE ISO — treat as UTC at parser |
| noaa/solar_wind_sample.json | services.swpc.noaa.gov | CSV-as-JSON [[headers],[row],...] | `speed` at column index 2; space-separated naive time |
| noaa/xray_sample.json | services.swpc.noaa.gov | list[dict] | Two records per minute (energy bands); flare class from `0.1-0.8nm` band |
| aurora/current_status_sample.xml | aurorawatch-api.lancs.ac.uk | flat XML | `<datetime>` uses compact `+0000` form; needs `email.utils` carve-out |
| blitzortung/sample_frames.bin | (synth placeholder) | LZW-obfuscated JSON | Real capture deferred to 05-04 Task 1 post-probe |

**Recapture procedure:** `bash scripts/capture-phase5-fixtures.sh` from repo root; commit the
diff with `chore(05-XX): refresh phase 5 fixtures (YYYY-MM-DD)`.

**Researcher's note (2026-05-25):** the CONTEXT-listed NOAA URLs returned 404. The capture
script uses the verified working URLs:
- `/json/planetary_k_index_1m.json` (Kp 1-min)
- `/products/solar-wind/plasma-2-hour.json` (solar wind plasma)
- `/json/goes/primary/xrays-6-hour.json` (GOES X-ray flux)

**Blitzortung note:** `sample_frames.bin` is a 17-byte ASCII placeholder. Plan 05-04 Task 1
must replace it with a real LZW-obfuscated WS frame capture once the port probe (8056 vs 443)
succeeds.
