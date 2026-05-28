# Enviro Weather provisioning runbook

Operator runbook for physically provisioning the Pimoroni Enviro Weather (Pico W
Aboard) node, flashing the firmware, joining it to the home wifi + Mosquitto
broker on the Pi, and verifying readings land in the `weather` table.

Phase 3 software (subscriber, broker config, ACL, /api/health surfacing,
local-integration smoke) shipped in plans 03-00 through 03-08. This runbook
closes the **hardware** side. The acceptance checklist that gates phase
sign-off is at
[`.planning/phases/03-weather-node/03-09-HARDWARE-ACCEPTANCE.md`](../../.planning/phases/03-weather-node/03-09-HARDWARE-ACCEPTANCE.md).

The runbook is split into two sections:

- **Part A — Indoor bench test** (run immediately when the board arrives, even
  before the Stevenson screen / NiMH cells land). Closes Phase 3 success
  criterion #1 (live publishes) end-to-end against the real device.
- **Part B — Outdoor deployment** (deferred until Stevenson screen + AA NiMH
  rechargeables arrive). Closes WEATHER-01 final mount + success criterion
  #4 (48-hour soak).

---

## Hardware checklist

Confirm before you start:

- [ ] Pimoroni Enviro Weather board (PIM589 — Pico W Aboard variant)
- [ ] USB-C cable for flashing + bench-test power
- [ ] 2× AA battery holder with switch + JST-PH cable (already ordered)
- [ ] Any 2× AA cells for Part A bench test (alkalines acceptable; NiMH not
      required until Part B)
- [ ] Mac/laptop on the same home wifi as the Pi (`observatory.local`)
- [ ] Pi reachable at `observatory.local`, `obs-api.service` running with
      Phase 3 code deployed (see § Pi-side prerequisites)
- [ ] Mosquitto installed + hardened (see § Pi-side prerequisites)

