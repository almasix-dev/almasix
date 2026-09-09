"""Console commands under test — answer their questions, read their output.

Laravel's `$this->artisan('mail:send')->expectsQuestion(...)->assertExitCode(0)`.
The command runs for real: the same kernel, the same signature parsing, the
same `handle()`. Only the terminal is a fake — questions are answered from a
queue, and output goes to a buffer the assertions read.
"""

from __future__ import annotations

import contextlib
import io
from collections.abc import Mapping, Sequence
from typing import Any

from almasix.console.command import Command, set_answer_sink

#: Marks "the command has not been run yet".
_NOT_RUN = -999


class AnswerSink:
    """The queue a faked prompt takes its answer from."""

    def __init__(self) -> None:
        self.expected: list[tuple[str | None, Any]] = []
        self.asked: list[str] = []

    def push(self, question: str | None, answer: Any) -> None:
        self.expected.append((question, answer))

    def answer(self, question: str, default: Any = None) -> Any:
        """What the test said to answer, or the default if it said nothing."""
        self.asked.append(question)
        for index, (wanted, answer) in enumerate(self.expected):
            if wanted is None or wanted in question:
                del self.expected[index]
                return answer
        return default


class PendingCommand:
    """A command with expectations attached, waiting to be run.

    Every `expects_*` records something to check; every `assert_*` runs the
    command first if it has not run yet, so a chain ending in an assertion
    behaves the way Laravel's does.
    """

    def __init__(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        app: Any = None,
        kernel: Any = None,
    ) -> None:
        self.name = name
        self.arguments = dict(arguments or {})
        self.app = app
        self.kernel = kernel
        self.exit_code: int = _NOT_RUN
        self.output: str = ""
        self._answers = AnswerSink()
        self._expected_output: list[str] = []
        self._unexpected_output: list[str] = []
        self._expected_tables: list[tuple[Sequence[str], Sequence[Sequence[Any]]]] = []

    # --- expectations ---------------------------------------------------------

    def expects_question(self, question: str, answer: Any) -> PendingCommand:
        self._answers.push(question, answer)
        return self

    def expects_confirmation(self, question: str, answer: bool | str = True) -> PendingCommand:
        wanted = answer if isinstance(answer, bool) else str(answer).lower() in {"yes", "y", "true"}
        self._answers.push(question, wanted)
        return self

    def expects_choice(
        self,
        question: str,
        answer: Any,
        choices: Sequence[Any] | None = None,
    ) -> PendingCommand:
        del choices  # Laravel checks the options; the answer is what matters here.
        self._answers.push(question, answer)
        return self

    def expects_output(self, text: str) -> PendingCommand:
        self._expected_output.append(text)
        return self

    def doesnt_expect_output(self, text: str) -> PendingCommand:
        self._unexpected_output.append(text)
        return self

    def expects_table(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[Any]],
    ) -> PendingCommand:
        self._expected_tables.append((list(headers), [list(row) for row in rows]))
        return self

    # --- running ---------------------------------------------------------------

    def run(self) -> PendingCommand:
        """Run the command, then check everything that was expected of it."""
        if self.exit_code != _NOT_RUN:
            return self

        arguments, options = _split(self.arguments)
        buffer = io.StringIO()
        token = set_answer_sink(self._answers)
        try:
            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                self.exit_code = self._kernel().run_command(self.name, arguments, options)
        finally:
            set_answer_sink(None, token)
            self.output = buffer.getvalue()

        self._verify()
        return self

    def _kernel(self) -> Any:
        if self.kernel is not None:
            return self.kernel
        from almasix.console.facade import Smith

        return Smith.kernel(app=self.app)

    def _verify(self) -> None:
        for text in self._expected_output:
            if text not in self.output:
                raise AssertionError(
                    f"[{self.name}] never printed [{text}]. It printed: {self._printed()}."
                )
        for text in self._unexpected_output:
            if text in self.output:
                raise AssertionError(f"[{self.name}] printed [{text}], and should not have.")
        for headers, rows in self._expected_tables:
            self._verify_table(headers, rows)

    def _verify_table(self, headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
        for header in headers:
            if str(header) not in self.output:
                raise AssertionError(f"[{self.name}] printed no column [{header}].")
        for row in rows:
            for cell in row:
                if str(cell) not in self.output:
                    raise AssertionError(f"[{self.name}] printed no cell [{cell}].")

    def _printed(self) -> str:
        return repr(self.output.strip()) if self.output.strip() else "nothing"

    # --- assertions -------------------------------------------------------------

    def assert_exit_code(self, code: int) -> PendingCommand:
        self.run()
        if self.exit_code != code:
            raise AssertionError(
                f"[{self.name}] exited {self.exit_code}, not {code}. It printed: {self._printed()}."
            )
        return self

    def assert_not_exit_code(self, code: int) -> PendingCommand:
        self.run()
        if self.exit_code == code:
            raise AssertionError(f"[{self.name}] exited {code}, and should not have.")
        return self

    def assert_successful(self) -> PendingCommand:
        return self.assert_exit_code(Command.SUCCESS)

    def assert_ok(self) -> PendingCommand:
        return self.assert_successful()

    def assert_failed(self) -> PendingCommand:
        self.run()
        if self.exit_code == Command.SUCCESS:
            raise AssertionError(
                f"[{self.name}] succeeded, and should not have. It printed: {self._printed()}."
            )
        return self

    def assert_output_contains(self, text: str) -> PendingCommand:
        self.run()
        if text not in self.output:
            raise AssertionError(
                f"[{self.name}] never printed [{text}]. It printed: {self._printed()}."
            )
        return self

    def assert_asked(self, question: str) -> PendingCommand:
        self.run()
        if not any(question in asked for asked in self._answers.asked):
            asked = ", ".join(self._answers.asked) or "nothing"
            raise AssertionError(f"[{self.name}] never asked [{question}]. It asked: {asked}.")
        return self

    def assert_nothing_asked(self) -> PendingCommand:
        self.run()
        if self._answers.asked:
            raise AssertionError(f"[{self.name}] asked: {', '.join(self._answers.asked)}.")
        return self

    def __repr__(self) -> str:
        state = "not run" if self.exit_code == _NOT_RUN else f"exited {self.exit_code}"
        return f"PendingCommand({self.name!r}, {state})"


def _split(given: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """`{"name": "x", "--force": True}` — the way Laravel spells both at once."""
    arguments: dict[str, Any] = {}
    options: dict[str, Any] = {}
    for key, value in given.items():
        if key.startswith("--"):
            options[key[2:].replace("-", "_")] = value
        else:
            arguments[key] = value
    return arguments, options


def smith(
    command: str,
    arguments: Mapping[str, Any] | None = None,
    *,
    app: Any = None,
    kernel: Any = None,
) -> PendingCommand:
    """Run a Smith command under test (Laravel's `$this->artisan()` parity)."""
    return PendingCommand(command, arguments, app=app, kernel=kernel)
