# observatory

---

## Pi Setup (Phase 1)

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

   Plug in a USB stick (formatted FAT32, label `OBS_BACKUP`):

   ```bash
   sudo blkid /dev/sda1
   ```

   Take the UUID. Then:

   ```bash
   sudo nano /etc/fstab
   ```

   Find the `# observatory-backup` comment block, uncomment the `UUID=...` line, and replace
   `XXXX-XXXX` with the real UUID. Then:

   ```bash
   sudo mount -a
   findmnt /mnt/backup    # confirm it's mounted
   sudo systemctl start obs-backup.timer
   systemctl list-timers obs-backup.timer
   ```

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
   systemctl is-enabled obs-backup.timer        # expect "enabled"
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

This step belongs to Phase 2 (Muon Detector) but is documented here for completeness.

---
