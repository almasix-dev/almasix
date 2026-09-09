"""M21 Processes — façade, pending process, results, async, pools, pipes, fakes."""

from __future__ import annotations

import signal
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from almasix.framework.application import Application
from almasix.process import (
    Factory,
    InvokedProcess,
    OutOfFakeProcesses,
    PendingProcess,
    Process,
    ProcessException,
    ProcessFailedException,
    ProcessNotStartedException,
    ProcessPoolResults,
    ProcessResult,
    ProcessServiceProvider,
    ProcessTimedOutException,
    StrayProcessException,
    get_factory,
    set_factory,
)
from almasix.process.fake import FakeProcessResult, normalize_fake

PYTHON = sys.executable


@pytest.fixture(autouse=True)
def fresh_factory() -> Iterator[Factory]:
    """Every test starts with a pristine, process-wide factory."""
    factory = Factory()
    set_factory(factory)
    yield factory
    set_factory(None)


def python(code: str) -> list[str]:
    """A portable command: run this Python snippet in a child interpreter."""
    return [PYTHON, "-c", code]


# --- invoking processes -------------------------------------------------


def test_run_captures_output_and_exit_code() -> None:
    result = Process.run(python("print('hello')"))
    assert result.successful()
    assert result.failed() is False
    assert result.exit_code() == 0
    assert result.output() == "hello\n"
    assert result.error_output() == ""
    assert result.see_in_output("hello")
    assert result.see_in_error_output("hello") is False


def test_run_accepts_a_string_command_through_the_shell() -> None:
    result = Process.run("echo shell")
    assert result.output() == "shell\n"
    assert result.command() == "echo shell"


def test_run_records_a_failing_process() -> None:
    result = Process.run(python("import sys; sys.stderr.write('boom'); sys.exit(2)"))
    assert result.failed()
    assert result.exit_code() == 2
    assert result.error_output() == "boom"


def test_working_directory_and_environment(tmp_path: Path) -> None:
    result = Process.path(tmp_path).run(python("import os; print(os.getcwd())"))
    assert result.output().strip() == str(tmp_path.resolve())

    result = Process.env({"ALMASIX_DEMO": "42"}).run(
        python("import os; print(os.environ['ALMASIX_DEMO'])")
    )
    assert result.output() == "42\n"


def test_environment_is_merged_into_the_inherited_one() -> None:
    result = Process.env({"ALMASIX_DEMO": "1"}).run(
        python("import os; print('PATH' in os.environ)")
    )
    assert result.output() == "True\n"


def test_input_is_written_to_stdin() -> None:
    result = Process.input("piped\n").run(python("import sys; print(sys.stdin.read().strip())"))
    assert result.output() == "piped\n"


def test_input_accepts_bytes() -> None:
    result = Process.input(b"bytes\n").run(python("import sys; print(sys.stdin.read().strip())"))
    assert result.output() == "bytes\n"


def test_run_streams_output_to_a_callback() -> None:
    seen: list[tuple[str, str]] = []
    Process.run(
        python("import sys; print('out'); sys.stderr.write('err\\n')"),
        lambda kind, chunk: seen.append((kind, chunk)),
    )
    assert ("out", "out\n") in seen
    assert ("err", "err\n") in seen


def test_quietly_suppresses_the_output_callback_but_still_captures() -> None:
    seen: list[str] = []
    result = Process.quietly().run(python("print('quiet')"), lambda _k, c: seen.append(c))
    assert seen == []
    assert result.output() == "quiet\n"
    assert Process.quietly().is_quiet()


def test_tty_inherits_the_terminal_and_captures_nothing() -> None:
    result = Process.tty().run(python("print('tty')"))
    assert result.successful()
    assert result.output() == ""
    assert Process.tty().uses_tty()
    assert Process.tty(False).uses_tty() is False


def test_options_reach_popen() -> None:
    result = Process.options({"universal_newlines": True}).run(python("print('opts')"))
    assert result.output() == "opts\n"


