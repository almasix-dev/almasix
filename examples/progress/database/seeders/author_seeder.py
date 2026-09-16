"""AuthorSeeder."""

from __future__ import annotations

from app.models.author import Author

from almasix.orm import Seeder


class AuthorSeeder(Seeder):
    """AuthorSeeder."""

    async def run(self) -> None:
        """Seed the application's database."""
        await Author.factory().create({"name": "John Doe", "email": "john.doe@example.com", "phone": "1234567890", "address": "123 Main St", "city": "Anytown", "state": "CA", "zip": "12345", "country": "USA", "website": "https://www.example.com", "twitter": "https://twitter.com/john_doe", "facebook": "https://www.facebook.com/john.doe"})
