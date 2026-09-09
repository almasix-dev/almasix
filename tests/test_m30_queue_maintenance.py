"""M30 — the last of the built-ins: failed job maintenance and three one-liners.

``queue:flush``, ``queue:forget`` and ``queue:prune-failed`` all delete from the
failed job store, so every test here stands one up on a real SQLite database
and asserts what survived rather than which call was made. ``storage:unlink``,
``env`` and ``docs`` ride along because they landed in the same milestone.
"""

from __future__ import annotations

import asyncio
import webbrowser
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar
from uuid import uuid4

import pytest

from almasix.cache.helpers import set_manager as set_cache_manager
from almasix.console.commands.docs import DOCS_URL_VARIABLE
from almasix.console.commands.queue_failed import QueueFailedCommand
from almasix.console.kernel import ConsoleKernel
from almasix.console.output import Output
from almasix.events.facade import Event
from almasix.orm.facade import DB
from almasix.queue import Job, ShouldQueue, ensure_tables
from almasix.queue.failed import FailedJobRepository
from almasix.queue.manager import QueueManager

Build = Callable[..., ConsoleKernel]


class QuietJob(Job, ShouldQueue):
    """A job that does nothing, for filling the failed store up."""

    tries: ClassVar[int] = 1

    def handle(self) -> None:
        return None


def write_app(root: Path, *, environment: str, links: dict[str, str] | None) -> None:
    """The smallest tree ``ConsoleKernel.from_cwd`` will boot as an application."""
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "bootstrap").mkdir(exist_ok=True)
    (root / "bootstrap" / "app.py").write_text("# stub\n", encoding="utf-8")
    files = {
        "app.py": (
            f'config = {{"name": "M30", "env": "{environment}", "debug": False, "providers": []}}\n'
        ),
        "logging.py": "config = {'default': 'null', 'channels': {'null': {'driver': 'null'}}}\n",
        "database.py": (
            "config = {'default': 'sqlite', 'connections': "
            "{'sqlite': {'driver': 'sqlite', 'database': ':memory:'}}}\n"
        ),
        "queue.py": (
            "config = {'default': 'database', 'connections': {"
            "'database': {'driver': 'database', 'connection': 'sqlite', 'table': 'jobs'}}, "
            "'failed': {'driver': 'database', 'connection': 'sqlite', 'table': 'failed_jobs'}}\n"
        ),
        "cache.py": (
            "config = {'default': 'array', 'prefix': '', "
            "'stores': {'array': {'driver': 'array'}}}\n"
        ),
    }
    if links is not None:
        files["filesystems.py"] = f"config = {{'disks': {{}}, 'links': {links!r}}}\n"
    for name, body in files.items():
        (root / "config" / name).write_text(body, encoding="utf-8")


@pytest.fixture
def build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Build]:
    """Boot a disposable application and hand back its console kernel."""

    def make(
        *,
        environment: str = "local",
        links: dict[str, str] | None = None,
    ) -> ConsoleKernel:
        write_app(tmp_path, environment=environment, links=links)
        monkeypatch.chdir(tmp_path)
        kernel = ConsoleKernel.from_cwd(tmp_path)
        asyncio.run(ensure_tables("sqlite"))
        return kernel

    monkeypatch.delenv(DOCS_URL_VARIABLE, raising=False)
    yield make
    set_cache_manager(None)
    Event.set_dispatcher(None)


def repository(kernel: ConsoleKernel) -> FailedJobRepository:
    return FailedJobRepository(kernel.app.make(QueueManager).failed_config())


def fail_job(kernel: ConsoleKernel, *, hours_ago: float = 0.0) -> int:
    """Put one failed job in the store, stamped ``hours_ago`` in the past."""
    repo = repository(kernel)

    async def store() -> int:
        await repo.store(
            uuid=str(uuid4()),
            connection="database",
            queue="default",
            payload=QuietJob().serialize(),
            exception=RuntimeError("it did not work"),
        )
        newest = int((await repo.all(limit=1))[0]["id"])
        if hours_ago:
            await DB.statement(
                "UPDATE failed_jobs SET failed_at = :when WHERE id = :id",
                {"when": _ago(hours_ago), "id": newest},
                connection="sqlite",
            )
        return newest

    return asyncio.run(store())


def _ago(hours: float) -> datetime:
    """``hours`` before now, on the naive UTC clock the rows are stamped with."""
    return datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=hours)


def surviving(kernel: ConsoleKernel) -> list[int]:
    return sorted(int(row["id"]) for row in asyncio.run(repository(kernel).all()))


