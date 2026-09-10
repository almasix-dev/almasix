"""``smith ide:stubs`` — generate model / route type stubs."""

from __future__ import annotations

from pathlib import Path

from almasix.console.command import Command
from almasix.ide.stubs import generate_stubs


class IdeStubsCommand(Command):
    signature = (
        "ide:stubs "
        "{--path= : Application root (default: cwd / find bootstrap/app.py)} "
        "{--output= : Directory for .pyi files (default: .almasix/stubs)}"
    )
    description = "Generate .pyi stubs for models and named routes"

    def handle(self) -> int:
        given = self.option("path")
        base = Path(str(given)).expanduser() if given else None
        out_opt = self.option("output")
        output = Path(str(out_opt)).expanduser() if out_opt else None

        result = generate_stubs(base, output=output)
        if not result.ok:
            self.error(result.error or "Stub generation failed.")
            return self.FAILURE

        self.info(f"Stubs written under {result.output_dir}")
        for path in result.model_files:
            try:
                rel = path.relative_to(result.base_path)
            except ValueError:
                rel = path
            self.line(f"  model  -> {rel}")
        if result.routes_file is not None:
            try:
                rel = result.routes_file.relative_to(result.base_path)
            except ValueError:
                rel = result.routes_file
            self.line(f"  routes -> {rel}")
        self.info("ide:stubs ok")
        return self.SUCCESS
