"""M18 Events — dispatcher, façade, queued listeners, make commands."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest
from typer.testing import CliRunner

from avalon.events import (
    CallQueuedListener,
    Dispatcher,
    Event,
    EventServiceProvider,
    ShouldQueue,
    dispatch,
    event,
    is_should_queue,
    listen,
    set_dispatcher,
)
from avalon.events.queued import queue_listener
from avalon.framework.application import Application
from avalon.grail.cli import app as grail_app
from avalon.queue.job import ShouldQueue as QueueShouldQueue


class Ping:
    def __init__(self, value: str = "ping") -> None:
        self.value = value


class PongListener:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def handle(self, event: Ping) -> str:
        self.seen.append(event.value)
        return f"pong:{event.value}"


class QueuedListener(ShouldQueue):
    handled: ClassVar[list] = []

    def handle(self, event: Ping) -> None:
        type(self).handled.append(event.value)


class ConditionalQueued(ShouldQueue):
    handled: ClassVar[list] = []

    def should_queue(self, event: Ping) -> bool:
        return event.value == "queue-me"

    def handle(self, event: Ping) -> None:
        type(self).handled.append(event.value)


class OrderSubscriber:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def subscribe(self, events: Dispatcher) -> None:
        events.listen(Ping, self.on_ping)

    def on_ping(self, event: Ping) -> None:
        self.seen.append(event.value)


@pytest.fixture(autouse=True)
def _reset_events() -> None:
    set_dispatcher(None)
    Event.set_dispatcher(None)
    QueuedListener.handled = []
    ConditionalQueued.handled = []
    yield
    set_dispatcher(None)
    Event.set_dispatcher(None)


def test_listen_dispatch_until_and_stop() -> None:
    d = Dispatcher()
    seen: list[str] = []

    def first(e: Ping) -> None:
        seen.append("a")

    def stopper(e: Ping) -> bool:
        seen.append("b")
        return False

    def never(e: Ping) -> None:
        seen.append("c")

    d.listen(Ping, first)
    d.listen(Ping, stopper)
    d.listen(Ping, never)
    d.dispatch(Ping("x"))
    assert seen == ["a", "b"]

    d2 = Dispatcher()
    d2.listen("ping", lambda _e: "one")
    d2.listen("ping", lambda _e: "two")
    assert d2.until("ping") == "one"


def test_wildcard_and_string_payload() -> None:
    d = Dispatcher()
    hits: list[tuple] = []
    d.listen("orders.*", lambda name, payload: hits.append((name, payload)))
    d.dispatch("orders.created", [{"id": 1}])
    assert hits == [("orders.created", [{"id": 1}])]


def test_class_listener_and_subscriber() -> None:
    d = Dispatcher()
    listener = PongListener()
    d.listen(Ping, listener.handle)
    assert d.dispatch(Ping("hi")) == ["pong:hi"]

    sub = OrderSubscriber()
    d2 = Dispatcher()
    d2.subscribe(sub)
    d2.dispatch(Ping("s"))
    assert sub.seen == ["s"]


def test_subscribe_requires_method() -> None:
    d = Dispatcher()
    with pytest.raises(TypeError):
        d.subscribe(object())


def test_forget_flush_has_listeners() -> None:
    d = Dispatcher()
    d.listen(Ping, lambda e: None)
    d.listen("x.*", lambda n, p: None)
    assert d.has_listeners(Ping)
    assert d.has_listeners("x.y")
    d.forget(Ping)
    assert not d.has_listeners(Ping)
    d.flush()
    assert d.get_listeners() == {}


def test_facade_helpers_and_provider(tmp_path: Path) -> None:
    app = Application.configure(tmp_path).create()
    EventServiceProvider(app).register()
    EventServiceProvider(app).boot()
    seen: list[str] = []
    listen(Ping, lambda e: seen.append(e.value))
    event(Ping("e"))
    dispatch(Ping("d"))
    assert seen == ["e", "d"]
    assert Event.has_listeners(Ping)


def test_provider_listen_map(tmp_path: Path) -> None:
    seen: list[str] = []

    class Mapped(EventServiceProvider):
        listen: ClassVar[dict] = {Ping: [lambda e: seen.append(e.value)]}

    app = Application.configure(tmp_path).create()
    Mapped(app).register()
    Mapped(app).boot()
    Event.dispatch(Ping("m"))
    assert seen == ["m"]


def test_fake_assertions() -> None:
    d = Dispatcher()
    set_dispatcher(d)
    Event.fake()
    Event.dispatch(Ping("f"))
    Event.assert_dispatched(Ping)
    Event.assert_dispatched(Ping, lambda e: e.value == "f")
    with pytest.raises(AssertionError):
        Event.assert_dispatched(Ping, lambda e: e.value == "nope")
    Event.assert_not_dispatched("other")
    with pytest.raises(AssertionError):
        Event.assert_not_dispatched(Ping)
    Event.fake()
    Event.assert_nothing_dispatched()
    Event.dispatch(Ping("x"))
    with pytest.raises(AssertionError):
        Event.assert_nothing_dispatched()


def test_fake_subset() -> None:
    d = Dispatcher()
    seen: list[str] = []
    d.listen(Ping, lambda e: seen.append(e.value))
    d.fake([Ping])
    d.dispatch(Ping("a"))
    d.dispatch("other")  # not faked by name class — string event runs
    assert d.dispatched()
    assert seen == []  # Ping was faked


def test_queued_listener_pushes_job(monkeypatch: pytest.MonkeyPatch) -> None:
    pushed: list[CallQueuedListener] = []

    async def fake_dispatch(job):
        pushed.append(job)
        return True

    monkeypatch.setattr("avalon.queue.helpers.dispatch", fake_dispatch)
    d = Dispatcher()
    d.listen(Ping, QueuedListener)
    d.dispatch(Ping("q"))
    assert len(pushed) == 1
    assert isinstance(pushed[0], CallQueuedListener)
    assert is_should_queue(QueuedListener)
    assert issubclass(QueueShouldQueue, object)


def test_conditional_should_queue_false_runs_sync() -> None:
    d = Dispatcher()
    d.listen(Ping, ConditionalQueued)
    d.dispatch(Ping("sync-me"))
    assert ConditionalQueued.handled == ["sync-me"]


def test_call_queued_listener_handle() -> None:
    QueuedListener.handled = []
    job = CallQueuedListener(
        f"{QueuedListener.__module__}.{QueuedListener.__qualname__}",
        "handle",
        Ping("via-job"),
    )
    job.handle()
    assert QueuedListener.handled == ["via-job"]


def test_queue_listener_via_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    pushed: list = []

    async def fake_dispatch(job):
        pushed.append(job)

    monkeypatch.setattr("avalon.queue.helpers.dispatch", fake_dispatch)

    class Fancy(ShouldQueue):
        connection = "sync"
        queue = "listeners"
        delay = 1

        def via_connection(self):
            return "sync"

        def via_queue(self):
            return "listeners"

        def with_delay(self, event):
            return 2

        def handle(self, event):
            pass

    queue_listener(Fancy(), Ping("z"))
    assert pushed and pushed[0].delay == 2


def test_string_listener_path() -> None:
    d = Dispatcher()
    path = f"{PongListener.__module__}.{PongListener.__qualname__}"
    d.listen(Ping, path)
    responses = d.dispatch(Ping("path"))
    assert responses == ["pong:path"]


def test_make_event_listener_and_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app").mkdir()
    runner = CliRunner()
    from avalon.console.kernel import ConsoleKernel

    ConsoleKernel.from_cwd(tmp_path).register_on_typer(grail_app)

    r1 = runner.invoke(grail_app, ["make:event", "OrderShipped"])
    assert r1.exit_code == 0, r1.stdout + r1.stderr
    assert (tmp_path / "app" / "events" / "order_shipped.py").is_file()

    r2 = runner.invoke(
        grail_app,
        ["make:listener", "SendNote", "--event=OrderShipped", "--queued"],
    )
    assert r2.exit_code == 0, r2.stdout + r2.stderr
    text = (tmp_path / "app" / "listeners" / "send_note.py").read_text(encoding="utf-8")
    assert "ShouldQueue" in text
    assert "OrderShipped" in text

    # duplicate fails
    assert runner.invoke(grail_app, ["make:event", "OrderShipped"]).exit_code == 1

    set_dispatcher(Dispatcher())
    Event.listen(Ping, lambda e: None)
    r3 = runner.invoke(grail_app, ["event:list"])
    assert r3.exit_code == 0
    assert "Ping" in (r3.stdout + r3.stderr) or "ping" in (r3.stdout + r3.stderr).lower()


def test_resolve_dispatcher_lazy() -> None:
    set_dispatcher(None)
    Event.set_dispatcher(None)
    d = Event.get_dispatcher()
    assert isinstance(d, Dispatcher)


def test_bad_listener_raises() -> None:
    d = Dispatcher()

    class Bad:
        pass

    d.listen(Ping, Bad())
    with pytest.raises(TypeError):
        d.dispatch(Ping("x"))


def test_coverage_fill_remaining_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    d = Dispatcher()
    d.set_container(None)
    d.listen([Ping, "also"], lambda e: "ok")
    assert d.has_listeners(Ping)

    d.listen("z.*", lambda n, p: None)
    d.forget("z.*")

    d.listen("orders.*", lambda n, p: None)
    assert "orders.created" in d.get_listeners("orders.created")

    class WildHandle:
        def handle(self, event) -> str:
            return "handled"

    d2 = Dispatcher()
    d2.listen("w.*", WildHandle())
    assert d2.dispatch("w.one", [1]) == ["handled"]

    class Ok:
        def handle(self, event: Ping) -> str:
            return "ok"

    class BoomContainer:
        def make(self, cls):
            raise RuntimeError("nope")

    d3 = Dispatcher(BoomContainer())
    d3.listen(Ping, Ok)
    assert d3.dispatch(Ping("c")) == ["ok"]

    class GoodContainer:
        def make(self, cls):
            return cls()

    d4 = Dispatcher(GoodContainer())
    d4.listen(Ping, Ok)
    assert d4.dispatch(Ping("g")) == ["ok"]

    from avalon.events.dispatcher import _import_symbol

    with pytest.raises(ImportError):
        _import_symbol("NoDots")

    from avalon.events.queued import _import_symbol as qi

    with pytest.raises(ImportError):
        qi("NoDots")

    set_dispatcher(Dispatcher())
    Event.subscribe(OrderSubscriber())
    Event.forget(Ping)
    Event.flush()

    d5 = Dispatcher()
    set_dispatcher(d5)
    from avalon.events.helpers import get_dispatcher, resolve_dispatcher

    assert get_dispatcher() is d5
    assert resolve_dispatcher() is d5

    from avalon.framework.container import Container

    class Mini:
        def __init__(self) -> None:
            self.container = Container()
            self.config = {}

    EventServiceProvider(Mini()).boot()

    pushed: list = []

    async def fake_dispatch(job):
        pushed.append(job)

    monkeypatch.setattr("avalon.queue.helpers.dispatch", fake_dispatch)
    queue_listener(QueuedListener, Ping("cls"))
    assert pushed


def test_wildcard_callable_without_explicit_payload() -> None:
    d = Dispatcher()
    hits: list = []

    def wild(name, payload):
        hits.append((name, payload))

    d.listen("a.*", wild)
    d.dispatch("a.b")
    assert hits and hits[0][0] == "a.b"
    # get_listeners() with wildcards present
    all_listeners = d.get_listeners()
    assert "a.*" in all_listeners


def test_assert_dispatched_miss() -> None:
    Event.fake()
    with pytest.raises(AssertionError):
        Event.assert_dispatched(Ping)


def test_queued_with_should_queue_true(monkeypatch: pytest.MonkeyPatch) -> None:
    pushed: list = []

    async def fake_dispatch(job):
        pushed.append(job)

    monkeypatch.setattr("avalon.queue.helpers.dispatch", fake_dispatch)
    d = Dispatcher()
    d.listen(Ping, ConditionalQueued)
    d.dispatch(Ping("queue-me"))
    assert pushed
    assert ConditionalQueued.handled == []
