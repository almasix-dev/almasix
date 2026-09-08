"""The `Scout` façade."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from almasix.scout.engines.base import Engine
from almasix.scout.manager import EngineManager


class Scout:
    """Static access to the engine manager (Laravel's `Scout` / `EngineManager`)."""

    _manager: EngineManager | None = None

    @classmethod
    def set_manager(cls, manager: EngineManager | None) -> None:
        cls._manager = manager

    @classmethod
    def manager(cls) -> EngineManager:
        if cls._manager is None:
            from almasix.scout.helpers import get_engine_manager

            cls._manager = get_engine_manager()
        return cls._manager

    # --- engines ------------------------------------------------------------

    @classmethod
    def engine(cls, name: str | None = None) -> Engine:
        return cls.manager().engine(name)

    @classmethod
    def extend(cls, driver: str, resolver: Callable[..., Engine]) -> EngineManager:
        """Register a custom engine — the whole of Laravel's "Custom Engines"."""
        return cls.manager().extend(driver, resolver)

    @classmethod
    def forget_engine(cls, name: str | None = None) -> None:
        cls.manager().forget_engine(name)

    @classmethod
    def driver(cls) -> str:
        return cls.manager().get_default_driver()

    @classmethod
    def use(cls, name: str) -> None:
        """Search with a different engine from here on."""
        cls.manager().set_default_driver(name)

    # --- testing --------------------------------------------------------

    @classmethod
    def fake(cls, hits: Sequence[Any] | None = None) -> Any:
        """Swap the engine for one that records instead of indexing.

        Every configured driver name resolves to the same recorder, so a test
        need not know which engine the code under test asked for.
        """
        from almasix.scout.testing import FakeEngine

        manager = cls.manager()
        engine = FakeEngine(manager.get_default_driver(), hits=hits)
        manager.forget_engine()
        manager.set_engine(manager.get_default_driver(), engine)
        manager.extend(manager.get_default_driver(), lambda *_: engine)
        return engine
