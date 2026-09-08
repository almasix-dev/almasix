"""Session and token authentication guards."""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from typing import Any

from almasix.auth import events as auth_events
from almasix.auth.cookies import queue_cookie, queue_forget_cookie
from almasix.auth.providers import ArticulateUserProvider, MemoryUserProvider
from almasix.translation import __

_auth: ContextVar[AuthManager | None] = ContextVar("almasix_auth", default=None)

_PASSWORD_CONFIRMED_AT = "auth.password_confirmed_at"
_INTENDED_URL = "url.intended"
_REMEMBER_YEARS = 5 * 365 * 24 * 60 * 60

ViaRequestCallback = Callable[[Any], Awaitable[Any | None] | Any]


class Guard:
    """Base guard: ``user()`` / ``check()`` / ``login()`` / ``logout()``."""

    def __init__(self, name: str = "web", provider: Any | None = None) -> None:
        self.name = name
        self.provider = provider
        self._user: Any = None
        self._via_remember = False
        self._logged_out = False
        self._via_request: ViaRequestCallback | None = None

    def user(self) -> Any:
        return self._user

    def id(self) -> Any:
        user = self._user
        if user is None:
            return None
        if hasattr(user, "get_auth_identifier"):
            return user.get_auth_identifier()
        if isinstance(user, dict):
            return user.get("id")
        return getattr(user, "id", None)

    def check(self) -> bool:
        return self._user is not None

    def guest(self) -> bool:
        return not self.check()

    def via_remember(self) -> bool:
        return self._via_remember

    def once(self, user: Any) -> None:
        """Authenticate for this request only (no session write)."""
        self._user = user
        self._via_remember = False

    def via_request(self, callback: ViaRequestCallback) -> None:
        """Laravel ``Auth::viaRequest`` — custom request resolver for this guard."""
        self._via_request = callback

    async def attempt(
        self,
        credentials: dict[str, Any],
        *,
        remember: bool = False,
    ) -> bool:
        raise NotImplementedError

    async def validate(self, credentials: dict[str, Any]) -> bool:
        raise NotImplementedError

    async def login(self, user: Any, *, remember: bool = False) -> None:
        self._user = user
        self._logged_out = False
        self._via_remember = False
        await auth_events.dispatch(auth_events.Login(user=user, guard=self.name, remember=remember))
        await auth_events.dispatch(auth_events.Authenticated(user=user, guard=self.name))

    async def login_using_id(self, identifier: Any, *, remember: bool = False) -> Any | None:
        if self.provider is None:
            return None
        user = await self.provider.retrieve_by_id(identifier)
        if user is None:
            return None
        await self.login(user, remember=remember)
        return user

    async def once_using_id(self, identifier: Any) -> Any | None:
        if self.provider is None:
            return None
        user = await self.provider.retrieve_by_id(identifier)
        if user is None:
            return None
        self.once(user)
        return user

    async def logout(self) -> None:
        user = self._user
        self._user = None
        self._via_remember = False
        self._logged_out = True
        if user is not None:
            await auth_events.dispatch(auth_events.Logout(user=user, guard=self.name))


class SessionGuard(Guard):
    """Stateful session + optional remember-me cookie guard."""

    async def attempt(
        self,
        credentials: dict[str, Any],
        *,
        remember: bool = False,
    ) -> bool:
        await auth_events.dispatch(
            auth_events.Attempting(credentials=credentials, guard=self.name, remember=remember)
        )
        if self.provider is None:
            await auth_events.dispatch(auth_events.Failed(credentials=credentials, guard=self.name))
            return False
        user = await self.provider.retrieve_by_credentials(credentials)
        if user is None or not await self.provider.validate_credentials(user, credentials):
            await auth_events.dispatch(auth_events.Failed(credentials=credentials, guard=self.name))
            return False
        await auth_events.dispatch(auth_events.Validated(user=user, guard=self.name))
        await self.provider.rehash_password_if_required(user, credentials)
        await self.login(user, remember=remember)
        return True

    async def validate(self, credentials: dict[str, Any]) -> bool:
        if self.provider is None:
            return False
        user = await self.provider.retrieve_by_credentials(credentials)
        if user is None:
            return False
        return await self.provider.validate_credentials(user, credentials)

    async def login(self, user: Any, *, remember: bool = False) -> None:
        from almasix.session.store import get_session

        # Set user before building remember cookie so ``id()`` works.
        self._user = user
        self._logged_out = False
        self._via_remember = False

        session = get_session()
        if session is not None:
            session.put(f"login_{self.name}", _session_payload(user))
            session.regenerate()
            session.put(_PASSWORD_CONFIRMED_AT, None)
        if remember:
            await self._cycle_remember_token(user)
            self._queue_remember_cookie(user)
        else:
            queue_forget_cookie(self.remember_cookie_name(), path=_cookie_path())
        await auth_events.dispatch(auth_events.Login(user=user, guard=self.name, remember=remember))
        await auth_events.dispatch(auth_events.Authenticated(user=user, guard=self.name))

    async def logout(self) -> None:
        from almasix.session.store import get_session

        user = self._user
        if user is not None and self.provider is not None:
            await self.provider.update_remember_token(user, None)
        queue_forget_cookie(self.remember_cookie_name(), path=_cookie_path())
        session = get_session()
        if session is not None:
            session.forget(f"login_{self.name}")
            session.forget(f"remember_{self.name}")
            session.forget(_PASSWORD_CONFIRMED_AT)
            session.regenerate()
        await Guard.logout(self)

    async def logout_other_devices(self, password: str) -> bool:
        """Verify password and rotate the session (invalidate other devices)."""
        user = self._user
        if user is None or self.provider is None:
            return False
        if not await self.provider.validate_credentials(user, {"password": password}):
            return False
        from almasix.session.store import get_session

        session = get_session()
        if session is not None:  # pragma: no branch
            session.regenerate()
        await self._cycle_remember_token(user)
        self._queue_remember_cookie(user)
        await auth_events.dispatch(auth_events.OtherDeviceLogout(user=user, guard=self.name))
        return True

    async def _cycle_remember_token(self, user: Any) -> str:
        token = secrets.token_urlsafe(40)
        if self.provider is not None:
            await self.provider.update_remember_token(user, token)
        from almasix.session.store import get_session

        session = get_session()
        if session is not None:
            session.put(f"remember_{self.name}", token)
        if isinstance(user, dict):
            user["remember_token"] = token
        elif not hasattr(user, "get_remember_token"):
            setattr(user, "remember_token", token)
        return token

    def _queue_remember_cookie(self, user: Any) -> None:
        identifier = _user_id(user)
        token = _remember_token_of(user)
        if identifier is None or not token:
            return
        queue_cookie(
            self.remember_cookie_name(),
            f"{identifier}|{token}",
            max_age=_remember_lifetime(),
            path=_cookie_path(),
            secure=_cookie_secure(),
            httponly=True,
            samesite="lax",
        )

    def remember_cookie_name(self) -> str:
        return f"remember_{self.name}"