def test_a_pending_process_reports_its_configuration(tmp_path: Path) -> None:
    pending = (
        Process.command("echo hi")
        .path(tmp_path)
        .timeout(5)
        .idle_timeout(2)
        .env({"A": "B"})
        .input("x")
    )
    assert pending.command_line() == "echo hi"
    assert pending.described_command == "echo hi"
    assert pending.working_directory() == tmp_path
    assert pending.timeout_seconds() == 5
    assert pending.idle_timeout_seconds() == 2
    assert pending.environment() == {"A": "B"}
    assert pending.input_content() == "x"
    assert Process.forever().timeout_seconds() is None


def test_pending_processes_are_immutable_between_fluent_calls() -> None:
    base = Process.timeout(30)
    assert base.timeout(1).timeout_seconds() == 1
    assert base.timeout_seconds() == 30


def test_running_without_a_command_is_an_error() -> None:
    with pytest.raises(ProcessNotStartedException):
        Process.pending().run()
    with pytest.raises(ProcessNotStartedException):
        Process.pending().start()


def test_when_and_unless_configure_conditionally() -> None:
    assert Process.when(True, lambda p, _v: p.timeout(1)).timeout_seconds() == 1
    assert Process.when(False, lambda p, _v: p.timeout(1)).timeout_seconds() == 60
    assert (
        Process.when(
            False, lambda p, _v: p.timeout(1), lambda p, _v: p.timeout(2)
        ).timeout_seconds()
        == 2
    )
    assert Process.unless(False, lambda p, _v: p.timeout(3)).timeout_seconds() == 3
    assert (
        Process.when(
            lambda p: p.timeout_seconds() == 60, lambda p, _v: p.timeout(4)
        ).timeout_seconds()
        == 4
    )
    # A callback that returns nothing leaves the process untouched.
    assert Process.when(True, lambda _p, _v: None).timeout_seconds() == 60


# --- results ------------------------------------------------------------


def test_throw_raises_only_on_failure() -> None:
    ok = ProcessResult("cmd", 0, "out")
    assert ok.throw() is ok
    assert ok.throw_if(True) is ok

    failed = ProcessResult("cmd", 1, "out", "err")
    with pytest.raises(ProcessFailedException) as excinfo:
        failed.throw()
    message = str(excinfo.value)
    assert "Exit Code: 1" in message
    assert "Output:\nout" in message
    assert "Error Output:\nerr" in message
    # The exception proxies the result it carries.
    assert excinfo.value.exit_code() == 1
    assert excinfo.value.result is failed


def test_throw_invokes_the_callback_before_raising() -> None:
    seen: list[str] = []
    with pytest.raises(ProcessFailedException):
        ProcessResult("cmd", 1).throw(lambda result, exc: seen.append(result.command()))
    assert seen == ["cmd"]


def test_throw_if_and_throw_unless_accept_values_and_callables() -> None:
    failed = ProcessResult("cmd", 1)
    assert failed.throw_if(False) is failed
    assert failed.throw_unless(True) is failed
    with pytest.raises(ProcessFailedException):
        failed.throw_if(lambda result: result.failed())
    with pytest.raises(ProcessFailedException):
        failed.throw_unless(lambda result: result.successful())


def test_result_repr_names_the_command() -> None:
    assert "echo hi" in repr(ProcessResult("echo hi", 0))


# --- asynchronous processes ---------------------------------------------


def test_start_returns_a_running_process_that_can_be_waited_on() -> None:
    invoked = Process.start(python("import time; time.sleep(0.05); print('late')"))
    assert isinstance(invoked, InvokedProcess)
    assert invoked.id() > 0
    result = invoked.wait()
    assert result.output() == "late\n"
    assert invoked.running() is False


def test_wait_accepts_an_output_callback() -> None:
    seen: list[str] = []
    Process.start(python("print('streamed')")).wait(lambda _kind, chunk: seen.append(chunk))
    assert "streamed\n" in seen


def test_latest_output_only_returns_new_chunks() -> None:
    invoked = Process.start(python("print('a'); print('b')"))
    invoked.wait()
    assert invoked.latest_output() == "a\nb\n"
    assert invoked.latest_output() == ""
    assert invoked.output() == "a\nb\n"


