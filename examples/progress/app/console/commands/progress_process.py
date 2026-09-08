"""Demo Process.run / start / pool / pipe / fakes (M21)."""

from __future__ import annotations

import sys

from almasix.console.command import Command
from almasix.process import Process, ProcessTimedOutException


def python(code: str) -> list[str]:
    """A command that works wherever this example runs."""
    return [sys.executable, "-c", code]


class ProgressProcessCommand(Command):
    signature = "progress:process"
    description = "Demo Process run, start, pool, pipe, and fakes (M21)"

    def handle(self) -> int:
        result = Process.run(python("print('hello from a subprocess')"))
        assert result.successful()
        self.info(f"run -> {result.output().strip()}")

        streamed: list[str] = []
        Process.run(
            python("print('first'); print('second')"),
            lambda _kind, chunk: streamed.append(chunk.strip()),
        )
        self.info(f"streamed -> {streamed}")

        invoked = Process.start(python("import time; time.sleep(0.05); print('done later')"))
        self.line(f"  started pid {invoked.id()}")
        self.info(f"start -> {invoked.wait().output().strip()}")

        results = Process.concurrently(
            lambda pool: [
                pool.as_("one").command(python("print('pool one')")),
                pool.as_("two").command(python("print('pool two')")),
            ]
        )
        assert results.successful()
        self.info(f"pool -> {results['one'].output().strip()} / {results['two'].output().strip()}")

        piped = Process.pipe(
            [
                python("print('almasix pipes')"),
                python("import sys; print(sys.stdin.read().upper().strip())"),
            ]
        )
        self.info(f"pipe -> {piped.output().strip()}")

        try:
            Process.timeout(0.2).run(python("import time; time.sleep(30)"))
        except ProcessTimedOutException as exception:
            self.info(f"timeout -> {exception}")

        Process.fake(
            {
                "deploy *": Process.sequence()
                .push_result(error_output="locked", exit_code=1)
                .push_output("deployed"),
            }
        )
        Process.prevent_stray_processes()
        assert Process.run("deploy staging").failed()
        assert Process.run("deploy staging").output().strip() == "deployed"
        Process.assert_ran_times("deploy *", 2)
        Process.assert_didnt_run("rm *")
        Process.assert_sequences_are_empty()
        self.info("fakes -> sequence drained, assertions green")

        self.success("process demo ok")
        return 0
