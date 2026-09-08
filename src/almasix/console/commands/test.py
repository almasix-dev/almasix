"""``smith test`` — run the application's tests.

Laravel's `artisan test` wraps PHPUnit; this wraps pytest, because that is what
a Python application's tests are written with. The point of the command is not
to replace `pytest` on the command line: it is that a test run starts from the
application root with `APP_ENV=testing`, the way the framework's own does.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from almasix.console.command import Command


class TestCommand(Command):
    """Run the test suite."""

    signature = (
        "test {path? : A directory, file, or node id to run (default: tests/)} "
        "{--k= : Only tests whose name matches this expression} "
        "{--m= : Only tests with this marker} "
        "{--coverage : Report coverage for the application's own code} "
        "{--parallel : Run with pytest-xdist, if it is installed} "
        "{--stop : Stop at the first failure} "
        "{--quiet : Less output} "
        "{--env= : The APP_ENV the run uses (default: testing)}"
    )
    description = "Run the application's tests through pytest"
    boots_application = False

    def handle(self) -> int:
        root = Path.cwd()
        target = str(self.argument("path") or "")
        if not target and not (root / "tests").is_dir():
            self.error("There is no tests/ directory here. Try: smith make:test PostTest")
            return self.FAILURE

        argv = [sys.executable, "-m", "pytest", target or "tests"]
        argv.extend(self._flags())

        environment = dict(os.environ)
        environment["APP_ENV"] = str(self.option("env") or "testing")
        self.line(f"running {' '.join(argv[2:])} with APP_ENV={environment['APP_ENV']}")
        try:
            completed = subprocess.run(argv, cwd=root, env=environment, check=False)
        except FileNotFoundError:
            self.error("pytest is not installed. Try: pip install pytest pytest-asyncio")
            return self.FAILURE
        return int(completed.returncode)

    def _flags(self) -> list[str]:
        flags: list[str] = []
        expression = self.option("k")
        if expression and expression is not True:
            flags.extend(["-k", str(expression)])
        marker = self.option("m")
        if marker and marker is not True:
            flags.extend(["-m", str(marker)])
        if self.option("coverage"):
            flags.extend(["--cov=app", "--cov-report=term-missing"])
        if self.option("parallel"):
            flags.extend(["-n", "auto"])
        if self.option("stop"):
            flags.append("-x")
        if self.option("quiet"):
            flags.append("-q")
        return flags
