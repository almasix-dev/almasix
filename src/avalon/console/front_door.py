"""The argv front door.

Every Grail command is a :class:`~avalon.console.command.Command`. Typer's only
job is to turn a terminal line into ``name`` plus ``argv`` and hand it to the
kernel, so the CLI, ``Artisan.call``, and the scheduler all reach the same
command through the same parser.
"""

from __future__ import annotations

from pathlib import Path

import typer

from avalon.console.kernel import ConsoleKernel, DiscoveryFailure


class FrontDoor:
    """Keeps a Typer app pointed at the commands of the current directory.

    A ``grail`` process usually runs one command in one directory and exits, so
    a single kernel would do. But the CLI is also driven in-process — by tests,
    and by anything embedding Grail — where the directory moves under it. So the
    kernel is rebuilt when it no longer matches, and whatever the new directory
    contributes is attached as well.
    """

    def __init__(self, typer_app: typer.Typer) -> None:
        self.typer_app = typer_app
        self._kernel: ConsoleKernel | None = None

    def kernel(self, cwd: Path | None = None) -> ConsoleKernel:
        root = Path(cwd or Path.cwd()).resolve()
        current = self._kernel
        if current is not None and current.app.base_path == root:
            return current

        kernel = self._build(root)
        self._kernel = kernel
        kernel.register_on_typer(self.typer_app, resolve=self.kernel)
        report_failures(kernel)
        return kernel

    def _build(self, root: Path) -> ConsoleKernel:
        """Discover what ``root`` offers.

        The framework's own commands attach unconditionally, because generators
        and ``version`` have to work in a directory that is not an application
        yet. An application root additionally contributes its
        ``app/console/commands`` and the closure commands and scheduled tasks in
        ``routes/console.py`` — which needs a booted application, so that boot
        happens here, once, and only there.
        """
        from avalon.console.facade import Artisan, drain_pending

        kernel = ConsoleKernel.for_cwd(root)
        kernel.discover_framework_commands()

        if (root / "bootstrap" / "app.py").is_file():
            try:
                kernel.boot_application()
                kernel.discover()
                kernel.load_console_routes()
            except Exception as exc:
                kernel.failures.append(DiscoveryFailure("the application", exc))

        Artisan.set_kernel(kernel)
        drain_pending(kernel)
        return kernel


def install(typer_app: typer.Typer, *, cwd: Path | None = None) -> ConsoleKernel:
    """Register every command Grail can reach from ``cwd`` onto ``typer_app``."""
    return FrontDoor(typer_app).kernel(cwd)


def report_failures(kernel: ConsoleKernel) -> None:
    """Say which command modules did not load, on every run.

    A silent skip is how a typo turns into "No such command" with no cause, so
    the notice is printed whatever you typed — not only on ``grail list``.
    """
    for failure in kernel.failures:
        typer.secho(f"Command not loaded — {failure.summary()}", fg=typer.colors.YELLOW, err=True)
