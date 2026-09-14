"""``smith ide:index`` — dump the Almasix app symbol index (JSON for JetBrains)."""

from __future__ import annotations

from pathlib import Path

from almasix.console.command import Command
from almasix.console.display import to_json
from almasix.ide.index import build_ide_index


class IdeIndexCommand(Command):
    signature = (
        "ide:index "
        "{--path= : Application root (default: cwd / find bootstrap/app.py)} "
        "{--json : Output as JSON (default when stdout is not a TTY)}"
    )
    description = "Dump the Almasix app symbol index for IDE tooling"

    def handle(self) -> int:
        given = self.option("path")
        base = Path(str(given)).expanduser() if given else None
        payload = build_ide_index(base)
        if not payload.get("ok", False):
            self.error(payload.get("error") or "Index failed.")
            # Still emit JSON when requested so the IDE can show the error.
            if self.option("json"):
                self.line(to_json(payload))
            return self.FAILURE

        if self.option("json"):
            self.line(to_json(payload))
            return self.SUCCESS

        self.info(f"Index for {payload['base_path']}")
        self.line(f"  views            {len(payload.get('views', {}))}")
        self.line(f"  routes           {len(payload.get('routes', {}))}")
        self.line(f"  config_keys      {len(payload.get('config_keys', []))}")
        self.line(f"  models           {len(payload.get('models', {}))}")
        self.line(f"  translation_keys {len(payload.get('translation_keys', []))}")
        self.line(f"  middleware       {len(payload.get('middleware_aliases', []))}")
        self.line(f"  tables           {len(payload.get('tables', {}))}")
        self.line(f"  components       {len(payload.get('components', {}))}")
        self.line(f"  gates            {len(payload.get('gates', []))}")
        self.line(f"  validation_rules {len(payload.get('validation_rules', []))}")
        self.line(f"  smith_commands   {len(payload.get('smith_commands', []))}")
        self.line(f"  inertia_pages    {len(payload.get('inertia_pages', []))}")
        self.info("ide:index ok")
        return self.SUCCESS
