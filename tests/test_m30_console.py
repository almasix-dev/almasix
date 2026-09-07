"""M30 — Grail Console exhaust (Artisan parity)."""

from __future__ import annotations

import signal
from pathlib import Path
from typing import Any

import pytest

from avalon.console.command import (
    Command,
    Isolatable,
    PromptsForMissingInput,
    parse_signature,
)
from avalon.console.events import CommandFinished, CommandStarting, ConsoleStarting
from avalon.console.exceptions import CommandFailed, CommandNotFound
from avalon.console.facade import Artisan, _pending
from avalon.console.kernel import ConsoleKernel, _parse_argv
from avalon.events.facade import Event
from avalon.framework import Application


@pytest.fixture(autouse=True)
def _isolated_facades() -> Any:
    """Each test gets a clean Artisan kernel, closure registry, and listeners."""
    Artisan.set_kernel(None)
    _pending.clear()
    Event.flush()
    yield
    Artisan.set_kernel(None)
    _pending.clear()
    Event.flush()


class InjectedService:
    """Container-resolved dependency for closure commands."""

    value = "injected"


def kernel_for(tmp_path: Path, *commands: type[Command]) -> ConsoleKernel:
    kernel = ConsoleKernel(Application(tmp_path))
    for command_cls in commands:
        kernel.register(command_cls)
    Artisan.set_kernel(kernel)
    return kernel


# --- signature parsing --------------------------------------------------


def test_signature_supports_shortcuts_arrays_and_descriptions() -> None:
    name, arguments, options = parse_signature(
        "mail:send {user : The user ID} {tags?*} {--Q|queue=bulk : Which queue} {--id=*}"
    )
    assert name == "mail:send"
    assert arguments[0] == {
        "name": "user",
        "description": "The user ID",
        "optional": False,
        "array": False,
        "variadic": False,
        "default": None,
    }
    assert arguments[1]["array"] is True
    assert arguments[1]["optional"] is True
    assert options[0]["shortcut"] == "Q"
    assert options[0]["default"] == "bulk"
    assert options[0]["description"] == "Which queue"
    assert options[1] == {
        "name": "id",
        "shortcut": "",
        "description": "",
        "default": [],
        "is_flag": False,
        "array": True,
    }


def test_signature_argument_forms() -> None:
    _name, arguments, _options = parse_signature(
        "demo {required} {optional?} {defaulted=blue} {listed=*a,b} {legacy...}"
    )
    forms = {argument["name"]: argument for argument in arguments}
    assert forms["required"]["optional"] is False
    assert forms["optional"]["optional"] is True
    assert forms["defaulted"]["default"] == "blue"
    assert forms["listed"]["array"] is True
    assert forms["listed"]["default"] == ["a", "b"]
    assert forms["legacy"]["array"] is True


def test_signature_option_forms() -> None:
    _name, _arguments, options = parse_signature(
        "demo {--flag} {--value=} {--sized=10} {--many=*} {--seeded=*x,y}"
    )
    forms = {option["name"]: option for option in options}
    assert forms["flag"]["is_flag"] is True
    assert forms["value"]["default"] is None and forms["value"]["is_flag"] is False
    assert forms["sized"]["default"] == "10"
    assert forms["many"]["default"] == []
    assert forms["seeded"]["default"] == ["x", "y"]


def test_signature_rejects_invalid_tokens() -> None:
    with pytest.raises(ValueError, match="must include a name"):
        parse_signature("  ")
    with pytest.raises(ValueError, match="must include a name"):
        parse_signature("{orphan}")
    with pytest.raises(ValueError, match="Invalid signature token"):
        parse_signature("demo {bad token}")
    with pytest.raises(ValueError, match="Invalid signature token"):
        parse_signature("demo stray {ok}")
    with pytest.raises(ValueError, match="Invalid signature token"):
        parse_signature("demo {ok} stray")
    with pytest.raises(ValueError, match="Empty signature token"):
        parse_signature("demo {}")


# --- argv parsing -------------------------------------------------------


