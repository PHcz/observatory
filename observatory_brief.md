# Observatory — Reference material

Detailed reference for Phase 1. The active project context lives in [CLAUDE.md](CLAUDE.md); this file holds the supporting detail that doesn't need to be in context every turn.

Brief updated 23 May 2026.

---

## Changes from the earlier brief

- **Outdoor weather node simplified**: Pimoroni Enviro Weather (off-the-shelf board with BME280 + LTR-559 light sensor + Pico W wifi) replaces the original LoRa-based DIY node. £30 board + accessories. No soldering, no separate LoRa receiver on the Pi.
- **Wifi everywhere**: outdoor wifi reaches the sensor location, so LoRa is unnecessary. Sensors publish directly to the Pi's MQTT broker over wifi.
- **UV sensor dropped** — would require a second mount outside the Stevenson screen. LTR-559 light reading (lux) is a fine proxy. UV deferred to Phase 2.
- **Local-only setup** — no Cloudflare. FastAPI serves both the API and the static SvelteKit bundle. Browse to `http://observatory.local` from any device on the home wifi.
- Radio meteor detector removed — antenna too big for the spaces available
- External data sources added — earthquakes (USGS, EMSC, BGS), solar/space weather (NOAA), lightning (Blitzortung), aurora (AuroraWatch UK)
- iOS app removed — web app only
- Themes reduced to one (Hyborg)
- Loft location dropped — power is the constraint, and the Pi can live anywhere
- PicoMuon chosen over DIY Geiger path
- Pi 4 storage: stick with existing 32GB microSD, no SSD purchase
- Confirmed PicoMuon has an onboard BMP280 (temp + pressure) — no separate weather sensor needed for muon pressure correction

---

## Location

All indoor kit (Pi, muon detector) needs only **one mains socket** between them — total power draw is ~8W. The PicoMuon is <1W; the Pi 4 ~5-8W idle.

**Physical footprint:**

| Item | Size |
|---|---|
| Pi 4 with heatsink | ~85 × 56 × 25mm (smaller than a paperback) |
| PicoMuon | ~200 × 100 × 60mm est. (shoebox-sized) |

Together they fit on a single shelf. Examples of suitable locations:

- **Spare room or study** on a bookshelf
- **Hallway cupboard or understairs** with one socket
- **Heated garage or shed** if you have one
- **Boiler room** (often has a socket and is warm/stable)

No antennas, no spatial constraints beyond the outdoor weather node and a window/wall to mount it near.

---

## Access

The Pi serves everything locally on the home network. No cloud, no tunnels, no external dependencies for the web layer.

### From inside the house

Three ways to reach the dashboard, in increasing order of polish:

1. **By IP address**: `http://192.168.x.x:8000` — works immediately, easy to forget.
2. **By Bonjour/Avahi hostname**: `http://observatory.local` — Pi OS publishes this automatically. Works from macOS, iOS, Linux, Windows 10+ on the same network. **Recommended.**
3. **By router-assigned DNS**: most home routers let you set a static IP + name. Reach the Pi at `http://observatory`. Slightly fiddlier setup, cleanest result.

To enable `.local` access, set the Pi's hostname to `observatory` during initial setup. Avahi-daemon is included in Raspberry Pi OS by default — no extra config needed.

### Static IP

Reserve the Pi's IP on the router so it doesn't change between reboots. Most routers have this in the DHCP settings — bind the MAC address to a fixed IP. Important because the Pi is the central piece; you don't want to chase its IP around.

### From outside the house (Phase 2)

**Recommended path: Tailscale.** Install Tailscale on the Pi and on your phone/laptop. They're now on a virtual private network reachable from anywhere. Free for personal use, no port forwarding, no DNS, no certificate management. The Pi keeps its `http://observatory.local` URL within the Tailscale network too if you enable MagicDNS.

**Not recommended**: opening ports on the router. Don't expose the Pi directly to the internet.

For Phase 1, just home wifi access is plenty.

---

## External data sources — detail

All free, all polling-based, all add minimal complexity. Each poller is ~50 lines of Python.

