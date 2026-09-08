"""Eager loading — the cure for N+1, shipped with the relations."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import sqlalchemy as sa

from almasix.orm.builder import QueryBuilder, _split_alias
from almasix.orm.collection import Collection
from almasix.orm.relations import MorphTo, Relation


def _normalize(relations: Any) -> dict[str, Callable[[QueryBuilder], Any] | None]:
    """Accept `("a", "b.c")`, `{"a": callback}`, or a mix."""
    normalized: dict[str, Callable[[QueryBuilder], Any] | None] = {}
    if isinstance(relations, Mapping):
        for name, callback in relations.items():
            normalized[str(name)] = callback
        return normalized
    for item in relations:
        if isinstance(item, Mapping):
            normalized.update({str(k): v for k, v in item.items()})
        else:
            normalized.setdefault(str(item), None)
    return normalized


def _split(
    relations: dict[str, Callable[[QueryBuilder], Any] | None],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    top: dict[str, Any] = {}
    nested: dict[str, dict[str, Any]] = {}
    for name, callback in relations.items():
        head, _, tail = name.partition(".")
        if tail:
            top.setdefault(head, None)
            nested.setdefault(head, {})[tail] = callback
        else:
            # An explicit callback wins over a bare mention from a nested path.
            if callback is not None or head not in top:
                top[head] = callback
    return top, nested


def _children(models: Sequence[Any], name: str) -> list[Any]:
    collected: list[Any] = []
    for model in models:
        value = model.get_relations().get(name)
        if value is None:
            continue
        if isinstance(value, Collection):
            collected.extend(value)
        else:
            collected.append(value)
    return collected


async def eager_load(models: Sequence[Any], relations: Any) -> None:
    """Load `relations` onto `models` with one query per relation level."""
    if not models:
        return

    normalized = _normalize(relations)
    if not normalized:
        return
    top, nested = _split(normalized)

    for name, callback in top.items():
        relation = models[0].get_relation(name)

        if isinstance(relation, MorphTo):
            await relation.eager_load_into(models, name)
        else:
            builder = relation.eager_query(models)
            if callback is not None:
                callback(builder)
            results = await builder.get()
            relation.match(models, results, name)

        if name in nested:
            children = _children(models, name)
            if children:  # pragma: no branch
                await eager_load(children, nested[name])


_AGGREGATES: dict[str, Any] = {
    "count": lambda column: sa.func.count(),
    "sum": sa.func.sum,
    "avg": sa.func.avg,
    "min": sa.func.min,
    "max": sa.func.max,
    "exists": lambda column: sa.func.count(),
}


async def eager_load_counts(models: Sequence[Any], relation_name: str, alias: str) -> None:
    """Attach `{relation}_count` without hydrating the related rows."""
    await eager_load_aggregate(models, relation_name, alias, "count")


async def eager_load_aggregate(
    models: Sequence[Any],
    relation_name: str,
    alias: str,
    function: str,
    column: str | None = None,
    callback: Callable[[QueryBuilder], Any] | None = None,
) -> None:
    """Attach an aggregate over a relation without hydrating the related rows."""
    if not models:
        return
    if function not in _AGGREGATES:
        raise ValueError(f"Unsupported aggregate: {function!r}")
    if column is None and function not in ("count", "exists"):
        raise ValueError(f"Aggregate {function!r} needs a column")

    relation: Relation = models[0].get_relation(relation_name)
    grouping = relation.grouping_column()
    parent_key = relation.parent_match_key()

    builder = relation.eager_query(models)
    builder._selects = []
    builder._eager = {}
    builder._eager_counts = []
    if callback is not None:
        callback(builder)
    group = builder.column(grouping)
    target = builder.column(column) if column is not None else None
    builder.select(group.label("__group"), _AGGREGATES[function](target).label("__value"))
    builder.group_by(group)

    rows = await builder.get_raw()
    values = {row["__group"]: row["__value"] for row in rows}

    for model in models:
        value = values.get(model.get_raw_attribute(parent_key))
        model._extra[alias] = _finalize(function, value)


def _finalize(function: str, value: Any) -> Any:
    """Empty relations count zero and exist not at all; other aggregates are null."""
    if function == "count":
        return int(value or 0)
    if function == "exists":
        return bool(value)
    return value


def aggregate_alias(relation: str, function: str, column: str | None) -> str:
    """`posts_count`, `posts_exists`, `posts_sum_votes` — Laravel's naming."""
    base = relation.replace(".", "_")
    if function in ("count", "exists"):
        return f"{base}_{function}"
    return f"{base}_{function}_{str(column).replace('.', '_')}"


async def load_aggregates(
    models: Sequence[Any],
    relations: Any,
    function: str,
    column: str | None = None,
    constrained: Mapping[str, Any] | None = None,
) -> None:
    """Deferred aggregate loading — the `load_count` / `load_sum` family."""
    specs: list[tuple[str, Callable[[QueryBuilder], Any] | None]] = []
    for relation in relations:
        if isinstance(relation, Mapping):
            specs.extend((str(name), callback) for name, callback in relation.items())
        else:
            specs.append((str(relation), None))
    specs.extend((name, callback) for name, callback in (constrained or {}).items())

    for name, callback in specs:
        relation_name, _, alias = _split_alias(name)
        await eager_load_aggregate(
            models,
            relation_name,
            alias or aggregate_alias(relation_name, function, column),
            function,
            column,
            callback,
        )


def _morph_groups(models: Sequence[Any], relation_name: str) -> dict[type[Any], list[Any]]:
    """Bucket the loaded `morph_to` targets by their concrete class."""
    groups: dict[type[Any], list[Any]] = {}
    for model in models:
        target = model.get_relations().get(relation_name)
        if target is not None:
            groups.setdefault(type(target), []).append(target)
    return groups


def _morph_spec(spec: Mapping[Any, Any], group: type[Any]) -> Any:
    """The relations asked for a given morph target class."""
    for key, relations in spec.items():
        if key is group or (isinstance(key, str) and key == group.__name__):
            return relations
    return None


async def load_morph(
    models: Sequence[Any],
    relation_name: str,
    spec: Mapping[Any, Any],
) -> None:
    """Eager load per-type relations behind a `morph_to` — ``loadMorph``.

    A `morph_to` points at different classes on different rows, so one relation
    list cannot fit them all; the spec maps each target class to its own.
    """
    if not models:
        return
    await eager_load(models, [relation_name])
    for group, targets in _morph_groups(models, relation_name).items():
        relations = _morph_spec(spec, group)
        if relations:
            await eager_load(targets, relations)


async def load_morph_aggregate(
    models: Sequence[Any],
    relation_name: str,
    spec: Mapping[Any, Any],
    function: str = "count",
    column: str | None = None,
) -> None:
    """Aggregate per-type relations behind a `morph_to` — ``loadMorphCount``."""
    if not models:
        return
    await eager_load(models, [relation_name])
    for group, targets in _morph_groups(models, relation_name).items():
        relations = _morph_spec(spec, group)
        if relations:
            await load_aggregates(targets, relations, function, column)
