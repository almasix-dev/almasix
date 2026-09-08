"""Active Record model — Eloquent parity."""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timezone
from typing import Any, ClassVar

from avalon.orm.attributes import Attribute
from avalon.orm.builder import ModelNotFoundError, QueryBuilder
from avalon.orm.casts import (
    CastsAttributes,
    cast_format,
    cast_value,
    prepare_for_storage,
    resolve_cast,
    serialize_value,
)
from avalon.orm.collection import Collection
from avalon.orm.ids import fill_unique_ids
from avalon.orm.inflector import foreign_key, snake, table_name

EVENTS = (
    "retrieved",
    "creating",
    "created",
    "updating",
    "updated",
    "saving",
    "saved",
    "deleting",
    "deleted",
    "restoring",
    "restored",
    "replicating",
)

# Set by ``avalon.orm.seeder.without_model_events`` / ``WithoutModelEvents``.
_EVENTS_DISABLED = False

# Strictness, configured once at boot (Laravel does this in a provider).
_STRICT_DISCARDING = False
_STRICT_MISSING = False

# Classes whose timestamps are suspended, plus a global unguard switch.
_TIMESTAMPS_OFF: ContextVar[frozenset[type]] = ContextVar("_TIMESTAMPS_OFF", default=frozenset())
_UNGUARDED = False

_UNSET = object()

_ACCESSOR_HOOK = re.compile(r"^(get|set)_.+_attribute$")


class MassAssignmentError(RuntimeError):
    """Raised when a guarded attribute is mass-assigned."""


class DiscardedAttributeError(RuntimeError):
    """Raised when a non-fillable attribute would be silently discarded."""


class MissingAttributeError(AttributeError):
    """Raised when reading an attribute the model never loaded."""


class RelationNotLoadedError(AttributeError):
    """Raised when reading a relation that was never loaded.

    By default, Avalon never lazy-loads on attribute access: a hidden query
    there is how N+1 storms happen. Opt in with ``Model.lazy_relations = True``
    to allow ``await model.rel`` (explicit await — still no silent IO).
    """


class ModelMeta(type):
    """Wires table names, event buckets, and global scopes per subclass."""

    def __new__(mcls, name: str, bases: tuple[type, ...], namespace: dict[str, Any]) -> type:
        cls = super().__new__(mcls, name, bases, namespace)
        if not bases:  # the Model base itself
            return cls

        if namespace.get("table") is None and "table" not in namespace:
            cls.table = None  # resolved lazily by get_table()

        # Each subclass owns its listeners and scopes; never share the parent's.
        cls._events = {event: [] for event in EVENTS}
        cls._global_scopes = {}
        cls._attribute_casters = {}

        for base in reversed(bases):
            inherited_casters = getattr(base, "_attribute_casters", None)
            if inherited_casters:
                cls._attribute_casters.update(inherited_casters)
        for key, value in namespace.items():
            if isinstance(value, Attribute):
                cls._attribute_casters[key] = value

        for base in reversed(bases):
            inherited_scopes = getattr(base, "_global_scopes", None)
            if inherited_scopes:
                cls._global_scopes.update(inherited_scopes)
            inherited_events = getattr(base, "_events", None)
            if inherited_events:
                for event, listeners in inherited_events.items():
                    cls._events.setdefault(event, []).extend(listeners)

        booter = namespace.get("boot")
        if callable(booter):
            booter(cls)
        for base in bases:
            base_boot = getattr(base, f"boot_{snake(base.__name__)}", None)
            if callable(base_boot):
                base_boot(cls)
        return cls


