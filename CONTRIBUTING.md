# Contributing

Thanks for your interest! **Heads up:** Observatory is a personal project shared
as-is for others to learn from and fork. It is **not actively maintained** —
issues and pull requests are welcome but may not get a timely response (or any).
If you want to build your own, fork it and go.

## Development setup

Requirements: Python 3.11, [uv](https://docs.astral.sh/uv/), Node 20+ and npm.

```bash
git clone https://github.com/PHcz/observatory
cd observatory

# Python backend
uv sync                         # installs runtime + dev deps from uv.lock
uv run pytest                   # fast test suite (network/integration/slow excluded)

# Frontend
cd frontend
npm ci                          # reproducible install from package-lock.json
npm run build                   # builds the static bundle (adapter-static)
npm run test:unit -- --run      # vitest
```

Lint / type-check before submitting:

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
cd frontend && npm run check
```

See [docs/SETUP.md](docs/SETUP.md) for the full Pi build + deploy walkthrough.