def test_latest_error_output_only_returns_new_chunks() -> None:
    invoked = Process.start(python("import sys; sys.stderr.write('e\\n')"))
    invoked.wait()
    assert invoked.latest_error_output() == "e\n"
    assert invoked.latest_error_output() == ""
    assert invoked.error_output() == "e\n"


def test_signal_and_stop_end_a_long_process() -> None:
    invoked = Process.forever().start(python("import time; time.sleep(30)"))
    invoked.signal(signal.SIGTERM)
    invoked.wait()
    assert invoked.running() is False

    invoked = Process.forever().start(python("import time; time.sleep(30)"))
    invoked.stop(timeout=1)
    assert invoked.running() is False


def test_stop_kills_a_process_that_ignores_sigterm() -> None:
    ignoring = python(
        "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "print('ready', flush=True); time.sleep(30)"
    )
    invoked = Process.forever().start(ignoring)
    while not invoked.output():
        pass
    invoked.stop(timeout=0.2)
    assert invoked.running() is False


# --- timeouts -----------------------------------------------------------


def test_timeout_raises_and_carries_the_partial_result() -> None:
    with pytest.raises(ProcessTimedOutException) as excinfo:
        Process.timeout(0.2).run(python("import time; print('early', flush=True); time.sleep(30)"))
    assert "exceeded the timeout of 0.2 seconds" in str(excinfo.value)
    assert excinfo.value.result is not None
    assert excinfo.value.result.output() == "early\n"


def test_idle_timeout_raises_when_output_stalls() -> None:
    with pytest.raises(ProcessTimedOutException) as excinfo:
        Process.forever().idle_timeout(0.2).run(python("import time; time.sleep(30)"))
    assert "idle timeout" in str(excinfo.value)


def test_a_started_process_also_honours_its_timeout() -> None:
    invoked = Process.timeout(0.2).start(python("import time; time.sleep(30)"))
    with pytest.raises(ProcessTimedOutException):
        invoked.wait()
    assert invoked.running() is False


def test_forever_lets_a_slow_process_finish() -> None:
    result = Process.forever().run(python("import time; time.sleep(0.05); print('done')"))
    assert result.output() == "done\n"


# --- pools --------------------------------------------------------------


def test_concurrently_runs_processes_and_keys_results() -> None:
    results = Process.concurrently(
        lambda pool: [
            pool.command(python("print('first')")),
            pool.as_("second").command(python("print('second')")),
        ]
    )
    assert isinstance(results, ProcessPoolResults)
    assert results[0].output() == "first\n"
    assert results["second"].output() == "second\n"
    assert results[1].output() == "second\n"
    assert len(results) == 2
    assert results.keys() == [0, "second"]
    assert results.successful()
    assert results.failed() is False
    assert results.collect().count() == 2
    assert results.output() == ["first\n", "second\n"]
    assert [r.output() for r in results] == ["first\n", "second\n"]


def test_pool_results_report_failure() -> None:
    results = Process.concurrently(lambda pool: [pool.command(python("import sys; sys.exit(1)"))])
    assert results.failed()


def test_pool_processes_keep_the_full_pending_fluency(tmp_path: Path) -> None:
    results = Process.concurrently(
        lambda pool: [
            pool.as_("pwd")
            .path(tmp_path)
            .env({"X": "1"})
            .timeout(10)
            .command(python("import os; print(os.getcwd())"))
        ]
    )
    assert results["pwd"].output().strip() == str(tmp_path.resolve())


def test_pool_start_reports_running_processes_and_streams_keys() -> None:
    chunks: list[tuple[str, str, object]] = []
    pool = Process.pool(
        lambda pool: [
            pool.as_("a").command(python("import time; time.sleep(0.05); print('a')")),
            pool.as_("b").command(python("print('b')")),
        ]
    )
    assert len(pool) == 2
    assert len(pool.pending()) == 2
    invoked = pool.start(lambda kind, chunk, key: chunks.append((kind, chunk, key)))
    assert invoked.total() == 2
    assert len(invoked) == 2
    assert invoked["a"].id() > 0
    assert [p.id() for p in invoked] != []
    while invoked.running().is_not_empty():
        pass
    results = invoked.wait()
    assert results["b"].output() == "b\n"
    assert ("out", "a\n", "a") in chunks


