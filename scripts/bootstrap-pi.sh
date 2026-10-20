#!/usr/bin/env bash
# Observatory Pi bootstrap script.
# Idempotent — safe to re-run. Captures all OS-level prep so the Pi can be
# rebuilt from a fresh Pi OS Lite 64-bit (Bookworm) image after Pi Imager
# pre-config has been applied (see README).
#
# Usage:  sudo bash scripts/bootstrap-pi.sh
#
# Phase 1 scope:
#   - apt packages
#   - chrony NTP with makestep
#   - observatory system user + /var/lib/observatory + /etc/observatory + /mnt/backup
#   - SSH hardening
#   - tmpfs for /tmp and /var/log via fstab marker
#   - swap disabled
#   - uv installed system-wide, anchored to system Python 3.11
#   - venv created at /opt/observatory/.venv via `uv sync --frozen --no-dev`
#   - udev rule, mosquitto config installed
#   - yoyo migrations applied to /var/lib/observatory/observatory.db
#   - obs-backup.timer enabled
#
# Does NOT:
#   - install or enable observatory application services (muon, pollers, API) — those land in Phase 2+
#   - format the USB backup stick (ext4, label OBS_BACKUP) — operator step, see docs/OPERATIONS.md
#   - fill in the PicoMuon udev PID — happens in Phase 2 with device plugged in
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/opt/observatory}"

if [ "$EUID" -ne 0 ]; then
  echo "Must run as root: sudo bash scripts/bootstrap-pi.sh" >&2
  exit 1
fi

log() { echo "[bootstrap] $*"; }

# --- SECTION 1: apt update + package installs ---
log "Section 1: apt packages"
apt-get update -qq
apt-get install -y \
  chrony \
  mosquitto mosquitto-clients \
  sqlite3 \
  avahi-daemon \
  git \
  curl \
  jq \
  ca-certificates \
  build-essential \
  unattended-upgrades

# Daily security updates (security audit 2026-10-20, F48: never installed, and
# 48 security updates had accumulated). Debian's stock origins: security plus
# stable point releases. Automatic reboot stays off -- an unplanned 3 a.m.
# reboot of the observatory is worse than a patched-but-not-yet-running kernel.
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
CONF

# No purpose on a headless sensor Pi, and both run as root. ModemManager also
# probes /dev/ttyACM* -- where the muon detector and indoor node live.
systemctl disable --now bluetooth.service ModemManager.service 2>/dev/null || true

# --- SECTION 2: chrony config with makestep ---
log "Section 2: chrony"
if ! grep -q "# observatory-managed" /etc/chrony/chrony.conf 2>/dev/null; then
  cat > /etc/chrony/chrony.conf << 'CHRONYEOF'
# observatory-managed
pool pool.ntp.org iburst
pool uk.pool.ntp.org iburst
keyfile /etc/chrony/chrony.keys
driftfile /var/lib/chrony/chrony.drift
logdir /var/log/chrony
makestep 1.0 3
rtcsync
CHRONYEOF
  systemctl enable chrony
  systemctl restart chrony
  systemctl disable systemd-timesyncd 2>/dev/null || true
  systemctl stop systemd-timesyncd 2>/dev/null || true
fi

# --- SECTION 3: observatory system user (no shell, no device groups) ---
log "Section 3: observatory user"
if ! id -u observatory >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin observatory
fi
# Device access is granted per unit, not per account (security audit M8):
# obs-muon gets SupplementaryGroups=dialout, obs-api gets video (vcgencmd).
# Membership on the account let every service open the indoor node's USB
# serial port. Strip it on re-runs of older installs.
for grp in dialout video; do
  if id -nG observatory | tr ' ' '\n' | grep -qx "$grp"; then
    gpasswd -d observatory "$grp"
  fi
done

# --- SECTION 4: directories ---
log "Section 4: directories"
install -d -o observatory -g observatory -m 0750 /var/lib/observatory
install -d -o root -g observatory -m 0750 /etc/observatory
install -d -m 0755 /mnt/backup
# observatory user has --no-create-home, but uv needs a writable cache dir.
# Create the home dir explicitly (no login shell, just a place for $HOME).
install -d -o observatory -g observatory -m 0750 /home/observatory

# Seed /etc/observatory/observatory.env if absent (operator fills real values)
if [ ! -f /etc/observatory/observatory.env ]; then
  cp "$REPO_ROOT/.env.example" /etc/observatory/observatory.env
  chown root:observatory /etc/observatory/observatory.env
  chmod 0640 /etc/observatory/observatory.env
  log "Seeded /etc/observatory/observatory.env from .env.example — edit before first service start"
