"""Search commands — importing, flushing, and managing indexes.

The `database` and `collection` engines have nothing to import: they search
the table directly. These commands are for the engines that keep an index of
their own, and they say so rather than pretending to work.
"""

from __future__ import annotations

import asyncio
import importlib
import pkgutil
from pathlib import Path
from typing import Any

from almasix.console.command import Command


class SearchableModelFinder:
    """Finds `Searchable` models under `app.models`, the way `model:prune` does."""

    def __init__(self, command: Command) -> None:
        self.command = command

    def find(self, wanted: list[str]) -> list[Any]:
        found: dict[str, Any] = {}
        for module in self._modules():
            for name in dir(module):
                candidate = getattr(module, name)
                if not isinstance(candidate, type) or not self._searchable(candidate):
                    continue
                found[candidate.__name__] = candidate

        if not wanted:
            return sorted(found.values(), key=lambda model: model.__name__)

        selected = []
        for name in wanted:
            model = found.get(name.replace("\\", ".").rsplit(".", 1)[-1]) or self._import(name)
            if model is None:
                self.command.warn(f"Model [{name}] was not found, or is not searchable.")
                continue
            selected.append(model)
        return selected

    @staticmethod
    def _searchable(candidate: type) -> bool:
        from almasix.scout import Searchable

        return issubclass(candidate, Searchable) and candidate is not Searchable

    def _import(self, name: str) -> Any:
        """Accept a dotted path — `app.models.post.Post` — as well as a name."""
        module, _, attribute = name.replace("\\", ".").rpartition(".")
        if not module:
            return None
        try:
            candidate = getattr(importlib.import_module(module), attribute, None)
        except ModuleNotFoundError:
            return None
        return candidate if isinstance(candidate, type) and self._searchable(candidate) else None

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


class ScoutImportCommand(Command):
    """Put every row of a model into its search index."""

    signature = (
        "scout:import {model? : The model to import (default: every searchable model)} "
        "{--chunk= : How many records go into one index request}"
    )
    description = "Import the given model into the search index"

    def handle(self) -> int:
        models = SearchableModelFinder(self).find(_named(self.argument("model")))
        if not models:
            self.info("No searchable models found.")
            return self.SUCCESS

        chunk = self.option("chunk")
        size = int(chunk) if chunk and chunk is not True else None

        for model in models:
            imported = asyncio.run(model.make_all_searchable(size))
            self.line(f"{model.__name__} -> {model.searchable_as()}: {imported} record(s)")
        self.success("Imported.")
        return self.SUCCESS


class ScoutQueueImportCommand(Command):
    """The same import, handed to the queue a chunk at a time."""

    signature = (
        "scout:queue-import {model? : The model to import (default: every searchable model)} "
        "{--chunk= : How many records go into one job}"
    )
    description = "Import the given model into the search index using queued jobs"

    def handle(self) -> int:
        models = SearchableModelFinder(self).find(_named(self.argument("model")))
        if not models:
            self.info("No searchable models found.")
            return self.SUCCESS

        chunk = self.option("chunk")
        size = int(chunk) if chunk and chunk is not True else 500

        for model in models:
            queued = asyncio.run(_queue_import(model, size))
            self.line(f"{model.__name__}: {queued} job(s) queued")
        self.success("Queued.")
        return self.SUCCESS


class ScoutFlushCommand(Command):
    """Empty a model's index."""

    signature = "scout:flush {model? : The model to flush (default: every searchable model)}"
    description = "Flush all of the model's records from the index"

    def handle(self) -> int:
        models = SearchableModelFinder(self).find(_named(self.argument("model")))
        if not models:
            self.info("No searchable models found.")
            return self.SUCCESS

        for model in models:
            asyncio.run(model.remove_all_from_search())
            self.line(f"{model.__name__} -> {model.searchable_as()}: flushed")
        self.success("Flushed.")
        return self.SUCCESS


