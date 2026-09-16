"""DatabaseSeeder — entry point for `smith db:seed` / `smith migrate --seed`."""

from __future__ import annotations

from almasix.orm import Seeder


class DatabaseSeeder(Seeder):
    """DatabaseSeeder."""

    async def run(self) -> None:
        """Seed the application's database."""
        # from app.models.user import User
        #
        # await User.factory().count(10).create()
        # await self.call([UserSeeder])
