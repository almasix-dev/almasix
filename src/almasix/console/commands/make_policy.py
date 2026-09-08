"""``make:policy``."""

from __future__ import annotations

from pathlib import Path

from almasix.console.command import Command
from almasix.console.stub import render
from almasix.orm.inflector import snake


class MakePolicyCommand(Command):
    signature = "make:policy {name} {--model=} {--resource} {--force}"
    description = "Create a new policy class"

    def handle(self) -> int:
        raw = str(self.argument("name") or "")
        name = _pascal(raw)
        if not name:
            self.error("A policy name is required.")
            return 1
        if not name.endswith("Policy"):
            name = f"{name}Policy"
        model_opt = str(self.option("model") or "")
        resource = bool(self.option("resource"))
        force = bool(self.option("force"))
        base_path = Path.cwd()
        path = base_path / "app" / "policies" / f"{snake(name)}.py"
        if path.exists() and not force:
            self.error(f"Policy already exists: {path}")
            return 1
        model_name = _pascal(model_opt) if model_opt else ""
        if model_name:
            stub = "policy.stub"
        elif resource:
            stub = "policy-resource.stub"
        else:
            stub = "policy.plain.stub"
        body = render(
            stub,
            {
                "class": name,
                "model": model_name,
                "modelVariable": snake(model_name) if model_name else "",
                "namespacedModel": f"app.models.{snake(model_name)}" if model_name else "",
            },
            base_path=base_path,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        init = path.parent / "__init__.py"
        if not init.exists():
            init.write_text('"""Application policies."""\n', encoding="utf-8")
        self.info(f"Policy created: {path}")
        return 0


def _pascal(name: str) -> str:
    parts = name.replace("-", "_").replace("/", "_").split("_")
    return "".join(p[:1].upper() + p[1:] for p in parts if p)