class ScoutIndexCommand(Command):
    """Create a search index by name."""

    signature = (
        "scout:index {name : The index to create} {--key= : The primary key of the documents}"
    )
    description = "Create an index on the search engine"

    def handle(self) -> int:
        from almasix.scout import Scout

        key = self.option("key")
        options = {"primaryKey": str(key)} if key and key is not True else {}
        try:
            asyncio.run(Scout.engine().create_index(str(self.argument("name")), options))
        except Exception as exc:
            self.error(str(exc))
            return self.FAILURE
        self.success(f"Index [{self.argument('name')}] created.")
        return self.SUCCESS


class ScoutDeleteIndexCommand(Command):
    """Delete a search index by name."""

    signature = "scout:delete-index {name : The index to delete}"
    description = "Delete an index from the search engine"

    def handle(self) -> int:
        from almasix.scout import Scout

        try:
            asyncio.run(Scout.engine().delete_index(str(self.argument("name"))))
        except Exception as exc:
            self.error(str(exc))
            return self.FAILURE
        self.success(f"Index [{self.argument('name')}] deleted.")
        return self.SUCCESS


class ScoutDeleteAllIndexesCommand(Command):
    """Delete every index the engine knows about."""

    signature = "scout:delete-all-indexes"
    description = "Delete all indexes from the search engine"

    def handle(self) -> int:
        from almasix.scout import Scout

        try:
            asyncio.run(Scout.engine().delete_all_indexes())
        except Exception as exc:
            self.error(str(exc))
            return self.FAILURE
        self.success("All indexes deleted.")
        return self.SUCCESS


class ScoutSyncIndexSettingsCommand(Command):
    """Push the index settings from `config/scout.py` to the engine."""

    signature = "scout:sync-index-settings"
    description = "Sync the configured index settings with the search engine"

    def handle(self) -> int:
        models = SearchableModelFinder(self).find([])
        if not models:
            self.info("No searchable models found.")
            return self.SUCCESS

        synced = 0
        for model in models:
            try:
                if asyncio.run(model.searchable_using().sync_settings(model)):
                    self.line(f"{model.__name__} -> {model.searchable_as()}: settings updated")
                    synced += 1
            except Exception as exc:
                self.error(f"{model.__name__}: {exc}")
                return self.FAILURE

        if synced == 0:
            self.info("No index settings are configured.")
            return self.SUCCESS
        self.success(f"{synced} index(es) updated.")
        return self.SUCCESS


class ScoutStatusCommand(Command):
    """What search is configured to do, and which models take part.

    Laravel has no such command; Almasix does, because "which engine is this
    application actually using" is the first question every search bug asks.
    """

    signature = "scout:status"
    description = "Show the search engine and the models it indexes"

    def handle(self) -> int:
        from almasix.scout import get_engine_manager

        manager = get_engine_manager()
        self.line(f"searching via [{manager.get_default_driver()}]")
        self.line(f"  queue: {'yes' if manager.queues else 'no'}")
        self.line(f"  after commit: {'yes' if manager.after_commit else 'no'}")
        self.line(f"  soft deletes indexed: {'yes' if manager.soft_delete else 'no'}")

        models = SearchableModelFinder(self).find([])
        if not models:
            self.comment("No searchable models. Mix in almasix.scout.Searchable.")
            return self.SUCCESS
        for model in models:
            self.line(f"  {model.__name__} -> {model.searchable_as()}")
        return self.SUCCESS


def _named(argument: Any) -> list[str]:
    """The model argument, as a list the finder understands."""
    return [str(argument)] if argument and argument is not True else []


async def _queue_import(model: Any, size: int) -> int:
    """Hand each chunk of keys to the queue rather than indexing here."""
    from almasix.queue.helpers import dispatch as queue_dispatch
    from almasix.scout.jobs import MakeSearchable

    queued = 0

    async def push(models: Any) -> None:
        nonlocal queued
        wanted = [record for record in models if record.should_be_searchable()]
        if not wanted:
            return
        await queue_dispatch(MakeSearchable.for_models(wanted))
        queued += 1

    await model.scout_base_query().order_by(model.get_scout_key_name()).chunk(size, push)
    return queued