class TokenGuard(Guard):
    """Stateless API token guard (classic ``api_token`` column lookup)."""

    def __init__(
        self,
        name: str = "api",
        provider: Any | None = None,
        *,
        input_key: str = "api_token",
        storage_key: str = "api_token",
    ) -> None:
        super().__init__(name, provider)
        self.input_key = input_key
        self.storage_key = storage_key

    async def attempt(
        self,
        credentials: dict[str, Any],
        *,
        remember: bool = False,
    ) -> bool:
        token = credentials.get(self.input_key) or credentials.get("token")
        if not token or self.provider is None:
            return False
        user = await self.provider.retrieve_by_credentials({self.storage_key: token})
        if user is None:
            return False
        self.once(user)
        await auth_events.dispatch(auth_events.Authenticated(user=user, guard=self.name))
        return True

    async def validate(self, credentials: dict[str, Any]) -> bool:
        return await self.attempt(credentials)

    async def login(self, user: Any, *, remember: bool = False) -> None:
        self.once(user)
        await auth_events.dispatch(auth_events.Login(user=user, guard=self.name, remember=False))
        await auth_events.dispatch(auth_events.Authenticated(user=user, guard=self.name))

    async def set_user_from_request_token(self, token: str | None) -> Any | None:
        if not token or self.provider is None:
            return None
        try:
            user = await self.provider.retrieve_by_credentials({self.storage_key: token})
        except Exception:
            return None
        if user is None:
            return None
        self.once(user)
        return user


