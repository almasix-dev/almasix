"""Demo deployment + production ops (M38).

Proves ``smith serve --workers``, ``optimize``, the ``/up`` health probe,
deployment docs, the container sketch, and the Trusted Publishing release path.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

from fastapi.testclient import TestClient

from almasix import __version__
from almasix.console.command import Command
from almasix.console.commands.runtime import ServeCommand

ROOT = Path(__file__).resolve().parents[5]  # …/almasix (repo root)


class ProgressDeployCommand(Command):
    signature = "progress:deploy"
    description = "Demo deployment ops — serve --workers, optimize, /up, docs, release path (M38)"

    def handle(self) -> int:
        signature = ServeCommand.signature
        if "--workers" not in signature:
            self.error("serve signature missing --workers")
            return 1
        self.info("smith serve --workers -> present")

        source = inspect.getsource(ServeCommand.handle)
        if "proxy_headers" not in source:
            self.error("serve does not pass proxy_headers to uvicorn")
            return 1
        self.info("smith serve --proxy-headers -> wired to uvicorn")

        code = self.call("optimize")
        if code != 0:
            self.error("optimize -> failed")
            return code
        self.info("optimize / view:cache -> ok")

        module = importlib.import_module("bootstrap.app")
        client = TestClient(module.asgi)
        response = client.get("/up")
        if response.status_code != 200:
            self.error(f"/up -> {response.status_code}")
            return 1
        self.info("GET /up -> 200")

        docs = ROOT / "website" / "src" / "content" / "docs" / "deployment.md"
        if not docs.is_file():
            self.error("Starlight Deployment page missing")
            return 1
        body = docs.read_text(encoding="utf-8")
        for needle in ("--workers", "/up", "APP_DEBUG", "examples/deploy", "Trusted Publishing"):
            if needle not in body:
                self.error(f"deployment.md missing {needle!r}")
                return 1
        self.info("docs/deployment.md -> present")

        deploy = ROOT / "examples" / "deploy"
        for name in ("Dockerfile", "docker-compose.yml", "README.md"):
            if not (deploy / name).is_file():
                self.error(f"examples/deploy/{name} missing")
                return 1
        self.info("examples/deploy -> Dockerfile + compose")

        publish = ROOT / ".github" / "workflows" / "publish.yml"
        if not publish.is_file() or "Trusted Publishing" not in publish.read_text(encoding="utf-8"):
            self.error("publish.yml Trusted Publishing workflow missing")
            return 1
        self.info("publish.yml -> Trusted Publishing (PyPI + TestPyPI)")

        self.info(f"almasix.__version__ -> {__version__}")
        if __version__ != "0.6.0":
            self.error("expected package version 0.6.0 for this release line")
            return 1

        self.success("deployment + production ops ok")
        return 0
