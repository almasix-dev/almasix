"""Create teams, team_user, and team_invitations."""

from __future__ import annotations

from almasix.orm import Blueprint, Migration, Schema


class CreateTeamsTables(Migration):
    async def up(self) -> None:
        await Schema.create("teams", self.teams)
        await Schema.create("team_user", self.team_user)
        await Schema.create("team_invitations", self.invitations)

    async def down(self) -> None:
        await Schema.drop_if_exists("team_invitations")
        await Schema.drop_if_exists("team_user")
        await Schema.drop_if_exists("teams")

    def teams(self, table: Blueprint) -> None:
        table.id()
        table.foreign_id("user_id").constrained("users").cascade_on_delete()
        table.string("name")
        table.boolean("personal_team").default(False)
        table.timestamps()

    def team_user(self, table: Blueprint) -> None:
        table.id()
        table.foreign_id("team_id").constrained("teams").cascade_on_delete()
        table.foreign_id("user_id").constrained("users").cascade_on_delete()
        table.string("role").nullable()
        table.unique(["team_id", "user_id"])
        table.timestamps()

    def invitations(self, table: Blueprint) -> None:
        table.id()
        table.foreign_id("team_id").constrained("teams").cascade_on_delete()
        table.string("email")
        table.string("role").nullable()
        table.timestamps()
        table.unique(["team_id", "email"])
