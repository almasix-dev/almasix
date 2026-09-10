"""Conduit component base — Livewire 4-shaped public state + lifecycle."""

from __future__ import annotations

import inspect
from typing import Any, ClassVar

from almasix.validation import Validator, validator
from almasix.validation.form_request import ValidationException


class Component:
    """Reactive Conduit component (Livewire 4 parity target).

    Public properties are class attributes that are not callable and do not
    start with ``_``. Methods invoked via ``wire:click`` / ``$wire`` are public
    methods that are not lifecycle hooks.

    Keep using the ``wire:*`` attribute vocabulary for Livewire familiarity;
    the Python package is ``almasix.conduit``.
    """

    lazy: ClassVar[bool] = False
    defer: ClassVar[bool] = False
    query_string: ClassVar[list[str] | dict[str, str]] = []
    lazy_placeholder: ClassVar[str | None] = None
    #: Named island view map: ``{"stats": "conduit.counter"}`` or view names.
    island_views: ClassVar[dict[str, str]] = {}

    def __init__(self, **kwargs: Any) -> None:
        self.__conduit_id: str | None = None
        self.__conduit_name: str | None = None
        self.__errors: dict[str, list[str]] = {}
        self.__dispatches: list[dict[str, Any]] = []
        self.__skip_render = False
        self.__renderless = False
        self.__island: str | None = None
        self.__parent: Component | None = None
        self.__children: list[Component] = []
        for key, value in kwargs.items():
            if key in self._public_property_names():
                setattr(self, key, value)

    @property
    def conduit_id(self) -> str | None:
        return self.__conduit_id

    @conduit_id.setter
    def conduit_id(self, value: str | None) -> None:
        self.__conduit_id = value

    # Back-compat aliases used internally during the Flux → Conduit rename window.
    @property
    def flux_id(self) -> str | None:
        return self.conduit_id

    @flux_id.setter
    def flux_id(self, value: str | None) -> None:
        self.conduit_id = value

    @property
    def conduit_name(self) -> str | None:
        return self.__conduit_name

    @conduit_name.setter
    def conduit_name(self, value: str | None) -> None:
        self.__conduit_name = value

    @property
    def flux_name(self) -> str | None:
        return self.conduit_name

    @flux_name.setter
    def flux_name(self, value: str | None) -> None:
        self.conduit_name = value

    @property
    def errors(self) -> dict[str, list[str]]:
        return self.__errors

    def mount(self, **kwargs: Any) -> None:
        """Called once when the component is first created."""

    def hydrate(self) -> None:
        """Called after state is restored from a snapshot."""

    def dehydrate(self) -> None:
        """Called before state is snapshotted for the client."""

    def booted(self) -> None:
        """Called after hydrate / mount, before render."""

    def rendering(self) -> None:
        """Called immediately before ``render()``."""

    def rendered(self, html: str) -> str:
        """Hook after HTML is produced; return possibly modified HTML."""
        return html

    def render(self) -> str:
        """Return a Prism view name."""
        raise NotImplementedError(f"{type(self).__name__}.render() must return a view name")

    def render_island(self, name: str) -> str | None:
        """Return a Prism view for a named island, or ``None`` to fall back."""
        return self.island_views.get(name)

    @classmethod
    def _public_property_names(cls) -> set[str]:
        skip = {
            "lazy",
            "defer",
            "lazy_placeholder",
            "query_string",
            "island_views",
            "mount",
            "hydrate",
            "dehydrate",
            "booted",
            "rendering",
            "rendered",
            "render",
            "render_island",
            "get_public_properties",
            "set_property",
            "call",
            "dispatch",
            "dispatch_self",
            "dispatch_to",
            "validate",
            "add_error",
            "reset_error_bag",
            "skip_render",
            "get_error_bag",
            "sync_query_string",
            "apply_query_string",
            "js",
            "toggle",
        }
        names: set[str] = set()
        for klass in cls.__mro__:
            if klass is object or klass is Component:
                continue
            for key, value in vars(klass).items():
                if key.startswith("_") or key in skip:
                    continue
                if callable(value) and not isinstance(value, property):
                    continue
                if isinstance(value, (classmethod, staticmethod)):
                    continue
                names.add(key)
        return names

    def get_public_properties(self) -> dict[str, Any]:
        return {name: getattr(self, name, None) for name in sorted(self._public_property_names())}

    def set_property(self, name: str, value: Any) -> None:
        if name not in self._public_property_names():
            raise AttributeError(f"{type(self).__name__} has no public property {name!r}")
        from almasix.conduit.attributes import locked_property_names

        if name in locked_property_names(type(self)):
            raise AttributeError(
                f"Property {name!r} is locked and cannot be updated from the client"
            )
        setattr(self, name, value)

    def toggle(self, name: str) -> None:
        if name not in self._public_property_names():
            raise AttributeError(name)
        setattr(self, name, not bool(getattr(self, name, False)))

    def call(self, method: str, *params: Any) -> Any:
        if method.startswith("_") or method in {
            "mount",
            "hydrate",
            "dehydrate",
            "booted",
            "rendering",
            "rendered",
            "render",
            "render_island",
        }:
            raise AttributeError(f"Cannot call protected method {method!r}")
        # Livewire-style $toggle('prop')
        if method == "$toggle" and params:
            self.toggle(str(params[0]))
            return None
        fn = getattr(self, method, None)
        if not callable(fn):
            raise AttributeError(f"{type(self).__name__} has no method {method!r}")
        result = fn(*params)
        if inspect.iscoroutine(result):
            raise TypeError(
                f"{type(self).__name__}.{method} must be synchronous "
                "(use wire:click.async on the client for non-blocking UI)"
            )
        return result

    def dispatch(self, event: str, **params: Any) -> None:
        self.__dispatches.append({"event": event, "params": params, "to": None})

    def dispatch_self(self, event: str, **params: Any) -> None:
        self.__dispatches.append({"event": event, "params": params, "to": "self"})

    def dispatch_to(self, name: str, event: str, **params: Any) -> None:
        self.__dispatches.append({"event": event, "params": params, "to": name})

    def js(self, expression: str) -> None:
        """Queue a JS expression to run on the client after the response (Livewire ``$js``)."""
        self.__dispatches.append({"event": "__js", "params": {"expr": expression}, "to": "self"})

    def take_dispatches(self) -> list[dict[str, Any]]:
        items = list(self.__dispatches)
        self.__dispatches.clear()
        return items

    def validate(self, rules: Any | None = None, *, messages: dict | None = None) -> dict[str, Any]:
        data = self.get_public_properties()
        schema = rules if rules is not None else getattr(self, "rules", None)
        if schema is None:
            return data
        v: Validator = validator(data, schema, messages=messages)
        if v.fails():
            self.__errors = {k: list(errs) for k, errs in v.errors().items()}
            raise ValidationException(dict(self.__errors))
        self.__errors = {}
        return v.validated()

    def add_error(self, key: str, message: str) -> None:
        self.__errors.setdefault(key, []).append(message)

    def reset_error_bag(self, *keys: str) -> None:
        if not keys:
            self.__errors.clear()
            return
        for key in keys:
            self.__errors.pop(key, None)

    def get_error_bag(self) -> dict[str, list[str]]:
        return dict(self.__errors)

    def skip_render(self) -> None:
        self.__skip_render = True

    def renderless(self) -> None:
        """Skip HTML morph (Livewire ``.renderless`` / ``$this->skipRender()``)."""
        self.__skip_render = True
        self.__renderless = True

    def target_island(self, name: str) -> None:
        self.__island = name

    def take_island(self) -> str | None:
        name = self.__island
        self.__island = None
        return name

    def should_render(self) -> bool:
        return not self.__skip_render

    def reset_skip_render(self) -> None:
        self.__skip_render = False
        self.__renderless = False

    def query_string_map(self) -> dict[str, str]:
        qs = self.query_string
        if isinstance(qs, dict):
            return dict(qs)
        return {name: name for name in qs}

    def apply_query_string(self, query: dict[str, Any]) -> None:
        for prop, key in self.query_string_map().items():
            if key in query and prop in self._public_property_names():
                raw = query[key]
                current = getattr(self, prop, None)
                if isinstance(current, bool):
                    setattr(self, prop, str(raw).lower() in {"1", "true", "yes", "on"})
                elif isinstance(current, int) and not isinstance(current, bool):
                    try:
                        setattr(self, prop, int(raw))
                    except (TypeError, ValueError):
                        setattr(self, prop, raw)
                else:
                    setattr(self, prop, raw)

    def sync_query_string(self) -> dict[str, Any]:
        return {key: getattr(self, prop, None) for prop, key in self.query_string_map().items()}
