"""Membership — pivot row on team_user (role per member)."""

from __future__ import annotations

from almasix.orm import Model


class Membership(Model):
    table = "team_user"
    fillable = ("team_id", "user_id", "role")
    timestamps = True

    def team(self):
        from app.models.team import Team

        return self.belongs_to(Team, "team_id")

    def user(self):
        from app.models.user import User

        return self.belongs_to(User, "user_id")
