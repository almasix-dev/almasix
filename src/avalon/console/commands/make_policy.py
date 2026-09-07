"""``make:policy``."""

from __future__ import annotations

from pathlib import Path

from avalon.console.command import Command
from avalon.orm.inflector import snake


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
        path = Path.cwd() / "app" / "policies" / f"{snake(name)}.py"
        if path.exists() and not force:
            self.error(f"Policy already exists: {path}")
            return 1
        model_name = _pascal(model_opt) if model_opt else ""
        body = _policy_stub(name, model_name=model_name, resource=resource or bool(model_name))
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


def _policy_stub(name: str, *, model_name: str, resource: bool) -> str:
    imports = [
        "from __future__ import annotations",
        "",
        "from avalon.auth import Policy",
    ]
    model_import = ""
    user_arg = "user"
    if model_name:
        model_import = f"from app.models.{snake(model_name)} import {model_name}\n"
        user_arg = "user"
    methods = "    pass\n"
    if resource:
        target = model_name or "model"
        instance = snake(target) if model_name else "model"
        methods = f'''    def view_any(self, {user_arg}) -> bool:
        return True

    def view(self, {user_arg}, {instance}: {target}) -> bool:
        return True

    def create(self, {user_arg}) -> bool:
        return True

    def update(self, {user_arg}, {instance}: {target}) -> bool:
        return False

    def delete(self, {user_arg}, {instance}: {target}) -> bool:
        return False

    def restore(self, {user_arg}, {instance}: {target}) -> bool:
        return False

    def force_delete(self, {user_arg}, {instance}: {target}) -> bool:
        return False
'''
        if not model_name:
            methods = methods.replace(": model", "")
    return f'''"""{name}."""

{chr(10).join(imports)}
{model_import}

class {name}(Policy):
    """{name}."""

{methods}'''