Deferred to Part B (no rush — Part A doesn't need these):

- [ ] TFA 98.1114 protective sensor shelter (Stevenson screen) — Weather
      Spares, £20 — see [observatory_brief.md §Stevenson screen](../../observatory_brief.md)
- [ ] 4× AA NiMH rechargeables + charger (Eneloop or similar) — Amazon, £15 —
      see [observatory_brief.md §Power](../../observatory_brief.md). Expected
      cell life on 2× AA NiMH at 5-min read / 25-min upload cadence is
      8-14 months.
- [ ] Mounting bracket / post for screen (1.5-2 m above ground, north-facing)

---

## Pi-side prerequisites

Before flashing the board, the Pi must already have Phase 3 code + broker config
deployed. If you already did this on the Phase 3 software-close session, skip
to Part A.

### 1. Pull Phase 3 code + restart obs-api

```bash
ssh pi@observatory.local
cd ~/observatory
git pull
uv sync
sudo systemctl restart obs-api.service
sudo systemctl status obs-api.service
```

Expected: `active (running)`. If failing, check `journalctl -u obs-api.service`.

### 2. Apply migration 0003 (UNIQUE(node_id, ts) on weather)

```bash
uv run python -m yoyo apply --database "sqlite:///var/lib/observatory/observatory.db" migrations/
```

(Idempotent — re-running is safe; `migrations/0003_weather_unique.sql` is the
only one new since Phase 2 baseline.)

### 3. Install hardened Mosquitto config + create users

If not already done from Phase 3 deploy:

```bash
# 1. Render mosquitto.conf with the Pi's LAN IP (bootstrap-pi.sh Section 14d
#    does this; manual one-liner here):
sudo cp ~/observatory/deploy/mosquitto/mosquitto.conf /etc/mosquitto/conf.d/observatory.conf
sudo cp ~/observatory/deploy/mosquitto/acl.conf /etc/mosquitto/acl
LAN_IP=$(hostname -I | awk '{print $1}')
sudo sed -i "s/\${LAN_IP}/${LAN_IP}/" /etc/mosquitto/conf.d/observatory.conf

# 2. Create password file with two users.
#    Pick strong random passwords; store them in /etc/observatory/secrets.env
#    (gitignored). Generate via: openssl rand -base64 24
export OBS_MQTT_PUB_PASSWORD="$(openssl rand -base64 24)"
export OBS_MQTT_SUB_PASSWORD="$(openssl rand -base64 24)"
echo "OBS_MQTT_PUB_PASSWORD=${OBS_MQTT_PUB_PASSWORD}" | sudo tee -a /etc/observatory/secrets.env
echo "OBS_MQTT_SUB_PASSWORD=${OBS_MQTT_SUB_PASSWORD}" | sudo tee -a /etc/observatory/secrets.env
sudo chmod 600 /etc/observatory/secrets.env

# 3. Hash them into /etc/mosquitto/passwords (see deploy/mosquitto/README.md
#    for the canonical procedure).
umask 077
sudo touch /etc/mosquitto/passwords
sudo chown mosquitto:mosquitto /etc/mosquitto/passwords
sudo chmod 640 /etc/mosquitto/passwords
sudo mosquitto_passwd -c -b /etc/mosquitto/passwords \
     enviro-observatory-weather "${OBS_MQTT_PUB_PASSWORD}"
sudo mosquitto_passwd -b /etc/mosquitto/passwords \
     obs-api-subscriber "${OBS_MQTT_SUB_PASSWORD}"

# 4. Wire the subscriber password into the obs-api env file so the FastAPI
#    subscriber can authenticate. /etc/observatory/observatory.env is the
#    EnvironmentFile= for obs-api.service.
echo "OBSERVATORY_MQTT_USERNAME=obs-api-subscriber" | sudo tee -a /etc/observatory/observatory.env
echo "OBSERVATORY_MQTT_PASSWORD=${OBS_MQTT_SUB_PASSWORD}" | sudo tee -a /etc/observatory/observatory.env
echo "OBSERVATORY_MQTT_BROKER_HOST=localhost" | sudo tee -a /etc/observatory/observatory.env
echo "OBSERVATORY_MQTT_BROKER_PORT=1883" | sudo tee -a /etc/observatory/observatory.env
echo "OBSERVATORY_WEATHER_NICKNAME=observatory-weather" | sudo tee -a /etc/observatory/observatory.env

# 5. Reload Mosquitto + restart obs-api so the new env vars and creds load.
sudo systemctl restart mosquitto
sudo systemctl restart obs-api.service
```

Verify both are healthy:

```bash
sudo systemctl is-active mosquitto obs-api.service
# expected: active\nactive
ss -tlnp | grep 1883
# expected: <LAN-IP>:1883 (NOT 0.0.0.0)
```

See [`deploy/mosquitto/README.md`](../mosquitto/README.md) for the full
hardening reference (LAN-bind, off-network nmap probe, ACL test).

### 4. Pre-board smoke (optional)

Confirm the whole pipeline works with the existing mock publisher before
plugging in real hardware:

```bash
# On the Pi (or laptop with broker port forwarded):
uv run python scripts/fake-enviro.py \
    --broker-host localhost \
    --broker-port 1883 \
    --username enviro-observatory-weather \
    --password "${OBS_MQTT_PUB_PASSWORD}" \
    --nickname observatory-weather \
    --interval 5 \
    --count 3
```

Then check the DB picked them up:

```bash
sqlite3 /var/lib/observatory/observatory.db \
    "SELECT ts, node_id, temp_c, humidity_pct, pressure_hpa, lux, battery_v \
     FROM weather WHERE node_id='observatory-weather' ORDER BY ts DESC LIMIT 5"
```

You should see 3 rows. If yes, the broker → subscriber → SQLite path is healthy
and the only remaining variable is the real board.

---

# Part A — Indoor bench test

Run this section as soon as the board lands. Goal: prove the real Pimoroni
firmware can publish to your broker and that rows land in `weather`.

## A.1 Flash latest firmware

1. Download the latest `enviro-vX.Y.uf2` release from
   <https://github.com/pimoroni/enviro/releases>.
2. Hold the **BOOTSEL** button on the Pico W while plugging USB-C into your
   laptop. The board mounts as a USB volume named `RPI-RP2`.
3. Drag the `.uf2` file onto the volume. The board reboots automatically and
   the volume disappears.

## A.2 Enter provisioning AP mode

1. Disconnect USB. With cells (or USB) attached, **press and hold the on-board
   provisioning button while powering on** (see the firmware release notes —
   varies by board rev; the Weather rev presents a single user button).
2. After a few seconds the board hosts a wifi access point named `enviro`.
3. On your laptop, join `enviro` (no password). A captive portal should pop
   up; if not, browse to <http://192.168.4.1/>.

## A.3 Captive-portal configuration

Set the following values **verbatim** — they match what the Pi-side subscriber
and ACL expect.

| Field             | Value                                                   |
| ----------------- | ------------------------------------------------------- |
| Board type        | **Weather**                                             |
| Nickname          | `observatory-weather`                                   |
| Wifi SSID         | _your home wifi SSID_                                   |
| Wifi password     | _your home wifi password_                               |
| Destination       | **MQTT**                                                |
| Broker host       | `observatory.local` (fallback to the Pi's LAN IP if mDNS flakes) |
| Broker port       | `1883`                                                  |
| Broker username   | `enviro-observatory-weather`                            |
| Broker password   | value of `OBS_MQTT_PUB_PASSWORD` from `/etc/observatory/secrets.env` |
| Reading frequency | **5 minutes**                                           |
| Upload frequency  | **25 minutes** (= 5 readings batched per upload)        |

Save. The board reboots into normal operation.

For the bench test you can shorten the wait by setting reading=1 / upload=1
during this session and re-provisioning to 5/25 before mounting outside.

## A.4 Verify on the Pi

Open two SSH sessions to `observatory.local`:

### Session 1 — watch live MQTT traffic

```bash
sudo cat /etc/observatory/secrets.env  # grab the subscriber password
mosquitto_sub -h localhost \
    -u obs-api-subscriber \
    -P "${OBS_MQTT_SUB_PASSWORD}" \
    -t 'enviro/#' -v
```

Within one upload cycle (1 min if you shortened it, otherwise up to 25 min) a
JSON payload appears on `enviro/observatory-weather`. The output line begins
with the topic name followed by the full JSON envelope (nickname, model, uid,
timestamp, readings).

### Session 2 — confirm SQLite rows

```bash
sqlite3 /var/lib/observatory/observatory.db \
    "SELECT datetime(ts, 'unixepoch') AS iso_ts, node_id, temp_c, \
            humidity_pct, pressure_hpa, lux, battery_v \
     FROM weather WHERE node_id='observatory-weather' \
     ORDER BY ts DESC LIMIT 5"
```

At least one row should have arrived. Sanity-check the readings against the
room (~20°C, ~40-60% RH, ~1000 hPa, lux > 0 in daylight, battery_v ~ 2.6-3.0
on fresh alkalines).

### Session 3 — confirm /api/health weather block

From any device on the home wifi:

```bash
curl -s http://observatory.local:8000/api/health | jq '.local.weather'
```

Expected shape (per Phase 3 plan 03-04):

```json
{
  "source": "observatory-weather",
  "last_event_ts": 1748449200,
  "staleness_threshold_sec": 1800,
  "status": "healthy"
}
```

If `last_event_ts` is `null`, no rows have been written yet. Wait for an
upload cycle and re-curl. `status` flips to `stale` after 1800 s (= 30 min)
without a row, and `down` after 3600 s.

### Session 4 — dashboard sanity check

Open <http://observatory.local:8000/> in a browser. The weather panel (top
hero number) should show real outside temperature within ~1 upload cycle.
WebSocket fan-out is part of Phase 7 and runs in the same process.

## A.5 Optional — capture baseline payloads

For Phase 8 regression fixtures, leave a capture script running for a few
hours and archive the JSON files:

```bash
uv run python scripts/capture-enviro-payloads.py \
    --broker-host localhost \
    --username obs-api-subscriber \
    --password "${OBS_MQTT_SUB_PASSWORD}" \
    --out-dir captures/enviro/$(date +%Y%m%d)
```

Commit nothing — the capture is a local-only debugging artefact unless you
choose to promote one into `tests/weather/fixtures/`.

## A.6 Bench-test sign-off

When Part A passes, fill in the **Bench test** section of
[`03-09-HARDWARE-ACCEPTANCE.md`](../../.planning/phases/03-weather-node/03-09-HARDWARE-ACCEPTANCE.md)
and commit. This closes Phase 3 success criterion #1 (live publishes) and the
hardware half of WEATHER-02 (broker carries real traffic). WEATHER-01,
SEC-03 off-network probe, and the 48 h soak (success criterion #4) remain
open until Part B.

---

# Part B — Outdoor deployment (DEFERRED until screen + NiMH arrive)

Do not run this section until the Stevenson screen and AA NiMH rechargeables
are on hand. Purchasing notes are in
[`observatory_brief.md` §Stevenson screen](../../observatory_brief.md) and
§Power.

## B.1 Charge cells + install in holder

1. Charge 2× AA NiMH (Eneloop or similar) to full on a smart charger.
2. Insert into the 2× AA holder (switch in OFF position).
3. Measure cell voltage with a multimeter — fresh NiMH ≈ 1.35-1.4 V each, so
   pack ≈ 2.7-2.8 V. NiMH cutoff is around 2.0 V (battery_v in the readings
   will show this).

## B.2 Re-provision to production cadence (if you shortened it for bench)

Repeat steps A.2 + A.3 with **Reading frequency = 5 minutes, Upload frequency
= 25 minutes**. Skip if Part A already locked these values.

## B.3 Mount in Stevenson screen

1. Power the board from the AA holder via the JST-PH cable (USB-C
   disconnected).
2. Confirm one upload cycle arrives via `mosquitto_sub` (Session 1 above) on
   battery power.
3. Insert the board into the TFA 98.1114 internal mount per the screen
   instructions. Route the JST cable through the base opening; leave slack so
   there's no strain on the connector.
4. Close the screen.

## B.4 Mount the screen outside

Per WMO convention and Stevenson screen norms:

- North-facing (Northern hemisphere) — louvres receive no direct sunlight.
- 1.5-2.0 m above ground (over grass if possible; not over hot tarmac).
- Clear of buildings/trees on the sun-facing side (avoids re-radiated heat).
- Use the brackets included with the TFA shelter; secure to a fence post,
  pole, or wall bracket.

## B.5 First-light verification

Wait one full upload cycle (25 min). Then:

```bash
mosquitto_sub -h localhost -u obs-api-subscriber -P "${OBS_MQTT_SUB_PASSWORD}" \
    -t 'enviro/observatory-weather' -v -C 1
sqlite3 /var/lib/observatory/observatory.db \
    "SELECT datetime(ts, 'unixepoch'), temp_c, humidity_pct, pressure_hpa, \
            lux, battery_v FROM weather WHERE node_id='observatory-weather' \
     ORDER BY ts DESC LIMIT 1"
```

Outdoor temp should match a nearby reference (Met Office UK / phone weather
app) within ~1-2 °C. Lux outdoors during daylight should be in the
hundreds-to-tens-of-thousands range.

## B.6 SEC-03 off-network probe

From a device **off** the home network (mobile hotspot on your phone):

```bash
nmap <your-public-IP-or-pi-LAN-IP-if-reachable> -p 1883
```

Expected: `filtered` or `connection refused`. If `open`, Mosquitto is exposed
beyond the LAN — `ss -tlnp | grep 1883` on the Pi must show
`<LAN-IP>:1883`, not `0.0.0.0:1883`. Re-render
`/etc/mosquitto/conf.d/observatory.conf` with the correct LAN IP and restart
Mosquitto.

## B.7 48-hour soak (success criterion #4)

Leave the node running for at least 48 h after outdoor mount. Then:

```bash
uv run python scripts/check-weather-gaps.py --since-hours 48
```

The script exits 0 when the max inter-row gap is ≤ 4500 s (= 75 min = 3 ×
25 min upload cadence). Output is JSON on stdout + a human summary on
stderr; capture both into the acceptance file.

If the script exits non-zero:

- Inspect `journalctl -u obs-api.service --since '48 hours ago' | grep
  weather_mqtt_disconnected` for subscriber-side outages.
- Inspect `journalctl -u mosquitto --since '48 hours ago' | grep -E
  'crash|restart|killed'` for broker-side issues.
- Inspect the most recent `battery_v` value — if < 2.2 V, low-battery is the
  likely cause; swap cells.

## B.8 Final sign-off

Fill in the **Outdoor deployment** + **48 h soak** sections of
[`03-09-HARDWARE-ACCEPTANCE.md`](../../.planning/phases/03-weather-node/03-09-HARDWARE-ACCEPTANCE.md),
tick the **PASS** decision, commit, and Phase 3 is fully closed.

---

## Troubleshooting

### Board won't enter AP mode

- Firmware version mismatch — re-flash with the latest `.uf2`.
- Wrong button hold — check the release notes for your firmware version;
  the trigger varies between firmware releases.

### Board joins wifi but no MQTT publishes

- Check the captive portal saved the broker host correctly. mDNS
  (`observatory.local`) sometimes flakes on cheap consumer routers; fall back
  to the Pi's LAN IP.
- Confirm the broker is reachable from the board's vantage point:
  `mosquitto_pub -h <broker> -u enviro-observatory-weather -P "${PW}" \
       -t enviro/test -m hi` from your laptop on the same wifi.

### Broker logs `auth failure for client <uid>` for the Enviro

- Password mismatch. Re-run the captive portal step A.3 and re-enter
  `OBS_MQTT_PUB_PASSWORD`.
- Username typo: must be exactly `enviro-observatory-weather`.

### Publishes arrive on mosquitto_sub but no rows in `weather`

- Check obs-api logs: `journalctl -u obs-api.service | grep weather`. Look for
  `weather_payload_invalid` (schema drift), `weather_write_error` (SQLite
  issue), or `unknown_weather_nickname` (the board's nickname doesn't match
  `OBSERVATORY_WEATHER_NICKNAME=observatory-weather`).
- Confirm migration 0003 ran: `sqlite3 /var/lib/observatory/observatory.db \
    ".indexes weather"` should list `idx_weather_node_ts`.

### `/api/health` shows `weather.status: down`

- No rows for ≥ 3600 s. Drop back to mosquitto_sub to see if publishes are
  still arriving; if yes the subscriber is wedged — `systemctl restart
  obs-api.service` and inspect logs.

### 48 h soak FAIL — large gap mid-window

- Cross-reference the `check-weather-gaps.py` gap timestamp against
  `journalctl --since '<gap-ts>' --until '<gap-ts+1h>'` for wifi outage,
  broker restart, or power loss on the Pi.
- If the gap correlates with low `battery_v` readings, the NiMH cells are
  dying earlier than expected — swap and restart the soak.

---

## References

- Pimoroni Enviro firmware releases — <https://github.com/pimoroni/enviro/releases>
- Pimoroni MQTT destination docs — <https://github.com/pimoroni/enviro/blob/main/documentation/destinations/mqtt.md>
- [`deploy/mosquitto/README.md`](../mosquitto/README.md) — broker hardening + password file procedure
- [`scripts/check-weather-gaps.py`](../../scripts/check-weather-gaps.py) — 48 h soak gap analyser
- [`scripts/fake-enviro.py`](../../scripts/fake-enviro.py) — pre-hardware mock publisher (also usable to smoke-test the broker after creds change)
- [`scripts/capture-enviro-payloads.py`](../../scripts/capture-enviro-payloads.py) — payload capture for Phase 8 regression baselines
- [`observatory_brief.md`](../../observatory_brief.md) §Stevenson screen + §Power — purchasing notes for TFA 98.1114 + AA NiMH
- [`.planning/phases/03-weather-node/03-CONTEXT.md`](../../.planning/phases/03-weather-node/03-CONTEXT.md) — locked decisions (nickname, cadence, schema field renames, failure policy)
