# Observatory — Phase 1 (Lean)

A weather station, particle observatory, and dashboard for terrestrial and space events. Web only. Single visual theme.

Brief updated 23 May 2026. See [observatory_brief.md](observatory_brief.md) for full reference material (shopping list, supplier links, alternatives, external API justifications, reference links).

---

## Summary

A Raspberry Pi 4 acts as the brain, placed wherever convenient indoors (no loft required). An outdoor Pimoroni Enviro Weather board reports back over wifi. A muon detector lives next to the Pi. External data feeds (earthquakes, space weather, lightning, aurora) are polled from free public APIs. Everything logs to SQLite. A FastAPI backend exposes JSON + WebSocket and serves a static SvelteKit web app — all from the Pi itself. Accessible from any device on the home network at `http://observatory.local`.

iOS app, additional themes, wind/rain node, air quality node, second muon detector, the radio meteor detector, and remote access (Tailscale) are explicitly deferred to Phase 2.

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│  Pi 4 (on home network, http://observatory.local)│
│  ├── Mosquitto (MQTT broker)                     │
│  ├── Muon detector via USB serial                │
│  ├── External API pollers ─── earthquakes,       │
│  │                            solar, lightning,  │
│  │                            aurora             │
│  ├── SQLite                                      │
│  └── FastAPI ── JSON + WebSocket + static files  │
│                 (serves the SvelteKit bundle)    │
└────▲─────────────────────────────────────────────┘
     │ wifi · MQTT
     │
┌────┴─────────────────────────┐
│  Pimoroni Enviro Weather     │
│  (outside in Stevenson scr.) │
│  ├── BME280 (temp/hum/pres)  │
│  ├── LTR-559 (light)         │
│  └── Pico W · deep sleep     │
└──────────────────────────────┘

      Home wifi · http://observatory.local
            ▲
            │
   ┌────────┴────────┐
   │ Any device on   │  Laptop, phone, tablet
   │ the home wifi   │
   └─────────────────┘
```

### Data flow

1. **Pimoroni Enviro Weather** wakes from deep sleep on a schedule (e.g. every 5 minutes), reads BME280 + LTR-559, connects to home wifi, publishes a single MQTT message to the Pi, sleeps again. Runs for months on 2× AA rechargeables.
2. **Muon detector** streams events over USB serial; Python service writes to SQLite. PicoMuon includes onboard BMP280 for pressure correction.
3. **External API pollers** — small Python services that fetch from public APIs on a schedule (5–15 min intervals depending on source) and write events to SQLite.
4. **FastAPI** reads SQLite, serves JSON over REST and pushes live updates over WebSocket. Also serves the built SvelteKit static bundle from `/`.
5. **Browser** on any device on the home wifi loads the web app from `http://observatory.local`, then opens a WebSocket back to the same host.

---

## Phasing

| Weekend | Task |
|---|---|
| 1 | **Wipe and reinstall Pi 4** (fresh Pi OS Lite, 64-bit, Bookworm). Hostname `observatory`, static IP reserved on router. Boot, update, install Mosquitto + SQLite + FastAPI skeleton. Test wiring with a USB-connected BME280 to confirm the pipeline works. Confirm `http://observatory.local:8000` works from laptop. Set up weekly backup cron to a USB stick. |
| 2 | Configure Pimoroni Enviro Weather: flash latest firmware, run provisioning to set wifi + MQTT broker. Mount in Stevenson screen outside. Verify readings arrive at the Pi's MQTT broker. |
| 3 | Muon detector setup. PicoMuon = plug and play. |
| 4 | External API pollers — earthquakes (USGS+EMSC+BGS) and space weather (NOAA). |
| 5 | Remaining external pollers — lightning and aurora. |
| 6–7 | SvelteKit web app with `adapter-static`, Hyborg theme. WebSocket live updates. Build locally, deploy to Pi via rsync. |
| 8+ | Polish, ongoing data collection, decide on Phase 2 additions. |

---

## Software stack

### On the Pi

- **OS**: Raspberry Pi OS Lite (64-bit), Bookworm — fresh install, wiping prior project setup
- **Mosquitto**: MQTT broker
- **SQLite**: single-file database
- **FastAPI + uvicorn**: REST + WebSocket API
- **Muon detector code**: Python service reading USB serial, writing events to SQLite
- **observatory-collector**: Python service tying MQTT and muon serial together with synchronised timestamps
- **observatory-pollers**: small Python services for each external API, run on a schedule via systemd timers or APScheduler. One per source for isolation; failure in one doesn't take down the others.

### Sensor node firmware

- **Pimoroni's official Enviro firmware** on the Enviro Weather board. Pre-built MicroPython firmware. Handles deep sleep, RTC scheduling, MQTT publishing out of the box.
- Source: https://github.com/pimoroni/enviro

### Web frontend

- **SvelteKit** with `adapter-static` — builds to a folder of static HTML/JS/CSS, no server runtime needed.
- Build locally on dev machine, copy `build/` to the Pi via `scp` or `rsync`.
- **FastAPI serves the built bundle** at `/` using `StaticFiles`. Same process handles API + UI.
- **D3 or Observable Plot** for charts.
- **WebSocket** to `ws://observatory.local:8000/ws` — same host as the page, no CORS faff.
- **Hyborg theme only**: near-white background, Inter typography, large numerals, sage green accent (#6b8e6b), clean readable charts with proper Y-axis labels and current-value markers.

---

## Data model

Single SQLite database. Tables:

```sql
-- Local measurements
CREATE TABLE weather (
  id INTEGER PRIMARY KEY,
  node_id TEXT NOT NULL,
  ts INTEGER NOT NULL,
  temp_c REAL,
  humidity_pct REAL,
  pressure_hpa REAL,
  lux REAL,                     -- from LTR-559 light sensor
  battery_v REAL,
  wifi_rssi INTEGER
);
CREATE INDEX idx_weather_ts ON weather(ts);

CREATE TABLE muon_events (
  id INTEGER PRIMARY KEY,
  ts INTEGER NOT NULL,
  detector_pressure_hpa REAL,
  detector_temp_c REAL,
  amplitude REAL,
  coincidence INTEGER
);
CREATE INDEX idx_muon_ts ON muon_events(ts);

-- External data
CREATE TABLE earthquakes (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,         -- 'usgs' | 'emsc' | 'bgs'
  external_id TEXT NOT NULL,    -- source's event ID, for dedup
  ts INTEGER NOT NULL,
  magnitude REAL,
  depth_km REAL,
  latitude REAL,
  longitude REAL,
  place TEXT,
  UNIQUE(source, external_id)
);
CREATE INDEX idx_quakes_ts ON earthquakes(ts);
CREATE INDEX idx_quakes_mag ON earthquakes(magnitude);

CREATE TABLE space_weather (
  id INTEGER PRIMARY KEY,
  ts INTEGER NOT NULL,
  kp_index REAL,
  solar_wind_kms REAL,
  flare_class TEXT,             -- 'X1.2', 'M3.4', 'C2.1', etc
  flare_peak_ts INTEGER         -- nullable
);
CREATE INDEX idx_sw_ts ON space_weather(ts);

CREATE TABLE lightning_strikes (
  id INTEGER PRIMARY KEY,
  ts INTEGER NOT NULL,
  latitude REAL,
  longitude REAL,
  distance_km REAL              -- pre-computed from home location
);
CREATE INDEX idx_lightning_ts ON lightning_strikes(ts);

CREATE TABLE aurora_status (
  id INTEGER PRIMARY KEY,
  ts INTEGER NOT NULL,
  status TEXT NOT NULL,         -- 'green' | 'yellow' | 'amber' | 'red'
  detail TEXT
);
CREATE INDEX idx_aurora_ts ON aurora_status(ts);
```

Back up the `.db` file weekly to a USB stick (cron job, set up in Weekend 1).

---

## API sketch

### REST

```
GET  /api/current               -> latest values across all data
GET  /api/weather?from&to&agg   -> weather time series
GET  /api/muon?from&to&agg      -> muon flux time series, pressure-corrected
GET  /api/earthquakes?from&to&min_mag -> recent earthquake list
GET  /api/space-weather/current -> latest Kp, solar wind, flare class
GET  /api/space-weather?from&to -> time series
GET  /api/lightning/summary     -> hour counts, nearest strike, total today
GET  /api/aurora/current        -> current AuroraWatch status
GET  /api/events/recent         -> mixed event feed
GET  /api/stats/today           -> daily summary
```

### WebSocket

```
WS  /ws  -> {type: 'weather'|'muon'|'earthquake'|'space_weather'|'lightning'|'aurora', data: {...}}
```

---

## Dashboard layout (current sketch)

Top to bottom:

1. **Header** — current outside temp as the hero number, local time / sunrise / moon phase aside
2. **Stats row** — pressure, humidity, muons/min, light (lux)
3. **Muon flux chart** — 24h, pressure-corrected, with current-value marker
4. **Space weather** — solar flare class, solar wind, Kp index (9-cell bar)
5. **Earthquakes + Lightning** — side by side; earthquakes as a list with magnitude pills, lightning as counts + sparkline
6. **Aurora** — single-line status with coloured dot
7. **Temperature today** — supplementary 24h chart

See `observatory_dashboard.html` for the worked sketch.

---

## Security & privacy — required check before every commit

This repo is **public**. Nothing sensitive may enter the history. A
**sensitive-data gate runs on every commit** (pre-commit) and must pass —
do not bypass it with `--no-verify`.

What is enforced (`scripts/check-sensitive.sh`, wired in `.pre-commit-config.yaml`):
1. **No personal email in authorship** — `git user.email` must be a
   `@users.noreply.github.com` identity.
2. **No secret/credential files** — `.env*`, `*.pem`, `*.key`, the real
   `deploy/mosquitto/passwords` are refused (only `*.example` templates ship).
3. **No GPS EXIF in images** — home-location leak guard (via `exiftool`).
4. **No project-specific PII/secrets** — matched against
   `.git-sensitive-patterns`, a **local, gitignored** file whose real values
   (personal email, home lat/lon, etc.) never enter the repo. Copy
   `.git-sensitive-patterns.example` → `.git-sensitive-patterns` and fill it in
   on each clone.

Generic API keys/tokens are additionally caught by the **gitleaks** pre-commit
hook. Secrets, home coordinates, and the real `.env` live only on the Pi
(`/etc/observatory/observatory.env`) and in local gitignored files. When in
doubt, assume a value is sensitive and keep it out of git.

---

## Scope guardrails — Notes for future Peter

- **Phase 1 is intentionally narrow**: weather node + muon detector + external data feeds + web dashboard, served locally. Resist scope creep.
- **Defer to Phase 2**: iOS app, additional themes, UV sensor, wind/rain sensors, air quality node, radio meteor detector, cloud chamber, Moomin lamp, Tailscale for remote access.
- **No Cloudflare, no cloud, no tunnels**. Just the Pi on the home network. Tailscale is the right path if remote access becomes a real need later.
- **Web app first, no iOS**. If the project earns its keep after six months, build an iOS companion then.
- **Single theme (Hyborg) keeps the frontend simple**. The four-theme abstraction is deferred.
- **Set the Pi hostname to `observatory`** during initial install so `http://observatory.local` works via Avahi from day one.
- **Reserve the Pi's IP on the router** so it doesn't change between reboots.
- **Local-first by design**: even external API polls are cached locally; the dashboard reads from SQLite, never from upstream APIs directly.
- **PicoMuon has onboard temp/pressure** (BMP280) — pressure-corrected muon flux from a single device, no extra wiring.
- **Space weather is the most valuable external feed**: it gives muon data context that nothing else does.
- **Back up the SQLite weekly**. Months of accumulated data is the whole point.
- **Pi storage strategy**: 32GB microSD as boot/run drive, USB stick as rolling backup target. SSD deferred (poor value at current UK prices for <10GB/year write workload).
- When returning to this after a break: re-read this file, then `observatory_brief.md` for the supplier/reference detail.
