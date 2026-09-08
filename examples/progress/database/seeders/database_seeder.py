"""DatabaseSeeder — entry point for `python smith db:seed` / `migrate --seed`."""

from __future__ import annotations

from almasix.orm import Seeder
from database.seeders.demo_seeder import DemoSeeder


class DatabaseSeeder(Seeder):
    """DatabaseSeeder."""

    async def run(self) -> None:
        await self.call([DemoSeeder])
