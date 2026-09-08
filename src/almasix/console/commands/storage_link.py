"""The public storage symlinks — ``storage:link`` and ``storage:unlink``."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from almasix.console.command import Command

if TYPE_CHECKING:
    from almasix.framework.application import Application

#: Laravel's single public link, for an application that configures none.
DEFAULT_LINKS = {"public/storage": "storage/app/public"}


def configured_links(app: Application) -> dict[str, str]:
    """The ``filesystems.links`` map both commands work through."""
    links = dict(app.config.get("filesystems.links") or {})
    return links or dict(DEFAULT_LINKS)


class StorageLinkCommand(Command):
    signature = "storage:link {--relative} {--force}"
    description = "Create the symbolic links configured for the application"

    def handle(self) -> int:
        links = configured_links(self.app)

        relative = bool(self.option("relative"))
        force = bool(self.option("force"))
        base = Path(self.app.base_path)

        for link, target in links.items():
            link_path = base / link
            target_path = base / target
            target_path.mkdir(parents=True, exist_ok=True)
            link_path.parent.mkdir(parents=True, exist_ok=True)

            if link_path.exists() or link_path.is_symlink():
                if force:
                    if link_path.is_symlink() or link_path.is_file():
                        link_path.unlink()
                    else:
                        self.error(f"The [{link}] link already exists and is not a symlink.")
                        return 1
                else:
                    self.warn(f"The [{link}] link already exists.")
                    continue

            if relative:
                target_arg = os.path.relpath(target_path, start=link_path.parent)
            else:
                target_arg = str(target_path)

            link_path.symlink_to(target_arg, target_is_directory=True)
            self.info(f"The [{link}] link has been connected to [{target}].")

        return 0


class StorageUnlinkCommand(Command):
    """Laravel's ``storage:unlink`` — remove the links ``storage:link`` made.

    A configured path that is a real directory rather than a symlink is left
    where it is and reported: it holds files nobody asked to delete, and
    Laravel's version silently skips it.
    """

    signature = "storage:unlink"
    description = "Delete the symbolic links configured for the application"

    def handle(self) -> int:
        base = Path(self.app.base_path)
        code = self.SUCCESS
        for link in configured_links(self.app):
            link_path = base / link
            # A broken symlink does not exist(), so ask what it is first.
            if link_path.is_symlink():
                link_path.unlink()
                self.info(f"The [{link}] link has been removed.")
            elif link_path.exists():
                self.error(f"The [{link}] path is not a symbolic link — refusing to delete it.")
                code = self.FAILURE
            else:
                self.comment(f"The [{link}] link does not exist.")
        return code
