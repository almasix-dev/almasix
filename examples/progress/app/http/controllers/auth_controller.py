"""Session login / logout for the progress demo."""

from __future__ import annotations

from almasix.auth import auth
from almasix.prism import view
from almasix.hashing import Hash
from almasix.http import Controller, Request, Response, redirect
from almasix.routing import url
from almasix.translation import __


class AuthController(Controller):
    async def show_login(self) -> Response:
        return view(
            "auth.login",
            {
                "action": url("/login", absolute=False),
                "home_url": url("/", absolute=False),
            },
        )

    async def login(self, request: Request) -> Response:
        email = str(request.input("email") or "").strip()
        password = str(request.input("password") or "")
        remember = bool(request.boolean("remember"))
        if not email or not password:
            request.session.flash("error", "Email and password are required.")
            return redirect("/login")

        ok = await auth().attempt(
            {"email": email, "password": password},
            remember=remember,
        )
        if not ok:
            request.session.flash("error", __("auth.failed"))
            return redirect("/login")

        user = auth().user()
        name = (
            user.get_attribute("name")
            if hasattr(user, "get_attribute")
            else (user.get("name") if isinstance(user, dict) else getattr(user, "name", email))
        )
        request.session.flash("status", f"Signed in as {name}.")
        from almasix.auth.guard import pull_intended_url

        return redirect(pull_intended_url("/"))

    async def logout(self, request: Request) -> Response:
        await auth().logout()
        request.session.flash("status", "Signed out.")
        return redirect("/")

    async def show_confirm(self) -> Response:
        return view(
            "auth.confirm_password",
            {"action": url("/confirm-password", absolute=False)},
        )

    async def confirm(self, request: Request) -> Response:
        from almasix.auth.middleware import mark_password_confirmed

        password = str(request.input("password") or "")
        user = auth().user()
        if user is None:
            return redirect("/login")
        hashed = (
            user.get_auth_password()
            if hasattr(user, "get_auth_password")
            else getattr(user, "password", None)
        )
        if not hashed or not Hash.check(password, str(hashed)):
            request.session.flash("error", __("auth.password"))
            return redirect("/confirm-password")
        mark_password_confirmed(request)
        return redirect("/")