def test_pool_run_is_start_then_wait() -> None:
    results = Process.pool(lambda pool: pool.command(python("print('x')"))).run()
    assert results[0].output() == "x\n"


def test_pool_signal_and_stop_reach_every_process() -> None:
    pool = Process.pool(
        lambda pool: [
            pool.command(python("import time; time.sleep(30)")),
            pool.command(python("import time; time.sleep(30)")),
        ]
    )
    invoked = pool.start()
    invoked.signal(signal.SIGTERM)
    invoked.wait()
    assert invoked.running().is_empty()

    invoked = Process.pool(lambda pool: pool.command(python("import time; time.sleep(30)"))).start()
    invoked.stop(timeout=1)
    assert invoked.running().is_empty()


def test_unknown_pool_keys_raise() -> None:
    results = Process.concurrently(lambda pool: pool.command(python("print('x')")))
    with pytest.raises(KeyError):
        results["nope"]


def test_pool_proxies_non_callable_attributes() -> None:
    pool = Process.pool(lambda pool: pool.command("echo hi"))
    assert pool.pending()[0].described_command == "echo hi"
    with pytest.raises(AttributeError):
        pool._missing


def test_pool_process_rejects_private_attributes() -> None:
    pool = Process.pool(lambda pool: None)
    process = pool.process()
    assert process.described_command == ""
    with pytest.raises(AttributeError):
        process._nope


# --- pipes --------------------------------------------------------------


def test_pipe_feeds_each_command_into_the_next() -> None:
    result = Process.pipe(
        [
            python("print('hello world')"),
            python("import sys; print(sys.stdin.read().upper().strip())"),
        ]
    )
    assert result.output() == "HELLO WORLD\n"


def test_pipe_accepts_a_callable_and_names_stages() -> None:
    seen: list[object] = []
    result = Process.pipe(
        lambda pipe: [
            pipe.as_("greet").command(python("print('hi')")),
            pipe.as_("shout").command(
                python("import sys; print(sys.stdin.read().upper().strip())")
            ),
        ],
        lambda _kind, _chunk, key: seen.append(key),
    )
    assert result.output() == "HI\n"
    assert "shout" in seen


def test_pipe_short_circuits_on_failure() -> None:
    result = Process.pipe([python("import sys; sys.exit(3)"), python("print('never')")])
    assert result.exit_code() == 3
    assert result.output() == ""


def test_an_empty_pipe_is_an_error() -> None:
    with pytest.raises(ValueError, match="at least one command"):
        Process.pipe([])


def test_pipe_rejects_private_attributes() -> None:
    from almasix.process.pipe import Pipe

    pipe = Pipe(get_factory())
    with pytest.raises(AttributeError):
        pipe._nope


# --- fakes --------------------------------------------------------------


def test_fake_everything_returns_empty_successful_results() -> None:
    Process.fake()
    result = Process.run("anything at all")
    assert result.successful()
    assert result.output() == ""


def test_fake_map_matches_commands_with_wildcards() -> None:
    Process.fake(
        {
            "cat *": "file contents",
            "bash *": Process.result(error_output="failed", exit_code=1),
        }
    )
    assert Process.run("cat notes.txt").output() == "file contents\n"
    failed = Process.run("bash deploy.sh")
    assert failed.exit_code() == 1
    assert failed.error_output() == "failed\n"


def test_fake_output_accepts_a_list_of_lines() -> None:
    Process.fake({"ls": Process.result(output=["one", "two"])})
    assert Process.run("ls").output() == "one\ntwo\n"


def test_unmatched_commands_still_run_for_real() -> None:
    Process.fake({"cat *": "faked"})
    assert Process.run(python("print('real')")).output() == "real\n"


