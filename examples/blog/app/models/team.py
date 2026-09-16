"""Team — Jetstream-shaped collaborative unit."""

from __future__ import annotations

from almasix.orm import HasFactory, Model


class Team(HasFactory, Model):
    """A team owned by a user with many members."""

    table = "teams"
    fillable = ("user_id", "name", "personal_team")
    casts = {"personal_team": "boolean"}

    def owner(self):
        from app.models.user import User

        return self.belongs_to(User, "user_id")

    def users(self):
        from app.models.user import User

        return self.belongs_to_many(User, "team_user", "team_id", "user_id")

    def invitations(self):
        from app.models.team_invitation import TeamInvitation

        return self.has_many(TeamInvitation, "team_id")

    def memberships(self):
        from app.models.membership import Membership

        return self.has_many(Membership, "team_id")