class Model(metaclass=ModelMeta):
    """Eloquent-shaped Active Record base."""

    table: ClassVar[str | None] = None
    primary_key: ClassVar[str] = "id"
    incrementing: ClassVar[bool] = True
    key_type: ClassVar[str] = "int"
    connection: ClassVar[str | None] = None
    timestamps: ClassVar[bool] = True
    created_at: ClassVar[str] = "created_at"
    updated_at: ClassVar[str] = "updated_at"
    per_page: ClassVar[int] = 15

    fillable: ClassVar[tuple[str, ...]] = ()
    guarded: ClassVar[tuple[str, ...]] = ("*",)
    hidden: ClassVar[tuple[str, ...]] = ()
    visible: ClassVar[tuple[str, ...]] = ()
    appends: ClassVar[tuple[str, ...]] = ()
    # A dict, or a classmethod returning one (Laravel's `casts()`).
    casts: ClassVar[Any] = {}
    # strftime format for serialized dates; None means ISO-8601.
    date_format: ClassVar[str | None] = None
    attributes: ClassVar[dict[str, Any]] = {}
    with_: ClassVar[tuple[str, ...]] = ()
    # Override to return a custom collection from multi-row reads.
    collection_class: ClassVar[type[Collection[Any]]] = Collection
    # When True, `await model.rel` lazy-loads that relation. Attribute use
    # without await still raises — async cannot hide IO in `__getattr__`.
    lazy_relations: ClassVar[bool] = False

    _events: ClassVar[dict[str, list[Callable[..., Any]]]] = {}
    _global_scopes: ClassVar[dict[str, Callable[[QueryBuilder], Any]]] = {}

    def __init__(self, attributes: Mapping[str, Any] | None = None, **kwargs: Any) -> None:
        self._attributes: dict[str, Any] = {}
        self._original: dict[str, Any] = {}
        self._relations: dict[str, Any] = {}
        self._exists = False
        self._extra: dict[str, Any] = {}
        # None means "use the class attribute" — overrides stay per instance.
        self._hidden: tuple[str, ...] | None = None
        self._visible: tuple[str, ...] | None = None
        self._appends: tuple[str, ...] | None = None
        self._cast_overrides: dict[str, Any] = {}
        self._attribute_cache: dict[str, Any] = {}
        # Muted for the duration of one quiet write; never process-wide.
        self._muted = False

        defaults = dict(type(self).attributes)
        if defaults:
            self._attributes.update(defaults)

        payload = {**(attributes or {}), **kwargs}
        if payload:
            self.fill(payload)

    # --- naming -------------------------------------------------------------

    @classmethod
    def get_table(cls) -> str:
        return cls.table or table_name(cls.__name__)

    @classmethod
    def get_foreign_key(cls) -> str:
        return foreign_key(cls.__name__, cls.primary_key)

    def get_key(self) -> Any:
        return self._attributes.get(type(self).primary_key)

    def set_key(self, value: Any) -> None:
        self._attributes[type(self).primary_key] = value

    def is_(self, other: Any) -> bool:
        return (
            isinstance(other, Model)
            and type(self) is type(other)
            and self.get_key() == other.get_key()
        )

    def is_not(self, other: Any) -> bool:
        return not self.is_(other)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Model):
            return self.is_(other)
        return NotImplemented

    def __hash__(self) -> int:
        return hash((type(self).__name__, self.get_key()))

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {type(self).primary_key}={self.get_key()!r}>"

    # --- query entrypoints --------------------------------------------------

    @classmethod
    def query(cls) -> QueryBuilder:
        builder = QueryBuilder(model=cls, connection=cls.connection)
        if cls.with_:
            builder.with_(*cls.with_)
        return builder

    @classmethod
    def new_query(cls) -> QueryBuilder:
        """Query without the model's default eager loads."""
        return QueryBuilder(model=cls, connection=cls.connection)

    @classmethod
    def where(cls, *args: Any, **kwargs: Any) -> QueryBuilder:
        return cls.query().where(*args, **kwargs)

    @classmethod
    def where_in(cls, column: str, values: Iterable[Any]) -> QueryBuilder:
        return cls.query().where_in(column, values)

    @classmethod
    def with_relations(cls, *relations: str, **constrained: Any) -> QueryBuilder:
        return cls.query().with_(*relations, **constrained)

    @classmethod
    async def all(cls) -> Collection[Any]:
        return await cls.query().get()

    @classmethod
    async def find(cls, key: Any) -> Any:
        return await cls.query().find(key)

    @classmethod
    async def find_or_fail(cls, key: Any) -> Any:
        return await cls.query().find_or_fail(key)

    @classmethod
    async def first(cls) -> Any:
        return await cls.query().first()

    @classmethod
    async def count(cls) -> int:
        return await cls.query().count()

    @classmethod
    async def paginate(cls, per_page: int | None = None, page: int = 1) -> Any:
        return await cls.query().paginate(per_page, page)

    @classmethod
    async def create(cls, attributes: Mapping[str, Any] | None = None, **kwargs: Any) -> Any:
        instance = cls()
        instance.fill({**(attributes or {}), **kwargs})
        await instance.save()
        return instance

    @classmethod
    async def force_create(cls, attributes: Mapping[str, Any]) -> Any:
        instance = cls()
        instance.force_fill(attributes)
        await instance.save()
        return instance

    @classmethod
    async def destroy(cls, *keys: Any) -> int:
        flat: list[Any] = []
        for key in keys:
            flat.extend(key if isinstance(key, (list, tuple, set)) else [key])
        deleted = 0
        for key in flat:
            found = await cls.find(key)
            if found is not None and await found.delete():
                deleted += 1
        return deleted

    # --- attributes ---------------------------------------------------------

    def fill(self, attributes: Mapping[str, Any]) -> Model:
        if _UNGUARDED:
            return self.force_fill(attributes)
        if self._totally_guarded() and attributes:
            offending = ", ".join(sorted(attributes))
            raise MassAssignmentError(
                f"Add [{offending}] to fillable to allow mass assignment on "
                f"{type(self).__name__}."
            )
        discarded = []
        for key, value in attributes.items():
            if self.is_fillable(key):
                self.set_attribute(key, value)
            else:
                discarded.append(key)
        if discarded and _STRICT_DISCARDING:
            raise DiscardedAttributeError(
                f"Add [{', '.join(sorted(discarded))}] to fillable to allow mass "
                f"assignment on {type(self).__name__}."
            )
        return self

    def force_fill(self, attributes: Mapping[str, Any]) -> Model:
        for key, value in attributes.items():
            self.set_attribute(key, value)
        return self

    @classmethod
    def is_fillable(cls, key: str) -> bool:
        if _UNGUARDED:
            return True
        if key in cls.fillable:
            return True
        if cls.is_guarded(key):
            return False
        return not cls.fillable

    @classmethod
    def is_guarded(cls, key: str) -> bool:
        return tuple(cls.guarded) == ("*",) or key in cls.guarded

    @classmethod
    def _totally_guarded(cls) -> bool:
        return not cls.fillable and tuple(cls.guarded) == ("*",)

    # --- casting ------------------------------------------------------------

    # --- strictness and guarding -------------------------------------------

    @staticmethod
    def prevent_silently_discarding_attributes(value: bool = True) -> None:
        """Raise instead of dropping non-fillable attributes during `fill`."""
        global _STRICT_DISCARDING
        _STRICT_DISCARDING = value

    @staticmethod
    def prevent_accessing_missing_attributes(value: bool = True) -> None:
        """Raise when reading an attribute a persisted model never retrieved."""
        global _STRICT_MISSING
        _STRICT_MISSING = value

    @classmethod
    def should_be_strict(cls, value: bool = True) -> None:
        """Turn on every strictness check at once (Laravel's ``shouldBeStrict``).

        Lazy loading is already strict in Avalon — unloaded relation access
        raises by default — so this covers the other two checks.
        """
        cls.prevent_silently_discarding_attributes(value)
        cls.prevent_accessing_missing_attributes(value)

    @staticmethod
    def unguard() -> None:
        """Stop enforcing mass-assignment rules process-wide."""
        global _UNGUARDED
        _UNGUARDED = True

    @staticmethod
    def reguard() -> None:
        """Enforce mass-assignment rules again."""
        global _UNGUARDED
        _UNGUARDED = False

    @classmethod
    @contextmanager
    def unguarded(cls) -> Iterator[None]:
        """Run a block with mass assignment unguarded, then restore it."""
        global _UNGUARDED
        previous = _UNGUARDED
        _UNGUARDED = True
        try:
            yield
        finally:
            _UNGUARDED = previous

    @classmethod
    @contextmanager
    def without_timestamps(cls) -> Iterator[None]:
        """Run a block without touching this model's timestamps."""
        token = _TIMESTAMPS_OFF.set(_TIMESTAMPS_OFF.get() | {cls})
        try:
            yield
        finally:
            _TIMESTAMPS_OFF.reset(token)

    @classmethod
    @contextmanager
    def without_events(cls) -> Iterator[None]:
        """Run a block with model events muted (``Model::withoutEvents``)."""
        from avalon.orm import model as model_mod

        previous = model_mod._EVENTS_DISABLED
        model_mod._EVENTS_DISABLED = True
        try:
            yield
        finally:
            model_mod._EVENTS_DISABLED = previous

    @classmethod
    def new_collection(cls, items: Any = None) -> Collection[Any]:
        """Build the collection type this model returns (``newCollection``)."""
        return cls.collection_class(items)

    @classmethod
    def class_casts(cls) -> dict[str, Any]:
        """Declared casts, whether `casts` is a dict or a `casts()` method."""
        declared = cls.casts
        if callable(declared):
            declared = declared(cls) if _accepts_argument(declared) else declared()
        return dict(declared or {})

    def get_casts(self) -> dict[str, Any]:
        """Effective casts — declared casts plus any query-time overrides."""
        return {**type(self).class_casts(), **self._cast_overrides}

    def merge_casts(self, casts: Mapping[str, Any]) -> Model:
        """Add casts to this instance only (Laravel's ``mergeCasts``)."""
        self._cast_overrides.update(casts)
        return self

    def has_cast(self, key: str) -> bool:
        return key in self.get_casts()

    def _caster(self, key: str) -> Attribute | None:
        return type(self)._attribute_casters.get(key)

    # --- attribute access ---------------------------------------------------

    def set_attribute(self, key: str, value: Any) -> None:
        caster = self._caster(key)
        if caster is not None:
            for name, written in caster.set_value(self, key, value).items():
                self._write_attribute(name, written)
            return

        mutator = getattr(self, f"set_{key}_attribute", None)
        if callable(mutator):
            mutated = mutator(value)
            if mutated is not None:
                value = mutated
            else:
                return
        self._write_attribute(key, value)

    def _write_attribute(self, key: str, value: Any) -> None:
        """Store a value, applying whichever cast is declared for the key."""
        self._attribute_cache.pop(key, None)
        cast = self.get_casts().get(key)
        if cast is not None:
            resolved = resolve_cast(cast)
            if isinstance(resolved, CastsAttributes):
                result = resolved.set(self, key, value, self.get_attributes())
                if isinstance(result, Mapping):
                    self._attributes.update(result)
                    return
                self._attributes[key] = result
                return
            value = prepare_for_storage(value, resolved)
        self._attributes[key] = value

    def get_attribute(self, key: str, default: Any = _UNSET) -> Any:
        caster = self._caster(key)
        if key in self._attributes:
            value = self._cast_for_read(key, self._attributes[key])
            if caster is not None:
                return caster.get_value(self, key, value)
            accessor = getattr(self, f"get_{key}_attribute", None)
            if callable(accessor):
                return accessor(value)
            return value

        if caster is not None and caster.has_getter():
            return caster.get_value(self, key, None)

        # A class cast may compose other columns, so it has no column itself.
        cast = self.get_casts().get(key)
        if cast is not None:
            resolved = resolve_cast(cast)
            if isinstance(resolved, CastsAttributes):
                return resolved.get(self, key, None, self.get_attributes())

        accessor = getattr(self, f"get_{key}_attribute", None)
        if callable(accessor):
            return accessor(None) if _accepts_argument(accessor) else accessor()

        if key in self._relations:
            return self._relations[key]
        if key in self._extra:
            return self._extra[key]
        if default is not _UNSET:
            return default
        if _STRICT_MISSING and self._exists:
            raise MissingAttributeError(
                f"{type(self).__name__}.{key} was not retrieved — add it to the "
                f"select, or read it with get_attribute({key!r}, default)."
            )
        return None

    def _cast_for_read(self, key: str, value: Any) -> Any:
        cast = self.get_casts().get(key)
        if cast is None:
            return value
        resolved = resolve_cast(cast)
        if isinstance(resolved, CastsAttributes):
            return resolved.get(self, key, value, self.get_attributes())
        return cast_value(value, resolved)

    def get_raw_attribute(self, key: str, default: Any = None) -> Any:
        return self._attributes.get(key, default)

    def get_attributes(self) -> dict[str, Any]:
        return dict(self._attributes)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        attributes = self.__dict__.get("_attributes", {})
        relations = self.__dict__.get("_relations", {})
        extra = self.__dict__.get("_extra", {})

        if name in attributes or name in self.get_casts():
            return self.get_attribute(name)
        if name in relations:
            return relations[name]
        if name in extra:
            return extra[name]

        # Computed attributes (`get_display_name_attribute`) need no column.
        accessor = getattr(type(self), f"get_{name}_attribute", None)
        if callable(accessor):
            return self.get_attribute(name)

        # A declared relation that was never loaded must fail loudly.
        # Unreachable for class methods (normal lookup finds them before __getattr__);
        # retained for plain callables stashed only on the type without a descriptor.
        method = getattr(type(self), name, None)
        if callable(method) and getattr(method, "_is_relation", False):  # pragma: no cover
            hint = (
                f"Use .with_({name!r}) when querying, await model.load({name!r}), "
                f"or await model.{name}().get()."
            )
            if type(self).lazy_relations:
                hint = (
                    f"Await it with `await model.{name}`, eager-load with "
                    f".with_({name!r}), or query with await model.{name}().get()."
                )
            raise RelationNotLoadedError(
                f"Relation {name!r} is not loaded on {type(self).__name__}. {hint}"
            )
        # Strict mode turns "you never selected this column" into a real error,
        # but accessor-hook probes (`set_x_attribute`) must still miss quietly.
        if _STRICT_MISSING and self._exists and not _ACCESSOR_HOOK.match(name):
            raise MissingAttributeError(
                f"{type(self).__name__}.{name} was not retrieved — add it to the "
                f"select, or read it with get_attribute({name!r}, default)."
            )
        raise AttributeError(f"{type(self).__name__!r} has no attribute {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_") or name in type(self).__dict__ or hasattr(type(self), name):
            object.__setattr__(self, name, value)
            return
        self.set_attribute(name, value)

    def __getitem__(self, key: str) -> Any:
        return self.get_attribute(key)

    def __setitem__(self, key: str, value: Any) -> None:
        self.set_attribute(key, value)

    # --- dirty tracking -----------------------------------------------------

    def sync_original(self) -> Model:
        self._original = dict(self._attributes)
        return self

    def get_original(self, key: str | None = None, default: Any = None) -> Any:
        if key is None:
            return dict(self._original)
        return self._original.get(key, default)

    def get_dirty(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in self._attributes.items()
            if key not in self._original or self._original[key] != value
        }

    def is_dirty(self, *keys: str) -> bool:
        dirty = self.get_dirty()
        if not keys:
            return bool(dirty)
        return any(key in dirty for key in keys)

    def is_clean(self, *keys: str) -> bool:
        return not self.is_dirty(*keys)

    def get_changes(self) -> dict[str, Any]:
        return dict(self._changes) if hasattr(self, "_changes") else {}

    def was_changed(self, *keys: str) -> bool:
        changes = self.get_changes()
        if not keys:
            return bool(changes)
        return any(key in changes for key in keys)

    @property
    def exists(self) -> bool:
        return self._exists

    # --- hydration ----------------------------------------------------------

    @classmethod
    def _hydrate(cls, row: Mapping[str, Any], casts: Mapping[str, Any] | None = None) -> Model:
        instance = cls()
        if casts:
            instance._cast_overrides.update(casts)
        instance._attributes = dict(row)
        instance._exists = True
        instance.sync_original()
        cls._fire_sync("retrieved", instance)
        return instance

    def new_instance(self, attributes: Mapping[str, Any] | None = None, exists: bool = False):
        instance = type(self)()
        if attributes:
            instance.force_fill(attributes)
        instance._exists = exists
        if exists:
            instance.sync_original()
        return instance

    # --- persistence --------------------------------------------------------

    def _fresh_timestamp(self) -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)

    def _timestamps_enabled(self) -> bool:
        if not type(self).timestamps:
            return False
        suspended = _TIMESTAMPS_OFF.get()
        return not any(issubclass(type(self), owner) for owner in suspended)

    def _touch_timestamps(self, *, creating: bool) -> None:
        if not self._timestamps_enabled():
            return
        now = self._fresh_timestamp()
        cls = type(self)
        if creating and cls.created_at and cls.created_at not in self.get_dirty():
            self._attributes.setdefault(cls.created_at, now)
        if cls.updated_at:  # pragma: no branch
            self._attributes[cls.updated_at] = now

    async def save(self) -> bool:
        if await self._fire_event("saving") is False:
            return False

        if self._exists:
            saved = await self._perform_update()
        else:
            saved = await self._perform_insert()

        if saved:
            await self._fire_event("saved")
        return saved

    async def _quietly(self, operation: Callable[[], Any]) -> Any:
        """Run one write with this instance's events muted."""
        previous = self._muted
        self._muted = True
        try:
            return await operation()
        finally:
            self._muted = previous

    async def save_quietly(self) -> bool:
        """Save without firing model events (``saveQuietly``)."""
        return await self._quietly(self.save)

    async def delete_quietly(self) -> bool:
        """Delete without firing model events (``deleteQuietly``)."""
        return await self._quietly(self.delete)

    async def force_delete_quietly(self) -> bool:
        """Force delete without firing model events (``forceDeleteQuietly``)."""
        return await self._quietly(self.force_delete)

    async def _perform_insert(self) -> bool:
        if await self._fire_event("creating") is False:
            return False
        fill_unique_ids(self)
        self._touch_timestamps(creating=True)

        cls = type(self)
        payload = dict(self._attributes)
        if cls.incrementing and payload.get(cls.primary_key) is None:  # pragma: no branch
            payload.pop(cls.primary_key, None)

        builder = cls.new_query()
        key = await builder.insert_get_id(payload)
        if cls.incrementing and key is not None:  # pragma: no branch
            self._attributes[cls.primary_key] = key

        self._exists = True
        self._changes = dict(self._attributes)
        self.sync_original()
        await self._fire_event("created")
        return True

    async def _perform_update(self) -> bool:
        dirty = self.get_dirty()
        if not dirty:
            return True
        if await self._fire_event("updating") is False:
            return False

        self._touch_timestamps(creating=False)
        dirty = self.get_dirty()
        cls = type(self)
        await cls.new_query().where(cls.primary_key, "=", self.get_key()).update(dirty)

        self._changes = dict(dirty)
        self.sync_original()
        await self._fire_event("updated")
        return True

    async def update(self, attributes: Mapping[str, Any] | None = None, **kwargs: Any) -> bool:
        if not self._exists:
            return False
        self.fill({**(attributes or {}), **kwargs})
        return await self.save()

    async def delete(self) -> bool:
        cls = type(self)
        if self.get_key() is None:
            return False
        if await self._fire_event("deleting") is False:
            return False

        if getattr(self, "_soft_deletes", False):
            deleted = await self._perform_soft_delete()
        else:
            await cls.new_query().where(cls.primary_key, "=", self.get_key()).delete()
            self._exists = False
            deleted = True

        if deleted:  # pragma: no branch
            await self._fire_event("deleted")
        return deleted

    async def force_delete(self) -> bool:
        cls = type(self)
        await cls.new_query().where(cls.primary_key, "=", self.get_key()).delete()
        self._exists = False
        await self._fire_event("deleted")
        return True

    async def refresh(self) -> Model:
        cls = type(self)
        fresh = await cls.new_query().without_global_scopes().where_key(self.get_key()).first()
        if fresh is not None:
            self._attributes = dict(fresh._attributes)
            self._relations.clear()
            self.sync_original()
        return self

    async def fresh(self) -> Any:
        cls = type(self)
        return await cls.new_query().without_global_scopes().where_key(self.get_key()).first()

    def replicate(self, exclude: Iterable[str] | None = None) -> Model:
        cls = type(self)
        skip = {cls.primary_key, cls.created_at, cls.updated_at, *(exclude or [])}
        clone = cls()
        clone.force_fill({k: v for k, v in self._attributes.items() if k not in skip})
        cls._fire_sync("replicating", clone)
        return clone

    async def touch(self) -> bool:
        if not self._timestamps_enabled():
            return False
        self._touch_timestamps(creating=False)
        return await self.save()

    # --- relations ----------------------------------------------------------

    def get_relation(self, name: str) -> Any:
        """Build the relation object itself, ignoring any loaded value."""
        declared = getattr(type(self), name, None)
        if isinstance(declared, RelationDescriptor):
            return declared.build(self)
        if declared is None:
            raise AttributeError(f"{type(self).__name__} has no relation {name!r}")
        if callable(declared):
            return declared(self)
        raise AttributeError(f"{name!r} on {type(self).__name__} is not a relation")

    def relation_loaded(self, name: str) -> bool:
        return name in self._relations

    def set_relation(self, name: str, value: Any) -> Model:
        self._relations[name] = value
        return self

    def unset_relation(self, name: str) -> Model:
        self._relations.pop(name, None)
        return self

    def get_relations(self) -> dict[str, Any]:
        return dict(self._relations)

    async def load(self, *relations: str) -> Model:
        from avalon.orm.eager import eager_load

        await eager_load([self], relations)
        return self

    async def load_missing(self, *relations: str) -> Model:
        pending = [name for name in relations if not self.relation_loaded(name.split(".")[0])]
        if pending:
            await self.load(*pending)
        return self

    def has_one(self, related: type[Model], foreign: str | None = None, local: str | None = None):
        from avalon.orm.relations import HasOne

        return HasOne(self, related, foreign or type(self).get_foreign_key(),
                      local or type(self).primary_key)

    def has_many(self, related: type[Model], foreign: str | None = None, local: str | None = None):
        from avalon.orm.relations import HasMany

        return HasMany(self, related, foreign or type(self).get_foreign_key(),
                       local or type(self).primary_key)

    def belongs_to(
        self,
        related: type[Model],
        foreign: str | None = None,
        owner: str | None = None,
    ):
        from avalon.orm.relations import BelongsTo

        return BelongsTo(self, related, foreign or related.get_foreign_key(),
                         owner or related.primary_key)

    def belongs_to_many(
        self,
        related: type[Model],
        table: str | None = None,
        foreign_pivot_key: str | None = None,
        related_pivot_key: str | None = None,
    ):
        from avalon.orm.relations import BelongsToMany

        return BelongsToMany(self, related, table, foreign_pivot_key, related_pivot_key)

    def has_many_through(
        self,
        related: type[Model],
        through: type[Model],
        first_key: str | None = None,
        second_key: str | None = None,
    ):
        from avalon.orm.relations import HasManyThrough

        return HasManyThrough(self, related, through, first_key, second_key)

    def has_one_through(
        self,
        related: type[Model],
        through: type[Model],
        first_key: str | None = None,
        second_key: str | None = None,
    ):
        from avalon.orm.relations import HasOneThrough

        return HasOneThrough(self, related, through, first_key, second_key)

    def morph_one(self, related: type[Model], name: str):
        from avalon.orm.relations import MorphOne

        return MorphOne(self, related, name)

    def morph_many(self, related: type[Model], name: str):
        from avalon.orm.relations import MorphMany

        return MorphMany(self, related, name)

    def morph_to(self, name: str, types: Mapping[str, type[Model]]):
        from avalon.orm.relations import MorphTo

        return MorphTo(self, name, types)

    def morph_to_many(self, related: type[Model], name: str, table: str | None = None):
        from avalon.orm.relations import MorphToMany

        return MorphToMany(self, related, name, table)

    def morphed_by_many(self, related: type[Model], name: str, table: str | None = None):
        from avalon.orm.relations import MorphToMany

        return MorphToMany(self, related, name, table, inverse=True)

    # --- scopes -------------------------------------------------------------

    @classmethod
    def add_global_scope(cls, name: str, scope: Callable[[QueryBuilder], Any]) -> None:
        cls._global_scopes = {**cls._global_scopes, name: scope}

    @classmethod
    def get_global_scopes(cls) -> dict[str, Callable[[QueryBuilder], Any]]:
        return dict(cls._global_scopes)

    @classmethod
    def without_global_scope(cls, name: str) -> QueryBuilder:
        return cls.query().without_global_scope(name)

    @classmethod
    def without_global_scopes(cls) -> QueryBuilder:
        return cls.query().without_global_scopes()

    # --- events -------------------------------------------------------------

    @classmethod
    def listen(cls, event: str, callback: Callable[..., Any]) -> None:
        if event not in EVENTS:
            raise ValueError(f"Unknown model event: {event!r}")
        cls._events = {**cls._events, event: [*cls._events.get(event, []), callback]}

    @classmethod
    def observe(cls, observer: Any) -> None:
        instance = observer() if isinstance(observer, type) else observer
        for event in EVENTS:
            handler = getattr(instance, event, None)
            if callable(handler):
                cls.listen(event, handler)

    async def _fire_event(self, event: str) -> Any:
        from avalon.orm import model as model_mod

        if self._muted or getattr(model_mod, "_EVENTS_DISABLED", False):
            return True
        for listener in type(self)._events.get(event, []):
            outcome = listener(self)
            if inspect.isawaitable(outcome):
                outcome = await outcome
            if outcome is False:
                return False
        return True

    @classmethod
    def _fire_sync(cls, event: str, instance: Model) -> None:
        from avalon.orm import model as model_mod

        if getattr(model_mod, "_EVENTS_DISABLED", False):
            return
        for listener in cls._events.get(event, []):
            outcome = listener(instance)
            if inspect.isawaitable(outcome):  # pragma: no branch
                outcome.close()  # sync context: retrieved/replicating must be sync

    # --- serialization ------------------------------------------------------

    def get_hidden(self) -> tuple[str, ...]:
        """Effective hidden keys — instance override, else the class attribute."""
        return self._hidden if self._hidden is not None else tuple(type(self).hidden)

    def get_visible(self) -> tuple[str, ...]:
        """Effective visible allowlist — instance override, else the class."""
        return self._visible if self._visible is not None else tuple(type(self).visible)

    def get_appends(self) -> tuple[str, ...]:
        """Effective appended keys — instance override, else the class."""
        return self._appends if self._appends is not None else tuple(type(self).appends)

    def _is_arrayable(self, key: str, hidden: Sequence[str], visible: Sequence[str]) -> bool:
        """Laravel's visible / hidden rules, applied to attributes and relations."""
        if visible and key not in visible:
            return False
        return key not in hidden

    def serialize_date(self, value: date) -> str:
        """Format a date for `to_dict()` — override to change the default."""
        fmt = type(self).date_format
        return value.strftime(fmt) if fmt else value.isoformat()

    def _serialize(self, key: str, value: Any) -> Any:
        """Serialize one attribute — a cast format wins, else `serialize_date`."""
        cast = self.get_casts().get(key)
        if isinstance(value, (datetime, date)) and cast_format(cast) is None:
            return self.serialize_date(value)
        return serialize_value(value, cast)

    def attributes_to_dict(self) -> dict[str, Any]:
        hidden = self.get_hidden()
        visible = self.get_visible()
        data: dict[str, Any] = {}
        for key in self._attributes:
            if not self._is_arrayable(key, hidden, visible):
                continue
            data[key] = self._serialize(key, self.get_attribute(key))
        # Appended accessors respect visible / hidden too, as in Laravel.
        for key in self.get_appends():
            if not self._is_arrayable(key, hidden, visible):
                continue
            data[key] = self._serialize(key, self.get_attribute(key))
        for key, value in self._extra.items():
            if self._is_arrayable(key, hidden, visible):
                data[key] = self._serialize(key, value)
        return data

    def relations_to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        hidden = self.get_hidden()
        visible = self.get_visible()
        for name, value in self._relations.items():
            if not self._is_arrayable(name, hidden, visible):
                continue
            if isinstance(value, Collection):
                data[name] = value.to_dict()
            elif isinstance(value, Model):
                data[name] = value.to_dict()
            else:
                data[name] = serialize_value(value)
        return data

    def to_dict(self) -> dict[str, Any]:
        return {**self.attributes_to_dict(), **self.relations_to_dict()}

    def to_json(self, **options: Any) -> str:
        """JSON for this model — extra keyword arguments go to `json.dumps`."""
        import json

        return json.dumps(self.to_dict(), **options)

    def make_hidden(self, *keys: str) -> Model:
        """Hide extra attributes on **this** model only (Laravel ``makeHidden``)."""
        self._hidden = tuple({*self.get_hidden(), *keys})
        return self

    def make_visible(self, *keys: str) -> Model:
        """Reveal normally hidden attributes on this model (``makeVisible``)."""
        self._hidden = tuple(k for k in self.get_hidden() if k not in keys)
        if self._visible is not None or type(self).visible:
            self._visible = tuple({*self.get_visible(), *keys})
        return self

    def set_hidden(self, keys: Sequence[str]) -> Model:
        """Replace this model's hidden list outright (``setHidden``)."""
        self._hidden = tuple(keys)
        return self

    def set_visible(self, keys: Sequence[str]) -> Model:
        """Replace this model's visible allowlist outright (``setVisible``)."""
        self._visible = tuple(keys)
        return self

    def merge_hidden(self, keys: Sequence[str]) -> Model:
        """Merge more keys into this model's hidden list (``mergeHidden``)."""
        return self.make_hidden(*keys)

    def merge_visible(self, keys: Sequence[str]) -> Model:
        """Merge more keys into this model's visible allowlist (``mergeVisible``)."""
        self._visible = tuple({*self.get_visible(), *keys})
        return self

    def append(self, *keys: str) -> Model:
        """Append accessors to this model's serialized form (``append``)."""
        self._appends = tuple({*self.get_appends(), *keys})
        return self

    def merge_appends(self, keys: Sequence[str]) -> Model:
        """Merge a list of accessors into the appended keys (``mergeAppends``)."""
        return self.append(*keys)

    def set_appends(self, keys: Sequence[str]) -> Model:
        """Replace this model's appended keys outright (``setAppends``)."""
        self._appends = tuple(keys)
        return self

    def without_appends(self) -> Model:
        """Drop every appended key from this model (``withoutAppends``)."""
        self._appends = ()
        return self


