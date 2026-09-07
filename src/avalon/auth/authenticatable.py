"""Authenticatable helpers for Articulate models."""

from __future__ import annotations

from typing import Any

from avalon.auth.access.authorizable import Authorizable


class AuthenticatableMixin(Authorizable):
    """Mixin / base helpers for user models (Laravel Authenticatable trait)."""

    remember_token_name = "remember_token"

    def get_auth_identifier_name(self) -> str:
        return getattr(self, "primary_key", None) or "id"

    def get_auth_identifier(self) -> Any:
        name = self.get_auth_identifier_name()
        if hasattr(self, "get_attribute"):
            return self.get_attribute(name)
        return getattr(self, name, None)

    def get_auth_password(self) -> str | None:
        if hasattr(self, "get_attribute"):
            value = self.get_attribute("password")
        else:
            value = getattr(self, "password", None)
        return str(value) if value is not None else None

    def get_remember_token(self) -> str | None:
        name = self.get_remember_token_name()
        if hasattr(self, "get_attribute"):
            value = self.get_attribute(name)
        else:
            value = getattr(self, name, None)
        return str(value) if value is not None else None

    def set_remember_token(self, token: str | None) -> None:
        name = self.get_remember_token_name()
        if hasattr(self, "set_attribute"):
            self.set_attribute(name, token)
        else:
            setattr(self, name, token)

    def get_remember_token_name(self) -> str:
        return str(getattr(self, "remember_token_name", "remember_token"))
