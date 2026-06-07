# NMDB neutron-monitor poller (Phase 13, MU2-06)

An isolated hourly oneshot poller that caches the **Oulu** neutron monitor's
counts/s from the NMDB / NEST ASCII export into SQLite (`nmdb_counts` +
`nmdb_meta`, migration `0007`). It is the global cosmic-ray reference the
dashboard overlays against local muon flux (`/api/nmdb`) and feeds the Forbush
indicator (`/api/forbush`).

## What it does

1. `fetch` the NEST `output=ascii` export over HTTPS from
   `https://www.nmdb.eu/nest/draw_graph.php` (shared SEC-05 hardened `_http.fetch`:
   TLS verify, timeouts, no off-host redirect, 5 MiB cap, retry/backoff).
2. `parse_nmdb` the fixed-format `YYYY-MM-DD HH:MM:SS;<counts/s>` rows into UTC-epoch
   `NmdbCount`s — strict on structure (no rows -> `ValueError`), tolerant per row
   (`null` count -> `None`, counted toward the parse-failure threshold).
3. `write_nmdb` appends the window (`INSERT OR IGNORE` on `UNIQUE(station, ts)` so a
   re-fetch does not duplicate) and upserts the single-row `nmdb_meta` freshness
   anchor (`fetched_at`).
4. Always emit one `poller_runs` audit row (`source='nmdb'`), in a second
   transaction so the audit survives a data-write rollback.

Exit `0` on success, `1` on fetch failure (`transient_fail`) or parse failure
(`parse_fail`, structural or over-threshold gap ratio). The poller is **oneshot
with no `Restart=`** — the hourly timer is the retry.

## Configuration

- `poller_nmdb_station` — NMDB station code, default `"OULU"` (the canonical global
  Forbush reference: high, stable count rate). Substituted into the NEST URL at
  runtime so the station stays configurable.
- `poller_nmdb_url` — the NEST URL template. **`yunits=0` is mandatory**: it returns
  ABSOLUTE counts/s; omitting it yields a relative scale that silently breaks the
  %-of-baseline math (Pitfall 3). `dtype=corr_for_efficiency`, `tresolution=60`
  (hourly), `last_days=8` (covers a full 7-day baseline window with margin).

## NMDB acceptable use + citation

NMDB asks scripted users to be gentle and to **cite the database**. An hourly poll
with a fixed `observatory/0.1` User-Agent is well within community norms. If you
publish any analysis derived from this data, cite NMDB (https://www.nmdb.eu) and
the Oulu station per their acknowledgement guidelines.

## Deploy note

`obs-api` does NOT auto-apply migrations. Run `apply_migrations()` for `0007`
(creating `nmdb_counts` + `nmdb_meta`) BEFORE starting the poller or the API, or
the writes and `/api/nmdb` route fail (Phase-10 deploy lesson). Enable but do not
start the timer in bootstrap; the operator gates start on chrony convergence:
`sudo systemctl start obs-nmdb-poll.timer`.
