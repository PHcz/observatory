# Observatory

> A Raspberry Pi weather station, cosmic-ray muon detector, and space/earth-event dashboard — all served on your home network.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

![Observatory dashboard (light theme): hero outside-temperature, stats row, pressure-corrected muon flux chart, space weather, earthquakes and lightning, and aurora status](docs/images/dashboard-light.png)

This repository is a **build-your-own guide**: everything you need to assemble and run your own copy. It is shared as a showcase, not a polished product — fork it, adapt it, build your own observatory.

## What it is

Observatory turns a Raspberry Pi 4 into the brain of a small home science station. An outdoor [Pimoroni Enviro Weather](https://thepihut.com/products/enviro-weather-pico-w-aboard-board-only) board reports temperature, humidity, pressure, and light over wifi; a [PicoMuon](https://ukraa.com/store/categories/cosmic-rays) cosmic-ray detector sits next to the Pi and streams muon events over USB. The Pi also polls free public APIs for earthquakes, solar weather, lightning, and aurora alerts.

Everything logs to a single SQLite database. A FastAPI backend exposes the data as JSON and pushes live updates over a WebSocket, and serves a SvelteKit dashboard from the same process. Open `http://observatory.local` from any device on your home wifi and you get the whole picture in one place. No cloud, no tunnels — local-first by design.

## What you'll need

A short summary of the core kit. The full bill of materials with supplier links and alternatives is in **[docs/HARDWARE.md](docs/HARDWARE.md)**.

| Part | Role | Rough cost |
|------|------|-----------|
| Raspberry Pi 4 (+ PSU, microSD, heatsink) | The brain — backend, database, dashboard | assumed owned (+£35–60 if buying) |
| Pimoroni Enviro Weather board | Outdoor temp/humidity/pressure/light sensor node | ~£30 |
| 4× AA NiMH rechargeables + charger, battery holder | Powers the weather node for months | ~£17 |
| Stevenson screen (TFA 98.1114 or 3D-printed) | Weatherproof housing for the sensor node | ~£5–20 |
| PicoMuon detector | Cosmic-ray muon detection (optional but the highlight) | ~£360 |

**Cost:** a **core weather + dashboard build runs ~£70–100** (Pi assumed already owned). Adding the **PicoMuon takes the full build to ~£450–480**, dominated by the detector itself.

**Effort:** roughly **6–8 weekends** from a fresh Pi to a running dashboard — provisioning the Pi, flashing the weather node, wiring the muon detector, adding the external data pollers, then building and deploying the web app.

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

**Data flow:**

- The **Enviro Weather** node wakes from deep sleep on a schedule (e.g. every 5 minutes), reads its sensors, publishes a single MQTT message to the Pi, and sleeps again — running for months on 4× AA rechargeables.
- The **muon detector** streams events over USB serial; a Python service writes them to SQLite. The PicoMuon's onboard BMP280 gives pressure-corrected flux from a single device.
- **External API pollers** — one small isolated Python service per source — fetch from public APIs on a schedule and write events to SQLite.
- **FastAPI** reads SQLite, serves REST + WebSocket, and serves the built SvelteKit bundle from `/`. The browser loads the page and opens a WebSocket back to the same host — no CORS to wrangle.

## Quick start

The dashboard and backend build and test with three headline commands:

```bash
uv sync                              # Python backend + dev deps from uv.lock
uv run pytest                        # fast test suite (no network, no Docker)
cd frontend && npm ci && npm run build   # static SvelteKit bundle
```

Full clean-machine build and deploy instructions — Pi provisioning, weather-node flashing, and rsync deploy — are in **[docs/SETUP.md](docs/SETUP.md)**.

## Screenshots

The dashboard ships with both a light and a dark theme (switchable from `/settings`).

![Light theme — the full dashboard: hero temperature, stats row, muon flux, space weather, earthquakes, lightning, and aurora](docs/images/dashboard-light.png)

![Dark theme — the same dashboard rendered in dark mode](docs/images/dashboard-dark.png)

## Project status

Showcase project, shared **as-is** — not actively maintained. Issues and pull requests may not get a timely response. Fork it and build your own. If you do want to contribute, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Documentation

- **[docs/HARDWARE.md](docs/HARDWARE.md)** — full bill of materials, supplier links, and alternatives
- **[docs/SETUP.md](docs/SETUP.md)** — fresh build and deploy from a clean clone
- **[docs/OPERATIONS.md](docs/OPERATIONS.md)** — day-to-day running and maintenance
- **[deploy/enviro/PROVISIONING.md](deploy/enviro/PROVISIONING.md)** — weather-node provisioning runbook
- **[observatory_brief.md](observatory_brief.md)** — the original project brief and reference material

## License

MIT — see [LICENSE](LICENSE).
