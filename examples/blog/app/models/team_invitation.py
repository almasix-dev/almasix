"""TeamInvitation — pending email invite to a team."""

from __future__ import annotations

from almasix.orm import Model


class TeamInvitation(Model):
    table = "team_invitations"
    fillable = ("team_id", "email", "role")

    def team(self):
        from app.models.team import Team

        return self.belongs_to(Team, "team_id")
