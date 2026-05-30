# Security Policy

Observatory is a personal hobby project designed to run on a home LAN, served
from a Raspberry Pi at `http://observatory.local`. By design it has **no remote
attack surface**: it is not exposed to the internet (no port forwarding, no
tunnels), FastAPI and Mosquitto are bound to the LAN interface only, and there
is no authentication layer because access is gated at the network level.

## Supported Versions

This is a showcase project shared as-is. Only the `main` branch is maintained.

## Reporting a Vulnerability

Please report security issues privately rather than opening a public issue:

- Use GitHub's **"Report a vulnerability"** button under the repository's
  **Security** tab (Private Vulnerability Reporting). This keeps the report
  private until any fix is published.

This is a personal project shared as-is; responses may not be timely, but
genuine security reports are appreciated.
