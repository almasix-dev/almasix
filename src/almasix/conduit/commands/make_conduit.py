"""``smith make:conduit`` — scaffold a Conduit component + Prism view."""

from __future__ import annotations

from pathlib import Path

from almasix.console.command import Command


class MakeConduitCommand(Command):
    signature = (
        "make:conduit {name : Component class name (e.g. Counter or Forms/Profile)}"
        " {--force : Overwrite existing files}"
    )

    def handle(self) -> int:
        raw = str(self.argument("name") or "").strip()
        if not raw:
            self.error("name is required")
            return 1
        parts = [p for p in raw.replace("\\", "/").replace(".", "/").split("/") if p]
        class_name = "".join(p[:1].upper() + p[1:] for p in parts[-1].replace("-", "_").split("_"))
        module_parts = [p.replace("-", "_").lower() for p in parts]
        if module_parts[-1] != class_name.lower() and "_" not in module_parts[-1]:
            # Counter -> counter.py
            module_parts[-1] = "".join(
                f"_{c.lower()}" if c.isupper() else c for c in class_name
            ).lstrip("_")
        rel = Path(*module_parts[:-1]) if len(module_parts) > 1 else Path()
        snake = module_parts[-1]
        class_path = self.app.path("app", "conduit", *rel.parts, f"{snake}.py")
        view_name = ".".join([*(rel.parts), snake]) if rel.parts else snake
        view_path = self.app.path(
            "resources", "views", "conduit", *rel.parts, f"{snake}.prism.html"
        )

        class_path.parent.mkdir(parents=True, exist_ok=True)
        view_path.parent.mkdir(parents=True, exist_ok=True)
        if class_path.exists() and not self.option("force"):
            self.error(f"{class_path} already exists")
            return 1

        class_path.write_text(
            f'''"""Conduit component: {class_name}."""

from __future__ import annotations

from almasix.conduit import Component


class {class_name}(Component):
    def render(self) -> str:
        return "conduit.{view_name}"
''',
            encoding="utf-8",
        )
        view_path.write_text(
            f"""<div>
  <h2>{class_name}</h2>
  {{{{-- Conduit view for {class_name} --}}}}
</div>
""",
            encoding="utf-8",
        )
        self.info(f"component → {class_path}")
        self.info(f"view → {view_path}")
        self.success("conduit component created")
        return 0
