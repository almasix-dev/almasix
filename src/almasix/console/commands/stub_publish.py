"""``smith stub:publish`` — copy the generator stubs into the application."""

from __future__ import annotations

from pathlib import Path

from almasix.console.command import Command
from almasix.console.stub import PUBLISHED_DIRECTORY, publish


class StubPublishCommand(Command):
    signature = (
        "stub:publish {--force : Overwrite stubs that were already published} "
        "{--scaffold : Also publish the `almasix new` scaffold tree}"
    )
    description = "Publish the generator stubs into stubs/ so they can be edited"
    boots_application = False

    def handle(self) -> int:
        root = Path.cwd()
        force = bool(self.option("force"))
        published = publish(root, force=force)
        if not published:
            self.warn(
                f"Stubs are already published in {PUBLISHED_DIRECTORY}/. "
                "Use --force to overwrite them."
            )
        else:
            for path in published:
                self.success(f"Stub published: {path.relative_to(root)}")
            self.line(f"{len(published)} stub(s) published. Edit them and every make:* follows.")

        if bool(self.option("scaffold")):
            self.publish_scaffold(root, force=force)
        return self.SUCCESS

    def publish_scaffold(self, root: Path, *, force: bool) -> None:
        """Publish the installer's tree, for a team with its own starting point."""
        from almasix.installer.scaffold import publish_scaffold_stubs

        target, count = publish_scaffold_stubs(root, force=force)
        relative = target.relative_to(root)
        if not count:
            self.warn(f"Scaffold stubs are already published in {relative}/.")
            return
        self.success(f"{count} scaffold stub(s) published: {relative}/")
        self.line(f"  almasix new myapp --stubs {relative}")
