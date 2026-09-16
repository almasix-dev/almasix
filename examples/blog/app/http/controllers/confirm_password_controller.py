"""Confirm password for sensitive actions."""

from __future__ import annotations

from almasix.auth import auth
from almasix.hashing import Hash
from almasix.http import Controller, Request, redirect
from almasix.support.helpers import now
from inertia import Inertia


class ConfirmPasswordController(Controller):
    async def show(self, request: Request):
        return Inertia.render("Auth/ConfirmPassword", {"status": request.session.get("status")})

    async def store(self, request: Request):
        user = auth().user()
        password = str(request.input("password") or "")
        stored = user.get_attribute("password") if user and hasattr(user, "get_attribute") else ""
        if not user or not Hash.check(password, str(stored or "")):
            request.session.flash("errors", {"password": ["The password is incorrect."]})
            return redirect("/confirm-password")
        request.session["auth.password_confirmed_at"] = now().timestamp()
        return redirect(request.session.get("url.intended") or "/dashboard")
