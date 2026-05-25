# Earthquake fixtures (pinned real captures)

These fixtures are **pinned** — they are committed once and only refreshed when a parser
test fails because the upstream shape changed. Do NOT auto-refresh from CI. The fail-loud
contract is: upstream format drift breaks tests, we update the fixture + parser together.

## Re-capture

Run `bash scripts/capture-earthquake-fixtures.sh` from the repo root. The script uses the
Observatory User-Agent and writes to the three subdirs.

## Captured shapes

| File | Source | Endpoint | Typical size |
|------|--------|----------|--------------|
| usgs/sample_4_5_day.json | USGS | /earthquakes/feed/v1.0/summary/4.5_day.geojson | ~6 KB / 8 features |
| emsc/sample_pastday.json | EMSC | /fdsnws/event/1/query?format=json&limit=200&minmag=2.5 | ~5–110 KB |
| bgs/sample_recent.xml | BGS | /feeds/MhSeismology.xml | ~20 KB / 43 items |

## Per-source notes

- **USGS** `time` is **integer milliseconds since epoch** (not ISO). Parser divides by 1000.
- **EMSC** uses `properties.unid` as the dedup key (== `feature.id`, kept for clarity).
- **BGS** has **no `<guid>`** — external_id is derived from the 14-digit suffix of `<link>`
  via regex `/recent_events/(\d{14})\.html`. `pubDate` is naive RFC 822 — parser assumes UTC
  at the parser level (NOT in `parse_ts()`), per RESEARCH Open Question 1.

Capture date and observed event counts go in the corresponding git commit.
