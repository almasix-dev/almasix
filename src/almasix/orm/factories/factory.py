"""Model factories — Laravel's `Illuminate\\Database\\Eloquent\\Factories`.

A factory describes one row's worth of plausible data in `definition()`, and
everything else — states, sequences, counts, relationships — layers on top of
that one method. Because Almasix's ORM is async, `make()` and `create()` are
coroutines; the rest of the builder is the Laravel API, spelled in snake_case.
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable, Iterable, Mapping
from collections.abc import Sequence as SequenceABC
from typing import Any, ClassVar

from almasix.orm.collection import Collection
from almasix.orm.factories.fake import Fake
from almasix.orm.factories.relationships import (
    BelongsToManyRelationship,
    BelongsToRelationship,
    Relationship,
    merge_recycled,
)
from almasix.orm.factories.sequence import CrossJoinSequence, Sequence
from almasix.orm.model import Model, RelationDescriptor
from almasix.support.str import Str

#: A state: a dict, or a callable given the attributes so far.
State = Mapping[str, Any] | Callable[..., Any]


class FactoryError(RuntimeError):
    """A factory could not be resolved, or does not know its model."""


async def _resolve(value: Any) -> Any:
    """Await what needs awaiting — states and hooks may be async."""
    return await value if inspect.isawaitable(value) else value


def _arity(callback: Callable[..., Any]) -> int:
    """How many positional arguments a callback will take."""
    target = callback if inspect.isfunction(callback) or inspect.ismethod(callback) else None
    if target is None:
        target = getattr(callback, "__call__", callback)  # noqa: B004 - callables and objects
    try:
        parameters = inspect.signature(target).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins without signatures
        return 1
    positional = [
        parameter
        for parameter in parameters.values()
        if parameter.kind
        in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD, parameter.VAR_POSITIONAL)
    ]
    if any(parameter.kind == parameter.VAR_POSITIONAL for parameter in positional):
        return 2
    return len(positional)


async def _call(callback: Callable[..., Any], *arguments: Any) -> Any:
    """Call a hook with as many arguments as it actually declared."""
    wanted = min(_arity(callback), len(arguments))
    return await _resolve(callback(*arguments[:wanted]))


class Factory:
    """The base every model factory extends.

    class UserFactory(Factory):
        model = User

        def definition(self):
            return {"name": self.fake.name(), "email": self.fake.unique().safe_email()}

    await User.factory().count(3).create()
    """

    #: The model this factory builds; guessed from the class name when unset.
    model: ClassVar[type[Model] | None] = None

    #: Where `Model.factory()` looks for `<Model>Factory`.
    namespace: ClassVar[str] = "database.factories"

    _model_name_resolver: ClassVar[Callable[[type[Factory]], type[Model]] | None] = None
    _factory_name_resolver: ClassVar[Callable[[type[Model]], type[Factory] | None] | None] = None

    def __init__(self) -> None:
        self._count: int | None = None
        self._states: list[State] = []
        self._has: list[Relationship | BelongsToManyRelationship] = []
        self._for: list[BelongsToRelationship] = []
        self._after_making: list[Callable[..., Any]] = []
        self._after_creating: list[Callable[..., Any]] = []
        self._connection: str | None = None
        self._recycle: dict[type[Model], list[Model]] = {}
        self.fake = Fake.resolve()

    # --- the one method a factory must write --------------------------------

    def definition(self) -> Mapping[str, Any]:
        """One row's worth of attributes. Override this."""
        raise NotImplementedError(f"{type(self).__name__} must define definition()")

    def configure(self) -> Factory:
        """Hook for registering `after_making` / `after_creating` up front."""
        return self

    @property
    def faker(self) -> Fake:
        """Laravel spells it `$this->faker`; both names reach one generator."""
        return self.fake

    # --- construction -------------------------------------------------------

    @classmethod
    def new(cls, attributes: Mapping[str, Any] | None = None) -> Factory:
        return cls().configure().state(attributes or {})

    @classmethod
    def times(cls, count: int) -> Factory:
        return cls.new().count(count)

    def new_instance(self, **overrides: Any) -> Factory:
        """A copy with one thing changed — a factory is immutable, like Laravel's."""
        clone = object.__new__(type(self))
        clone.__dict__.update(self.__dict__)
        for key, value in overrides.items():
            setattr(clone, f"_{key}", value)
        return clone

    # --- the builder --------------------------------------------------------

    def count(self, count: int | None) -> Factory:
        return self.new_instance(count=count)

    def connection(self, connection: str | None) -> Factory:
        return self.new_instance(connection=connection)

    def state(self, state: State) -> Factory:
        return self.new_instance(states=[*self._states, state])

    def set(self, key: str, value: Any) -> Factory:
        return self.state({key: value})

    def sequence(self, *sequence: Any) -> Factory:
        return self.state(Sequence(*sequence))

    def for_each_sequence(self, *sequence: Any) -> Factory:
        """One row per step — the sequence sets the count."""
        return self.state(Sequence(*sequence)).count(len(sequence))

    def cross_join_sequence(self, *sequence: list[Mapping[str, Any]]) -> Factory:
        return self.state(CrossJoinSequence(*sequence))

    def trashed(self, deleted_at: Any = None) -> Factory:
        """Rows that arrive already soft deleted."""
        model = self.model_name()
        column = getattr(model, "deleted_at", "deleted_at")
        stamp = deleted_at if deleted_at is not None else model()._fresh_timestamp()
        return self.state({column: stamp})

    def after_making(self, callback: Callable[..., Any]) -> Factory:
        return self.new_instance(after_making=[*self._after_making, callback])

    def after_creating(self, callback: Callable[..., Any]) -> Factory:
        return self.new_instance(after_creating=[*self._after_creating, callback])

    def recycle(
        self, models: Iterable[Model] | Model | Mapping[type[Model], list[Model]]
    ) -> Factory:
        """Reuse these models instead of creating fresh parents."""
        if isinstance(models, Mapping):
            merged = {**self._recycle}
            for key, value in models.items():
                merged.setdefault(key, []).extend(value)
        else:
            merged = merge_recycled(self._recycle, models)
        return self.new_instance(recycle=merged)

    def get_random_recycled_model(self, model: type[Model]) -> Model | None:
        pool = self._recycle.get(model)
        return self.fake.random_element(pool) if pool else None

    # --- relationships ------------------------------------------------------

    def has(self, factory: Factory, relationship: str | None = None) -> Factory:
        name = relationship or self._guess_has_relationship(factory.model_name())
        return self.new_instance(has=[*self._has, Relationship(factory, name)])

    def has_attached(
        self,
        factory: Factory | Model | Collection[Any] | list[Model],
        pivot: Mapping[str, Any] | Callable[[Model], Mapping[str, Any]] | None = None,
        relationship: str | None = None,
    ) -> Factory:
        related = factory.model_name() if isinstance(factory, Factory) else _class_of(factory)
        name = relationship or self._guess_has_relationship(related)
        attached = BelongsToManyRelationship(factory, pivot, name)
        return self.new_instance(has=[*self._has, attached])

    def for_(self, factory: Factory | Model, relationship: str | None = None) -> Factory:
        related = factory.model_name() if isinstance(factory, Factory) else type(factory)
        name = relationship or Str.snake(related.__name__)
        return self.new_instance(**{"for": [*self._for, BelongsToRelationship(factory, name)]})

    def _guess_has_relationship(self, related: type[Model]) -> str:
        """`Post` → `posts` when the model has it, else `post`."""
        plural = Str.snake(Str.plural(related.__name__))
        if _has_relation(self.model_name(), plural):
            return plural
        return Str.snake(Str.singular(related.__name__))

    def __getattr__(self, name: str) -> Any:
        """`has_posts(3)` / `for_author({"name": "Ada"})`, Laravel's magic methods."""
        if name.startswith("__") or not name.startswith(("has_", "for_")):
            raise AttributeError(f"{type(self).__name__} has no attribute {name!r}")
        relationship = name[4:]
        model = self.model_name()
        if not _has_relation(model, relationship):
            raise AttributeError(f"{model.__name__} has no relation {relationship!r}")
        related = model().get_relation(relationship).related

        def magic(*parameters: Any) -> Factory:
            first = parameters[0] if parameters else None
            factory = related.factory()
            if name.startswith("for_"):
                return self.for_(factory.state(first or {}), relationship)
            count = first if isinstance(first, int) and not isinstance(first, bool) else 1
            state = (
                first
                if isinstance(first, Mapping)
                else (parameters[1] if len(parameters) > 1 else {})
            )
            return self.has(factory.count(count).state(state), relationship)

        return magic

    # --- attributes ---------------------------------------------------------

    async def raw(
        self,
        attributes: Mapping[str, Any] | None = None,
        parent: Model | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """The attributes this factory would write, without touching a model."""
        factory = self.state(attributes) if attributes else self
        if factory._count is None:
            return await factory._expanded_attributes(parent)
        return [await factory._expanded_attributes(parent) for _ in range(factory._count)]

    async def _raw_attributes(self, parent: Model | None) -> dict[str, Any]:
        attributes = dict(await _resolve(self.definition()))
        states: list[State] = list(self._states)
        if self._for:
            states.insert(0, self._parent_resolvers)
        for state in states:
            if isinstance(state, Mapping):
                attributes.update(state)
                continue
            attributes.update(await _call(state, attributes, parent))
        return attributes

    async def _parent_resolvers(self, attributes: Mapping[str, Any]) -> dict[str, Any]:
        del attributes
        child = self.new_model()
        resolved: dict[str, Any] = {}
        for parent in self._for:
            resolved.update(await parent.recycle(self._recycle).attributes_for(child))
        return resolved

    async def _expanded_attributes(self, parent: Model | None) -> dict[str, Any]:
        definition = await self._raw_attributes(parent)
        for key, value in list(definition.items()):
            attribute = value
            if callable(attribute) and not isinstance(attribute, type):
                attribute = await _call(attribute, definition, parent)
            if isinstance(attribute, Factory):
                recycled = self.get_random_recycled_model(attribute.model_name())
                if recycled is not None:
                    attribute = recycled.get_key()
                else:
                    attribute = (await attribute.recycle(self._recycle).create()).get_key()
            elif isinstance(attribute, Model):
                attribute = attribute.get_key()
            definition[key] = attribute
        return definition

    # --- making and creating ------------------------------------------------

    def new_model(self, attributes: Mapping[str, Any] | None = None) -> Model:
        """A model instance filled past the guard — factories are trusted input."""
        model = self.model_name()
        instance = model()
        if attributes:
            instance.force_fill(dict(attributes))
        if self._connection is not None:
            instance.set_connection(self._connection)
        return instance

    async def make(
        self,
        attributes: Mapping[str, Any] | None = None,
        parent: Model | None = None,
    ) -> Any:
        if attributes:
            return await self.state(attributes).make(parent=parent)
        if self._count is None:
            instance = self.new_model(await self._expanded_attributes(parent))
            await self._call_after_making([instance])
            return instance
        model = self.model_name()
        if self._count < 1:
            return model.new_collection([])
        instances = [
            self.new_model(await self._expanded_attributes(parent)) for _ in range(self._count)
        ]
        await self._call_after_making(instances)
        return model.new_collection(instances)

    async def make_one(self, attributes: Mapping[str, Any] | None = None) -> Model:
        return await self.count(None).make(attributes)

    async def make_many(
        self, records: int | Iterable[Mapping[str, Any]] | None = None
    ) -> Collection[Any]:
        return await self._many(records, "make")

    async def create(
        self,
        attributes: Mapping[str, Any] | None = None,
        parent: Model | None = None,
    ) -> Any:
        if attributes:
            return await self.state(attributes).create(parent=parent)
        results = await self.make(parent=parent)
        models = [results] if isinstance(results, Model) else list(results)
        await self._store(models)
        await self._call_after_creating(models, parent)
        return results

    async def create_one(self, attributes: Mapping[str, Any] | None = None) -> Model:
        return await self.count(None).create(attributes)

    async def create_many(
        self,
        records: int | Iterable[Mapping[str, Any]] | None = None,
    ) -> Collection[Any]:
        return await self._many(records, "create")

    async def create_quietly(
        self,
        attributes: Mapping[str, Any] | None = None,
        parent: Model | None = None,
    ) -> Any:
        with self.model_name().without_events():
            return await self.create(attributes, parent)

    async def create_one_quietly(self, attributes: Mapping[str, Any] | None = None) -> Model:
        with self.model_name().without_events():
            return await self.create_one(attributes)

    async def create_many_quietly(
        self,
        records: int | Iterable[Mapping[str, Any]] | None = None,
    ) -> Collection[Any]:
        with self.model_name().without_events():
            return await self.create_many(records)

    def lazy(
        self,
        attributes: Mapping[str, Any] | None = None,
        parent: Model | None = None,
    ) -> Callable[[], Any]:
        """A callable that creates when it is finally called — Laravel's `lazy`."""
        return lambda: self.create(attributes, parent)

    async def _many(
        self,
        records: int | Iterable[Mapping[str, Any]] | None,
        method: str,
    ) -> Collection[Any]:
        """One row per record — the count names the records, it does not multiply them."""
        if records is None:
            records = self._count or 1
        if isinstance(records, int):
            records = [{} for _ in range(records)]
        build = getattr(self.count(None), method)
        return self.model_name().new_collection(
            [await build(dict(record)) for record in records],
        )

    async def _store(self, models: SequenceABC[Model]) -> None:
        for model in models:
            if self._connection is not None:
                model.set_connection(self._connection)
            await model.save()
            for name, value in list(model.get_relations().items()):
                if isinstance(value, Collection) and value.is_empty():
                    model.unset_relation(name)
            for child in self._has:
                await child.recycle(self._recycle).create_for(model)

    async def _call_after_making(self, models: SequenceABC[Model]) -> None:
        for model in models:
            for callback in self._after_making:
                await _call(callback, model)

    async def _call_after_creating(self, models: SequenceABC[Model], parent: Model | None) -> None:
        for model in models:
            for callback in self._after_creating:
                await _call(callback, model, parent)

    # --- resolution ---------------------------------------------------------

    @classmethod
    def model_name(cls) -> type[Model]:
        """The model this factory builds — declared, or guessed from the name."""
        if cls.model is not None:
            return cls.model
        if cls._model_name_resolver is not None:
            return cls._model_name_resolver(cls)
        guess = cls.__name__.removesuffix("Factory")
        found = _find_model(guess)
        if found is None:
            raise FactoryError(
                f"{cls.__name__} cannot find a model named {guess!r}; "
                "set `model = <Model>` on the factory"
            )
        return found

    @classmethod
    def factory_for_model(cls, model: type[Model]) -> Factory:
        """Laravel's `Factory::factoryForModel` — `<Model>Factory`, then import."""
        if cls._factory_name_resolver is not None:
            resolved = cls._factory_name_resolver(model)
            if resolved is not None:
                return resolved.new()
        found = _find_factory(model)
        if found is None:
            module = f"{cls.namespace}.{Str.snake(model.__name__)}_factory"
            try:
                importlib.import_module(module)
            except ModuleNotFoundError as exc:
                raise FactoryError(
                    f"No factory for {model.__name__}: define {model.__name__}Factory "
                    f"in {module}, or override `new_factory()` on the model"
                ) from exc
            found = _find_factory(model)
        if found is None:
            raise FactoryError(f"No factory for {model.__name__} in {cls.namespace}")
        return found.new()

    @classmethod
    def guess_model_names_using(
        cls,
        resolver: Callable[[type[Factory]], type[Model]] | None,
    ) -> None:
        Factory._model_name_resolver = resolver

    @classmethod
    def guess_factory_names_using(
        cls,
        resolver: Callable[[type[Model]], type[Factory] | None] | None,
    ) -> None:
        Factory._factory_name_resolver = resolver

    @classmethod
    def use_namespace(cls, namespace: str) -> None:
        Factory.namespace = namespace

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} of {self.model} x{self._count or 1}>"


