"""Document store commands — ``documents:index`` and ``documents:show``.

A document store has no migrations: a collection appears when you write to it.
What it does have is indexes, and those are worth declaring on the model and
creating deliberately, which is what these two commands are for.
"""

from __future__ import annotations

import asyncio
import importlib
import pkgutil
from pathlib import Path
from typing import Any

from almasix.console.command import Command


class DocumentModelFinder:
    """Finds `Document` subclasses under `app.models`, the way `model:prune` does."""

    def __init__(self, command: Command) -> None:
        self.command = command

    def find(self, wanted: list[str]) -> list[Any]:
        from almasix.orm.documents import Document

        found: dict[str, Any] = {}
        for module in self._modules():
            for name in dir(module):
                candidate = getattr(module, name)
                if not isinstance(candidate, type) or not issubclass(candidate, Document):
                    continue
                if candidate is Document:
                    continue
                found[candidate.__name__] = candidate

        if not wanted:
            return sorted(found.values(), key=lambda model: model.__name__)

        selected = []
        for name in wanted:
            model = found.get(name.rsplit(".", 1)[-1])
            if model is None:
                self.command.warn(f"Document [{name}] was not found.")
                continue
            selected.append(model)
        return selected

    def _modules(self) -> list[Any]:
        modules: list[Any] = []
        try:
            package = importlib.import_module("app.models")
        except ModuleNotFoundError:
            return modules

        modules.append(package)
        path = getattr(package, "__path__", None)
        if not path:
            return modules
        for info in pkgutil.iter_modules([str(Path(entry)) for entry in path]):
            try:
                modules.append(importlib.import_module(f"app.models.{info.name}"))
            except Exception as exc:
                self.command.warn(f"Could not import app.models.{info.name}: {exc}")
        return modules


class DocumentsIndexCommand(Command):
    """Create the indexes every `Document` model declares.

    class Article(Document):
        indexes = ({"keys": [("slug", 1)], "unique": True},)
    """

    signature = (
        "documents:index "
        "{--model=* : Class names of the documents to index (default: all of them)} "
        "{--pretend : Show the indexes that would be created}"
    )
    description = "Create the indexes declared on document models"

    def handle(self) -> int:
        models = DocumentModelFinder(self).find(
            [str(name) for name in (self.option("model") or [])]
        )
        if not models:
            self.info("No document models found.")
            return self.SUCCESS

        pretend = bool(self.option("pretend"))
        total = 0
        for model in models:
            if not model.indexes:
                continue
            for index in model.indexes:
                keys = ", ".join(
                    f"{field} {'asc' if int(direction) > 0 else 'desc'}"
                    for field, direction in index["keys"]
                )
                unique = " (unique)" if index.get("unique") else ""
                self.line(f"{model.__name__} [{model.get_table()}]: {keys}{unique}")
                total += 1
            if pretend:
                continue
            try:
                asyncio.run(model.sync_indexes())
            except Exception as exc:
                self.error(f"{model.__name__}: {exc}")
                return self.FAILURE

        if total == 0:
            self.info("No document model declares any indexes.")
            return self.SUCCESS
        verb = "would be created" if pretend else "created"
        self.success(f"{total} index(es) {verb}.")
        return self.SUCCESS


class DocumentsShowCommand(Command):
    """Show what a document store holds — collections, counts, indexes."""

    signature = (
        "documents:show "
        "{--database= : The document connection to inspect (default: the configured default)} "
        "{--collection= : Show one collection only}"
    )
    description = "Show the collections in a document store"

    def handle(self) -> int:
        given = self.option("database")
        if given is True:
            self.error(
                "Invalid value for '--database': provide a connection name, e.g. --database=mongodb."
            )
            return self.INVALID
        connection = str(given or "").strip() or None

        try:
            return asyncio.run(self.show(connection))
        except Exception as exc:
            self.error(str(exc))
            return self.FAILURE

    @staticmethod
    def only_document_connection(manager: Any) -> str:
        """Which store to show when nobody said.

        The application default when it holds documents, the single document
        connection when there is exactly one, and otherwise a refusal that
        lists the names — guessing between two stores helps nobody.
        """
        if manager.is_document():
            return manager.default
        names = manager.document_connection_names()
        if len(names) == 1:
            return names[0]
        if not names:
            raise RuntimeError("No document store is configured in config/database.py.")
        raise RuntimeError(
            f"Several document stores are configured ({', '.join(names)}) — "
            "name one with --database."
        )

    async def show(self, connection: str | None) -> int:
        from almasix.orm.documents import Query
        from almasix.orm.facade import get_manager

        manager = get_manager()
        store = manager.store(connection or self.only_document_connection(manager))
        wanted = self.option("collection")
        names = [str(wanted)] if wanted and wanted is not True else await store.collections()

        self.line(f"{store.driver} [{store.name}]")
        if not names:
            self.info("No collections yet — a document store creates them on first write.")
            return self.SUCCESS

        for name in sorted(names):
            documents = await store.count(Query(collection=name))
            self.line(f"  {name}: {documents} document(s)")
            for index in await store.indexes(name):
                keys = ", ".join(
                    f"{field} {'asc' if int(direction) > 0 else 'desc'}"
                    for field, direction in index.get("keys", [])
                )
                unique = " (unique)" if index.get("unique") else ""
                self.line(f"    index {index.get('name')}: {keys}{unique}")
        return self.SUCCESS
