"""``vendor:publish`` — copy files a package offers into the application."""

from __future__ import annotations

import shutil
from pathlib import Path

from almasix.console.command import Command
from almasix.providers.provider import ServiceProvider


class VendorPublishCommand(Command):
    signature = (
        "vendor:publish "
        "{--provider= : The provider whose files to publish} "
        "{--tag=* : Publish only the files under these tags} "
        "{--all : Publish every file every provider offers} "
        "{--force : Overwrite files that already exist} "
        "{--existing : Publish only over files that already exist}"
    )
    description = "Publish the files a package's provider offers"

    def handle(self) -> int:
        choice = self._chosen()
        if choice is None:
            return self.FAILURE
        provider, tags = choice

        published = 0
        for tag in tags or [None]:
            paths = ServiceProvider.paths_to_publish(provider, tag)
            if not paths:
                self.warn(self._nothing_matched(provider, tag))
                continue
            for source, destination in sorted(paths.items()):
                published += self._publish(source, destination)

        if not published:
            self.comment("Nothing to publish.")
        return self.SUCCESS

    def _chosen(self) -> tuple[str | None, list[str]] | None:
        """What the user asked for, prompting when they asked for nothing.

        Laravel prompts with the list of providers and tags rather than
        publishing everything by accident, and ``--all`` is how you say you
        meant everything. A non-interactive run with no selection is an
        error, not a silent publish of the whole vendor tree.
        """
        provider = self.option("provider")
        tags = [tag for tag in (self.option("tag") or []) if tag]
        if provider or tags:
            return provider, tags
        if self.option("all"):
            return None, []

        options = self._selectable()
        if not options:
            self.error("No provider offers anything to publish.")
            return None
        selected = self.choice("Which files should be published?", options)
        if selected.startswith("Tag: "):
            return None, [selected[5:]]
        return selected, []

    def _selectable(self) -> list[str]:
        return [
            *(f"Tag: {tag}" for tag in ServiceProvider.publishable_tags()),
            *ServiceProvider.publishable_providers(),
        ]

    def _nothing_matched(self, provider: str | None, tag: str | None) -> str:
        if tag is not None:
            return f"No files are tagged {tag!r}."
        return f"{provider} offers nothing to publish."

    def _publish(self, source: Path, destination: Path) -> int:
        if not source.exists():
            self.error(f"Missing: {source}")
            return 0
        if source.is_dir():
            return sum(
                self._publish(child, destination / child.relative_to(source))
                for child in sorted(source.rglob("*"))
                if child.is_file()
            )
        return self._publish_file(source, destination)

    def _publish_file(self, source: Path, destination: Path) -> int:
        if ServiceProvider.is_migration_publish(source):
            destination = ServiceProvider.migration_publish_destination(source, destination)
        exists = destination.exists()
        if exists and not self.option("force"):
            self.comment(f"Exists, skipped: {self._relative(destination)} (use --force)")
            return 0
        if not exists and self.option("existing"):
            return 0
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        self.success(f"Published: {self._relative(destination)}")
        return 1

    def _relative(self, path: Path) -> str:
        """A destination the way the user would name it, when it is inside the app."""
        base = getattr(self.app, "base_path", None)
        if base is None or not path.is_relative_to(base):
            return str(path)
        return str(path.relative_to(base))