def test_prevent_stray_processes_blocks_unmatched_commands() -> None:
    Process.fake({"cat *": "faked"})
    Process.prevent_stray_processes()
    with pytest.raises(StrayProcessException, match=r"\[rm -rf /\]"):
        Process.run("rm -rf /")
    Process.allow_stray_processes()
    assert Process.run(python("print('real')")).output() == "real\n"


def test_fake_accepts_a_callable_stub() -> None:
    Process.fake(lambda process: Process.result(output=process.described_command))
    assert Process.run("echo one").output() == "echo one\n"


def test_fake_callable_may_return_a_plain_string_or_none() -> None:
    Process.fake({"a": lambda _p: "text", "b": lambda _p: None})
    assert Process.run("a").output() == "text\n"
    assert Process.run("b").successful()


def test_fake_accepts_a_real_process_result() -> None:
    Process.fake({"x": ProcessResult("x", 7, "out", "err")})
    result = Process.run("x")
    assert result.exit_code() == 7
    assert result.output() == "out\n"


def test_unsupported_stubs_are_rejected() -> None:
    Process.fake({"x": 12345})
    with pytest.raises(ProcessException, match="Unsupported fake"):
        Process.run("x")


def test_fake_sequence_pops_in_order() -> None:
    Process.fake({"flaky": Process.sequence().push_result("", "nope", 1).push_output("recovered")})
    assert Process.run("flaky").failed()
    assert Process.run("flaky").output() == "recovered\n"
    Process.assert_sequences_are_empty()


def test_a_drained_sequence_raises() -> None:
    Process.fake({"once": Process.sequence().push_output("only")})
    Process.run("once")
    with pytest.raises(OutOfFakeProcesses):
        Process.run("once")


def test_a_sequence_can_answer_forever() -> None:
    Process.fake({"loop": Process.sequence().push_output("first").dont_fail_when_empty()})
    assert Process.run("loop").output() == "first\n"
    assert Process.run("loop").output() == ""

    Process.fake({"other": Process.sequence().when_empty(Process.result(output="fallback"))})
    assert Process.run("other").output() == "fallback\n"


def test_fail_when_empty_restores_the_default() -> None:
    sequence = Process.sequence().dont_fail_when_empty().fail_when_empty()
    Process.fake({"strict": sequence})
    with pytest.raises(OutOfFakeProcesses):
        Process.run("strict")


def test_fake_sequence_helper_attaches_to_the_factory() -> None:
    Process.fake_sequence("git *").push_output("a").push_error_output("b")
    assert Process.run("git status").output() == "a\n"
    assert Process.run("git push").failed()

    Process.fake_sequence().push_output("any")
    assert Process.run("whatever").output() == "any\n"


def test_unconsumed_sequences_fail_the_assertion() -> None:
    Process.fake({"x": Process.sequence().push_output("unused")})
    with pytest.raises(AssertionError, match="queued fake processes"):
        Process.assert_sequences_are_empty()


def test_describe_scripts_an_asynchronous_fake() -> None:
    Process.fake(
        {
            "bash *": Process.describe()
            .id(4242)
            .output("first")
            .output("second")
            .error_output("warning")
            .exit_code(3)
            .iterations(4)
        }
    )
    invoked = Process.start("bash import.sh")
    assert invoked.id() == 4242
    checks = 0
    while invoked.running():
        checks += 1
    assert checks == 4
    assert invoked.output() == "first\nsecond\n"
    assert invoked.error_output() == "warning\n"
    result = invoked.wait()
    assert result.exit_code() == 3


def test_describe_replaces_previously_scripted_output() -> None:
    description = (
        Process.describe()
        .output("old")
        .error_output("old error")
        .replace_output("new")
        .replace_error_output("new error")
    )
    Process.fake({"cmd": description})
    result = Process.run("cmd")
    assert result.output() == "new\n"
    assert result.error_output() == "new error\n"


def test_runs_for_is_an_alias_of_iterations() -> None:
    Process.fake({"cmd": Process.describe().runs_for(iterations=2)})
    invoked = Process.start("cmd")
    checks = 0
    while invoked.running():
        checks += 1
    assert checks == 2


