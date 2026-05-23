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
#   - venv created at /opt/observatory/.venv via `uv sync`
#   - udev rule, mosquitto config installed
#   - pre-commit hooks installed
#   - yoyo migrations applied to /var/lib/observatory/observatory.db
#   - obs-backup.timer enabled
#
# Does NOT:
#   - install or enable observatory application services (muon, pollers, API) — those land in Phase 2+
#   - fill in the USB backup UUID — operator does this after `blkid` (see README)
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
  ca-certificates \
  build-essential

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

# --- SECTION 3: observatory system user (no shell, member of dialout for serial) ---
log "Section 3: observatory user"
if ! id -u observatory >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin \
          --groups dialout observatory
fi

# --- SECTION 4: directories ---
log "Section 4: directories"
install -d -o observatory -g observatory -m 0750 /var/lib/observatory
install -d -o root -g observatory -m 0750 /etc/observatory
install -d -m 0755 /mnt/backup

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
    echo "# observatory-backup — uncomment after running blkid /dev/sda1 and replacing UUID:"
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
chown -R observatory:observatory "$REPO_ROOT"

# --- SECTION 9: uv sync (anchored to system Python 3.11) ---
log "Section 9: uv sync"
cd "$REPO_ROOT"
sudo -u observatory uv sync --python /usr/bin/python3.11

# --- SECTION 10: install deploy artifacts ---
log "Section 10: deploy artifacts"
cp "$REPO_ROOT/deploy/udev/99-picomuon.rules" /etc/udev/rules.d/
udevadm control --reload-rules

# Mosquitto config (Phase 1 baseline). Seed an admin password if absent.
cp "$REPO_ROOT/deploy/mosquitto/mosquitto.conf" /etc/mosquitto/mosquitto.conf
if [ ! -f /etc/mosquitto/passwords ]; then
  # Generate a random admin password and persist it to observatory.env
  PW="$(openssl rand -hex 16)"
  touch /etc/mosquitto/passwords
  mosquitto_passwd -b /etc/mosquitto/passwords admin "$PW"
  chown mosquitto:mosquitto /etc/mosquitto/passwords
  chmod 0640 /etc/mosquitto/passwords
  if ! grep -q "^MQTT_ADMIN_PASSWORD=" /etc/observatory/observatory.env; then
    echo "" >> /etc/observatory/observatory.env
    echo "# Generated by bootstrap-pi.sh — Phase 1 mosquitto admin user" >> /etc/observatory/observatory.env
    echo "MQTT_ADMIN_PASSWORD=$PW" >> /etc/observatory/observatory.env
  fi
fi
systemctl enable mosquitto
systemctl restart mosquitto

# --- SECTION 11: pre-commit hooks ---
log "Section 11: pre-commit hooks"
sudo -u observatory \
  "$REPO_ROOT/.venv/bin/pre-commit" install --install-hooks --config "$REPO_ROOT/.pre-commit-config.yaml"
sudo -u observatory \
  "$REPO_ROOT/.venv/bin/pre-commit" install --hook-type pre-push --config "$REPO_ROOT/.pre-commit-config.yaml"

# --- SECTION 12: apply yoyo migrations ---
log "Section 12: migrations"
sudo -u observatory \
  "$REPO_ROOT/.venv/bin/python" -c "
import sys
sys.path.insert(0, '$REPO_ROOT')
from observatory.db.migrations import apply_migrations
n = apply_migrations('/var/lib/observatory/observatory.db')
print(f'Applied {n} migration(s)')
"

# --- SECTION 13: install + enable backup timer ---
log "Section 13: backup timer"
cp "$REPO_ROOT/deploy/systemd/obs-backup.service" /etc/systemd/system/
cp "$REPO_ROOT/deploy/systemd/obs-backup.timer"   /etc/systemd/system/
systemctl daemon-reload
systemctl enable obs-backup.timer
# Do NOT start the timer here — it would fire backup.py which requires /mnt/backup
# to actually be mounted (operator hasn't filled UUID yet). Operator runs:
#   sudo systemctl start obs-backup.timer
# after configuring the USB stick mount.

log "Bootstrap complete."
log "Next steps for the operator:"
log "  1. Edit /etc/observatory/observatory.env — set real HOME_LAT and HOME_LON."
log "  2. Configure USB stick: blkid /dev/sda1 -> uncomment + fill UUID in /etc/fstab observatory-backup line."
log "  3. sudo mount -a, then start the obs-backup.timer (systemctl start)"
log "  4. Reboot to activate tmpfs mounts: sudo reboot"
log "  5. After reboot, run cold-boot acceptance checklist (see README)."
