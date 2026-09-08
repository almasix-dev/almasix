"""Running the schedule — one task, one tick, or a whole minute of seconds."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import io
import subprocess
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from avalon.console.mutex import Mutex
from avalon.console.scheduling.event import Event, call_hook
from avalon.console.scheduling.events import (
    ScheduledBackgroundTaskFinished,
    ScheduledTaskFailed,
    ScheduledTaskFinished,
    ScheduledTaskSkipped,
    ScheduledTaskStarting,
)
from avalon.console.scheduling.schedule import Schedule

Runner = Callable[[str], int]

INTERRUPT_KEY = "avalon:schedule:interrupt"
LOCK_PREFIX = "schedule:"
ONE_SERVER_PREFIX = "schedule-one-server:"


class Outcome:
    """What one task did, in the shape the hooks and events want."""

    __slots__ = ("code", "event", "output", "skipped")

    def __init__(self, event: Event, code: int, output: str, skipped: bool = False) -> None:
        self.event = event
        self.code = code
        self.output = output
        self.skipped = skipped

    def __repr__(self) -> str:
        state = "skipped" if self.skipped else f"exit {self.code}"
        return f"<Outcome {self.event.summary()!r} {state}>"


def run_event(
    event: Event,
    *,
    base_path: Path | str,
    runner: Runner | None = None,
    store: str | None = None,
) -> int:
    """Execute one task, honouring its constraints, locks, hooks, and output."""
    return run_task(event, base_path=base_path, runner=runner, store=store).code


def run_task(
    event: Event,
    *,
    base_path: Path | str,
    runner: Runner | None = None,
    store: str | None = None,
) -> Outcome:
    """Execute one task and report what happened."""
    base = Path(base_path)
    if not event.filters_pass():
        _dispatch(ScheduledTaskSkipped(event, "a constraint turned the task away"))
        return Outcome(event, 0, "", skipped=True)
    if _is_down_for_maintenance(base) and not event.runs_in_maintenance_mode:
        _dispatch(ScheduledTaskSkipped(event, "the application is down for maintenance"))
        return Outcome(event, 0, "", skipped=True)

    if event.runs_on_one_server:
        _require_name(event, "on_one_server")
        if not _claim_server(event, store):
            _dispatch(ScheduledTaskSkipped(event, "another server claimed the task"))
            return Outcome(event, 0, "", skipped=True)

    lock: Any = None
    mutex: Mutex | None = None
    if event.prevents_overlapping:
        lock = _cache_lock(
            f"{LOCK_PREFIX}{event.mutex_name()}",
            event.overlapping_expires_at * 60,
            store,
        )
        if lock is not None:
            if lock.get() is False:
                _dispatch(ScheduledTaskSkipped(event, "the previous run is still going"))
                return Outcome(event, 0, "", skipped=True)
        else:
            mutex = Mutex(base, event.mutex_name())
            if not mutex.acquire():
                _dispatch(ScheduledTaskSkipped(event, "the previous run is still going"))
                return Outcome(event, 0, "", skipped=True)

    try:
        return _execute(event, base=base, runner=runner)
    finally:
        if lock is not None:
            lock.release()
        if mutex is not None:
            mutex.release()


def run_due_events(
    schedule: Schedule,
    *,
    base_path: Path | str,
    runner: Runner | None = None,
    at: datetime | None = None,
    on_start: Callable[[Event], None] | None = None,
    on_finish: Callable[[Outcome], None] | None = None,
) -> list[Outcome]:
    """Run every due task, with the background ones running alongside.

    **Named deviation:** background tasks run in a worker thread rather than a
    detached OS process, so they still run simultaneously but ``schedule:run``
    waits for them before it exits. Python has no ``php artisan schedule:finish``
    to hand a detached process, and a thread outliving the interpreter would
    simply be killed.
    """
    base = Path(base_path)
    outcomes: list[Outcome] = []
    threads: list[tuple[threading.Thread, list[Outcome]]] = []

    for event in schedule.due_events(at):
        if on_start is not None:
            on_start(event)
        if event.runs_in_background:
            collected: list[Outcome] = []
            thread = threading.Thread(
                target=lambda event=event, collected=collected: collected.append(
                    run_task(event, base_path=base, runner=runner, store=schedule.cache_store)
                ),
                name=f"schedule:{event.mutex_name()}",
                daemon=True,
            )
            thread.start()
            threads.append((thread, collected))
            continue
        outcome = run_task(event, base_path=base, runner=runner, store=schedule.cache_store)
        outcomes.append(outcome)
        if on_finish is not None:
            on_finish(outcome)

    for thread, collected in threads:
        thread.join()
        if not collected:  # pragma: no cover - only if the thread itself died
            continue
        outcome = collected[0]
        outcomes.append(outcome)
        _dispatch(ScheduledBackgroundTaskFinished(outcome.event, outcome.code, outcome.output))
        if on_finish is not None:
            on_finish(outcome)

    return outcomes


def run_schedule(
    schedule: Schedule,
    *,
    base_path: Path | str,
    runner: Runner | None = None,
    on_start: Callable[[Event], None] | None = None,
    on_finish: Callable[[Outcome], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = datetime.now,
) -> list[Outcome]:
    """Run one minute of the schedule.

    With no sub-minute tasks this is a single tick, which is what cron wants.
    With them, it keeps running until the minute is out, waking on the seconds
    each task asked for — and stops early if ``schedule:interrupt`` says so.
    """
    started = now()
    outcomes = run_due_events(
        schedule,
        base_path=base_path,
        runner=runner,
        at=started,
        on_start=on_start,
        on_finish=on_finish,
    )
    if not schedule.has_sub_minute_events():
        return outcomes

    minute = started.replace(second=0, microsecond=0)
    seen: set[tuple[int, int]] = {
        (index, started.second)
        for index, event in enumerate(schedule.events)
        if event.repeat_seconds
    }
    while True:
        moment = now()
        if moment.replace(second=0, microsecond=0) != minute:
            break
        if interrupted(minute, base_path=base_path, store=schedule.cache_store):
            break
        for index, event in enumerate(schedule.events):
            if not event.repeat_seconds or not event.is_due(moment):
                continue
            marker = (index, moment.second)
            if marker in seen or not event.should_repeat_now(moment):
                continue
            seen.add(marker)
            if on_start is not None:
                on_start(event)
            outcome = run_task(
                event, base_path=base_path, runner=runner, store=schedule.cache_store
            )
            outcomes.append(outcome)
            if on_finish is not None:
                on_finish(outcome)
        sleep(0.2)
    return outcomes


def interrupt(
    *,
    base_path: Path | str,
    store: str | None = None,
    at: datetime | None = None,
) -> None:
    """Ask a running ``schedule:run`` to stop at the end of this second."""
    marker = (at or datetime.now()).replace(second=0, microsecond=0).isoformat()
    repository = _cache(store)
    if repository is not None:
        repository.put(INTERRUPT_KEY, marker, 60)
        return
    path = _interrupt_path(base_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(marker, encoding="utf-8")


def interrupted(minute: datetime, *, base_path: Path | str, store: str | None = None) -> bool:
    """Whether an interrupt was asked for during this minute."""
    marker = minute.replace(second=0, microsecond=0).isoformat()
    repository = _cache(store)
    if repository is not None:
        return bool(repository.get(INTERRUPT_KEY) == marker)
    path = _interrupt_path(base_path)
    if not path.is_file():
        return False
    return path.read_text(encoding="utf-8").strip() == marker


def clear_cache(schedule: Schedule, *, store: str | None = None) -> list[str]:
    """Release every without-overlapping lock the schedule holds."""
    repository = _cache(store or schedule.cache_store)
    cleared: list[str] = []
    if repository is None:
        return cleared
    for event in schedule.events:
        if not event.prevents_overlapping:
            continue
        name = f"{LOCK_PREFIX}{event.mutex_name()}"
        lock = repository.lock(name, seconds=event.overlapping_expires_at * 60)
        lock.force_release()
        cleared.append(event.mutex_name())
    return cleared


# --- executing one task ------------------------------------------------------


def _execute(event: Event, *, base: Path, runner: Runner | None) -> Outcome:
    _dispatch(ScheduledTaskStarting(event))
    started = time.monotonic()
    for callback in event.before_callbacks:
        call_hook(callback, None)

    buffer = io.StringIO()
    code = 0
    failure: BaseException | None = None
    try:
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = _invoke(event, runner)
    except BaseException as exc:
        failure = exc
        code = 1

    output = buffer.getvalue()
    runtime = time.monotonic() - started
    if event.output_path:
        _write_output(event, output)
    _mail_output(event, output, code)

    if failure is not None:
        _dispatch(ScheduledTaskFailed(event, failure, code, output))
        _report(failure)
    for callback in event.after_callbacks:
        call_hook(callback, output)
    hooks = event.success_callbacks if code == 0 else event.failure_callbacks
    for callback in hooks:
        call_hook(callback, output)
    if failure is None:
        _dispatch(ScheduledTaskFinished(event, runtime, code, output))
        if code != 0:
            _dispatch(ScheduledTaskFailed(event, None, code, output))
    return Outcome(event, code, output)


def _invoke(event: Event, runner: Runner | None) -> int:
    if event.callback is not None:
        result = event.callback()
        if inspect.isawaitable(result):
            # Avalon's ORM and queue are awaitable, so a scheduled callback is
            # allowed to be async; Laravel has nothing to do here.
            result = asyncio.run(result)
        return int(result) if isinstance(result, int) else 0
    if event.job is not None:
        return _dispatch_job(event)
    if event.shell:
        completed = subprocess.run(
            event.shell,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
        )
        print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="")
        return int(completed.returncode)
    if event.command and runner is not None:
        return int(runner(event.command))
    return 0


def _dispatch_job(event: Event) -> int:
    from avalon.queue.helpers import dispatch as dispatch_job

    job = event.job
    if event.job_queue is not None:
        job.queue = event.job_queue
    if event.job_connection is not None:
        job.connection = event.job_connection
    asyncio.run(dispatch_job(job))
    return 0


def _write_output(event: Event, output: str) -> None:
    path = Path(str(event.output_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a" if event.output_appends else "w", encoding="utf-8") as handle:
        handle.write(output)


def _mail_output(event: Event, output: str, code: int) -> None:
    if not event.email_addresses:
        return
    if event.email_only_on_failure and code == 0:
        return
    try:
        from avalon.console.scheduling.mail import mail_output

        mail_output(event, output, code)
    except Exception:  # pragma: no cover - mail must not fail the task
        pass


def _require_name(event: Event, feature: str) -> None:
    """One task on many servers needs a name every server agrees on.

    A command or a shell line names itself. A closure or a job does not, and
    two servers would take two different locks — so Laravel asks for
    ``name()``, and so do we.
    """
    if event.command or event.shell or event._name:
        return
    raise RuntimeError(
        f"A scheduled closure or job needs a name() before {feature}() can lock it."
    )


def _claim_server(event: Event, store: str | None) -> bool:
    """Take the one-server claim for this minute, and never give it back."""
    minute = datetime.now().strftime("%Y-%m-%d-%H-%M")
    lock = _cache_lock(f"{ONE_SERVER_PREFIX}{event.mutex_name()}:{minute}", 60, store)
    if lock is None:
        # Without a shared cache there is only this server to run on.
        return True
    return lock.get() is not False


def _cache_lock(name: str, seconds: int, store: str | None) -> Any | None:
    repository = _cache(store)
    if repository is None:
        return None
    return repository.lock(name, seconds=max(1, seconds))


def _cache(store: str | None) -> Any | None:
    try:
        from avalon.cache.manager import Cache

        Cache.manager()
        return Cache.store(store)
    except Exception:
        return None


def _interrupt_path(base_path: Path | str) -> Path:
    return Path(base_path) / "storage" / "framework" / "schedule" / "interrupt"


def _is_down_for_maintenance(base: Path) -> bool:
    return (base / "storage" / "framework" / "down").is_file()


def _dispatch(event: Any) -> None:
    try:
        from avalon.events.facade import Event as Bus

        Bus.dispatch(event)
    except Exception:  # pragma: no cover - events are best effort in the console
        pass


def _report(exception: BaseException) -> None:
    try:
        from avalon.support.helpers import report

        report(exception)
    except Exception:  # pragma: no cover - reporting must not fail the tick
        pass


# Kept for the tests and callers that predate the package split.
def _try_cache_lock(name: str) -> Any | None:
    return _cache_lock(f"{LOCK_PREFIX}{name}", 3600, None)


__all__ = [
    "INTERRUPT_KEY",
    "Outcome",
    "clear_cache",
    "interrupt",
    "interrupted",
    "run_due_events",
    "run_event",
    "run_schedule",
    "run_task",
]
