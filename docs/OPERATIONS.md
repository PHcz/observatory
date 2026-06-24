# Operations

Day-to-day running and maintenance of an Observatory deployment on a Raspberry Pi.

This document holds the operator runbook: how to bootstrap a fresh Pi into the
"observatory" platform, and how to run the muon-detector service once it's up.
For first-time build and deploy from a clean clone, see
[SETUP.md](SETUP.md); for the weather-node side, see
[../deploy/enviro/PROVISIONING.md](../deploy/enviro/PROVISIONING.md).

## Pi setup

This section is the operational reference for bootstrapping a fresh Raspberry Pi 4 into the
"observatory" platform: fresh OS image, then `scripts/bootstrap-pi.sh`, then a few manual steps.

### 1. First-Boot Setup (Pi Imager pre-config)

Use Raspberry Pi Imager 1.8.x or newer. Select **Raspberry Pi OS Lite (64-bit)** (Bookworm).
Click the gear/cog "OS Customization" button before writing.

**General tab:**

| Field | Value |
|-------|-------|
| Set hostname | `observatory` |
| Username | `ph` (or your preferred login username) |
| Password | (a strong password — used for emergency console access only) |
| Configure wireless LAN | Tick if you need wifi for the first boot |
| SSID | your home wifi SSID |
| Password | your home wifi password |
| Wireless LAN country | GB |
| Set locale settings | Europe/London, gb keyboard |

**Services tab:**

| Field | Value |
|-------|-------|
| Enable SSH | Tick |
| Allow public-key authentication only | Tick this option |
| Set authorized_keys | Paste contents of `~/.ssh/id_rsa.pub` (or `id_ed25519.pub`) from your dev machine |

**Do NOT commit the Imager preset file** — it would leak wifi password + your SSH public key.
This section is the canonical record of which boxes to tick.

Write the image, eject, plug into the Pi, power on.

### 2. Static IP — Router DHCP Reservation

Log into your home router and reserve a static IP for the Pi's MAC address. This is simpler
and more robust than configuring `nmcli` on the Pi (Bookworm uses NetworkManager — no
`dhcpcd.conf`). The Pi just sees normal DHCP and always gets the same address.

After reservation, confirm `ping observatory.local` works from your dev machine (Avahi is
pre-installed on Pi OS Lite).

### 3. Bootstrap the Pi

SSH in (key-only):

```bash
ssh ph@observatory.local
```

Clone the repo and run the bootstrap script:

```bash
sudo git clone https://github.com/PHcz/observatory /opt/observatory
cd /opt/observatory
sudo bash scripts/bootstrap-pi.sh
```

The script is idempotent — you can re-run it safely.

### 4. Post-Bootstrap Manual Steps

1. **Set real coordinates:**

   ```bash
   sudo nano /etc/observatory/observatory.env
   ```

   Set `HOME_LAT` and `HOME_LON` to your actual location.