| Source | What it gives you | API | Poll rate |
|---|---|---|---|
| **USGS Earthquake API** | Global earthquakes M4+ | [`earthquake.usgs.gov/fdsnws/event/1/`](https://earthquake.usgs.gov/fdsnws/event/1/) | 5 min |
| **EMSC SeismicPortal** | European-Mediterranean earthquakes, faster updates than USGS for this region. Has WebSocket too. | [`seismicportal.eu`](https://www.seismicportal.eu/) | 5 min |
| **BGS Earthquakes** | UK-specific including small events (M1+) | [`earthquakes.bgs.ac.uk`](https://earthquakes.bgs.ac.uk/) | 30 min |
| **NOAA SWPC** | Solar flares (X/M/C class), solar wind speed, geomagnetic Kp index | [`services.swpc.noaa.gov`](https://services.swpc.noaa.gov/) | 15 min |
| **Blitzortung** | Real-time lightning strikes across Europe | [`blitzortung.org`](https://www.blitzortung.org/) | 1 min when active |
| **AuroraWatch UK** | UK aurora visibility alerts (Lancaster University) | [`aurorawatch.lancs.ac.uk/api`](https://aurorawatch.lancs.ac.uk/api/) | 15 min |

### Why these specifically

- **Earthquakes** — global + European + UK gives you full coverage from "magnitude 6 in Peru" down to "magnitude 1.7 in Surrey." Three sources because each fills different gaps; USGS alone misses small UK events.
- **Space weather** — pairs directly with muon data. Solar storms cause Forbush decreases in cosmic ray flux 24-72 hours after a major flare. Without this data, the muon detector's most interesting signal is invisible.
- **Lightning** — local atmospheric phenomena that connects to your weather data. When a storm cluster passes over the UK you can see it in real time.
- **Aurora** — rare but exciting; one Lancaster-maintained API call tells you if it might be visible tonight.

### What's deliberately excluded

- **ISS / satellite passes** — fun but cluttered, deferred to Phase 2.
- **Volcanic eruptions** — Smithsonian feed updates weekly, too slow for a live dashboard.
- **Forecast weather** — this is an observatory, not a weather app. Met Office can do forecasts.
- **Bright fireballs** — would be a natural pair with a meteor detector; deferred until/unless that comes back.

---

## Shopping list

All prices verified May 2026. UK suppliers preferred.

### Already on hand (do not rebuy)

- Raspberry Pi 4 board
- Heatsink (already fitted)
- Original Pi 4 USB-C PSU
- microSD card (for first boot and recovery — **will be wiped of previous project**)
- Small USB sticks (~5GB, repurposed as weekly SQLite backup targets)

### Pi 4 brain

**Nothing to buy. Subtotal: £0.**

**Notes**:

- 32GB is plenty: Raspberry Pi OS Lite is ~3GB, the project code and dependencies maybe 1-2GB more, and the SQLite database grows by ~5-10GB per year worst case.
- Write workload is light: sensor readings every minute, external API polls every 5-15 minutes. A decent A1/A2-rated microSD card will last 2-4 years before wear becomes a real concern.
- **Critical**: weekly cron backup of the SQLite `.db` file to a USB stick.
- No safe-shutdown button without a case — use `sudo shutdown -h now` over SSH.
- Monitor temperature occasionally with `vcgencmd measure_temp`. Above 80°C = throttling.
- If the SD card ever shows signs of failing, upgrade to a **high-endurance microSD** like SanDisk Max Endurance 64GB (~£20).
- Portable USB SSD remains a future option, but at current UK prices (£100-140 for 500GB) it's not great value for a project that writes <10GB/year.

### Outdoor weather node — Pimoroni Enviro Weather

All-in-one off-the-shelf board with a Raspberry Pi Pico W (wifi), BME280 (temp/humidity/pressure), LTR-559 (light), JST battery connector, onboard RTC for deep sleep, Qw/ST port for future sensor expansion.

| Item | Supplier | Price | Notes |
|---|---|---|---|
| Pimoroni Enviro Weather (Pico W Aboard) | [The Pi Hut](https://thepihut.com/products/enviro-weather-pico-w-aboard-board-only) | £30 | Already ordered. |
| 2× AA battery holder with switch + JST-PH connector | [The Pi Hut](https://thepihut.com/collections/battery-holders) | £1.80 | JST-PH connector (not JST-XH/ZH). Already ordered. |
| 2× AA NiMH rechargeable batteries + charger | Amazon | £15 | Eneloop or similar. Realistically 8-14 months between charges with 5-min reading / 25-min publish cycle. |

**Subtotal: ~£47 with batteries and charger.**

**Why AA instead of the AAA Pimoroni suggests by default**:

- **2-3× longer battery life**: ~2000mAh AA NiMH vs ~800mAh AAA NiMH.
- **Better wifi antenna positioning**: AAA holder mounts behind the board (against the Pico W's antenna). AA holder lives next to the board in the Stevenson screen, leaving the antenna unobstructed.
- **AA cells more widely available** for emergency swaps.
- **TFA Stevenson screen has room** — AA pack fits next to the board without issue.

**Battery options (flexible)**:

The board accepts 2-5.5V input. Alternatives if AA NiMH isn't right:

- 2× AA alkaline (3V): 12-20 months, single-use
- 2× AAA NiMH (2.4V): 3-6 months, smallest fit (Pimoroni's default)
- 2× AAA alkaline (3V): 4-8 months, single-use
- Single-cell LiPo: also works but no onboard charging — need a LiPo Amigo charger separately

Battery life depends heavily on how often the board uploads over wifi. Pimoroni's firmware default of "read every 5 min, upload every 25 min" balances data granularity against battery life. Deep sleep current is 20µA.

**Wifi antenna placement note**: The Pico W's wireless antenna is on the back of the board. With AA in a separate holder, this isn't a problem.

**About a UV sensor (deferred)**:

The Enviro Weather has a Qw/ST connector, so a VEML6075 UV breakout (~£10) plugs in directly without soldering. *But* UV sensors need direct sunlight to read meaningfully — putting one inside a Stevenson screen defeats both: the Stevenson screen would block the UV, and the UV sensor's outside placement would defeat the screen's temperature accuracy. Adding UV properly means a second small enclosure on top of the screen with its own cable run. Not worth the complexity for Phase 1.

### Stevenson screen

Recommended:

| Item | Supplier | Price | Notes |
|---|---|---|---|
| TFA 98.1114 protective sensor shelter | [Weather Spares](https://weatherspares.co.uk/products/tfa-protective-sensor-shelter-stevenson-screen-98-1114) | £20 | In stock UK supplier. White louvred plastic, generous internal space (Enviro Weather fits), cable opening at bottom, mounting brackets included. |

Alternatives:

| Option | Cost | Notes |
|---|---|---|
| 3D print from Printables/Thingiverse | ~£10 filament | [MakerMeik design](https://www.printables.com/model/109971-radiation-shield-stevenson-screen-temperature-sens) is solid. Use PETG or ASA (PLA degrades in UV after 1-2 years). |
| Plant pot saucer stack | ~£5 | 6-8 white plastic saucers from B&Q with a central bolt and washers as spacers. |
| MetSpec MET01 | £80-150+ | [Weather Shop UK](https://www.weathershop.co.uk/metspec-met01screen-traditionaloutdoor). Met Office spec, powder-coated aluminium. Overkill. |

**Budget: £20 (TFA recommended)**

### Muon detector — UKRAA PicoMuon

Plug-and-play, two scintillators with 17mm separation, onboard BMP280 (temp + pressure), software pre-installed, USB output.

| Item | Supplier | Price | Notes |
|---|---|---|---|
| PicoMuon detector | [UKRAA store](https://ukraa.com/store/categories/cosmic-rays) | £360 | **Already delivered.** Inc. UK P&P, no VAT. Comes with a micro-USB cable in the box. |

### Totals

| Configuration | Cost |
|---|---|
| **As chosen (PicoMuon path)** | **~£463** |

---

## Reverse proxy (optional)

For Phase 1, FastAPI on port 8000 is fine. If you later want the dashboard on the standard port 80 without typing the port number:

- **Caddy** is the easy choice — single-line config, automatic HTTPS for local hostnames if you want it.
- **nginx** works too, slightly more config.

Skip this for the initial build. Add it later if `:8000` annoys you.

---

## Open questions / decisions to make during planning

1. **Stevenson screen**: TFA 98.1114 from Weather Spares (£20) is the recommended buy. 3D-print only if you have a printer; plant-pot stack if you want a laugh.
2. **Location**: pick a single shelf with a mains socket for Pi + muon detector. Weather node mounts outside.
3. **Blitzortung access**: their data is community-shared via Blue/Red station memberships. Check current public access rules at signup time. Worst case there's a 30-min delayed public feed.
4. **Home location for distance calculations**: needs your lat/long stored in config so the lightning poller can compute "nearest strike".
5. **Reverse proxy now or later**: Caddy on port 80 vs FastAPI directly on :8000. Default: skip Caddy for v1.

---

## Reference links

### Suppliers

- The Pi Hut: https://thepihut.com/
- Pimoroni: https://shop.pimoroni.com/
- Weather Spares (Stevenson screens, weather kit): https://weatherspares.co.uk/
- UKRAA: https://ukraa.com/store/categories/cosmic-rays
- UKRAA contact: `picomuon@ukraa.com`

### Hardware

- Pimoroni Enviro Weather (The Pi Hut): https://thepihut.com/products/enviro-weather-pico-w-aboard-board-only
- Pimoroni Enviro Weather (Pimoroni direct): https://shop.pimoroni.com/products/enviro-weather

### External data APIs

- USGS Earthquake API: https://earthquake.usgs.gov/fdsnws/event/1/
- EMSC SeismicPortal: https://www.seismicportal.eu/
- BGS UK Earthquakes: https://earthquakes.bgs.ac.uk/
- NOAA Space Weather Prediction Center: https://services.swpc.noaa.gov/
- Blitzortung lightning: https://www.blitzortung.org/
- AuroraWatch UK API: https://aurorawatch.lancs.ac.uk/api/

### Documentation & background

- Pimoroni Enviro firmware: https://github.com/pimoroni/enviro
- Enviro Weather docs: https://github.com/pimoroni/enviro/blob/main/documentation/boards/enviro-weather.md
- PicoMuon manual: https://www.astronomy.me.uk/wp-content/uploads/2026/03/UKRAA-PicoMuon_detector_Manual_ISSUE_1.1-acc_300326.pdf
- CosmicWatch (alternative DIY scintillator path, for reference only): http://www.cosmicwatch.lns.mit.edu/
- ESPHome: https://esphome.io/
