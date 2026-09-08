"""The broadcast manager — connections, channels, and authorization.

Two jobs live here. One is the usual manager-and-driver arrangement: resolve a
named connection out of `config/broadcasting.py`. The other is the channel
registry — the patterns declared in `routes/channels.py` and the callbacks
that decide who may listen to them.
"""

from __future__ import annotations

import inspect
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, get_type_hints

from almasix.broadcasting.broadcasters.base import Broadcaster
from almasix.broadcasting.channels import is_presence, is_private, strip_prefix
from almasix.broadcasting.events import (
    broadcast_allowed,
    broadcast_channels,
    broadcast_connections,
    broadcast_name,
    broadcast_payload,
)
from almasix.broadcasting.exceptions import AccessDeniedException
from almasix.broadcasting.signing import encode_channel_data, sign

Resolver = Callable[[str, dict[str, Any]], Broadcaster]


@dataclass
class ChannelRoute:
    """One registered channel pattern and the callback that authorizes it."""

    pattern: str
    callback: Any
    guards: list[str]
    regex: re.Pattern[str]

    def matches(self, channel: str) -> re.Match[str] | None:
        return self.regex.match(channel)


def compile_pattern(pattern: str) -> re.Pattern[str]:
    """`orders.{order}` → a regex capturing one dot-free segment per parameter."""
    parts: list[str] = []
    for token in re.split(r"(\{[^}]+\})", pattern):
        if token.startswith("{") and token.endswith("}"):
            parts.append(r"([^.]+)")
        elif token:
            parts.append(re.escape(token))
    return re.compile(f"^{''.join(parts)}$")