2. **Configure USB backup mount:**

   Plug in a USB stick. Format it **ext4** (no 4 GB file-size limit — the daily backup
   writes a temporary uncompressed DB copy to the stick before gzipping, which would
   eventually exceed FAT32's 4 GB cap) and label it `OBS_BACKUP`. **This erases the stick —
   make sure `/dev/sdX` is the USB device, not the SD card (`mmcblk0`):**

   ```bash
   lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT     # identify the USB device (e.g. /dev/sda1)
   sudo mkfs.ext4 -F -L OBS_BACKUP /dev/sda1      # if the stick has no partition, create one first
   ```

   Mount it by **label** (so future stick swaps need no fstab edit). The fstab line is:

   ```
   LABEL=OBS_BACKUP /mnt/backup ext4 defaults,nofail 0 2
   ```

   Then mount and grant the service user write access (ext4 stores real ownership, so the
   mount root is `root` until chowned):

   ```bash
   sudo systemctl daemon-reload
   sudo mount /mnt/backup
   sudo chown observatory:observatory /mnt/backup     # so obs-backup (User=observatory) can write
   findmnt /mnt/backup                                # confirm ext4 mounted
   sudo systemctl start obs-backup.timer obs-backup-verify.timer
   systemctl list-timers obs-backup.timer obs-backup-verify.timer
   ```

   **Swapping the stick later:** stop the timers, `cp -a /mnt/backup/observatory-* ~/staging/`
   to preserve history, `sudo umount /mnt/backup`, swap, `mkfs.ext4 -F -L OBS_BACKUP` the new
   one (it mounts automatically by label), `chown` it, copy the staged files back, restart the
   timers. The live DB on the SD card is the source of truth, so the stick can be reformatted
   freely.

   **Backup format & retention:** the daily backup (`obs-backup.timer`, 03:00) writes a
   gzip-compressed `observatory-YYYY-MM-DD.db.gz` (+ a `.ok` sentinel) to `/mnt/backup`,
   with **10-day** retention. A separate **weekly** integrity check (`obs-backup-verify.timer`,
   Sun 04:00) gunzips the newest copy and runs `PRAGMA integrity_check` — pure `sqlite3`,
   local-first (no `uv`/venv churn). **Restore:**
   `gunzip -c /mnt/backup/observatory-YYYY-MM-DD.db.gz > /var/lib/observatory/restore.db`
   (never `/tmp` — it is a small tmpfs that can't hold a full DB).

3. **Reboot to activate tmpfs:**

   ```bash
   sudo reboot
   ```

### 5. Cold-Boot Acceptance Checklist

After bootstrap and the configuration steps above, run this checklist to confirm Phase 1
acceptance. This is the literal pull-the-plug test:

1. **Pull the Pi's PSU.** Wait 30 seconds. Plug it back in.
2. Wait 2 minutes.
3. SSH to `ph@observatory.local`.
4. Run:

   ```bash
   chronyc tracking | grep "System time"        # expect offset < 0.5s
   findmnt /mnt/backup                          # expect a row (mounted)
   findmnt /tmp                                 # expect tmpfs
   findmnt /var/log                             # expect tmpfs
   swapon --show                                # expect EMPTY output
   systemctl is-active mosquitto                # expect "active"
   systemctl is-enabled obs-backup.timer obs-backup-verify.timer  # expect "enabled" x2
   ```

5. From a phone on the home wifi, load `http://observatory.local` in Safari. It should
   resolve (you'll get "connection refused" because no service is bound to :80 yet — that's
   fine; what matters is Avahi resolved the name).

### 6. Gitleaks Verification (one-shot)

After `pre-commit install` has been run (the bootstrap script does this), verify gitleaks
actually blocks a real secret commit by running:

```bash
cd /opt/observatory
bash scripts/verify-gitleaks.sh
```

Expected output: `OK: gitleaks blocked the staged secret`.

### 7. PicoMuon udev Rule

The committed udev rule (`deploy/udev/99-picomuon.rules`) uses a placeholder PID. With the
PicoMuon plugged in, identify the real PID:

```bash
sudo udevadm info --name=/dev/ttyACM0 --attribute-walk | grep -E 'idVendor|idProduct'
```

Edit `/opt/observatory/deploy/udev/99-picomuon.rules`, replace the `XXXX` in
`ATTRS{idProduct}=="XXXX"` with the 4-hex-digit value, then:

```bash
sudo cp /opt/observatory/deploy/udev/99-picomuon.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
ls -la /dev/picomuon    # expect a symlink to /dev/ttyACM*
```

This step belongs to the muon-detector setup but is documented here for completeness.

## Muon service operator notes

The `obs-muon.service` systemd unit is installed and enabled by `bootstrap-pi.sh`
but not started automatically. To bring it up:

```bash
sudo systemctl start obs-muon.service
systemctl status obs-muon.service
journalctl -u obs-muon -f
```

The unit runs as `observatory:dialout` and opens `/dev/picomuon` (the udev symlink
from `deploy/udev/99-picomuon.rules`). It blocks at startup until `chronyc tracking`
reports a sub-0.5s offset (typically <5s on a Pi that has been up for a minute).

**Pitfall 6 — exclusive port access.** The service opens the serial port with
`exclusive=True`. Before manually inspecting the device with `screen`, `cat`, or
`minicom`, stop the service:

```bash
sudo systemctl stop obs-muon.service
sudo screen /dev/picomuon 115200       # or whatever debug tool
# ...later...
sudo systemctl start obs-muon.service
```

**Watchdog.** The service uses `Type=notify` with `WatchdogSec=30s`. A process that
stops moving data through the pipeline (read OR DB flush) is killed and restarted
within 30s. Check with:

```bash
systemctl show obs-muon.service -p NRestarts,ActiveState
journalctl -u obs-muon --since "1 hour ago" | grep -E 'WATCHDOG|stopping|reopen'
```

**Verifying ingest.** Latest events:

```bash
sqlite3 /var/lib/observatory/observatory.db \
    "SELECT datetime(ts,'unixepoch'), detector_pressure_hpa, detector_temp_c, amplitude, coincidence \
     FROM muon_events ORDER BY id DESC LIMIT 5;"
```

A quick row-count + max-timestamp probe to confirm the pipeline is advancing:

```bash
sqlite3 /var/lib/observatory/observatory.db \
    "SELECT COUNT(*), MAX(ts) FROM muon_events;"
```

For the full acceptance procedure (unplug/replug, simulated silence, BMP280 column check),
run `bash scripts/verify-muon.sh`.

## Threshold alerts & phone notifications (ntfy)

The alert engine runs inside `obs-api` (evaluated on the DB-watcher tick, ~60 s). Three rules
ship: **frost risk** (temp < `ALERT_FROST_TEMP_C`, default 2 °C, with dewpoint spread <
`ALERT_FROST_DEWPOINT_SPREAD_C`, default 2 °C), **rapid pressure fall** (3 h drop >
`ALERT_PRESSURE_FALL_HPA_PER_3H`, default 1.6 hPa), and **Enviro offline** (newest weather
reading older than `ALERT_ENVIRO_STALE_SEC`, default 3600 s = 1 h). The first two must hold for
`ALERT_MIN_ACTIVE_MINUTES` (default 5) before firing — anti-flap hysteresis; the offline rule is
time-based and fires as soon as the gap exceeds the threshold.

**Where alerts appear:**
- **Dashboard** — the *Weather Alerts* panel (ACTIVE + RECENT-24 h) plus a coloured dot on the
  pressure stat; updates live over the WebSocket `alert` channel.
- **API** — `GET /api/alerts` → `{active, recent}`.
- **Phone push** — via [ntfy](https://ntfy.sh) and/or [Telegram](https://telegram.org), if
  enabled (below). Pushes on the *crossing* **and** on resolution (e.g. "Enviro Online" after a
  battery swap). Each channel is independent and fire-and-forget.

**Enabling phone push (ntfy).** Off by default. Set on the Pi `.env`
(`/etc/observatory/observatory.env`) — note these keys take **no** `OBSERVATORY_` prefix (the
Settings model uses no env prefix; the var name is just the field name):

```bash
sudo sed -i '/^ALERT_NTFY_ENABLED=/d;/^ALERT_NTFY_TOPIC=/d' /etc/observatory/observatory.env
printf 'ALERT_NTFY_ENABLED=true\nALERT_NTFY_TOPIC=observatory-<random>\n' \
  | sudo tee -a /etc/observatory/observatory.env >/dev/null   # pick a private, hard-to-guess topic
sudo systemctl restart obs-api.service
```

Then subscribe a device to that topic — the ntfy app (iOS/Android) or just open
`https://ntfy.sh/observatory-<random>` in a browser. Optional: `ALERT_NTFY_URL` (default
`https://ntfy.sh`; point at a self-hosted server) and `ALERT_NTFY_TOKEN` (Bearer token for a
reserved/authenticated topic).

**Privacy:** a public `ntfy.sh` topic is protected only by the obscure name — anyone who learns
it can read (or post to) it. Fine for frost/storm; for stronger privacy reserve the topic with a
token or self-host ntfy. Keep the real topic/token in the Pi `.env` only — never commit them.

The notifier is fire-and-forget: if ntfy is unreachable it logs a warning and never disrupts the
dashboard or the `alerts` table.

**Enabling phone push (Telegram).** A second, independent channel — useful as a private,
authenticated alternative to a public ntfy topic. Off by default.

1. In Telegram, message **@BotFather** → `/newbot`, follow the prompts, copy the bot token.
2. Send your new bot any message (e.g. `hi`) so it has a chat to reply to.
3. Read your numeric chat id: open `https://api.telegram.org/bot<token>/getUpdates` and find
   `message.chat.id`.
4. Set on the Pi `.env` (no `OBSERVATORY_` prefix — the var name is the field name):

```bash
printf 'ALERT_TELEGRAM_ENABLED=true\nALERT_TELEGRAM_BOT_TOKEN=<token>\nALERT_TELEGRAM_CHAT_ID=<chat_id>\n' \
  | sudo tee -a /etc/observatory/observatory.env >/dev/null
sudo systemctl restart obs-api.service
```

Both channels can run at once; either can be enabled alone. Keep the token/chat id in the Pi
`.env` only — never commit them.

## Daily Dependabot vulnerability check (Telegram)

`obs-vuln-check.timer` runs `python -m observatory.ops.vuln_check` once a day (09:30 local),
queries the GitHub Dependabot **alerts** API for the repo, and — if any alert is *open* — sends a
Telegram message listing them worst-first. A clean run is silent. Outbound-only (no inbound
exposure), same sanctioned-egress justification as the pollers.

Set on the Pi `.env` (reuses the `ALERT_TELEGRAM_*` channel above for delivery):

```bash
printf 'VULN_CHECK_GITHUB_TOKEN=<fine_grained_pat>\nVULN_CHECK_REPO=PHcz/observatory\n' \
  | sudo tee -a /etc/observatory/observatory.env >/dev/null
sudo systemctl enable --now obs-vuln-check.timer
systemctl list-timers obs-vuln-check.timer
sudo systemctl start obs-vuln-check.service   # run once now to test
journalctl -u obs-vuln-check.service -n 20 --no-pager
```

The PAT must be a **fine-grained** token scoped to `PHcz/observatory` with **Dependabot alerts:
Read-only**. With no token set the check is a silent no-op (exit 0), so the timer is safe to
enable before the token is in place. Keep the PAT in the Pi `.env` only — never commit it.
