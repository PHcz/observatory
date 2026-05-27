# Mosquitto deploy bundle

Files installed to `/etc/mosquitto/` by `bootstrap-pi.sh`:

| Source                        | Destination                              |
|-------------------------------|------------------------------------------|
| `mosquitto.conf`              | `/etc/mosquitto/conf.d/observatory.conf` |
| `acl.conf`                    | `/etc/mosquitto/acl`                     |
| `passwords` (operator-built)  | `/etc/mosquitto/passwords`               |

The committed `mosquitto.conf` uses a `${LAN_IP}` placeholder on the
`listener 1883 ${LAN_IP}` directive. `bootstrap-pi.sh` resolves the Pi's
real LAN IP via Phase 6's `resolve_lan_ip()` helper and renders the file
during install. The same placeholder convention is used for Phase 5/6
templates — see `scripts/bootstrap-pi.sh` Section 14d.

## Generating the passwords file (one-time, on the Pi)

The real `passwords` file is gitignored (`deploy/mosquitto/passwords` and
`/etc/mosquitto/passwords`). After bootstrap, generate it on the Pi:

```bash
set -euo pipefail
umask 077
sudo touch /etc/mosquitto/passwords
sudo chown mosquitto:mosquitto /etc/mosquitto/passwords
sudo chmod 640 /etc/mosquitto/passwords

# Replace placeholders with real secrets — sourced from
# /etc/observatory/secrets.env or read prompt-by-prompt.
sudo mosquitto_passwd -c -b /etc/mosquitto/passwords \
     enviro-observatory-weather "${OBS_MQTT_PUB_PASSWORD}"
sudo mosquitto_passwd -b /etc/mosquitto/passwords \
     obs-api-subscriber "${OBS_MQTT_SUB_PASSWORD}"
sudo systemctl reload mosquitto
```

The example file `passwords.example` shows the on-disk format but the
hashes are placeholders — DO NOT copy it into place.

## LAN-bind verification (SEC-03)

After installing and starting mosquitto:

```bash
ss -tlnp | grep 1883
# expected: 192.168.x.y:1883 (NOT 0.0.0.0:1883)
```

From an off-network device (cellular / different subnet):

```bash
nmap <pi-ip> -p 1883
# expected: filtered or refused
```

## ACL test

```bash
mosquitto_pub -h <pi-ip> -u obs-api-subscriber -P "${PW}" \
     -t enviro/observatory-weather -m hi
# expected: connect OK, publish DENIED (subscriber is read-only)
```

Symmetric publisher check:

```bash
mosquitto_pub -h <pi-ip> -u enviro-observatory-weather -P "${PW}" \
     -t enviro/observatory-weather -m '{"test":true}'
# expected: success

mosquitto_sub -h <pi-ip> -u enviro-observatory-weather -P "${PW}" \
     -t enviro/observatory-weather
# expected: subscription DENIED (publisher is write-only)
```
