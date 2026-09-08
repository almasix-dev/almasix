"""Prune stale models (Laravel ``model:prune``)."""

from __future__ import annotations

import asyncio
import importlib
import pkgutil
from pathlib import Path
from typing import Any

from almasix.console.command import Command


class ModelPruneCommand(Command):
    signature = (
        "model:prune "
        "{--model=* : Class names of the models to prune} "
        "{--except=* : Class names of the models to exclude} "
        "{--chunk=1000 : The number of models to retrieve per chunk} "
        "{--pretend : Report how many models would be pruned}"
    )
    description = "Prune models that are no longer needed"

    def handle(self) -> int:
        chunk = int(self.option("chunk") or 1000)
        pretend = bool(self.option("pretend"))
        wanted = [str(name) for name in (self.option("model") or [])]
        excluded = {str(name) for name in (self.option("except") or [])}

        if wanted and excluded:
            self.error("The --model and --except options cannot be combined.")
            return self.INVALID

        models = [
            model
            for model in self._prunable_models(wanted)
            if model.__name__ not in excluded
        ]
        if not models:
            self.info("No prunable models found.")
            return self.SUCCESS

        for model in models:
            if pretend:
                total = asyncio.run(model.prunable_query().count())
                self.info(f"{model.__name__}: {total} model(s) would be pruned.")
                continue
            pruned = asyncio.run(model.prune(chunk))
            self.info(f"{model.__name__}: {pruned} model(s) pruned.")
        return self.SUCCESS

    # --- discovery ----------------------------------------------------------

    def _prunable_models(self, wanted: list[str]) -> list[Any]:
        from almasix.orm.pruning import MassPrunable, Prunable

        found: dict[str, Any] = {}
        for module in self._model_modules():
            for name in dir(module):
                candidate = getattr(module, name)
                if not isinstance(candidate, type) or not issubclass(candidate, Prunable):
                    continue
                if candidate in (Prunable, MassPrunable):  # the base mixins
                    continue
                found[candidate.__name__] = candidate

        if not wanted:
            return sorted(found.values(), key=lambda model: model.__name__)

        selected = []
        for name in wanted:
            model = found.get(name.rsplit(".", 1)[-1])
            if model is None:
                self.warn(f"Model [{name}] was not found or is not prunable.")
                continue
            selected.append(model)
        return selected

    def _model_modules(self) -> list[Any]:
        """Import `app.models` so its Prunable subclasses are registered."""
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
            except Exception as exc:  # noqa: BLE001 — one bad module must not stop pruning
                self.warn(f"Could not import app.models.{info.name}: {exc}")
        return modules