fi

# --- SECTION 5: SSH hardening ---
log "Section 5: SSH hardening"
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#\?PubkeyAuthentication .*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
systemctl reload ssh

# --- SECTION 6: fstab — tmpfs and (commented) USB backup ---
log "Section 6: fstab"
if ! grep -q "# observatory-tmpfs" /etc/fstab; then
  cat "$REPO_ROOT/deploy/fstab/observatory-tmpfs.fstab" >> /etc/fstab
  log "Appended tmpfs lines to /etc/fstab (reboot required for them to take effect)"
fi

# Append the USB backup template as a commented line if not present.
if ! grep -q "# observatory-backup" /etc/fstab; then
  {
    echo ""
    echo "# observatory-backup — uncomment once the stick is formatted ext4 with label OBS_BACKUP:"
    sed 's/^/# /' "$REPO_ROOT/deploy/fstab/observatory-backup.fstab.template"
  } >> /etc/fstab
fi

# Disable swap
log "Disabling swap"
dphys-swapfile swapoff 2>/dev/null || true
systemctl disable dphys-swapfile 2>/dev/null || true
swapoff -a || true

# --- SECTION 7: install uv (system-wide, anchored to system Python) ---
log "Section 7: uv"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | \
    env UV_INSTALL_DIR="/usr/local/bin" sh
fi

# --- SECTION 8: clone repo (only if /opt/observatory missing) ---
log "Section 8: repo"
if [ ! -d "$REPO_ROOT/.git" ]; then
  git clone https://github.com/PHcz/observatory "$REPO_ROOT"
fi
# Root-owned code tree: a compromised service must not be able to modify the
# code it runs or the unit files root installs from deploy/ (audit M8).
chown -R root:root "$REPO_ROOT"

# --- SECTION 9: uv sync (anchored to system Python 3.11) ---
log "Section 9: uv sync"
cd "$REPO_ROOT"
# Production install: exactly uv.lock (--frozen), runtime deps only (--no-dev),
# plus the analysis extra that the muon endpoints import. Re-run this same
# command after every uv.lock change -- the venv is NOT updated by rsyncing code
# (security audit 2026-10-20, M10). TMPDIR must be on real disk: /tmp is a 64 MB
# tmpfs and large wheels fail there with a misleading "network" error.
# Runs as root: the venv is part of the root-owned code tree.
install -d -m 0700 /var/tmp/uv-sync
env TMPDIR=/var/tmp/uv-sync UV_CACHE_DIR=/var/cache/uv-sync uv sync --frozen --no-dev --extra analysis --python /usr/bin/python3.11

# --- SECTION 10: install deploy artifacts ---
log "Section 10: deploy artifacts"
cp "$REPO_ROOT/deploy/udev/99-picomuon.rules" /etc/udev/rules.d/
udevadm control --reload-rules
udevadm trigger
# Re-evaluating udev rules creates /dev/picomuon if the PicoMuon is already
# plugged in. Safe no-op if the device isn't present yet.

# Mosquitto, as deploy/mosquitto/README.md describes and the live Pi runs
# (security audit 2026-10-20, F22/F50/C6). The repo config is a conf.d drop-in:
# the stock /etc/mosquitto/mosquitto.conf include_dir's conf.d, so it is never
# overwritten. ${LAN_IP} must be rendered -- an unrendered listener line stops
# mosquitto starting. The ACL is installed too (it used not to be, though the
# config names it). Passwords stay an operator step (README): bootstrap no
# longer invents an `admin` user that no ACL entry or service uses.
MQ_LAN_IP="$(ip -o -f inet addr show "$(ip route show default | awk '{print $5; exit}')" \
  | awk '{print $4; exit}' | cut -d/ -f1)"
install -d -m 0755 /etc/mosquitto/conf.d
sed "s#\${LAN_IP}#${MQ_LAN_IP}#" "$REPO_ROOT/deploy/mosquitto/mosquitto.conf" \
  > /etc/mosquitto/conf.d/observatory.conf
install -m 0640 -o root -g mosquitto "$REPO_ROOT/deploy/mosquitto/acl.conf" /etc/mosquitto/acl
if [ ! -f /etc/mosquitto/passwords ]; then
  install -m 0640 -o mosquitto -g mosquitto /dev/null /etc/mosquitto/passwords
  log "mosquitto: empty passwords file created -- create the users per deploy/mosquitto/README.md"