def _accepts_argument(func: Callable[..., Any]) -> bool:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):  # pragma: no cover - builtins
        return False
    return bool(signature.parameters)


class PendingRelation:
    """What `user.posts` gives you when `posts` was never loaded.

    Calling it (`user.posts()`) returns the relation so you can keep querying.
    Using it as data raises — silently querying per row is the N+1 bug.

    When the model sets ``lazy_relations = True``, the pending relation is
    awaitable: ``posts = await user.posts`` loads then returns the value.
    """

    __slots__ = ("_func", "_instance", "_name")

    def __init__(self, instance: Any, func: Callable[..., Any], name: str) -> None:
        object.__setattr__(self, "_instance", instance)
        object.__setattr__(self, "_func", func)
        object.__setattr__(self, "_name", name)

    def __call__(self) -> Any:
        return self._func(self._instance)

    def __await__(self) -> Any:
        return self._lazy_load().__await__()

    async def _lazy_load(self) -> Any:
        instance = self._instance
        name = self._name
        cls = type(instance)
        if not cls.lazy_relations:
            raise RelationNotLoadedError(
                f"Relation {name!r} is not loaded on {cls.__name__}. "
                f"Set {cls.__name__}.lazy_relations = True to allow "
                f"`await model.{name}`, or use .with_({name!r}), "
                f"await model.load({name!r}), or await model.{name}().get()."
            )
        await instance.load(name)
        return instance._relations[name]

    def _fail(self) -> Any:
        name = self._name
        cls = type(self._instance)
        if cls.lazy_relations:
            raise RelationNotLoadedError(
                f"Relation {name!r} is not loaded on {cls.__name__}. "
                f"Await it first: `value = await model.{name}` "
                f"(lazy_relations is enabled). "
                f"Or eager-load with .with_({name!r})."
            )
        raise RelationNotLoadedError(
            f"Relation {name!r} is not loaded on {cls.__name__}. "
            f"Eager load it with .with_({name!r}), call await model.load({name!r}), "
            f"or query it directly with await model.{name}().get()."
        )

    def __iter__(self) -> Any:
        return self._fail()

    def __len__(self) -> int:
        return self._fail()

    def __bool__(self) -> bool:
        return self._fail()

    def __getitem__(self, key: Any) -> Any:
        return self._fail()

    def __getattr__(self, item: str) -> Any:
        return self._fail()

    def __repr__(self) -> str:
        lazy = " lazy" if type(self._instance).lazy_relations else ""
        return (
            f"<unloaded{lazy} relation {self._name!r} on "
            f"{type(self._instance).__name__}>"
        )


class RelationDescriptor:
    """Descriptor backing `@relation` methods."""

    _is_relation = True

    def __init__(self, func: Callable[..., Any]) -> None:
        self.func = func
        self.name = func.__name__
        self.__doc__ = func.__doc__

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        relations = obj.__dict__.get("_relations", {})
        if self.name in relations:
            return relations[self.name]
        return PendingRelation(obj, self.func, self.name)

    def __set__(self, obj: Any, value: Any) -> None:
        obj._relations[self.name] = value

    def build(self, obj: Any) -> Any:
        return self.func(obj)


def relation(method: Callable[..., Any]) -> RelationDescriptor:
    """Declare a relation: `model.rel()` queries it, `model.rel` reads loaded data.

    With ``Model.lazy_relations = True``, unloaded access is awaitable:
    ``await model.rel`` loads then returns the related value.
    """
    return RelationDescriptor(method)


__all__ = [
    "EVENTS",
    "MassAssignmentError",
    "Model",
    "ModelNotFoundError",
    "RelationNotLoadedError",
    "relation",
]
