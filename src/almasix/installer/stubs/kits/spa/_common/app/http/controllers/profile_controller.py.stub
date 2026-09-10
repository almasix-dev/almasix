"""Profile, password, appearance, account deletion."""

from __future__ import annotations

from almasix.auth import auth
from almasix.hashing import Hash
from almasix.http import Controller, Request, redirect
from inertia import Inertia


class ProfileController(Controller):
    async def edit(self, request: Request):
        user = auth().user()
        return Inertia.render(
            "Settings/Profile",
            {
                "user": {
                    "name": user.get_attribute("name") if user else "",
                    "email": user.get_attribute("email") if user else "",
                    "profile_photo_path": user.get_attribute("profile_photo_path") if user else None,
                },
                "status": request.session.get("status"),
            },
        )

    async def password(self, request: Request):
        return Inertia.render(
            "Settings/Password",
            {"status": request.session.get("status")},
        )

    async def update(self, request: Request):
        user = auth().user()
        if user is None:
            return redirect("/login")
        name = str(request.input("name") or "").strip()
        email = str(request.input("email") or "").strip()
        if not name or not email:
            request.session.flash("errors", {"name": ["Name and email are required."]})
            return redirect("/settings/profile")
        user.set_attribute("name", name)
        if email != user.get_attribute("email"):
            user.set_attribute("email", email)
            user.set_attribute("email_verified_at", None)
        await user.save()
        request.session.flash("status", "Profile updated.")
        return redirect("/settings/profile")

    async def update_password(self, request: Request):
        user = auth().user()
        if user is None:
            return redirect("/login")
        current = str(request.input("current_password") or "")
        password = str(request.input("password") or "")
        confirm = str(request.input("password_confirmation") or "")
        if not Hash.check(current, str(user.get_attribute("password") or "")):
            request.session.flash("errors", {"current_password": ["Current password is incorrect."]})
            return redirect("/settings/password")
        if not password or password != confirm:
            request.session.flash("errors", {"password": ["Password confirmation does not match."]})
            return redirect("/settings/password")
        user.set_attribute("password", password)
        await user.save()
        request.session.flash("status", "Password updated.")
        return redirect("/settings/password")

    async def destroy(self, request: Request):
        user = auth().user()
        if user is None:
            return redirect("/login")
        password = str(request.input("password") or "")
        if not Hash.check(password, str(user.get_attribute("password") or "")):
            request.session.flash("errors", {"password": ["Password is incorrect."]})
            return redirect("/settings/profile")
        await auth().logout()
        await user.delete()
        return redirect("/")

    async def update_photo(self, request: Request):
        user = auth().user()
        if user is None:
            return redirect("/login")
        path = str(request.input("profile_photo_path") or "").strip() or None
        user.set_attribute("profile_photo_path", path)
        await user.save()
        request.session.flash("status", "Photo updated.")
        return redirect("/settings/profile")

    async def appearance(self, request: Request):
        return Inertia.render("Settings/Appearance", {"status": request.session.get("status")})