fi
systemctl enable mosquitto
systemctl restart mosquitto

# --- SECTION 10b: host firewall (security audit 2026-10-20, H2) ---
# Inbound is dropped except LAN-sourced SSH, dashboard/API, MQTT and mDNS, so a
# UPnP port mapping on the router can never expose the Pi. The LAN subnet is
# detected from the default-route interface rather than hard-coded.
log "Section 10b: nftables firewall"
apt-get install -y nftables
LAN_IFACE="$(ip route show default | awk '{print $5; exit}')"
LAN_V4_NET="$(python3 -c 'import ipaddress,sys; print(ipaddress.ip_interface(sys.argv[1]).network)' \
  "$(ip -o -f inet addr show "$LAN_IFACE" | awk '{print $4; exit}')")"
install -d -m 0755 /etc/nftables.d
sed "s#@LAN_V4_NET@#${LAN_V4_NET}#" "$REPO_ROOT/deploy/nftables/observatory.nft" \
  > /etc/nftables.d/observatory.nft
install -m 0755 "$REPO_ROOT/deploy/nftables/nftables.conf" /etc/nftables.conf
nft -c -f /etc/nftables.conf
systemctl enable nftables.service
# Rules apply at the next boot rather than now: loading a stateful ruleset under
# live connections drops their traffic (conntrack never saw them open).

# Keep IPv6 link-local only, so an ISP IPv6 rollout cannot silently give the Pi
# a public address. Takes effect at the next connect -- the link is not bounced.
WIFI_CON="$(nmcli -t -f NAME,DEVICE con show --active | awk -F: -v d="$LAN_IFACE" '$2==d{print $1}')"
[ -n "$WIFI_CON" ] && nmcli con mod "$WIFI_CON" ipv6.method link-local

# --- SECTION 11: (removed) pre-commit hooks ---
# Commits happen on the dev machine, where the hooks are installed. The Pi runs
# a runtime-only venv (see Section 9), so it has no pre-commit to install.

# --- SECTION 12: apply yoyo migrations + enable WAL mode ---
log "Section 12: migrations"
sudo -u observatory \
  "$REPO_ROOT/.venv/bin/python" -c "
import sys
sys.path.insert(0, '$REPO_ROOT')
from observatory.db.migrations import apply_migrations
n = apply_migrations('/var/lib/observatory/observatory.db')
print(f'Applied {n} migration(s)')
"

# yoyo uses its own sqlite3 connection that bypasses observatory.db.connection.get_conn(),
# so PRAGMA journal_mode=WAL is never applied during migration. journal_mode IS persisted
# in the database header (unlike busy_timeout and synchronous which are per-connection),
# so we set it once here. Without this, the DB stays in default 'delete' mode until the
# first service connects via get_conn() — and the Phase 1 acceptance check fails.
log "Section 12b: enable WAL mode on observatory.db"
sudo -u observatory sqlite3 /var/lib/observatory/observatory.db "PRAGMA journal_mode=WAL" >/dev/null

# --- SECTION 13: install + enable backup timer ---
log "Section 13: backup timer"
cp "$REPO_ROOT/deploy/systemd/obs-backup.service"        /etc/systemd/system/
cp "$REPO_ROOT/deploy/systemd/obs-backup.timer"          /etc/systemd/system/
cp "$REPO_ROOT/deploy/systemd/obs-backup-verify.service" /etc/systemd/system/
cp "$REPO_ROOT/deploy/systemd/obs-backup-verify.timer"   /etc/systemd/system/
systemctl daemon-reload
systemctl enable obs-backup.timer
systemctl enable obs-backup-verify.timer
# Do NOT start the timers here — they require /mnt/backup to actually be mounted
# (operator hasn't filled UUID yet). Operator runs:
#   sudo systemctl start obs-backup.timer obs-backup-verify.timer
# after configuring the USB stick mount.

# --- SECTION 14: install + enable obs-muon service (do NOT start) ---
log "Section 14: obs-muon service"
cp "$REPO_ROOT/deploy/systemd/obs-muon.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable obs-muon.service
# Do NOT start the service here — operator should:
#   1. Confirm PicoMuon is plugged in (`ls /dev/picomuon`)
#   2. Confirm chrony has converged (`chronyc tracking | grep "System time"`)
#   3. Start with: sudo systemctl start obs-muon.service
# The 02-07 acceptance script `scripts/verify-muon.sh` automates these checks.
# Pitfall 6 reminder: do NOT open /dev/picomuon with screen/cat/minicom while
# the service is running — the reader holds the port with exclusive=True and
# will refuse to share it.

