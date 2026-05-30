# Setup

How to build Observatory from a clean `git clone` — dev-machine setup first, then
the Pi build and deploy. For the hardware you'll need, see [HARDWARE.md](HARDWARE.md).

## Fresh-clone dev setup

Requirements: Python 3.11, [uv](https://docs.astral.sh/uv/), Node 20+ and npm.

```bash
git clone https://github.com/PHcz/observatory
cd observatory

# --- Python backend ---
uv sync                 # resolves from uv.lock; installs runtime + dev deps
uv run pytest           # fast suite — network/integration/slow markers are
                        # excluded by default, so no live network and no Docker

# --- Frontend (SvelteKit, adapter-static) ---
cd frontend
npm ci                  # reproducible install from package-lock.json
npm run build           # builds the static bundle into frontend/build/
npm run test:unit -- --run   # vitest
```

Success means: `uv sync` exits 0, `uv run pytest` is all-green, and `npm run build`
exits 0 with `frontend/build/` populated.

**Notes:**

- `npm ci` runs `svelte-kit sync` automatically via the `prepare` script, so
  `npm run build` works on a brand-new checkout (the generated `.svelte-kit/` types
  exist by build time).
- The default `uv run pytest` runs the **fast** suite only. The **integration** suite
  (`uv run pytest -m integration`) is optional and requires Docker — it spins up a
  Mosquitto container — so it's not needed for the basic build proof.
- Lint and type-check before submitting changes:

  ```bash
  uv run ruff check . && uv run ruff format --check .
  uv run mypy
  cd frontend && npm run check
  ```

## Pi build & deploy

The full Raspberry Pi bootstrap runbook — fresh OS image, `scripts/bootstrap-pi.sh`,
static IP, USB backup, cold-boot acceptance, and the muon-service operator notes —
lives in [OPERATIONS.md](OPERATIONS.md). Follow that to stand up the Pi.

Deploy flow once the Pi is bootstrapped:

1. Build the frontend locally: `cd frontend && npm ci && npm run build`.
2. `rsync` the built `frontend/build/` bundle to the Pi (FastAPI serves it as static
   files from `/`, alongside the JSON + WebSocket API on the same host).
3. Restart the API service on the Pi to pick up the new bundle.

For the outdoor weather node — flashing the Enviro Weather firmware and provisioning
its wifi + MQTT settings — follow [../deploy/enviro/PROVISIONING.md](../deploy/enviro/PROVISIONING.md).
