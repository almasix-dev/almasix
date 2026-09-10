"""``smith inertia:start-ssr`` — document / launch the Node SSR worker."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from almasix.console.command import Command


class InertiaStartSsrCommand(Command):
    signature = "inertia:start-ssr {--check : Only verify the SSR bundle exists}"
    description = "Start (or check) the Inertia Node SSR worker"

    def handle(self) -> int:
        bundle = self.app.path("bootstrap", "ssr.js")
        package_stub = Path(__file__).resolve().parents[1] / "ssr" / "server.js"
        if self.option("check"):
            exists = Path(bundle).is_file() or package_stub.is_file()
            self.info(f"ssr bundle → {bundle if Path(bundle).is_file() else package_stub}")
            self.info(f"exists → {exists}")
            return 0 if exists else 1

        target = Path(bundle) if Path(bundle).is_file() else package_stub
        if not target.is_file():
            self.error(
                "No SSR bundle. Copy packages/inertia/src/inertia/ssr/server.js to bootstrap/ssr.js"
            )
            return 1
        node = shutil.which("node")
        if not node:
            self.error("node is not on PATH")
            return 1
        self.info(f"starting SSR worker → {target}")
        subprocess.Popen([node, str(target)])
        self.success("inertia SSR worker started (background)")
        return 0
