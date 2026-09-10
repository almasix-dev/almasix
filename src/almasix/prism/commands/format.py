"""``smith prism:format`` — format ``.prism.html`` templates."""

from __future__ import annotations

from pathlib import Path

from almasix.console.command import Command
from almasix.prism.formatter import format_prism


class PrismFormatCommand(Command):
    signature = (
        "prism:format {path? : File or directory} "
        "{--check : Fail if files would change} "
        "{--write : Write changes (default when not --check)}"
    )
    description = "Format Prism (.prism.html) templates"
    boots_application = False

    def handle(self) -> int:
        root = Path(self.argument("path") or ".").expanduser()
        if not root.exists():
            self.error(f"Path not found: {root}")
            return self.FAILURE

        files = self._collect(root)
        if files is None:
            return self.FAILURE
        if not files:
            self.info("No .prism.html files found.")
            return self.SUCCESS

        check = bool(self.option("check"))
        write = not check

        changed = 0
        for path in files:
            original = path.read_text(encoding="utf-8")
            formatted = format_prism(original)
            if formatted == original:
                continue
            changed += 1
            rel: Path | str = path
            try:
                rel = path.relative_to(Path.cwd())
            except ValueError:
                pass
            if check:
                self.line(f"would reformat: {rel}")
            elif write:
                path.write_text(formatted, encoding="utf-8")
                self.line(f"formatted: {rel}")

        if check and changed:
            self.error(f"{changed} file(s) would be reformatted.")
            return self.FAILURE

        if changed == 0:
            self.info(f"Already formatted ({len(files)} file(s)).")
        elif write:
            self.info(f"Formatted {changed} of {len(files)} file(s).")
        return self.SUCCESS

    def _collect(self, root: Path) -> list[Path] | None:
        """Return matching files, or ``None`` when ``root`` is an invalid file."""
        if root.is_file():
            if not root.name.endswith(".prism.html"):
                self.error(f"Not a .prism.html file: {root}")
                return None
            return [root]
        return sorted(p for p in root.rglob("*.prism.html") if p.is_file())
