# Indoor air node (ESPHome)

Firmware config for the indoor CO₂ node: **Adafruit ESP32-S2 Feather** (onboard
BME280) + **Adafruit SCD-41**, mains-USB powered. Publishes CO₂ / temperature /
humidity / pressure to the Pi's MQTT broker under `indoor/<room>/sensor/<metric>/state`.
The Pi side (`observatory.indoor.subscriber`, in obs-api's lifespan) coalesces
those into one `indoor_air` row per cycle.

## Files
- `indoor-air.yaml` — the ESPHome config (safe to commit; uses `!secret`).
- `secrets.yaml.example` — template. Copy to `secrets.yaml` (gitignored) and fill in.

## Flash (first time — over USB)
```bash
uv tool install esphome            # once
cd firmware/indoor-air
cp secrets.yaml.example secrets.yaml   # then edit it
esphome compile indoor-air.yaml
# put the S2 in download mode: hold BOOT, tap RESET, release BOOT
esphome upload indoor-air.yaml --device /dev/cu.usbmodemXXXX
```
The ESP32-S2's first flash needs manual download mode (BOOT+RESET). After that,
updates go over wifi: `esphome run indoor-air.yaml` (OTA, no USB).

## Broker side (on the Pi, one-time)
Create the `indoor-node` user + ACL, then reload:
```bash
sudo mosquitto_passwd -b /etc/mosquitto/passwords indoor-node '<mqtt_password>'
# append to /etc/mosquitto/acl:
#   user indoor-node
#   topic readwrite indoor/#
#   user obs-api-subscriber
#   topic read indoor/#
sudo systemctl reload mosquitto
```

## Notes
- 2.4 GHz wifi only (ESP32 limitation).
- Onboard BME280 temperature reads a few °C warm (board self-heat) — add a
  `filters: - offset: -N` under the temperature sensor once you know the real
  room temp, or switch to the SCD-41's own temperature.