class AuthManager:
    """Resolves named guards from ``config/auth.py`` (with safe defaults)."""

    def __init__(self) -> None:
        self._guards: dict[str, Guard] = {}
        self._providers: dict[str, Any] = {}
        self._default = "web"
        self._via_request: dict[str, ViaRequestCallback] = {}

    def configure_from_config(self) -> None:
        try:
            from almasix.config import config

            self._default = str(config("auth.defaults.guard", "web") or "web")
        except Exception:
            self._default = "web"

    def should_use(self, name: str) -> None:
        """Laravel ``Auth::shouldUse`` / ``setDefaultDriver``."""
        self._default = name

    set_default_driver = should_use

    def via_request(self, guard: str, callback: ViaRequestCallback) -> None:
        self._via_request[guard] = callback
        if guard in self._guards:
            self._guards[guard].via_request(callback)

    def guard(self, name: str | None = None) -> Guard:
        key = name or self._default
        if key not in self._guards:
            self._guards[key] = self._resolve_guard(key)
            if key in self._via_request:
                self._guards[key].via_request(self._via_request[key])
        return self._guards[key]

    def _resolve_guard(self, name: str) -> Guard:
        try:
            from almasix.config import config

            guards = dict(config("auth.guards", {}) or {})
        except Exception:
            guards = {}
        spec = dict(guards.get(name) or {})
        driver = str(spec.get("driver") or ("session" if name == "web" else "token"))
        provider_name = str(spec.get("provider") or "users")
        provider = self._resolve_provider(provider_name)
        if driver == "session":
            return SessionGuard(name, provider)
        if driver == "token":
            return TokenGuard(
                name,
                provider,
                input_key=str(spec.get("input_key") or "api_token"),
                storage_key=str(spec.get("storage_key") or "api_token"),
            )
        return Guard(name, provider)

    def _resolve_provider(self, name: str) -> Any | None:
        if name in self._providers:
            return self._providers[name]
        try:
            from almasix.config import config

            providers = dict(config("auth.providers", {}) or {})
        except Exception:
            providers = {}
        spec = dict(providers.get(name) or {})
        driver = str(spec.get("driver") or "articulate")
        if driver == "memory":
            provider = MemoryUserProvider(list(spec.get("users") or []))
        elif driver == "articulate":
            model_path = spec.get("model")
            if not model_path:
                self._providers[name] = None
                return None
            try:
                model = _import_string(str(model_path))
            except Exception:
                # Soft-fail when the app has not created the user model yet
                # (fresh scaffolds) or the import path is temporarily wrong.
                self._providers[name] = None
                return None
            provider = ArticulateUserProvider(model)
        else:
            provider = None
        self._providers[name] = provider
        return provider

    def user(self) -> Any:
        for guard in self._guards.values():
            if guard.check():
                return guard.user()
        return self.guard().user()

    def check(self) -> bool:
        if any(g.check() for g in self._guards.values()):
            return True
        return self.guard().check()

    def guest(self) -> bool:
        return not self.check()

    async def login(self, user: Any, *, remember: bool = False) -> None:
        await self.guard().login(user, remember=remember)

    async def logout(self) -> None:
        await self.guard().logout()

    async def attempt(
        self,
        credentials: dict[str, Any],
        *,
        remember: bool = False,
    ) -> bool:
        return await self.guard().attempt(credentials, remember=remember)

    async def validate(self, credentials: dict[str, Any]) -> bool:
        return await self.guard().validate(credentials)

    def id(self) -> Any:
        for guard in self._guards.values():
            if guard.check():
                return guard.id()
        return self.guard().id()

    def via_remember(self) -> bool:
        return self.guard().via_remember()


def _session_payload(user: Any) -> dict[str, Any]:
    if isinstance(user, dict):
        return {k: v for k, v in user.items() if k != "password"}
    if hasattr(user, "get_auth_identifier"):
        payload: dict[str, Any] = {"id": user.get_auth_identifier()}
        for attr in ("email", "name"):
            if hasattr(user, "get_attribute"):
                value = user.get_attribute(attr)
            else:
                value = getattr(user, attr, None)
            if value is not None:
                payload[attr] = value
        return payload
    return _user_to_dict(user)


def _user_to_dict(user: Any) -> dict[str, Any]:
    if hasattr(user, "to_dict"):
        data = dict(user.to_dict())
        data.pop("password", None)
        return data
    if hasattr(user, "__dict__"):
        return {
            key: value
            for key, value in vars(user).items()
            if not key.startswith("_") and key != "password"
        }
    return {"user": str(user)}


def _user_id(user: Any) -> Any:
    if hasattr(user, "get_auth_identifier"):
        return user.get_auth_identifier()
    if isinstance(user, dict):
        return user.get("id")
    return getattr(user, "id", None)


def _remember_token_of(user: Any) -> str | None:
    if hasattr(user, "get_remember_token"):
        return user.get_remember_token()
    if isinstance(user, dict):
        value = user.get("remember_token")
        return str(value) if value is not None else None
    value = getattr(user, "remember_token", None)
    return str(value) if value is not None else None


def _remember_lifetime() -> int:
    try:
        from almasix.config import config

        minutes = int(config("auth.remember", 0) or 0)
        if minutes > 0:
            return minutes * 60
    except Exception:
        pass
    return _REMEMBER_YEARS


def _cookie_path() -> str:
    try:
        from almasix.config import config

        return str(config("session.path", "/") or "/")
    except Exception:
        return "/"


def _cookie_secure() -> bool:
    try:
        from almasix.config import config

        return bool(config("session.secure", False))
    except Exception:
        return False


def _import_string(path: str) -> type:
    module_path, _, name = path.rpartition(".")
    if not module_path:
        raise ImportError(f"Invalid model path: {path}")
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, name)


def get_auth() -> AuthManager | None:
    return _auth.get()


def set_auth(manager: AuthManager | None) -> Token[AuthManager | None]:
    return _auth.set(manager)


def reset_auth(token: Token[AuthManager | None]) -> None:
    _auth.reset(token)


def auth() -> AuthManager:
    """Return the request AuthManager (empty manager outside HTTP)."""
    manager = get_auth()
    if manager is None:
        manager = AuthManager()
        manager.configure_from_config()
        return manager
    return manager


def guest() -> bool:
    return auth().guest()


def auth_failed_message() -> str:
    return __("auth.failed")


def pull_intended_url(default: str = "/") -> str:
    from almasix.session.store import get_session

    session = get_session()
    if session is None:
        return default
    return str(session.pull(_INTENDED_URL, default) or default)


def store_intended_url(url: str) -> None:
    from almasix.session.store import get_session

    session = get_session()
    if session is not None:
        session.put(_INTENDED_URL, url)
