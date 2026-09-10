"""Component registry and embed helpers."""

from __future__ import annotations

import importlib
import re
from typing import Any

from almasix.conduit.component import Component

_NAME_RE = re.compile(r"^[a-zA-Z][\w.-]*$")


class ComponentRegistry:
    """Maps dotted names (``counter``, ``forms.profile``) to Component classes."""

    def __init__(self) -> None:
        self._map: dict[str, type[Component]] = {}
        self._namespaces: list[str] = ["app.conduit"]

    def add_namespace(self, namespace: str) -> None:
        if namespace not in self._namespaces:
            self._namespaces.insert(0, namespace)

    def register(self, name: str, cls: type[Component]) -> None:
        if not issubclass(cls, Component):
            raise TypeError(f"{cls!r} is not a Conduit Component")
        self._map[name] = cls

    def resolve(self, name: str) -> type[Component]:
        if name in self._map:
            return self._map[name]
        dotted = name.replace("-", "_").replace("/", ".")
        if not _NAME_RE.match(name.replace(".", "a").replace("-", "a")):
            raise KeyError(f"Invalid Conduit component name {name!r}")
        parts = [p for p in dotted.split(".") if p]
        class_name = _studly(parts[-1])
        module_tail = ".".join(parts)
        for ns in self._namespaces:
            module_name = f"{ns}.{module_tail}"
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                continue
            candidate = getattr(module, class_name, None)
            if isinstance(candidate, type) and issubclass(candidate, Component):
                self._map[name] = candidate
                return candidate
        raise KeyError(f"Conduit component [{name}] not found")

    def make(self, name: str, **params: Any) -> Component:
        cls = self.resolve(name)
        instance = cls(**{k: v for k, v in params.items() if k in cls._public_property_names()})
        instance.conduit_name = name
        return instance


def _studly(value: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[-_\s]+", value) if part)


class Conduit:
    """Façade for registry + initial HTML embed."""

    _registry: ComponentRegistry | None = None

    @classmethod
    def registry(cls) -> ComponentRegistry:
        if cls._registry is None:
            cls._registry = ComponentRegistry()
        return cls._registry

    @classmethod
    def register(cls, name: str, component: type[Component]) -> None:
        cls.registry().register(name, component)

    @classmethod
    def component(cls, name: str, **params: Any) -> Component:
        return cls.registry().make(name, **params)

    @classmethod
    def mount(cls, name: str, **params: Any) -> str:
        from almasix.conduit.mechanism import embed_component

        return embed_component(cls.component(name, **params))


def conduit(name: str, **params: Any) -> str:
    """Embed a Conduit component by name (controllers / views)."""
    return Conduit.mount(name, **params)