def _meta(signature: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _name, arguments, options = parse_signature(signature)
    return arguments, options


def test_argv_handles_shortcuts_and_arrays() -> None:
    arguments_meta, options_meta = _meta("demo {name} {--Q|queue=} {--id=*} {--force}")
    arguments, options = _parse_argv(
        ["ada", "-Q", "high", "--id=1", "--id", "2", "--force"],
        arguments_meta,
        options_meta,
    )
    assert arguments == {"name": "ada"}
    assert options == {"queue": "high", "id": ["1", "2"], "force": True}


def test_argv_accepts_attached_shortcut_values_and_terminator() -> None:
    arguments_meta, options_meta = _meta("demo {rest*} {--Q|queue=}")
    arguments, options = _parse_argv(
        ["-Qbulk", "--", "--not-an-option"], arguments_meta, options_meta
    )
    assert options["queue"] == "bulk"
    assert arguments["rest"] == ["--not-an-option"]


def test_argv_defaults_unknown_options_and_missing_arguments() -> None:
    arguments_meta, options_meta = _meta("demo {name?} {tags=*a} {--flag} {--value=v}")
    arguments, options = _parse_argv(["--unknown=x", "--bare"], arguments_meta, options_meta)
    assert arguments == {"name": None, "tags": ["a"]}
    assert options == {"flag": False, "value": "v", "unknown": "x", "bare": True}


def test_argv_requires_required_arguments() -> None:
    arguments_meta, options_meta = _meta("demo {name}")
    with pytest.raises(Exception, match="Missing required argument"):
        _parse_argv([], arguments_meta, options_meta)
    arguments, _options = _parse_argv([], arguments_meta, options_meta, prompt_for_missing=True)
    assert arguments == {}


def test_argv_value_option_consumes_next_token_or_becomes_true() -> None:
    arguments_meta, options_meta = _meta("demo {--value=}")
    _arguments, options = _parse_argv(["--value", "here"], arguments_meta, options_meta)
    assert options["value"] == "here"
    _arguments, options = _parse_argv(["--value"], arguments_meta, options_meta)
    assert options["value"] is True


# --- command surface ----------------------------------------------------


class SurfaceCommand(Command):
    signature = "surface {name} {--loud}"
    description = "Exercises the output surface"

    def handle(self) -> int:
        self.line("line")
        self.info("info")
        self.comment("comment")
        self.question("question")
        self.warn("warn")
        self.error("error")
        self.success("success")
        self.alert("alert")
        self.new_line(2)
        self.table(["a"], [["1"]])
        assert self.arguments() == {"name": self.argument("name")}
        assert self.options()["loud"] is self.option("loud")
        assert self.has_option("loud") and not self.has_option("nope")
        return self.SUCCESS


def test_command_output_and_input_surface(capsys: pytest.CaptureFixture[str]) -> None:
    assert SurfaceCommand().run({"name": "ada"}, {"loud": True}) == 0
    out = capsys.readouterr()
    assert "alert" in out.out
    assert "error" in out.err


def test_exit_code_constants_and_fail() -> None:
    class Failing(Command):
        signature = "failing"

        def handle(self) -> int:
            self.fail("nope")
            return self.SUCCESS  # pragma: no cover - fail() raises

    assert (Command.SUCCESS, Command.FAILURE, Command.INVALID) == (0, 1, 2)
    assert Failing().run() == Command.FAILURE

    class SilentlyFailing(Command):
        signature = "silent-fail"

        def handle(self) -> int:
            raise CommandFailed

    assert SilentlyFailing().run() == Command.FAILURE


def test_with_progress_bar_maps_items(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AVALON_PROMPTS_INTERACTIVE", "0")
    command = Command()
    assert command.with_progress_bar([1, 2, 3], lambda item: item * 2) == [2, 4, 6]
    assert command.with_progress_bar([1]) == [1]


def test_choice_supports_multiple(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_multiselect(question: str, choices: Any, default: Any = None) -> Any:
        captured["default"] = default
        return ["a"]

    monkeypatch.setattr("avalon.console.prompts.multiselect", fake_multiselect)
    command = Command()
    assert command.choice("pick", ["a", "b"], "a", multiple=True) == ["a"]
    assert captured["default"] == ["a"]
    assert command.choice("pick", ["a"], ["a"], multiple=True) == ["a"]
    assert captured["default"] == ["a"]
    assert command.choice("pick", ["a"], None, multiple=True) == ["a"]
    assert captured["default"] == []


def test_trap_registers_and_survives_unavailable_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []
    command = Command()
    command.trap(signal.SIGUSR1, seen.append)
    handler = signal.getsignal(signal.SIGUSR1)
    assert callable(handler)
    handler(signal.SIGUSR1, None)
    assert seen == [signal.SIGUSR1]
    signal.signal(signal.SIGUSR1, signal.SIG_DFL)

    def explode(*_args: Any) -> None:
        raise ValueError("signal only works in main thread")

    monkeypatch.setattr(signal, "signal", explode)
    command.trap([signal.SIGUSR1, signal.SIGUSR2], seen.append)  # no raise


# --- Artisan façade -----------------------------------------------------


class EchoCommand(Command):
    signature = "echo {word} {--upper} {--tag=*}"
    description = "Echo a word"

    def handle(self) -> int:
        word = str(self.argument("word"))
        tags = self.option("tag") or []
        self.line(word.upper() if self.option("upper") else word)
        for tag in tags:
            self.line(f"tag:{tag}")
        return self.SUCCESS


def test_artisan_call_with_argv_string(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    kernel_for(tmp_path, EchoCommand)
    assert Artisan.call("echo hello --upper") == 0
    assert Artisan.output().strip() == "HELLO"
    assert capsys.readouterr().out.strip() == "HELLO"


def test_artisan_call_with_parameters_including_arrays_and_booleans(tmp_path: Path) -> None:
    kernel_for(tmp_path, EchoCommand)
    code = Artisan.call(
        "echo",
        {"word": "hi", "--upper": True, "--tag": ["a", "b"]},
        silent=True,
    )
    assert code == 0
    assert Artisan.output().splitlines() == ["HI", "tag:a", "tag:b"]
    Artisan.call("echo", {"word": "hi", "--upper": False}, silent=True)
    assert Artisan.output().strip() == "hi"
    Artisan.call("echo", {"word": ["listed"]}, silent=True)
    assert Artisan.output().strip() == "listed"
    Artisan.call("echo", {"word": "tagged", "--tag": "solo"}, silent=True)
    assert Artisan.output().splitlines() == ["tagged", "tag:solo"]


def test_artisan_call_silently_produces_no_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel_for(tmp_path, EchoCommand)
    assert Artisan.call_silently("echo quiet") == 0
    assert capsys.readouterr().out == ""
    assert Artisan.output().strip() == "quiet"


def test_artisan_registry_helpers(tmp_path: Path) -> None:
    kernel_for(tmp_path, EchoCommand)
    assert Artisan.has("echo") is True
    assert Artisan.has("missing") is False
    assert "echo" in Artisan.all()
    with pytest.raises(ValueError, match="command name is required"):
        Artisan.call("   ")


def test_artisan_kernel_resolves_from_application(tmp_path: Path) -> None:
    application = Application(tmp_path)
    kernel = ConsoleKernel(application)
    application.container.instance(ConsoleKernel, kernel)
    Artisan.set_kernel(None)
    assert Artisan.kernel(application) is kernel


def test_artisan_kernel_boots_from_cwd_when_nothing_is_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    booted = ConsoleKernel(Application(tmp_path))
    monkeypatch.setattr(ConsoleKernel, "from_cwd", classmethod(lambda _cls: booted))

    Artisan.set_kernel(None)
    assert Artisan.kernel() is booted

    Artisan.set_kernel(None)
    assert Artisan.kernel(Application(tmp_path)) is booted


def test_signature_parameters_gives_up_on_unsupported_callables() -> None:
    from avalon.console.facade import _signature_parameters, _resolve_parameters

    assert _signature_parameters(print) is not None
    assert _resolve_parameters(Command(), object()) == {}


def test_commands_can_call_other_commands(tmp_path: Path) -> None:
    class Caller(Command):
        signature = "caller"

        def handle(self) -> int:
            assert self.call("echo loud --upper") == 0
            assert self.call_silently("echo quiet") == 0
            return self.SUCCESS

    kernel = kernel_for(tmp_path, EchoCommand, Caller)
    assert kernel.run_command("caller") == 0


# --- closure commands ---------------------------------------------------


def test_closure_commands_register_and_receive_input(tmp_path: Path) -> None:
    kernel = kernel_for(tmp_path)
    seen: dict[str, Any] = {}

    def send(user: str, queue: str, command: Command) -> int:
        seen["user"] = user
        seen["queue"] = queue
        seen["command"] = command.name()
        return 0

    handle = Artisan.command("closure:send {user} {--queue=default}", send)
    handle.purpose("Send a thing")
    assert kernel.commands["closure:send"].description == "Send a thing"
    assert kernel.run_argv("closure:send", ["7", "--queue=bulk"]) == 0
    assert seen == {"user": "7", "queue": "bulk", "command": "closure:send"}


def test_closure_commands_queue_until_a_kernel_exists(tmp_path: Path) -> None:
    Artisan.set_kernel(None)
    Artisan.command("closure:later {--flag}", lambda flag: 0)
    assert _pending
    kernel = ConsoleKernel(Application(tmp_path))
    from avalon.console.facade import drain_pending

    Artisan.set_kernel(kernel)
    drain_pending(kernel)
    assert "closure:later" in kernel.commands
    assert not _pending


def test_closure_command_uses_docstring_and_resolves_dependencies(tmp_path: Path) -> None:
    kernel = kernel_for(tmp_path)
    kernel.app.container.instance(InjectedService, InjectedService())
    seen: dict[str, Any] = {}

    def run(service: InjectedService, missing: str = "fallback") -> int:
        """Documented closure."""
        seen["service"] = service.value
        seen["missing"] = missing
        return 0

    Artisan.command("closure:deps", run)
    assert kernel.commands["closure:deps"].description == "Documented closure."
    assert kernel.run_argv("closure:deps", []) == 0
    assert seen == {"service": "injected", "missing": "fallback"}


def test_closure_command_falls_back_when_an_annotation_cannot_be_evaluated(
    tmp_path: Path,
) -> None:
    class LocalOnly:  # not importable from the module globals
        pass

    kernel = kernel_for(tmp_path)
    seen: dict[str, Any] = {}

    def run(thing: LocalOnly | None = None) -> int:
        seen["thing"] = thing
        return 0

    Artisan.command("closure:local", run)
    assert kernel.run_argv("closure:local", []) == 0
    assert seen == {"thing": None}


def test_closure_command_reports_parameters_it_cannot_fill(tmp_path: Path) -> None:
    kernel = kernel_for(tmp_path)
    Artisan.command("closure:mystery", lambda mystery: 0)
    with pytest.raises(TypeError, match="mystery"):
        kernel.run_argv("closure:mystery", [])


def test_closure_command_skips_unresolvable_parameters(tmp_path: Path) -> None:
    kernel = kernel_for(tmp_path)
    calls: list[str] = []

    def run(*args: Any, **kwargs: Any) -> int:
        calls.append("ran")
        return 0

    Artisan.command("closure:varargs", run)
    assert kernel.run_argv("closure:varargs", []) == 0
    assert calls == ["ran"]


# --- isolatable commands ------------------------------------------------


class IsolatedCommand(Isolatable, Command):
    signature = "isolated:work"
    description = "Isolatable"
    ran = 0

    def handle(self) -> int:
        type(self).ran += 1
        return self.SUCCESS


def test_isolated_command_runs_once_at_a_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from avalon.console import isolation

    # Pin the filesystem backend so a cache store booted by another test
    # cannot change which lock this exercises.
    monkeypatch.setattr(isolation, "_cache_lock", lambda *_a, **_k: None)
    kernel = kernel_for(tmp_path, IsolatedCommand)
    IsolatedCommand.ran = 0
    assert kernel.run_argv("isolated:work", ["--isolated"]) == 0
    assert IsolatedCommand.ran == 1

    from avalon.console import isolation

    held = isolation.acquire("isolated:work", 60, tmp_path)
    assert held is not None
    assert kernel.run_argv("isolated:work", ["--isolated"]) == Command.SUCCESS
    assert kernel.run_argv("isolated:work", ["--isolated=12"]) == 12
    assert IsolatedCommand.ran == 1
    held.release()

    assert kernel.run_argv("isolated:work", []) == 0
    assert IsolatedCommand.ran == 2


def test_isolation_prefers_the_cache_lock(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from avalon.console import isolation

    class FakeLock:
        """Mirrors the CacheLock API (``get`` / ``release``)."""

        released = False

        def get(self) -> bool:
            return True

        def release(self) -> None:
            type(self).released = True

    monkeypatch.setattr(isolation, "_cache_lock", lambda *_a, **_k: FakeLock())
    lock = isolation.acquire("demo", 30, tmp_path)
    assert lock is not None
    lock.release()
    assert FakeLock.released is True

    monkeypatch.setattr(isolation, "_cache_lock", lambda *_a, **_k: None)
    first = isolation.acquire("demo", 30, tmp_path)
    assert first is not None
    assert isolation.acquire("demo", 30, tmp_path) is None
    first.release()


def test_isolation_cache_lock_helper_survives_a_missing_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from avalon.cache.manager import Cache
    from avalon.console import isolation

    def unbooted() -> None:
        raise RuntimeError("cache is not configured")

    monkeypatch.setattr(Cache, "manager", staticmethod(unbooted))
    assert isolation._cache_lock("demo", 30) is None


def test_isolation_uses_the_cache_lock_when_the_cache_is_booted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from avalon.cache.manager import Cache
    from avalon.console import isolation

    sentinel = object()
    monkeypatch.setattr(Cache, "manager", staticmethod(lambda: None))
    monkeypatch.setattr(Cache, "lock", staticmethod(lambda name, seconds=None: sentinel))
    assert isolation._cache_lock("demo", 30) is sentinel


def test_isolation_reports_a_held_cache_lock(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from avalon.console import isolation

    class HeldLock:
        def get(self) -> bool:
            return False

        def release(self) -> None:  # pragma: no cover - never reached
            raise AssertionError("a lock we never took must not be released")

    monkeypatch.setattr(isolation, "_cache_lock", lambda *_a, **_k: HeldLock())
    assert isolation.acquire("demo", 30, tmp_path) is None


# --- prompting for missing input ---------------------------------------


class NeedsInput(PromptsForMissingInput, Command):
    signature = "needs:input {user} {--flag}"
    description = "Prompts for missing input"
    seen: str = ""

    def prompt_for_missing_arguments_using(self) -> dict[str, Any]:
        return {"user": lambda: "prompted"}

    def handle(self) -> int:
        type(self).seen = str(self.argument("user"))
        return self.SUCCESS


def test_missing_arguments_are_prompted_for(tmp_path: Path) -> None:
    kernel = kernel_for(tmp_path, NeedsInput)
    assert kernel.run_argv("needs:input", []) == 0
    assert NeedsInput.seen == "prompted"
    assert kernel.run_argv("needs:input", ["given"]) == 0
    assert NeedsInput.seen == "given"


def test_default_missing_argument_question(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []

    class Plain(PromptsForMissingInput, Command):
        signature = "plain {user_id}"

        def ask(self, question: str, default: str | None = None, *, required: bool = False) -> str:
            asked.append(question)
            return "42"

    assert Plain().prompt_for_missing_argument("user_id") == "42"
    assert asked == ["What is the user id?"]

    class Configured(PromptsForMissingInput, Command):
        signature = "configured {user}"

        def prompt_for_missing_arguments_using(self) -> dict[str, Any]:
            return {"user": "Which user?"}

        def ask(self, question: str, default: str | None = None, *, required: bool = False) -> str:
            asked.append(question)
            return "7"

    assert Configured().prompt_for_missing_argument("user") == "7"
    assert asked[-1] == "Which user?"


# --- events -------------------------------------------------------------


def test_console_events_are_dispatched(tmp_path: Path) -> None:
    starting: list[CommandStarting] = []
    finished: list[CommandFinished] = []
    Event.listen(CommandStarting, starting.append)
    Event.listen(CommandFinished, finished.append)

    kernel = kernel_for(tmp_path, EchoCommand)
    assert kernel.run_argv("echo", ["hi"]) == 0
    assert starting[0].command == "echo"
    assert starting[0].arguments == {"word": "hi"}
    assert finished[0].exit_code == 0


def test_console_starting_is_dispatched_on_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[ConsoleStarting] = []
    Event.listen(ConsoleStarting, seen.append)
    kernel = ConsoleKernel(Application(tmp_path))
    kernel.discover()
    assert seen and "inspire" in seen[0].commands


def test_command_finished_fires_for_dump_and_die(tmp_path: Path) -> None:
    from avalon.debug import DumpAndDie

    class Dumping(Command):
        signature = "dumping"

        def handle(self) -> int:
            raise DumpAndDie(["x"])

    finished: list[CommandFinished] = []
    Event.listen(CommandFinished, finished.append)
    kernel = kernel_for(tmp_path, Dumping)
    assert kernel.run_command("dumping") == 0
    assert finished[0].exit_code == 0


def test_event_dispatch_failures_do_not_break_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("no dispatcher")

    monkeypatch.setattr("avalon.events.facade.Event.dispatch", explode)
    kernel = kernel_for(tmp_path, EchoCommand)
    assert kernel.run_argv("echo", ["hi"]) == 0


# --- kernel errors ------------------------------------------------------


def test_unknown_commands_raise_command_not_found(tmp_path: Path) -> None:
    kernel = kernel_for(tmp_path)
    with pytest.raises(CommandNotFound, match="Command not found: nope"):
        kernel.run_command("nope")
    with pytest.raises(KeyError):
        kernel.run_argv("nope", [])
    assert str(CommandNotFound("nope")) == "Command not found: nope"


def test_isolated_exit_code_falls_back_for_unparsable_values() -> None:
    from avalon.console.kernel import _isolated_exit_code

    assert _isolated_exit_code(True) == Command.SUCCESS
    assert _isolated_exit_code("nonsense") == Command.SUCCESS
    assert _isolated_exit_code("7") == 7
    assert _isolated_exit_code(None) == Command.SUCCESS


# --- queueing commands --------------------------------------------------


def test_artisan_queue_dispatches_a_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from avalon.console.queued import CallQueuedCommand

    kernel_for(tmp_path, EchoCommand)
    dispatched: list[CallQueuedCommand] = []

    async def fake_dispatch(job: CallQueuedCommand) -> str:
        dispatched.append(job)
        return "queued"

    monkeypatch.setattr("avalon.queue.helpers.dispatch", fake_dispatch)
    result = asyncio.run(
        Artisan.queue("echo hi", {"--upper": True}, connection="redis", queue="bulk")
    )
    assert result == "queued"
    job = dispatched[0]
    assert (job.command, job.parameters) == ("echo hi", {"--upper": True})
    assert (job.connection_name(), job.queue_name()) == ("redis", "bulk")
    assert job.should_queue() is True
    assert job.handle() == 0
    assert Artisan.output().strip() == "HI"


def test_queued_command_defaults(tmp_path: Path) -> None:
    from avalon.console.queued import CallQueuedCommand

    kernel_for(tmp_path, EchoCommand)
    job = CallQueuedCommand("echo hi")
    assert job.parameters == {}
    assert job.connection_name() is None
    assert job.queue_name() == "default"


# --- kernel errors ------------------------------------------------------


def test_kernel_reports_command_exceptions(tmp_path: Path) -> None:
    class Broken(Command):
        signature = "broken"

        def handle(self) -> int:
            raise RuntimeError("boom")

    kernel = kernel_for(tmp_path, Broken)
    with pytest.raises(RuntimeError, match="boom"):
        kernel.run_command("broken")
