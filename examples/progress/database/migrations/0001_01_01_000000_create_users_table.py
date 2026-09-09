"""Create the tables authentication needs: users, password resets, sessions."""

from __future__ import annotations

from typing import Any

from almasix.orm import Migration, Schema


class CreateUsersTable(Migration):
    """The auth trio Almasix's guards, brokers, and session driver read."""

    async def up(self) -> None:
        await Schema.create("users", self.users)
        await Schema.create("password_reset_tokens", self.password_reset_tokens)
        await Schema.create("sessions", self.sessions)

    async def down(self) -> None:
        await Schema.drop_if_exists("sessions")
        await Schema.drop_if_exists("password_reset_tokens")
        await Schema.drop_if_exists("users")

    def users(self, table: Any) -> None:
        table.id()
        table.string("name")
        table.string("email").unique()
        table.timestamp("email_verified_at").nullable()
        table.string("password")
        table.remember_token()
        table.timestamps()

    def password_reset_tokens(self, table: Any) -> None:
        table.string("email").primary()
        table.string("token")
        table.timestamp("created_at").nullable()

    def sessions(self, table: Any) -> None:
        # Read by the `database` session driver (SESSION_DRIVER=database).
        table.string("id").primary()
        table.integer("user_id").nullable().index()
        table.string("ip_address", 45).nullable()
        table.text("user_agent").nullable()
        table.text("payload")
        table.integer("last_activity").index()
