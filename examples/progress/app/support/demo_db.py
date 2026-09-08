"""Shared migrate + seed for the M5 ORM living-example endpoints.

Schema: `database/migrations/`. Seed: `database/seeders/` via DatabaseSeeder
(same entry point as `python smith migrate --seed`).
"""

from __future__ import annotations

from pathlib import Path

from app.models.user import User
from almasix.orm.migration import Migrator
from almasix.orm.seeder import Seeder, load_database_seeder

_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS = _ROOT / "database" / "migrations"


async def ensure_demo_database() -> None:
    """Apply pending migrations; seed once when the demo tables are empty."""
    await Migrator(_MIGRATIONS).run()
    if await User.query().count() > 0:
        return
    seeder_cls = load_database_seeder(_ROOT)
    await Seeder().resolve(seeder_cls)()
