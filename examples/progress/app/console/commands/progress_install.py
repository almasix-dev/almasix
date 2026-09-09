"""Demo the installer: every stack, every database, and the default tables (M32).

Runs `almasix new` the way the four stacks configure it, in a temporary
directory, and reports what each one produced — including whether the
application it wrote actually answers a request.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from almasix.console.command import Command
from almasix.installer.options import Answers, resolve_plan
from almasix.installer.scaffold import (
    DATABASES,
    DEFAULT_MIGRATIONS,
    STACKS,
    scaffold_app,
)


class ProgressInstallCommand(Command):
    signature = "progress:install {--keep : Leave the generated applications on disk}"
    description = "Demo `almasix new` — stacks, databases, and the default migrations (M32)"

    def handle(self) -> int:
        workspace = Path(tempfile.mkdtemp(prefix="almasix_m32_"))
        try:
            self.every_stack(workspace)
            self.every_database(workspace)
            self.the_default_migrations(workspace)
            self.the_questions(workspace)
            self.the_stub_tree(workspace)
        finally:
            if self.option("keep"):
                self.line(f"kept -> {workspace}")
            else:
                shutil.rmtree(workspace, ignore_errors=True)
        self.success("installer demo ok")
        return self.SUCCESS

    def every_stack(self, workspace: Path) -> None:
        """Four stacks, four different frontends, one application shape."""
        for stack in STACKS:
            root = scaffold_app(
                f"stack_{stack.name}",
                destination=workspace / "stacks" / stack.name,
                stack=stack.name,
            )
            frontend = "package.json + vite" if stack.node else "no Node"
            files = sum(1 for path in root.rglob("*") if path.is_file())
            self.line(f"stack {stack.name:<10} -> {frontend}, {files} files")
            self.line(f"  errors:publish bundle -> {stack.error_bundle}")
            for rel in (
                "resources/views/layouts/minimal.prism.html",
                "resources/views/layouts/app.prism.html",
                "resources/views/auth/login.prism.html",
                "resources/views/auth/register.prism.html",
                "resources/views/dashboard.prism.html",
            ):
                assert (root / rel).is_file(), rel
            welcome = (root / "resources" / "views" / "welcome.prism.html").read_text(
                encoding="utf-8"
            )
            assert "Build something remarkable" in welcome
            self.line("  ui kit -> layouts + auth + dashboard")

    def every_database(self, workspace: Path) -> None:
        """The choice writes .env and config/database.py, and touches SQLite's file."""
        from almasix.installer.scaffold import sql_connection_name

        for database in DATABASES:
            root = scaffold_app(
                f"db_{database.name}",
                destination=workspace / "databases" / database.name,
                database=database.name,
            )
            env = (root / ".env").read_text(encoding="utf-8")
            connection = next(
                line for line in env.splitlines() if line.startswith("DB_CONNECTION=")
            )
            file_made = (root / "database" / "database.sqlite").is_file()
            config = (root / "config" / "database.py").read_text(encoding="utf-8")
            sql_default = sql_connection_name(database)
            assert f'env("DB_CONNECTION", "{sql_default}")' in config
            if database.name == "mongodb":
                assert "MONGODB_HOST=" in env
                assert "MONGODB_DATABASE=db_mongodb" in env
                assert database.extra == "almasix[mongodb]"
                self.line(
                    f"database {database.name:<8} -> {connection} + MONGODB_*, "
                    f"sqlite file: {file_made}, sql default: {sql_default}"
                )
            else:
                self.line(f"database {database.name:<8} -> {connection}, sqlite file: {file_made}")

    def the_default_migrations(self, workspace: Path) -> None:
        """The tables auth, sessions, cache, and the queue read — and they run."""
        root = scaffold_app("migrated", destination=workspace / "migrated")
        for filename, _stub, class_name in DEFAULT_MIGRATIONS:
            self.line(f"migration -> {filename} ({class_name})")

        completed = subprocess.run(
            [sys.executable, "smith", "migrate", "--force"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        for line in completed.stdout.splitlines():
            self.line(f"  {line}")
        self.line(f"migrate -> exit {completed.returncode}")
        self.line(f"tables -> {', '.join(self.tables(root))}")
        self.line(f"welcome page -> {self.serve(root)}")

    def tables(self, root: Path) -> list[str]:
        import sqlite3

        with sqlite3.connect(root / "database" / "database.sqlite") as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            ).fetchall()
        return [name for (name,) in rows if not name.startswith("sqlite_")]

    def serve(self, root: Path) -> str:
        """Boot the generated application in a subprocess and ask it for a page."""
        script = (
            "import importlib, sys;"
            "from fastapi.testclient import TestClient;"
            "sys.path.insert(0, '.');"
            "module = importlib.import_module('bootstrap.app');"
            "response = TestClient(module.asgi).get('/');"
            "print(response.status_code, 'Build something remarkable' in response.text)"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        return completed.stdout.strip().splitlines()[-1] if completed.stdout else "no answer"

    def the_questions(self, workspace: Path) -> None:
        """Every prompt has a flag, and --no-interaction takes the defaults."""
        default = resolve_plan("d", workspace / "d", Answers(), interactive=False)
        self.line(
            "no-interaction -> "
            f"stack={default.stack}, database={default.database}, tests={default.tests}, "
            f"git={default.git}, install={default.install}, migrate={default.migrate}"
        )

        flagged = resolve_plan(
            "f",
            workspace / "f",
            Answers(stack="bootstrap", database="pgsql", git=True, tests=False),
            interactive=False,
        )
        self.line(
            f"flags -> stack={flagged.stack}, database={flagged.database}, "
            f"tests={flagged.tests}, git={flagged.git}, asked={flagged.asked}"
        )

    def the_stub_tree(self, workspace: Path) -> None:
        """The scaffold is a stub tree, so a team can fork it and scaffold from it."""
        from almasix.installer.scaffold import publish_scaffold_stubs

        target, count = publish_scaffold_stubs(workspace / "team")
        (target / "app" / "routes" / "web.py.stub").write_text(
            '"""{{ app_display }} routes, our way."""\n', encoding="utf-8"
        )
        root = scaffold_app("forked", destination=workspace / "forked", stubs=target)

        self.line(f"stub:publish --scaffold -> {count} stubs")
        self.line(f"--stubs -> {(root / 'routes' / 'web.py').read_text().strip()}")
        importlib.invalidate_caches()
