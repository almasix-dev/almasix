"""``model:show`` — one Articulate model, as it is declared and as it is stored.

Laravel's ``model:show`` merges what a model class says about itself with what
its table actually holds. So does this, and it holds the same line the other
introspection commands do: a fact Almasix cannot check is left out rather than
guessed. A model whose database is unreachable still shows its declared shape,
with the column details named as the part that needs a connection.

It lives beside ``model:prune`` rather than in ``introspection`` because every
question it answers is an ORM question — relation kinds, casts, model events —
and none of them are about the application's environment or its routes.
"""

from __future__ import annotations

import asyncio
import importlib
from typing import Any

from almasix.console.command import Command
from almasix.console.display import to_json
from almasix.console.repl import discover_app_classes
from almasix.orm.model import EVENTS, Model, RelationDescriptor
from almasix.orm.relations import MorphTo
from almasix.orm.schema import Schema

_SCOPE_PREFIX = "scope_"
_ACCESSOR_PREFIX = "get_"
_ACCESSOR_SUFFIX = "_attribute"

#: Attribute facts worth a word of their own in the rendered table.
_FLAGS = ("primary", "increments", "fillable", "hidden", "appended", "accessor")


class ModelShowCommand(Command):
    """Laravel's ``model:show`` — everything one model knows about itself.

    Relations are built against an empty instance, which names their type and
    their related model without querying anything.

    Laravel also names the model's policy. Almasix does not, because finding
    one means importing and instantiating a class guessed from the model's
    name, and building objects is more than an introspection command should
    do on the way to describing one.
    """

    signature = (
        "model:show {model : The model class — Post, or app.models.post.Post} "
        "{--database= : The connection to read column details from} "
        "{--json : Output as JSON}"
    )
    description = "Show a model's table, attributes, relationships, and events"

    def handle(self) -> int:
        given = self.option("database")
        if given is True:
            self.error(
                "Invalid value for '--database': provide a connection name, e.g. --database=sqlite."
            )
            return self.INVALID

        model = self._resolve(str(self.argument("model") or ""))
        if model is None:
            return self.FAILURE

        connection = str(given or "").strip() or model.connection
        columns, schema_error = self._columns(model, connection)
        report = self._report(model, connection, columns, schema_error)

        if self.option("json"):
            self.line(to_json(report))
            return self.SUCCESS
        self._render(report)
        return self.SUCCESS

    # --- resolution -----------------------------------------------------

    def _resolve(self, name: str) -> type[Model] | None:
        """The model named on the command line, or ``None`` after an error."""
        found = self._locate(name)
        if found is None:
            self.error(f"Model [{name}] was not found.")
            known = sorted(self._app_models())
            if known:
                self.line(f"Known models: {', '.join(known)}.")
            else:
                self.line(
                    "Name a class under app.models, or a dotted path like app.models.post.Post."
                )
            return None
        if not (isinstance(found, type) and issubclass(found, Model)):
            self.error(f"[{name}] is not an Almasix model.")
            return None
        return found

    def _locate(self, name: str) -> Any:
        """A dotted path imports; a bare name comes from the models package."""
        if "." in name:
            module_name, _, attribute = name.rpartition(".")
            try:
                return getattr(importlib.import_module(module_name), attribute, None)
            except ImportError:
                return None
        return self._app_models().get(name)

    def _app_models(self) -> dict[str, type[Model]]:
        """The application's models, found the way Loupe finds them."""
        return {
            name: found
            for name, found in discover_app_classes().items()
            if isinstance(found, type) and issubclass(found, Model)
        }

    # --- the report -----------------------------------------------------

    def _columns(
        self, model: type[Model], connection: str | None
    ) -> tuple[list[dict[str, Any]], str]:
        """Reflected columns, plus the reason there are none."""
        table = model.get_table()
        try:
            columns = asyncio.run(Schema.columns(table, connection=connection))
        except Exception as exc:
            return [], f"Column details need a database connection: {exc}"
        if not columns:
            return [], f"Table [{table}] does not exist yet, so it has no columns to show."
        return columns, ""

    def _report(
        self,
        model: type[Model],
        connection: str | None,
        columns: list[dict[str, Any]],
        schema_error: str,
    ) -> dict[str, Any]:
        return {
            "class": _dotted(model),
            "table": model.get_table(),
            "connection": connection or self.app.config.get("database.default"),
            "primary_key": model.primary_key,
            "key_type": model.key_type,
            "incrementing": model.incrementing,
            "timestamps": [model.created_at, model.updated_at] if model.timestamps else None,
            "soft_deletes": getattr(model, "deleted_at", None)
            if getattr(model, "_soft_deletes", False)
            else None,
            "attributes": self._attributes(model, columns),
            "relations": self._relations(model),
            "scopes": self._scopes(model),
            "observers": self._observers(model),
            "schema_error": schema_error or None,
        }

    def _attributes(
        self, model: type[Model], columns: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Stored columns first, then the attributes only the class declares."""
        casts = model.class_casts()
        accessors = _accessors(model)
        stored = {column["name"]: column for column in columns}
        names = [*stored, *sorted(_declared_names(model, casts, accessors) - set(stored))]
        return [
            {
                "name": name,
                "type": stored[name]["type"] if name in stored else None,
                "cast": _cast_name(casts[name]) if name in casts else None,
                "nullable": stored[name]["nullable"] if name in stored else None,
                "default": stored[name]["default"] if name in stored else None,
                "primary": name == model.primary_key,
                "increments": name == model.primary_key and model.incrementing,
                "fillable": model.is_fillable(name),
                "hidden": name in model.hidden,
                "appended": name in model.appends,
                "accessor": name in accessors,
            }
            for name in names
        ]

    def _relations(self, model: type[Model]) -> list[dict[str, Any]]:
        declared = {
            name
            for name in dir(model)
            if isinstance(getattr(model, name, None), RelationDescriptor)
        }
        probe = model()
        names = sorted(declared | set(model._dynamic_relations))
        return [self._relation(probe, name) for name in names]

    def _relation(self, probe: Model, name: str) -> dict[str, Any]:
        """One relation, built on an empty model so nothing is queried."""
        try:
            relation = probe.get_relation(name)
            kind = type(relation).__name__
            # A morph_to points wherever the row says; there is no one model.
            related = None if isinstance(relation, MorphTo) else _dotted(relation.related)
        except Exception:
            return {"name": name, "type": None, "related": None}
        return {"name": name, "type": kind, "related": related}

    def _scopes(self, model: type[Model]) -> dict[str, list[str]]:
        return {
            "global": sorted(model.get_global_scopes()),
            "local": sorted(
                name[len(_SCOPE_PREFIX) :]
                for name in dir(model)
                if name.startswith(_SCOPE_PREFIX) and callable(getattr(model, name, None))
            ),
        }

    def _observers(self, model: type[Model]) -> list[dict[str, str]]:
        """Registered listeners, in the order the model fires their events."""
        return [
            {"event": event, "listener": _callable_name(listener)}
            for event in EVENTS
            for listener in model._events.get(event, [])
        ]

    # --- rendering ------------------------------------------------------

    def _render(self, report: dict[str, Any]) -> None:
        timestamps = report["timestamps"]
        self._pairs(
            [
                ("Class", report["class"]),
                ("Table", report["table"]),
                ("Connection", report["connection"] or "(none configured)"),
                ("Primary Key", report["primary_key"]),
                ("Key Type", report["key_type"]),
                ("Incrementing", _yes(report["incrementing"])),
                ("Timestamps", " / ".join(timestamps) if timestamps else "off"),
                ("Soft Deletes", report["soft_deletes"] or "off"),
            ]
        )
        if report["schema_error"]:
            self.new_line()
            self.warn(report["schema_error"])

        self._section("Attributes")
        self.table(
            ("Attribute", "Type", "Cast", "Nullable", "Default", "Flags"),
            [
                (
                    row["name"],
                    row["type"] or "",
                    row["cast"] or "",
                    _yes(row["nullable"]),
                    "" if row["default"] is None else str(row["default"]),
                    ", ".join(flag for flag in _FLAGS if row[flag]),
                )
                for row in report["attributes"]
            ],
        )

        self._section("Relations")
        if report["relations"]:
            self.table(
                ("Relation", "Type", "Related"),
                [
                    (row["name"], row["type"] or "", row["related"] or "")
                    for row in report["relations"]
                ],
            )
        else:
            self.line("  (none)")

        self._section("Scopes")
        scopes = report["scopes"]
        if scopes["global"] or scopes["local"]:
            self.table(
                ("Scope", "Kind"),
                [
                    *((name, "global") for name in scopes["global"]),
                    *((name, "local") for name in scopes["local"]),
                ],
            )
        else:
            self.line("  (none)")

        self._section("Observers")
        if report["observers"]:
            self.table(
                ("Event", "Listener"),
                [(row["event"], row["listener"]) for row in report["observers"]],
            )
        else:
            self.line("  (none)")

    def _pairs(self, rows: list[tuple[str, Any]]) -> None:
        width = max(len(label) for label, _ in rows)
        for label, value in rows:
            self.line(f"  {label:<{width}}  {value}")

    def _section(self, title: str) -> None:
        self.new_line()
        self.comment(title)


def _declared_names(model: type[Model], casts: dict[str, Any], accessors: set[str]) -> set[str]:
    """Every attribute the class names, whether or not the table has it yet."""
    names = {
        model.primary_key,
        *casts,
        *model.fillable,
        *model.hidden,
        *model.appends,
        *model.attributes,
        *accessors,
    }
    if model.timestamps:
        names.update({model.created_at, model.updated_at})
    if getattr(model, "_soft_deletes", False):
        names.add(model.deleted_at)
    # A model that keeps one timestamp only leaves the other one unnamed.
    names.discard("")
    names.discard(None)
    return names


def _accessors(model: type[Model]) -> set[str]:
    """Attributes the class computes: ``Attribute`` objects and get hooks.

    ``Model`` answers to ``get_raw_attribute`` itself, and that is its API
    rather than an accessor for a column named ``raw``, so the hooks a model
    inherits are not counted.
    """
    names = set(model._attribute_casters)
    for name in dir(model):
        if (
            name.startswith(_ACCESSOR_PREFIX)
            and name.endswith(_ACCESSOR_SUFFIX)
            and not hasattr(Model, name)
        ):
            names.add(name[len(_ACCESSOR_PREFIX) : -len(_ACCESSOR_SUFFIX)])
    return names


def _cast_name(cast: Any) -> str:
    """A cast as it reads in the table: ``datetime``, ``Status``, ``MoneyCast``."""
    if isinstance(cast, str):
        return cast
    if isinstance(cast, type):
        return cast.__name__
    return type(cast).__name__


def _callable_name(listener: Any) -> str:
    """``UserObserver.created`` for a bound method, else ``module.function``."""
    owner = getattr(listener, "__self__", None)
    if owner is not None:
        return f"{type(owner).__name__}.{listener.__name__}"
    return _dotted(listener)


def _dotted(target: Any) -> str:
    name = getattr(target, "__qualname__", None) or getattr(target, "__name__", None)
    if name is None:
        return str(target)
    module = getattr(target, "__module__", "")
    return f"{module}.{name}" if module else name


def _yes(value: bool | None) -> str:
    """``yes`` / ``no``, or nothing at all when the answer is unknown."""
    if value is None:
        return ""
    return "yes" if value else "no"
