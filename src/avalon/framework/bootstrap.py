"""Fluent application bootstrap — Laravel 11-shaped ``configure`` / ``with_middleware``."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

from avalon.http.trust import (
    HEADER_X_FORWARDED_ALL,
    normalize_hosts,
    normalize_proxies,
)

if TYPE_CHECKING:
    from avalon.config import ConfigRepository
    from avalon.framework.application import Application

MiddlewareCallback = Callable[["Middleware"], None]


class Middleware:
    """Mutate HTTP middleware stacks after ``config/http.py`` loads.

    Mirrors Laravel's ``bootstrap/app.php`` ``->withMiddleware`` configurator:
    aliases, global stack, named groups, trusted proxies, and trusted hosts.
    """

    def __init__(self, config: ConfigRepository) -> None:
        self._config = config
        http = dict(config.get("http", {}) or {})
        self._global = list(http.get("middleware") or [])
        groups = http.get("middleware_groups") or {}
        self._groups: dict[str, list[Any]] = {
            str(name): list(members or []) for name, members in dict(groups).items()
        }
        self._aliases: dict[str, Any] = dict(http.get("middleware_aliases") or {})
        self._trusted_proxies: list[str] | str | None = http.get("trusted_proxies")
        self._trusted_headers: int = int(
            http.get("trusted_headers", HEADER_X_FORWARDED_ALL) or HEADER_X_FORWARDED_ALL
        )
        hosts = http.get("trusted_hosts")
        self._trusted_hosts: list[str] | None = list(hosts) if hosts else None

    def append(self, *middleware: Any) -> Self:
        """Append to the global middleware stack (every route)."""
        self._global.extend(middleware)
        return self

    def prepend(self, *middleware: Any) -> Self:
        """Prepend to the global middleware stack."""
        self._global[0:0] = list(middleware)
        return self

    def use(self, middleware: Sequence[Any]) -> Self:
        """Replace the global middleware stack."""
        self._global = list(middleware)
        return self

    def alias(self, aliases: Mapping[str, Any]) -> Self:
        """Register or replace short names used in routes / groups."""
        self._aliases.update(dict(aliases))
        return self

    def web(
        self,
        *,
        append: Sequence[Any] | None = None,
        prepend: Sequence[Any] | None = None,
        replace: Sequence[Any] | None = None,
    ) -> Self:
        return self.group("web", append=append, prepend=prepend, replace=replace)

    def api(
        self,
        *,
        append: Sequence[Any] | None = None,
        prepend: Sequence[Any] | None = None,
        replace: Sequence[Any] | None = None,
    ) -> Self:
        return self.group("api", append=append, prepend=prepend, replace=replace)

    def group(
        self,
        name: str,
        *,
        append: Sequence[Any] | None = None,
        prepend: Sequence[Any] | None = None,
        replace: Sequence[Any] | None = None,
    ) -> Self:
        """Configure a named middleware group."""
        if replace is not None:
            self._groups[name] = list(replace)
            return self
        current = list(self._groups.get(name) or [])
        if prepend:
            current = [*list(prepend), *current]
        if append:
            current = [*current, *list(append)]
        self._groups[name] = current
        return self

    def trust_proxies(
        self,
        at: Any = "*",
        headers: int = HEADER_X_FORWARDED_ALL,
    ) -> Self:
        """Trust ``X-Forwarded-*`` from these peers (Laravel ``trustProxies``).

        ``at`` may be ``"*"``, an IP/CIDR string, or a sequence of those.
        """
        self._trusted_proxies = normalize_proxies(at)
        self._trusted_headers = int(headers)
        return self

    def trust_hosts(self, at: Any) -> Self:
        """Enable Host-header allowlisting (Laravel ``trustHosts``).

        ``at`` may be a host, list of hosts (``*.example.com`` wildcards OK),
        or a callable returning either.
        """
        from avalon.http.trust import TrustHosts

        self._trusted_hosts = normalize_hosts(at)
        self._aliases.setdefault("trust.hosts", TrustHosts)
        if "trust.hosts" not in self._global:
            self.prepend("trust.hosts")
        return self

    def apply(self) -> None:
        """Write the configured stacks back into the config repository."""
        self._config.set("http.middleware", self._global)
        self._config.set("http.middleware_groups", self._groups)
        self._config.set("http.middleware_aliases", self._aliases)
        if self._trusted_proxies is not None:
            self._config.set("http.trusted_proxies", self._trusted_proxies)
            self._config.set("http.trusted_headers", self._trusted_headers)
        if self._trusted_hosts is not None:
            self._config.set("http.trusted_hosts", self._trusted_hosts)


class ApplicationBuilder:
    """``Application.configure(base_path).with_middleware(...).create()``."""

    def __init__(self, base_path: str | Path | None = None) -> None:
        self._base_path = Path(base_path or Path.cwd()).resolve()
        self._middleware_callbacks: list[MiddlewareCallback] = []
        self._schedule_callbacks: list[Callable[[Any], None]] = []

    def with_middleware(self, callback: MiddlewareCallback) -> Self:
        self._middleware_callbacks.append(callback)
        return self

    def with_schedule(self, callback: Callable[[Any], None]) -> Self:
        """Define scheduled tasks here instead of in ``routes/console.py``.

        The callback is handed the schedule as it is registered, which is what
        Laravel's ``withSchedule`` does.
        """
        self._schedule_callbacks.append(callback)
        return self

    def create(self) -> Application:
        from avalon.framework.application import Application

        app = Application(self._base_path)
        app._middleware_callbacks = list(self._middleware_callbacks)  # noqa: SLF001
        booted = app.bootstrap()
        if self._schedule_callbacks:
            from avalon.console.scheduling import schedule

            for callback in self._schedule_callbacks:
                callback(schedule)
        return booted
