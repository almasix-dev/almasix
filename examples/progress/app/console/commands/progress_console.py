"""M30 living example — the Artisan-shaped console surface."""

from __future__ import annotations

import signal

from avalon.console import Artisan, Command, Isolatable, PromptsForMissingInput


class ProgressConsoleCommand(PromptsForMissingInput, Command):
    signature = (
        "progress:console {report : Which report to build} "
        "{--T|tag=* : Tags to attach} {--dry-run : Skip the write}"
    )
    description = "M30 living example — signatures, output, and Artisan.call"

    def prompt_for_missing_arguments_using(self) -> dict[str, str]:
        return {"report": "Which report should we build?"}

    def handle(self) -> int:
        tags = self.option("tag") or ["none"]
        self.alert(f"Building {self.argument('report')}")
        self.table(["Setting", "Value"], [["tags", ", ".join(tags)], ["dry run", self.dry_run]])

        rows = self.with_progress_bar([1, 2, 3], lambda step: step * 10, label="Crunching")
        self.line(f"  steps -> {rows}")

        self.call_silently("progress:hello")
        self.comment(f"  called progress:hello -> {Artisan.output().strip()}")

        if self.dry_run:
            self.warn("Dry run: nothing written.")
            return self.SUCCESS
        self.success("progress:console ok")
        return self.SUCCESS


class ProgressImportCommand(Isolatable, Command):
    signature = "progress:import {--sleep=0 : Seconds to hold the lock}"
    description = "M30 living example — an isolatable, signal-trapping worker"

    def isolatable_id(self) -> str:
        return "progress:import"

    def isolation_lock_seconds(self) -> int:
        return 60

    def handle(self) -> int:
        self.stopping = False
        self.trap([signal.SIGTERM, signal.SIGINT], lambda _number: self._stop())
        self.info("Importing (send SIGTERM to stop early)…")
        if not self.stopping:
            self.line("  imported 1 batch")
        self.success("progress:import ok")
        return self.SUCCESS

    def _stop(self) -> None:
        self.stopping = True
        self.warn("Stopping after the current batch.")
