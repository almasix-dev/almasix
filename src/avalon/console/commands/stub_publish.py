"""``grail stub:publish`` — copy the generator stubs into the application."""

from __future__ import annotations

from pathlib import Path

from avalon.console.command import Command
from avalon.console.stub import PUBLISHED_DIRECTORY, publish


class StubPublishCommand(Command):
    signature = "stub:publish {--force : Overwrite stubs that were already published}"
    description = "Publish the generator stubs into stubs/ so they can be edited"
    boots_application = False

    def handle(self) -> int:
        root = Path.cwd()
        published = publish(root, force=bool(self.option("force")))
        if not published:
            self.warn(
                f"Stubs are already published in {PUBLISHED_DIRECTORY}/. "
                "Use --force to overwrite them."
            )
            return self.SUCCESS
        for path in published:
            self.success(f"Stub published: {path.relative_to(root)}")
        self.line(f"{len(published)} stub(s) published. Edit them and every make:* follows.")
        return self.SUCCESS