# --- SECTION 14b: install + enable earthquake poller timers (do NOT start) ---
log "Section 14b: earthquake poller timers"
cp "$REPO_ROOT/deploy/systemd/obs-usgs-poll.service" /etc/systemd/system/
cp "$REPO_ROOT/deploy/systemd/obs-usgs-poll.timer"   /etc/systemd/system/
cp "$REPO_ROOT/deploy/systemd/obs-emsc-poll.service" /etc/systemd/system/
cp "$REPO_ROOT/deploy/systemd/obs-emsc-poll.timer"   /etc/systemd/system/
cp "$REPO_ROOT/deploy/systemd/obs-bgs-poll.service"  /etc/systemd/system/
cp "$REPO_ROOT/deploy/systemd/obs-bgs-poll.timer"    /etc/systemd/system/
systemctl daemon-reload
systemctl enable obs-usgs-poll.timer
systemctl enable obs-emsc-poll.timer
systemctl enable obs-bgs-poll.timer
# Do NOT start the timers here — operator should:
#   1. Confirm /etc/observatory/observatory.env has the POLLER_* defaults
#      (auto-loaded from .env.example pattern; usually no edit needed)
#   2. Confirm chrony has converged (`chronyc tracking | grep "System time"`)
#   3. Start with: sudo systemctl start obs-usgs-poll.timer obs-emsc-poll.timer obs-bgs-poll.timer
# The 04-06 acceptance script `scripts/verify-pollers.sh` automates the validation.

# --- SECTION 14d: install Phase 5 services (NOAA + Aurora timers, Blitzortung + API long-running) ---
log "Section 14d: Phase 5 services (NOAA + Aurora timers, Blitzortung + API)"
for unit in \
  obs-noaa-poll.service obs-noaa-poll.timer \
  obs-aurora-poll.service obs-aurora-poll.timer \
  obs-blitzortung.service \
  obs-api.service; do
  install -m 644 "$REPO_ROOT/deploy/systemd/$unit" /etc/systemd/system/
done
systemctl daemon-reload
# Enable timers — operator gates start on chrony convergence + env review
systemctl enable obs-noaa-poll.timer
systemctl enable obs-aurora-poll.timer
# Long-running services — enable only (operator confirms /etc/observatory/observatory.env first,
# then `systemctl start obs-blitzortung.service obs-api.service`).
systemctl enable obs-blitzortung.service
systemctl enable obs-api.service
# Sanity-check tip for the operator: `curl http://observatory.local:8000/api/health | jq`

# --- SECTION 14e: install Phase 10 forecast poller timer (do NOT start) ---
log "Section 14e: Phase 10 Open-Meteo forecast poller timer"
for unit in \
  obs-forecast-poll.service obs-forecast-poll.timer; do
  install -m 644 "$REPO_ROOT/deploy/systemd/$unit" /etc/systemd/system/
done
systemctl daemon-reload
# Enable but do NOT start — OPERATOR STEP: operator gates start on chrony
# convergence + env review, then `systemctl start obs-forecast-poll.timer`.
systemctl enable obs-forecast-poll.timer

# --- SECTION 14f: install Phase 11 air-quality poller timer (do NOT start) ---
log "Section 14f: Phase 11 Open-Meteo air-quality poller timer"
for unit in \
  obs-airquality-poll.service obs-airquality-poll.timer; do
  install -m 644 "$REPO_ROOT/deploy/systemd/$unit" /etc/systemd/system/
done
systemctl daemon-reload
# Enable but do NOT start — OPERATOR STEP: operator gates start on chrony
# convergence + env review, then `systemctl start obs-airquality-poll.timer`.
# REMINDER: obs-api does NOT auto-apply migrations — apply_migrations() (Section 12
# above) must have run so the 0006 air_quality + air_quality_meta tables AND the
# 0007 nmdb_counts + nmdb_meta tables (Phase 13 MU2-06) exist BEFORE the API or
# pollers touch them (Phase 10 deploy lesson). On upgrade, re-run apply_migrations()
# for 0007 BEFORE restarting obs-api or the /api/nmdb /api/forbush routes 500.
# NOTE: the live muon-analysis route (/api/muon/analysis) imports picomuon
# (polars/scipy) in-process — the obs-api venv must carry the `.[analysis]` extra,
# or the route lazy-imports and degrades to empty-state.
systemctl enable obs-airquality-poll.timer