def test_a_faked_started_process_streams_to_its_callback() -> None:
    Process.fake({"cmd": Process.describe().output("chunk")})
    seen: list[str] = []
    Process.start("cmd").wait(lambda _kind, chunk: seen.append(chunk))
    assert seen == ["chunk\n"]


def test_faked_processes_record_signals_and_stops() -> None:
    Process.fake({"cmd": Process.describe().output("x").iterations(5)})
    invoked = Process.start("cmd")
    invoked.signal(signal.SIGKILL)
    invoked.stop(sig=signal.SIGTERM)
    assert invoked.running() is False


def test_fakes_work_in_pools_and_pipes() -> None:
    Process.fake({"one": "1", "two": "2"})
    results = Process.concurrently(
        lambda pool: [pool.command("one"), pool.as_("second").command("two")]
    )
    assert results[0].output() == "1\n"
    assert results["second"].output() == "2\n"

    Process.fake({"a": "A", "b": "B"})
    assert Process.pipe(["a", "b"]).output() == "B\n"


def test_normalize_fake_defends_against_self_returning_callbacks() -> None:
    pending = PendingProcess(None).command("x")

    def loop(_process: object) -> object:
        return loop

    with pytest.raises(ProcessException, match="returned itself"):
        normalize_fake(loop, pending)


def test_fake_process_result_as_handle_carries_both_streams() -> None:
    handle = FakeProcessResult("out", "err", 1).as_handle("cmd")
    assert handle.wait() == 1
    assert handle.output() == "out\n"
    assert handle.error_output() == "err\n"


# --- assertions ---------------------------------------------------------


def test_assertions_match_patterns_and_callables() -> None:
    Process.fake()
    Process.run("ls -la")
    Process.run("cat notes.txt")

    Process.assert_ran("ls -la")
    Process.assert_ran("cat *")
    Process.assert_ran(lambda process: process.described_command == "ls -la")
    Process.assert_ran(lambda process, result: result.successful())
    Process.assert_ran_times("ls *", 1)
    Process.assert_didnt_run("rm *")

    with pytest.raises(AssertionError, match="not invoked"):
        Process.assert_ran("rm *")
    with pytest.raises(AssertionError, match="unexpected process"):
        Process.assert_didnt_run("ls *")
    with pytest.raises(AssertionError, match="it ran 1"):
        Process.assert_ran_times("ls *", 3)


def test_assert_nothing_ran() -> None:
    Process.assert_nothing_ran()
    Process.fake()
    Process.run("ls")
    with pytest.raises(AssertionError, match="none were expected"):
        Process.assert_nothing_ran()


def test_recorded_returns_process_and_result_pairs() -> None:
    Process.fake({"ls": "listing"})
    Process.run("ls")
    pairs = Process.recorded()
    assert len(pairs) == 1
    process, result = pairs[0]
    assert process.described_command == "ls"
    assert result.output() == "listing\n"
    assert Process.recorded("nope") == []


def test_started_processes_are_recorded_and_updated_on_wait() -> None:
    Process.fake({"cmd": Process.describe().output("done").exit_code(0)})
    invoked = Process.start("cmd")
    assert len(Process.recorded()) == 1
    assert Process.recorded()[0][1].exit_code() is None
    invoked.wait()
    assert Process.recorded()[0][1].exit_code() == 0
    assert Process.recorded()[0][1].output() == "done\n"


def test_a_recorded_entry_unpacks_like_a_pair() -> None:
    Process.fake()
    Process.run("ls")
    entry = Process.factory()._recorded[0]
    process, result = entry
    assert process.described_command == "ls"
    assert result.successful()


def test_a_process_without_a_factory_records_nothing() -> None:
    result = PendingProcess(None).run("echo detached")
    assert result.output() == "detached\n"


# --- container wiring ---------------------------------------------------


def test_the_provider_binds_and_boots_the_factory() -> None:
    app = Application(base_path=Path.cwd())
    provider = ProcessServiceProvider(app)
    provider.register()
    factory = app.container.resolve(Factory)
    assert app.container.resolve("process") is factory
    provider.boot()
    assert get_factory() is factory


