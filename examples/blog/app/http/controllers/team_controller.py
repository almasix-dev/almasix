"""Teams — create, switch, invite, leave, delete."""

from __future__ import annotations

from app.models.team import Team
from app.models.team_invitation import TeamInvitation
from app.models.user import User

from almasix.auth import auth
from almasix.http import Controller, Request, redirect
from almasix.http.exceptions import NotFoundHttpException
from inertia import Inertia


class TeamController(Controller):
    async def index(self, request: Request):
        user = auth().user()
        teams = []
        if user is not None:
            owned = await user.owned_teams().get()  # type: ignore[attr-defined]
            member = await user.teams().get()  # type: ignore[attr-defined]
            seen = set()
            for t in list(owned) + list(member):
                key = t.get_key()
                if key in seen:
                    continue
                seen.add(key)
                teams.append(
                    {
                        "id": key,
                        "name": t.get_attribute("name"),
                        "personal_team": bool(t.get_attribute("personal_team")),
                        "owner_id": t.get_attribute("user_id"),
                    }
                )
        return Inertia.render(
            "Teams/Index",
            {
                "teams": teams,
                "currentTeamId": user.get_attribute("current_team_id") if user else None,
                "status": request.session.get("status"),
            },
        )

    async def store(self, request: Request):
        user = auth().user()
        if user is None:
            return redirect("/login")
        name = str(request.input("name") or "").strip()
        if not name:
            request.session.flash("errors", {"name": ["Team name is required."]})
            return redirect("/teams")
        team = await Team.create(user_id=user.get_key(), name=name, personal_team=False)
        await team.users().attach(user.get_key(), {"role": "owner"})  # type: ignore[attr-defined]
        user.set_attribute("current_team_id", team.get_key())
        await user.save()
        request.session.flash("status", "Team created.")
        return redirect(f"/teams/{team.get_key()}")

    async def show(self, request: Request, team: str):
        user = auth().user()
        model = await Team.query().find(team)
        if model is None:
            raise NotFoundHttpException("Team not found.")
        members = []
        for m in await model.users().get():  # type: ignore[attr-defined]
            members.append(
                {
                    "id": m.get_key(),
                    "name": m.get_attribute("name"),
                    "email": m.get_attribute("email"),
                    "role": getattr(m, "pivot", None) and getattr(m.pivot, "role", None) or "member",
                }
            )
        invites = [
            {"id": i.get_key(), "email": i.get_attribute("email"), "role": i.get_attribute("role")}
            for i in await model.invitations().get()  # type: ignore[attr-defined]
        ]
        return Inertia.render(
            "Teams/Show",
            {
                "team": {
                    "id": model.get_key(),
                    "name": model.get_attribute("name"),
                    "personal_team": bool(model.get_attribute("personal_team")),
                    "owner_id": model.get_attribute("user_id"),
                },
                "members": members,
                "invitations": invites,
                "isOwner": user and user.get_key() == model.get_attribute("user_id"),
                "status": request.session.get("status"),
            },
        )

    async def update(self, request: Request, team: str):
        user = auth().user()
        model = await Team.query().find(team)
        if model is None or user is None or user.get_key() != model.get_attribute("user_id"):
            raise NotFoundHttpException("Team not found.")
        name = str(request.input("name") or "").strip()
        if name:
            model.set_attribute("name", name)
            await model.save()
        request.session.flash("status", "Team updated.")
        return redirect(f"/teams/{team}")

    async def destroy(self, request: Request, team: str):
        user = auth().user()
        model = await Team.query().find(team)
        if model is None or user is None or user.get_key() != model.get_attribute("user_id"):
            raise NotFoundHttpException("Team not found.")
        if model.get_attribute("personal_team"):
            request.session.flash("errors", {"team": ["Personal teams cannot be deleted."]})
            return redirect(f"/teams/{team}")
        await model.delete()
        request.session.flash("status", "Team deleted.")
        return redirect("/teams")

    async def switch(self, request: Request, team: str):
        user = auth().user()
        if user is None:
            return redirect("/login")
        model = await Team.query().find(team)
        if model is None:
            raise NotFoundHttpException("Team not found.")
        user.set_attribute("current_team_id", model.get_key())
        await user.save()
        request.session.flash("status", "Switched team.")
        return redirect("/dashboard")

    async def invite(self, request: Request, team: str):
        user = auth().user()
        model = await Team.query().find(team)
        if model is None or user is None or user.get_key() != model.get_attribute("user_id"):
            raise NotFoundHttpException("Team not found.")
        email = str(request.input("email") or "").strip()
        role = str(request.input("role") or "member").strip() or "member"
        if not email:
            request.session.flash("errors", {"email": ["Email is required."]})
            return redirect(f"/teams/{team}")
        await TeamInvitation.create(team_id=model.get_key(), email=email, role=role)
        request.session.flash("status", "Invitation created.")
        return redirect(f"/teams/{team}")

    async def remove_member(self, request: Request, team: str, user: str):
        actor = auth().user()
        model = await Team.query().find(team)
        if model is None or actor is None or actor.get_key() != model.get_attribute("user_id"):
            raise NotFoundHttpException("Team not found.")
        await model.users().detach(user)  # type: ignore[attr-defined]
        request.session.flash("status", "Member removed.")
        return redirect(f"/teams/{team}")

    async def leave(self, request: Request, team: str):
        user = auth().user()
        model = await Team.query().find(team)
        if model is None or user is None:
            raise NotFoundHttpException("Team not found.")
        if user.get_key() == model.get_attribute("user_id"):
            request.session.flash("errors", {"team": ["Owners cannot leave; delete the team instead."]})
            return redirect(f"/teams/{team}")
        await model.users().detach(user.get_key())  # type: ignore[attr-defined]
        request.session.flash("status", "You left the team.")
        return redirect("/teams")
