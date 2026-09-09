"""IoC service container with constructor autowiring."""

from __future__ import annotations

import inspect
import sys
from collections.abc import Callable
from typing import Any, TypeVar, get_type_hints

T = TypeVar("T")

Factory = Callable[["Container"], Any]


class ResolutionError(KeyError):
    """Raised when the container cannot resolve a dependency."""


class CircularDependencyError(ResolutionError):
    """Two classes each need the other built first.

    A subclass because it is not the same problem as an unbound name: a
    parameter's default can stand in for something nobody registered, but a
    cycle is a mistake in the wiring and has to be reported.
    """


class Container:
    """Laravel-style service container."""

    def __init__(self) -> None:
        self._bindings: dict[type | str, Factory] = {}
        self._instances: dict[type | str, Any] = {}
        self._aliases: dict[type | str, type | str] = {}
        self._build_stack: list[type | str] = []

    def bind(self, abstract: type | str, factory: Factory) -> None:
        self._bindings[abstract] = factory
        self._instances.pop(abstract, None)

    def singleton(self, abstract: type | str, factory: Factory) -> None:
        def wrapper(container: Container) -> Any:
            if abstract not in container._instances:
                container._instances[abstract] = factory(container)
            return container._instances[abstract]

        self.bind(abstract, wrapper)

    def instance(self, abstract: type | str, obj: Any) -> None:
        self._instances[abstract] = obj
        self._bindings[abstract] = lambda _c: obj

    def alias(self, abstract: type | str, alias: type | str) -> None:
        self._aliases[alias] = abstract

    def bound(self, abstract: type | str) -> bool:
        abstract = self._aliases.get(abstract, abstract)
        return abstract in self._bindings or abstract in self._instances

    def has(self, abstract: type | str) -> bool:
        return self.bound(abstract)

    def resolve(self, abstract: type[T] | str) -> T | Any:
        abstract = self._aliases.get(abstract, abstract)

        if abstract in self._instances and abstract not in self._bindings:
            return self._instances[abstract]

        if abstract in self._bindings:
            return self._bindings[abstract](self)

        if isinstance(abstract, type):
            return self._autowire(abstract)

        raise ResolutionError(f"Nothing bound for {abstract!r}")

    def make(self, abstract: type[T] | str) -> T | Any:
        """Alias of :meth:`resolve`."""
        return self.resolve(abstract)

    def _autowire(self, cls: type[T]) -> T:
        if cls in self._build_stack:
            cycle = " -> ".join(str(item) for item in [*self._build_stack, cls])
            raise CircularDependencyError(f"Circular dependency detected: {cycle}")

        self._build_stack.append(cls)
        try:
            module = sys.modules.get(cls.__module__)
            globalns = dict(getattr(module, "__dict__", {}))
            localns = {cls.__name__: cls, **globalns}
            try:
                hints = get_type_hints(cls.__init__, globalns=globalns, localns=localns)
            except Exception:
                hints = {}

            signature = inspect.signature(cls.__init__)
            kwargs: dict[str, Any] = {}
            for name, param in signature.parameters.items():
                if name == "self":
                    continue
                if param.kind in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ):
                    continue

                annotation = hints.get(name, param.annotation)
                if isinstance(annotation, str):
                    annotation = self._evaluate_string_annotation(annotation, globalns, localns)

                has_default = param.default is not inspect.Parameter.empty
                if annotation is not inspect.Parameter.empty and annotation is not Any:
                    try:
                        kwargs[name] = self.resolve(annotation)
                    except CircularDependencyError:
                        # A cycle is a mistake in the wiring, and a default
                        # cannot stand in for it — report it either way.
                        raise
                    except ResolutionError:
                        # A parameter that says what it wants *and* what to do
                        # without it is optional: `mode: str | None = None` on a
                        # middleware means "the container may fill this", not
                        # "refuse to build me unless str is bound".
                        if not has_default:
                            raise
                elif has_default:
                    continue
                else:
                    raise ResolutionError(
                        f"Cannot autowire {cls.__qualname__}: parameter {name!r} "
                        "has no type hint or default"
                    )

            return cls(**kwargs)
        finally:
            self._build_stack.pop()

    def _evaluate_string_annotation(
        self,
        annotation: str,
        globalns: dict[str, Any],
        localns: dict[str, Any],
    ) -> Any:
        try:
            return eval(annotation, globalns, localns)
        except Exception:
            return annotation