class HasFactory:
    """Gives a model `Model.factory()` — Laravel's `HasFactory` trait."""

    @classmethod
    def factory(cls, *parameters: Any) -> Factory:
        factory = cls.new_factory() or Factory.factory_for_model(cls)  # type: ignore[arg-type]
        first = parameters[0] if parameters else None
        count = first if isinstance(first, int) and not isinstance(first, bool) else None
        state: Mapping[str, Any] = {}
        if isinstance(first, Mapping):
            state = first
        elif len(parameters) > 1 and isinstance(parameters[1], Mapping):
            state = parameters[1]
        return factory.count(count).state(state)

    @classmethod
    def new_factory(cls) -> Factory | None:
        """Override to name the factory explicitly instead of by convention."""
        return None


def _class_of(value: Any) -> type[Model]:
    if isinstance(value, Model):
        return type(value)
    for item in value:
        if isinstance(item, Model):  # pragma: no branch - collections hold models
            return type(item)
    raise FactoryError("has_attached() was given nothing it could attach")


def _has_relation(model: type[Model], name: str) -> bool:
    declared = getattr(model, name, None)
    if isinstance(declared, RelationDescriptor):
        return True
    return name in model._dynamic_relations


def _subclasses(cls: type) -> Iterable[type]:
    for subclass in cls.__subclasses__():
        yield subclass
        yield from _subclasses(subclass)


def _find_model(name: str) -> type[Model] | None:
    for subclass in _subclasses(Model):
        if subclass.__name__ == name:
            return subclass
    return None


def _find_factory(model: type[Model]) -> type[Factory] | None:
    named = f"{model.__name__}Factory"
    fallback: type[Factory] | None = None
    for subclass in _subclasses(Factory):
        if subclass.model is model:
            return subclass
        if subclass.__name__ == named:
            fallback = subclass
    return fallback