def test_boot_falls_back_to_the_global_factory() -> None:
    app = Application(base_path=Path.cwd())
    provider = ProcessServiceProvider(app)
    provider.boot()
    assert get_factory() is not None


def test_the_facade_exposes_the_factory() -> None:
    assert Process.factory() is get_factory()
    assert isinstance(Process.pending(), PendingProcess)


def test_get_factory_creates_one_on_demand() -> None:
    set_factory(None)
    assert isinstance(get_factory(), Factory)


def test_the_facade_forwards_every_configuration_call() -> None:
    assert Process.idle_timeout(3).idle_timeout_seconds() == 3
    assert Process.options({"close_fds": True}).described_command == ""
    assert Process.command("echo hi").described_command == "echo hi"


# --- edges --------------------------------------------------------------


def test_match_fake_returns_nothing_when_not_faking() -> None:
    factory = Factory()
    assert factory.match_fake(PendingProcess(factory).command("ls")) is None


def test_signal_and_stop_are_harmless_after_a_process_exits() -> None:
    invoked = Process.run(python("print('bye')"))
    assert invoked.successful()

    started = Process.start(python("print('bye')"))
    started.wait()
    started.signal(signal.SIGTERM)
    assert started.stop() == 0


def test_timed_out_kind_reports_nothing_before_a_deadline() -> None:
    import time

    from almasix.process.runner import ProcessHandle

    handle = ProcessHandle(python("print('x')"))
    handle.wait()
    assert handle.timed_out_kind(time.monotonic(), 30, 30) is None
    assert handle.timed_out_kind(time.monotonic(), None, None) is None


def test_a_factory_less_process_can_be_started() -> None:
    invoked = PendingProcess(None).start(python("print('detached')"))
    assert invoked.wait().output() == "detached\n"


def test_unless_accepts_a_callable_condition() -> None:
    pending = Process.unless(lambda p: p.timeout_seconds() == 1, lambda p, _v: p.timeout(9))
    assert pending.timeout_seconds() == 9


def test_pool_processes_return_plain_values_from_non_fluent_calls() -> None:
    pool = Process.pool(lambda pool: None)
    process = pool.process().command("echo hi")
    assert process.timeout_seconds() == 60


def test_a_pipe_counts_its_stages() -> None:
    from almasix.process.pipe import Pipe

    pipe = Pipe(get_factory())
    pipe.command("a")
    pipe.command("b")
    assert len(pipe) == 2


def test_a_fake_handle_streams_latest_output_in_chunks() -> None:
    Process.fake({"cmd": Process.describe().output("a").error_output("b").iterations(2)})
    invoked = Process.start("cmd")
    while invoked.running():
        pass
    assert invoked.latest_output() == "a\n"
    assert invoked.latest_output() == ""
    assert invoked.latest_error_output() == "b\n"
    assert invoked.latest_error_output() == ""


def test_a_fake_handle_never_times_out() -> None:
    Process.fake({"cmd": Process.describe().output("a")})
    invoked = Process.timeout(0.0001).start("cmd")
    assert invoked.wait().successful()


def test_a_fake_result_with_only_error_output() -> None:
    Process.fake({"cmd": Process.result(error_output="only errors", exit_code=1)})
    invoked = Process.start("cmd")
    result = invoked.wait()
    assert result.output() == ""
    assert result.error_output() == "only errors\n"


def test_a_fake_stub_may_be_a_tuple_of_lines() -> None:
    Process.fake({"cmd": ("one", "two")})
    assert Process.run("cmd").output() == "one\ntwo\n"


def test_a_fake_handle_answers_the_whole_handle_contract() -> None:
    handle = Process.describe().output("x").exit_code(4).as_handle("cmd")
    assert handle.exit_code() is None
    assert handle.timed_out_kind(0.0, 1, 1) is None
    assert handle.stop() == 4
    assert handle.stopped is True
    assert handle.signals == []
