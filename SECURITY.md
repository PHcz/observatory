# Security Policy

Observatory is a personal hobby project that runs on a home LAN, served from a
Raspberry Pi at `http://observatory.local:8000`.

## Threat model

**No inbound access from the internet.** There is no port forwarding, tunnel
or cloud relay. The router is not trusted to guarantee that: the Pi's own
**nftables** firewall admits SSH (22), the API (8000) and MQTT (1883) only from
the local IPv4 subnet and IPv6 link-local addresses, and the Pi keeps IPv6 at
link-local so an ISP IPv6 rollout cannot expose it without a deliberate change.
The API listens on the dual-stack wildcard (`[::]:8000`); the firewall, not the
bind address, is the boundary.

**No user authentication.** Anyone on the home network can read the dashboard
and its API, including guests on the same wifi. Data that would locate the
house is coarsened before it is served (sunrise/sunset times to the minute,
lightning distances rounded, no raw strike coordinates).

**Browsers on the LAN are the main attack path.** A web page visited from a
laptop on the home wifi can try to reach the Pi:

- WebSocket and HTTP requests must carry an allowed **Origin** (LAN hosts only),
  checked before a WebSocket is accepted.
- Every request must carry an allowed **Host** header, which stops DNS-rebinding
  attacks.
- Responses carry a Content-Security-Policy (no remote code, no framing),
  `nosniff` and `no-referrer`. The dashboard loads nothing from the internet;
  its font is self-hosted.

**MQTT is plaintext on the wifi.** The sensor boards publish without TLS. Each
board has its own broker credentials, restricted by ACL to its own topic, so a
captured password lets an attacker on the wifi inject readings for that one
board, nothing more. The outdoor board stores the wifi password and is
physically reachable; putting the sensors on a separate IoT SSID is
recommended.

**Outbound only.** The Pi polls public data APIs (USGS, EMSC, BGS, NOAA SWPC,
AuroraWatch, Open-Meteo, NMDB, Blitzortung) over verified TLS and can send
threshold alerts to Telegram and, if enabled, **ntfy**. On the public
`ntfy.sh` server without an access token, anyone who knows the topic name can
read the alerts, so the topic name must be treated as a secret.

**Defence in depth on the Pi.** Every service runs as an unprivileged account
under a systemd sandbox (read-only system and code tree, no home access,
private `/tmp`, no device access except the muon detector's serial port and
the VideoCore mailbox). Secrets live only in root-owned env files on the Pi,
never in this repository; the pre-commit gate (gitleaks plus a local PII
pattern check) blocks them from commits. Security updates install
automatically, and a daily check audits the installed Python packages.

## Supported Versions

This is an actively-maintained personal project. Only the `main` branch is supported.

## Reporting a Vulnerability

Please report security issues privately rather than opening a public issue:

- Use GitHub's **"Report a vulnerability"** button under the repository's
  **Security** tab (Private Vulnerability Reporting). This keeps the report
  private until any fix is published.

This project is actively maintained; genuine security reports are appreciated
and I'll respond as promptly as I can.
