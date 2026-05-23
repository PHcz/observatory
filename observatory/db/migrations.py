"""yoyo-migrations wrapper. Apply pending .sql migrations to the database."""

from __future__ import annotations

from pathlib import Path

import yoyo


def _migrations_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "migrations"


def apply_migrations(db_path: str, migrations_dir: str | None = None) -> int:
    """Apply any pending yoyo migrations. Returns the count of applied migrations."""
    mdir = Path(migrations_dir) if migrations_dir else _migrations_dir()
    backend = yoyo.get_backend(f"sqlite:///{db_path}")
    migrations = yoyo.read_migrations(str(mdir))
    with backend.lock():
        to_apply = backend.to_apply(migrations)
        count = len(list(to_apply))
        backend.apply_migrations(backend.to_apply(migrations))
    return count
