"""Cache and warm-up commands — ``cache:*``, ``view:*``, and ``optimize``.

Laravel's ``optimize`` caches four things: config, routes, events, and views.
Almasix caches one of them, and the reason is the runtime rather than an
omission — see :class:`OptimizeCommand`.
"""

from __future__ import annotations

from almasix.console.command import Command

#: What Laravel caches that Almasix does not, and why. Printed by ``optimize``
#: so the difference is visible where a Laravel user would look for it.
NOT_CACHED = {
    "config": "read once per process, not once per request — 0.5ms, against a stale-cache footgun",
    "routes": "built once per process, at boot, for the same reason",
    "events": "listeners are registered once per process, at boot, for the same reason",
}


class CacheClearCommand(Command):
    signature = "cache:clear {--store= : The store to flush (default: the configured one)}"
    description = "Flush the application cache"

    def handle(self) -> int:
        from almasix.cache import Cache

        store = self.option("store")
        if not Cache.store(store or None).flush():
            self.error("The cache could not be flushed.")
            return self.FAILURE
        self.success(f"Application cache cleared: {store or 'default'} store.")
        return self.SUCCESS


class CacheForgetCommand(Command):
    signature = (
        "cache:forget {key : The cache key to forget} {--store= : The store to forget it from}"
    )
    description = "Remove one item from the cache"

    def handle(self) -> int:
        from almasix.cache import Cache

        key = str(self.argument("key"))
        if Cache.store(self.option("store") or None).forget(key):
            self.success(f"{key} forgotten.")
        else:
            self.warn(f"{key} was not in the cache.")
        return self.SUCCESS


class ViewCommand(Command):
    """Shared by `view:cache` and `view:clear`: finding the view engine."""

    def _engine(self):
        """The application's view engine, or `None` with a message printed.

        This asks whether one is *bound* rather than trying to build one: a
        bare `Engine` autowires into an object with no template paths, and
        `view:cache` would then report success on having compiled nothing.
        """
        from almasix.prism.engine import Engine

        if not self.app.bound(Engine):
            self.error("No view engine is configured: bootstrap the application first.")
            return None
        try:
            return self.app.make(Engine)
        except Exception as exc:
            self.error(f"No view engine is configured: {exc}")
            return None


class ViewCacheCommand(ViewCommand):
    signature = "view:cache"
    description = "Compile every Prism template"

    def handle(self) -> int:
        """Compile-check every template, which is what there is to precompile.

        Blade compiles to PHP files on disk and Laravel ships them with a
        deploy. Prism compiles to Python functions held by the engine, so
        there is no artifact to carry between processes — but compiling every
        template still answers the question a deploy asks, which is whether
        they all compile. A template that does not will say so here rather
        than on a request.
        """
        engine = self._engine()
        if engine is None:
            return self.FAILURE
        try:
            compiled = engine.cache_views()
        except Exception as exc:
            self.error(f"{type(exc).__name__}: {exc}")
            self.error("A template failed to compile. Nothing was cached.")
            return self.FAILURE
        self.success(f"{compiled} template(s) compiled.")
        self.comment(
            "Compiled views live in the process, so this warms this run and checks the rest."
        )
        return self.SUCCESS


class ViewClearCommand(ViewCommand):
    signature = "view:clear"
    description = "Drop the compiled Prism templates"

    def handle(self) -> int:
        engine = self._engine()
        if engine is None:
            return self.FAILURE
        engine.clear_cache()
        self.success("Compiled views cleared.")
        return self.SUCCESS


class OptimizeCommand(Command):
    signature = "optimize"
    description = "Cache what Almasix can cache, and say what it deliberately does not"

    def handle(self) -> int:
        """Laravel's ``optimize`` for the one target that means anything here.

        Caching config, routes, and listeners buys a PHP request the work of a
        boot it would otherwise repeat. An Almasix process boots once and serves
        for its lifetime, so the same caches would save half a millisecond and
        cost a class of bug where an edit does not take. They are named rather
        than shipped.
        """
        code = self.call("view:cache")
        self.new_line()
        self.comment("Not cached, by decision:")
        for target, reason in NOT_CACHED.items():
            self.line(f"  {target:<8} {reason}")
        return code


class OptimizeClearCommand(Command):
    signature = "optimize:clear"
    description = "Clear the application cache and the compiled templates"

    def handle(self) -> int:
        codes = [self.call("cache:clear"), self.call("view:clear")]
        return self.FAILURE if any(codes) else self.SUCCESS