# --- queue:flush --------------------------------------------------------


def test_flush_deletes_every_failed_job(build: Build, capsys: pytest.CaptureFixture[str]) -> None:
    kernel = build()
    fail_job(kernel)
    fail_job(kernel, hours_ago=200)

    assert kernel.run_argv("queue:flush", ["--force"]) == 0

    assert "Deleted 2 failed job(s)." in capsys.readouterr().out
    assert surviving(kernel) == []


def test_flush_with_hours_spares_a_job_that_failed_inside_the_window(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    recent = fail_job(kernel, hours_ago=1)
    fail_job(kernel, hours_ago=5)

    assert kernel.run_argv("queue:flush", ["--hours", "3", "--force"]) == 0

    assert "Deleted 1 failed job(s)." in capsys.readouterr().out
    assert surviving(kernel) == [recent]


def test_flush_with_hours_of_zero_deletes_jobs_that_failed_a_moment_ago(
    build: Build,
) -> None:
    """A zero-hour window puts the cutoff at now, which every row is behind."""
    kernel = build()
    fail_job(kernel)

    assert kernel.run_argv("queue:flush", ["--hours=0", "--force"]) == 0
    assert surviving(kernel) == []


def test_flush_counts_nothing_when_the_store_is_already_empty(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("queue:flush", ["--force"]) == 0
    assert "Deleted 0 failed job(s)." in capsys.readouterr().out


def test_flush_asks_first_and_leaves_the_store_alone_when_refused(
    build: Build, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    kept = fail_job(kernel)
    monkeypatch.setattr(Output, "confirm", lambda *a, **k: False)

    assert kernel.run_argv("queue:flush", []) == 1

    out = capsys.readouterr().out
    assert "This deletes every failed job." in out
    assert "Nothing was changed." in out
    assert surviving(kernel) == [kept]


def test_flush_names_the_window_it_is_about_to_delete(
    build: Build, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    fail_job(kernel, hours_ago=9)
    monkeypatch.setattr(Output, "confirm", lambda *a, **k: True)

    assert kernel.run_argv("queue:flush", ["--hours=6"]) == 0

    assert "This deletes every job that failed more than 6 hour(s) ago." in capsys.readouterr().out
    assert surviving(kernel) == []


def test_flush_will_not_empty_production_without_force(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build(environment="production")
    kept = fail_job(kernel)

    assert kernel.run_argv("queue:flush", []) == 1

    assert "Application is in production (production)." in capsys.readouterr().err
    assert surviving(kernel) == [kept]


def test_flush_says_which_hours_it_could_not_read(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--hours`` with nothing after it parses as a flag, not as a number."""
    kernel = build()
    kept = fail_job(kernel)

    assert kernel.run_argv("queue:flush", ["--hours", "--force"]) == 2

    assert "Invalid value for '--hours': provide a number" in capsys.readouterr().err
    assert surviving(kernel) == [kept]


def test_flush_rejects_an_empty_hours(build: Build, capsys: pytest.CaptureFixture[str]) -> None:
    kernel = build()

    assert kernel.run_argv("queue:flush", ["--hours=", "--force"]) == 2
    assert "Invalid value for '--hours': provide a number" in capsys.readouterr().err


def test_flush_rejects_hours_that_are_not_a_number(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("queue:flush", ["--hours=lately", "--force"]) == 2
    assert "'lately' is not a valid number" in capsys.readouterr().err


def test_flush_rejects_a_window_that_reaches_into_the_future(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    kept = fail_job(kernel)

    assert kernel.run_argv("queue:flush", ["--hours=-5", "--force"]) == 2

    assert "'-5' is not a length of time" in capsys.readouterr().err
    assert surviving(kernel) == [kept]


def test_flush_rejects_a_window_with_no_end(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("queue:flush", ["--hours=inf", "--force"]) == 2
    assert "'inf' is not a length of time" in capsys.readouterr().err


# --- queue:forget -------------------------------------------------------


def test_forget_deletes_the_failed_job_it_was_given(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    doomed = fail_job(kernel)
    kept = fail_job(kernel)

    assert kernel.run_argv("queue:forget", [str(doomed)]) == 0

    assert f"Deleted failed job [{doomed}]." in capsys.readouterr().out
    assert surviving(kernel) == [kept]


def test_forget_reports_an_id_that_is_not_in_the_store(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    kept = fail_job(kernel)

    assert kernel.run_argv("queue:forget", ["4040"]) == 1

    assert "No failed job matches ID [4040]." in capsys.readouterr().out
    assert surviving(kernel) == [kept]


def test_forget_says_which_id_it_could_not_read(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    kept = fail_job(kernel)

    assert kernel.run_argv("queue:forget", ["the-first-one"]) == 2

    err = capsys.readouterr().err
    assert "Invalid failed job ID: 'the-first-one' is not a valid integer." in err
    assert surviving(kernel) == [kept]


# --- queue:prune-failed -------------------------------------------------


def test_prune_failed_deletes_only_what_has_aged_out_of_the_default_window(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    recent = fail_job(kernel, hours_ago=2)
    fail_job(kernel, hours_ago=30)

    assert kernel.run_argv("queue:prune-failed", []) == 0

    assert "Pruned 1 failed job(s) older than 24 hour(s)." in capsys.readouterr().out
    assert surviving(kernel) == [recent]


def test_prune_failed_honours_the_window_it_was_given(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    recent = fail_job(kernel, hours_ago=0.5)
    fail_job(kernel, hours_ago=2)

    assert kernel.run_argv("queue:prune-failed", ["--hours", "1"]) == 0

    assert "Pruned 1 failed job(s) older than 1 hour(s)." in capsys.readouterr().out
    assert surviving(kernel) == [recent]


def test_prune_failed_says_when_nothing_is_old_enough_to_go(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    kept = fail_job(kernel)

    assert kernel.run_argv("queue:prune-failed", []) == 0

    assert "No failed jobs older than 24 hour(s) to prune." in capsys.readouterr().out
    assert surviving(kernel) == [kept]


def test_prune_failed_falls_back_to_the_default_window_when_called_in_process(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    """``Artisan.call`` passes the options it was given, not the signature's."""
    kernel = build()
    recent = fail_job(kernel, hours_ago=2)
    fail_job(kernel, hours_ago=30)

    assert kernel.run_command("queue:prune-failed") == 0

    assert "Pruned 1 failed job(s) older than 24 hour(s)." in capsys.readouterr().out
    assert surviving(kernel) == [recent]


def test_prune_failed_says_which_hours_it_could_not_read(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    kept = fail_job(kernel, hours_ago=200)

    assert kernel.run_argv("queue:prune-failed", ["--hours=never"]) == 2

    assert "'never' is not a valid number" in capsys.readouterr().err
    assert surviving(kernel) == [kept]


# --- storage:unlink -----------------------------------------------------


def test_storage_unlink_removes_the_link_storage_link_made(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    assert kernel.run_argv("storage:link", []) == 0
    assert (tmp_path / "public" / "storage").is_symlink()

    assert kernel.run_argv("storage:unlink", []) == 0

    assert "The [public/storage] link has been removed." in capsys.readouterr().out
    assert not (tmp_path / "public" / "storage").is_symlink()
    assert (tmp_path / "storage" / "app" / "public").is_dir()


def test_storage_unlink_says_so_plainly_when_there_is_no_link(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("storage:unlink", []) == 0
    assert "The [public/storage] link does not exist." in capsys.readouterr().out


def test_storage_unlink_refuses_to_delete_a_real_directory(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    real = tmp_path / "public" / "storage"
    real.mkdir(parents=True)
    (real / "invoice.pdf").write_text("keep me", encoding="utf-8")

    assert kernel.run_argv("storage:unlink", []) == 1

    assert "is not a symbolic link — refusing to delete it" in capsys.readouterr().err
    assert (real / "invoice.pdf").is_file()


def test_storage_unlink_removes_a_link_whose_target_is_gone(build: Build, tmp_path: Path) -> None:
    """A broken link is still a link, and it is exactly what needs clearing."""
    kernel = build()
    link = tmp_path / "public" / "storage"
    link.parent.mkdir(parents=True)
    link.symlink_to(tmp_path / "nowhere", target_is_directory=True)

    assert kernel.run_argv("storage:unlink", []) == 0
    assert not link.is_symlink()


def test_storage_unlink_removes_every_configured_link(build: Build, tmp_path: Path) -> None:
    kernel = build(
        links={"public/storage": "storage/app/public", "public/media": "storage/app/media"}
    )
    assert kernel.run_argv("storage:link", []) == 0

    assert kernel.run_argv("storage:unlink", []) == 0

    assert not (tmp_path / "public" / "storage").is_symlink()
    assert not (tmp_path / "public" / "media").is_symlink()


# --- env ----------------------------------------------------------------


def test_env_prints_the_current_application_environment(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build(environment="staging")

    assert kernel.run_argv("env", []) == 0
    assert "Current application environment: staging" in capsys.readouterr().out


def test_env_reads_an_application_that_names_no_environment_as_production(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    kernel.app.config.set("app.env", None)

    assert kernel.run_argv("env", []) == 0
    assert "Current application environment: production" in capsys.readouterr().out


# --- docs ---------------------------------------------------------------


def opened(monkeypatch: pytest.MonkeyPatch, *, works: bool = True) -> list[str]:
    """Record what would have been opened, so no test grows a browser window."""
    urls: list[str] = []

    def fake_open(url: str, *args: Any, **kwargs: Any) -> bool:
        urls.append(url)
        return works

    monkeypatch.setattr(webbrowser, "open", fake_open)
    return urls


def test_docs_opens_the_documentation_site_it_was_pointed_at(
    build: Build, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    monkeypatch.setenv(DOCS_URL_VARIABLE, "https://docs.example.test/")
    urls = opened(monkeypatch)

    assert kernel.run_argv("docs", []) == 0

    assert urls == ["https://docs.example.test"]
    assert "Opening https://docs.example.test" in capsys.readouterr().out


def test_docs_opens_the_page_it_was_given(build: Build, monkeypatch: pytest.MonkeyPatch) -> None:
    kernel = build()
    monkeypatch.setenv(DOCS_URL_VARIABLE, "https://docs.example.test")
    urls = opened(monkeypatch)

    assert kernel.run_argv("docs", ["/articulate/casts/"]) == 0
    assert urls == ["https://docs.example.test/articulate/casts"]


def test_docs_reports_a_browser_it_could_not_open(
    build: Build, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    monkeypatch.setenv(DOCS_URL_VARIABLE, "https://docs.example.test")
    opened(monkeypatch, works=False)

    assert kernel.run_argv("docs", []) == 0

    out = capsys.readouterr().out
    assert "No browser could be opened." in out
    assert "https://docs.example.test" in out


def test_docs_says_the_documentation_site_is_not_published_yet(
    build: Build, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    urls = opened(monkeypatch)

    assert kernel.run_argv("docs", []) == 0

    out = capsys.readouterr().out
    assert "Almasix's documentation site is not published yet." in out
    assert "website/src/content/docs/" in out
    assert DOCS_URL_VARIABLE in out
    assert urls == []


def test_docs_names_the_source_file_for_the_page_it_was_given(
    build: Build, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    opened(monkeypatch)

    assert kernel.run_argv("docs", ["queues"]) == 0
    assert "website/src/content/docs/queues.md" in capsys.readouterr().out


def test_docs_answers_in_a_directory_that_is_not_an_application(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Nobody has an application booted at the moment they need the docs."""
    monkeypatch.delenv(DOCS_URL_VARIABLE, raising=False)
    monkeypatch.chdir(tmp_path)
    kernel = ConsoleKernel.for_cwd(tmp_path)
    kernel.discover()

    assert kernel.commands["docs"].boots_application is False
    assert kernel.run_argv("docs", []) == 0
    assert "not published yet" in capsys.readouterr().out


@pytest.mark.parametrize(
    "command",
    [
        "queue:failed",
        "queue:flush --force",
        "queue:forget 1",
        "queue:prune-failed",
        "queue:retry --all",
    ],
)
def test_a_missing_failed_jobs_table_is_a_sentence_not_a_traceback(
    build: Build, capsys: pytest.CaptureFixture[str], command: str
) -> None:
    """Nothing creates this table for an application, so every command meets it absent.

    Before the guard, a fresh app's first ``queue:failed`` raised a
    SQLAlchemy ``OperationalError`` out of the console, complete with a
    rendered traceback and a link to the SQLAlchemy error docs.
    """
    kernel = build()
    asyncio.run(DB.statement("DROP TABLE failed_jobs", connection="sqlite"))
    name, *argv = command.split()

    code = kernel.run_argv(name, argv)
    output = capsys.readouterr()

    assert code == 1
    assert "The failed_jobs table does not exist." in output.out + output.err
    assert "Traceback" not in output.out + output.err


def test_a_database_error_that_is_not_a_missing_table_still_raises(build: Build) -> None:
    """The guard names one problem; it must not swallow every other one."""
    from sqlalchemy.exc import OperationalError

    kernel = build()
    command = QueueFailedCommand(kernel.app)

    async def boom() -> None:
        raise OperationalError("SELECT 1", {}, Exception("database is locked"))

    with pytest.raises(OperationalError):
        command.read_store(boom())
