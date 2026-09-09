"""Signet token endpoints — issue a PAT for mobile / API clients (M37)."""

from __future__ import annotations

from almasix.auth import auth
from almasix.hashing import Hash
from almasix.http import Controller, UnauthorizedHttpException
from almasix.http.exceptions import UnprocessableEntityHttpException
from almasix.http.request import Request
from app.models.user import User


class SignetController(Controller):
    """Issue and inspect personal access tokens."""

    async def issue_token(self, request: Request) -> dict[str, str]:
        email = str(request.input("email") or "").strip()
        password = str(request.input("password") or "")
        device_name = str(request.input("device_name") or "api-token").strip()
        errors: dict[str, list[str]] = {}
        if not email:
            errors["email"] = ["The email field is required."]
        if not password:
            errors["password"] = ["The password field is required."]
        if not device_name:
            errors["device_name"] = ["The device_name field is required."]
        if errors:
            raise UnprocessableEntityHttpException("The given data was invalid.", errors=errors)

        user = await User.query().where("email", "=", email).first()
        if user is None or not Hash.check(password, str(user.get_attribute("password") or "")):
            raise UnauthorizedHttpException("The provided credentials are incorrect.")

        abilities = request.input("abilities")
        if isinstance(abilities, str):
            ability_list = [part.strip() for part in abilities.split(",") if part.strip()]
        elif isinstance(abilities, list):
            ability_list = [str(item) for item in abilities]
        else:
            ability_list = ["*"]

        issued = await user.create_token(device_name, ability_list)
        return {"token": issued.plain_text_token, "token_type": "Bearer"}

    async def user(self) -> dict:
        user = auth().guard("signet").user() or auth().user()
        if user is None:
            return {"user": None}
        payload = {
            "id": user.get_key() if hasattr(user, "get_key") else getattr(user, "id", None),
            "email": user.get_attribute("email") if hasattr(user, "get_attribute") else None,
            "name": user.get_attribute("name") if hasattr(user, "get_attribute") else None,
        }
        token_can = getattr(user, "token_can", None)
        return {
            "user": payload,
            "abilities": {
                "server:update": bool(token_can("server:update")) if token_can else True,
                "*": bool(token_can("*")) if token_can else True,
            },
        }