class BroadcastManager:
    """Resolves broadcasters, remembers channels, and sends events."""

    def __init__(self, app: Any | None = None, config: Mapping[str, Any] | None = None) -> None:
        self.app = app
        self._config = dict(config or {})
        self._drivers: dict[str, Broadcaster] = {}
        self._custom: dict[str, Resolver] = {}
        self._channels: list[ChannelRoute] = []

    # ------------------------------------------------------------------
    # Configuration

    def set_config(self, config: Mapping[str, Any]) -> None:
        self._config = dict(config)
        self._drivers.clear()

    @property
    def config(self) -> dict[str, Any]:
        return self._config

    def get_default_driver(self) -> str:
        return str(self._config.get("default") or "log")

    def set_default_driver(self, name: str) -> None:
        self._config["default"] = name

    def extend(self, driver: str, resolver: Resolver) -> BroadcastManager:
        """Teach the manager a driver of your own (Laravel `Broadcast::extend`)."""
        self._custom[driver] = resolver
        return self

    def connection(self, name: str | None = None) -> Broadcaster:
        key = name or self.get_default_driver()
        if key not in self._drivers:
            self._drivers[key] = self._resolve(key)
        return self._drivers[key]

    #: Laravel calls the same thing `driver()`.
    driver = connection

    def set_connection(self, name: str, broadcaster: Broadcaster) -> None:
        """Install a broadcaster directly — fakes, tests, custom wiring."""
        self._drivers[name] = broadcaster

    def purge(self, name: str | None = None) -> None:
        if name is None:
            self._drivers.clear()
        else:
            self._drivers.pop(name, None)

    def connection_config(self, name: str) -> dict[str, Any]:
        connections = self._config.get("connections") or {}
        cfg = connections.get(name)
        if cfg is None:
            raise KeyError(
                f"Broadcast connection [{name}] is not configured. "
                f"Add it to config/broadcasting.py under 'connections'."
            )
        return dict(cfg)

    def _resolve(self, name: str) -> Broadcaster:
        cfg = self.connection_config(name)
        driver = str(cfg.get("driver") or "null")
        if driver in self._custom:
            return self._custom[driver](name, cfg)

        if driver == "null":
            from almasix.broadcasting.broadcasters.null import NullBroadcaster

            return NullBroadcaster(name, cfg)
        if driver == "log":
            from almasix.broadcasting.broadcasters.log import LogBroadcaster

            return LogBroadcaster(name, cfg)
        if driver == "websocket":
            from almasix.broadcasting.broadcasters.websocket import WebsocketBroadcaster

            return WebsocketBroadcaster(name, cfg)
        if driver == "redis":
            from almasix.broadcasting.broadcasters.redis import RedisBroadcaster

            return RedisBroadcaster(name, cfg)
        if driver == "pusher":
            from almasix.broadcasting.broadcasters.pusher import PusherBroadcaster

            return PusherBroadcaster(name, cfg)
        raise ValueError(f"Unsupported broadcast driver: {driver!r}")

    # ------------------------------------------------------------------
    # Channel registry

    def channel(
        self,
        pattern: str,
        callback: Any = None,
        *,
        guards: Sequence[str] | None = None,
    ) -> Any:
        """Register who may listen on `pattern`.

        Used as a call or as a decorator:

            Broadcast.channel("orders.{order}", lambda user, order: ...)

            @Broadcast.channel("orders.{order}")
            def orders(user, order): ...
        """
        if callback is None:

            def decorator(fn: Any) -> Any:
                self.channel(pattern, fn, guards=guards)
                return fn

            return decorator

        self._channels.append(
            ChannelRoute(
                pattern=pattern,
                callback=callback,
                guards=list(guards or []),
                regex=compile_pattern(pattern),
            )
        )
        return self

    def channels(self) -> list[ChannelRoute]:
        return list(self._channels)

    def forget_channels(self) -> None:
        self._channels.clear()

    def channel_for(self, name: str) -> ChannelRoute | None:
        """The route matching a channel name, prefix ignored."""
        bare = strip_prefix(name)
        for route in self._channels:
            if route.matches(bare) is not None:
                return route
        return None

    # ------------------------------------------------------------------
    # Authorization

    async def authorize(self, user: Any, channel: str) -> Any:
        """Ask the registered callback whether `user` may join `channel`.

        Returns whatever the callback returned: falsey denies, `True` allows,
        and a mapping allows and becomes the presence member info. A channel
        nobody registered is denied — silence is not consent.
        """
        route = self.channel_for(channel)
        if route is None:
            return False
        match = route.matches(strip_prefix(channel))
        assert match is not None
        if user is None:
            return False

        callback = self._callable_for(route)
        arguments = await self._bind(callback, list(match.groups()))
        if arguments is None:
            return False
        result = callback(user, *arguments)
        if inspect.isawaitable(result):
            result = await result
        return result

    def _callable_for(self, route: ChannelRoute) -> Any:
        """The function to call, whether the route registered one or a class.

        A channel class is Laravel's other spelling: a class with a `join`
        method, resolved out of the container so it can take dependencies.
        """
        callback = route.callback
        if inspect.isclass(callback):
            instance = self.app.make(callback) if self.app is not None else callback()
            return instance.join
        return callback

    async def _bind(self, callback: Any, values: list[str]) -> list[Any] | None:
        """Turn captured segments into arguments, resolving models on the way.

        A parameter annotated with a model gets that model looked up by key,
        exactly as route model binding does. A missing record denies the
        subscription rather than raising.
        """
        parameters = [
            parameter
            for parameter in inspect.signature(callback).parameters.values()
            if parameter.kind
            in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
        ][1:]  # the first parameter is always the user

        # `from __future__ import annotations` turns every annotation into a
        # string, so ask typing for the real classes before looking for models.
        try:
            hints = get_type_hints(callback)
        except Exception:  # noqa: BLE001 — an unresolvable hint just means no binding
            hints = {}

        bound: list[Any] = []
        for index, value in enumerate(values):
            parameter = parameters[index] if index < len(parameters) else None
            annotation = (
                hints.get(parameter.name, parameter.annotation) if parameter is not None else None
            )
            model = await self._resolve_model(annotation, value)
            if model is False:
                return None
            bound.append(value if model is None else model)
        return bound

    async def _resolve_model(self, annotation: Any, value: str) -> Any:
        """The record `value` names, `None` when the parameter is a plain value."""
        if not inspect.isclass(annotation):
            return None
        # A model is a class you can await a record out of; `str` has a
        # `find` too, which is why the test is for a coroutine.
        finder = getattr(annotation, "find", None)
        if finder is None or not inspect.iscoroutinefunction(finder):
            return None
        record = await finder(value)
        return record if record is not None else False

    async def auth(self, request: Any) -> dict[str, Any]:
        """The response for `POST /broadcasting/auth`.

        Mirrors Pusher's contract, so the same endpoint satisfies Almasix's
        own socket server and a hosted one: an `auth` signature, plus
        `channel_data` when the channel is a presence channel.
        """
        channel = str(request.input("channel_name") or "")
        socket_id = str(request.input("socket_id") or "")
        if not channel or not socket_id:
            raise AccessDeniedException(channel, "A socket_id and channel_name are required.")

        if not is_private(channel):
            return {"auth": ""}

        route = self.channel_for(channel)
        user = self._user_for(request, route.guards if route else [])
        result = await self.authorize(user, channel)
        if not result:
            raise AccessDeniedException(channel)

        broadcaster = self.connection()
        secret = broadcaster.auth_secret()
        if not secret:
            from almasix.broadcasting.exceptions import BroadcastException

            raise BroadcastException(
                f"Broadcast connection [{broadcaster.name}] has no secret to sign with. "
                f"Set one in config/broadcasting.py, or set APP_KEY."
            )

        if is_presence(channel):
            info = result if isinstance(result, Mapping) else None
            channel_data = encode_channel_data(_user_key(user), info)
            return {
                "auth": sign(broadcaster.auth_key(), secret, socket_id, channel, channel_data),
                "channel_data": channel_data,
            }
        return {"auth": sign(broadcaster.auth_key(), secret, socket_id, channel)}

    def user_auth(self, request: Any) -> dict[str, Any]:
        """The response for `POST /broadcasting/user-auth`.

        Some socket servers ask the application to identify a connection
        before any channel is involved; this answers that.
        """
        user = self._user_for(request, [])
        if user is None:
            raise AccessDeniedException("", "Unauthenticated.")
        payload = json.dumps({"user_id": str(_user_key(user))}, separators=(",", ":"))
        broadcaster = self.connection()
        secret = broadcaster.auth_secret() or ""
        return {
            "auth": sign(broadcaster.auth_key(), secret, "", "", payload),
            "user_data": payload,
        }

    def _user_for(self, request: Any, guards: Sequence[str]) -> Any:
        """The authenticated user, trying each guard the channel named."""
        if not guards:
            return request.user()
        for guard in guards:
            user = request.user(guard)
            if user is not None:
                return user
        return None

    # ------------------------------------------------------------------
    # Sending

    async def event(
        self,
        channels: Any,
        event: str,
        payload: Mapping[str, Any] | None = None,
        *,
        socket: str | None = None,
        connection: str | None = None,
    ) -> None:
        """Send an ad-hoc event, without defining an event class for it."""
        from almasix.broadcasting.channels import channel_names

        names = channel_names(channels)
        if not names:
            return
        await self._send(self.connection(connection), names, event, dict(payload or {}), socket)

    async def broadcast_event(self, event: Any, *, connection: str | None = None) -> None:
        """Send a `ShouldBroadcast` event over every connection it asks for."""
        if not broadcast_allowed(event):
            return
        names = broadcast_channels(event)
        if not names:
            return

        payload = broadcast_payload(event)
        name = broadcast_name(event)
        socket = getattr(event, "socket", None)
        targets = [connection] if connection is not None else broadcast_connections(event)
        for target in targets:
            await self._send(self.connection(target), names, name, payload, socket)

    async def _send(
        self,
        broadcaster: Broadcaster,
        names: Sequence[str],
        event: str,
        payload: dict[str, Any],
        socket: str | None,
    ) -> None:
        """One broadcast, with encrypted channels handled separately.

        A `private-encrypted-` channel gets the payload sealed with the
        application key, so whoever relays the message — Redis, a hosted
        socket service — never sees it in the clear.
        """
        plain = [name for name in names if not name.startswith("private-encrypted-")]
        sealed = [name for name in names if name.startswith("private-encrypted-")]
        if plain:
            await broadcaster.broadcast(plain, event, payload, socket=socket)
        if sealed:
            await broadcaster.broadcast(sealed, event, self._encrypt(payload), socket=socket)

    def _encrypt(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        from almasix.encryption.helpers import encrypt_string

        return {"ciphertext": encrypt_string(json.dumps(dict(payload), default=str))}

    def queue(self, event: Any) -> None:
        """Hand a broadcast to the queue, or send it now if it asked to be.

        This is what the event dispatcher calls, and it is deliberately sync:
        dispatching an event must not require an event loop.
        """
        from almasix.broadcasting.jobs import queue_broadcast

        queue_broadcast(event)


def _user_key(user: Any) -> Any:
    """A user's identifier, however this application spells it."""
    for attribute in ("get_auth_identifier", "get_key"):
        method = getattr(user, attribute, None)
        if callable(method):
            return method()
    return getattr(user, "id", None)