# --- SECTION 14g: install Phase 13 NMDB neutron-monitor poller timer (do NOT start) ---
log "Section 14g: Phase 13 NMDB neutron-monitor poller timer (Oulu)"
for unit in \
  obs-nmdb-poll.service obs-nmdb-poll.timer; do
  install -m 644 "$REPO_ROOT/deploy/systemd/$unit" /etc/systemd/system/
done
systemctl daemon-reload
# Enable but do NOT start — OPERATOR STEP: operator gates start on chrony
# convergence + env review, then `systemctl start obs-nmdb-poll.timer`.
# REMINDER: obs-api does NOT auto-apply migrations — apply_migrations() (Section 12
# above) must have run so the 0007 nmdb_counts + nmdb_meta tables (Phase 13 MU2-06)
# exist BEFORE the API or this poller touch them. On upgrade, re-run
# apply_migrations() for 0007 BEFORE restarting obs-api or /api/nmdb 500s.
systemctl enable obs-nmdb-poll.timer

# --- SECTION 15: install journald drop-in for log rotation (OPS-03) ---
log "Section 15: journald drop-in for log rotation"
install -d -m 755 /etc/systemd/journald.conf.d
JOURNAL_DST=/etc/systemd/journald.conf.d/observatory.conf
JOURNAL_SRC="$REPO_ROOT/deploy/journald/observatory.conf"

# Idempotent: only restart journald if the file content actually changed.
if [[ ! -f "$JOURNAL_DST" ]] || ! cmp -s "$JOURNAL_SRC" "$JOURNAL_DST"; then
  install -m 644 "$JOURNAL_SRC" "$JOURNAL_DST"
  systemctl restart systemd-journald
  log "Section 15: journald restarted with new SystemMaxUse=500M, SystemKeepFree=200M, MaxFileSec=1week."
else
  log "Section 15: journald drop-in already current (no restart needed)."
fi

log "Bootstrap complete."
log "Next steps for the operator:"
log "  0. Add YOUR login user (the one you SSH in as, e.g. 'ph' or 'pi') to the 'observatory' group"
log "     so verify-*.sh scripts can read /var/lib/observatory/observatory.db:"
log "       sudo usermod -aG observatory \$USER"
log "     Then log out and back in for the group membership to apply."
log "  1. Edit /etc/observatory/observatory.env — set real HOME_LAT and HOME_LON."
log "  2. Configure USB stick: mkfs.ext4 -L OBS_BACKUP (see docs/OPERATIONS.md) -> uncomment the observatory-backup line in /etc/fstab."
log "  3. sudo mount -a, then start the obs-backup.timer (systemctl start)"
log "  4. Reboot to activate tmpfs mounts: sudo reboot"
log "  5. After reboot, run cold-boot acceptance checklist (see README)."
log "  6. Phase 2: confirm /dev/picomuon exists, then: sudo systemctl start obs-muon.service"
log "     (Pitfall 6: stop the service before opening /dev/picomuon with screen/cat/minicom.)"
log "  7. Phase 4: start the earthquake poller timers: sudo systemctl start obs-usgs-poll.timer obs-emsc-poll.timer obs-bgs-poll.timer"
log "  8. Phase 5: start NOAA + Aurora timers: sudo systemctl start obs-noaa-poll.timer obs-aurora-poll.timer"
log "  9. Phase 5: start long-running services: sudo systemctl start obs-blitzortung.service obs-api.service"
log " 10. Phase 10: start the forecast timer: sudo systemctl start obs-forecast-poll.timer"
log " 11. Phase 11: start the air-quality timer: sudo systemctl start obs-airquality-poll.timer"
log "     (apply_migrations runs 0006 air_quality/air_quality_meta during bootstrap; obs-api"
log "      does NOT auto-migrate — re-run apply_migrations() before restart on upgrade.)"
log " 12. Phase 13: start the NMDB timer: sudo systemctl start obs-nmdb-poll.timer"
log "     (apply_migrations runs 0007 nmdb_counts/nmdb_meta during bootstrap; obs-api"
log "      does NOT auto-migrate — re-run apply_migrations() before restart on upgrade.)"
log " 13. Health check: curl http://observatory.local:8000/api/health | jq"
