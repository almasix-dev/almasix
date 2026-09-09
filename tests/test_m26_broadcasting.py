"""M26 Broadcasting — channels, drivers, authorization, sockets, models."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from almasix.broadcasting import (
    Broadcast,
    BroadcastEvent,
    BroadcastException,
    BroadcastManager,
    BroadcastsEvents,
    Channel,
    EncryptedPrivateChannel,
    FakeBroadcaster,
    InteractsWithBroadcasting,
    InteractsWithSockets,
    LogBroadcaster,
    NullBroadcaster,
    PresenceChannel,
    PrivateChannel,
    PusherBroadcaster,
    RedisBroadcaster,
    ShouldBroadcast,
    ShouldBroadcastNow,
    SocketHub,
    WebsocketBroadcaster,
    broadcast,
    default_broadcasting_config,
    flush_broadcasts,
    get_broadcast_manager,
    set_broadcast_manager,
)
from almasix.broadcasting.channels import (
    channel_names,
    is_presence,
    is_private,
    model_channel_name,
    strip_prefix,
    to_channel,
    to_channels,
)
from almasix.broadcasting.endpoints import BroadcastingController, BroadcastingSocket
from almasix.broadcasting.events import (
    ShouldBroadcastAfterCommit,
    broadcast_allowed,
    broadcast_channels,
    broadcast_name,
    broadcast_payload,
    is_broadcastable,
)
from almasix.broadcasting.exceptions import AccessDeniedException
from almasix.broadcasting.jobs import job_for, queue_broadcast
from almasix.broadcasting.manager import compile_pattern
from almasix.broadcasting.model import BroadcastsEventsAfterCommit
from almasix.broadcasting.signing import encode_channel_data, sign, signature, verify
from almasix.broadcasting.sockets import decode_frame, get_hub, new_socket_id, set_hub
from almasix.http.exceptions import ForbiddenHttpException
from almasix.orm.model import Model
from almasix.orm.soft_deletes import SoftDeletes
from tests.orm_support import memory_db  # noqa: F401

CONFIG: dict[str, Any] = {
    "default": "test",
    "connections": {
        "test": {"driver": "websocket", "key": "app-key", "secret": "app-secret"},
        "quiet": {"driver": "null"},
        "logged": {"driver": "log"},
    },
}


@pytest.fixture(autouse=True)
def _isolated_manager() -> Iterator[BroadcastManager]:
    """Every test gets its own manager, hub, and no leftover channels."""
    manager = BroadcastManager(config=CONFIG)
    set_broadcast_manager(manager)
    set_hub(SocketHub())
    yield manager
    set_broadcast_manager(None)
    Broadcast.set_manager(None)
    set_hub(None)


class Recorder:
    """A connected client that keeps its frames."""

    def __init__(self, fails: bool = False) -> None:
        self.frames: list[dict[str, Any]] = []
        self.fails = fails

    async def __call__(self, frame: dict[str, Any]) -> None:
        if self.fails:
            raise RuntimeError("the browser went away")
        self.frames.append(frame)

    def events(self) -> list[str]:
        return [frame["event"] for frame in self.frames]

    def last(self, event: str) -> dict[str, Any] | None:
        for frame in reversed(self.frames):
            if frame.get("event") == event:
                return frame
        return None


class Order:
    """A model-shaped object, without a database behind it."""

    def __init__(self, key: int = 1, user_id: int = 7) -> None:
        self.id = key
        self.user_id = user_id

    def get_key(self) -> int:
        return self.id

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "user_id": self.user_id}

    @classmethod
    async def find(cls, key: Any) -> Order | None:
        return cls(int(key)) if str(key) != "404" else None


class User:
    def __init__(self, key: int = 7, name: str = "Ada") -> None:
        self.id = key
        self.name = name

    def get_key(self) -> int:
        return self.id


class OrderShipped(ShouldBroadcast, InteractsWithSockets, InteractsWithBroadcasting):
    def __init__(self, order: Order) -> None:
        self.order = order

    def broadcast_on(self) -> list[Any]:
        return [Channel("shipping"), PrivateChannel(f"orders.{self.order.id}")]


# ---------------------------------------------------------------- channels


def test_a_channel_carries_its_visibility_in_its_name() -> None:
    assert Channel("orders").full_name == "orders"
    assert PrivateChannel("orders").full_name == "private-orders"
    assert PresenceChannel("lobby").full_name == "presence-lobby"
    assert EncryptedPrivateChannel("secrets").full_name == "private-encrypted-secrets"
    assert str(Channel("orders")) == "orders"
    assert repr(PrivateChannel("orders")) == "<PrivateChannel 'private-orders'>"


def test_channels_compare_by_their_wire_name() -> None:
    assert Channel("orders") == Channel("orders")
    assert Channel("orders") == "orders"
    assert Channel("orders") != PrivateChannel("orders")
    assert len({Channel("orders"), Channel("orders")}) == 1


def test_a_model_names_the_channel_it_owns() -> None:
    order = Order(3)
    assert model_channel_name(order).endswith("Order.3")
    assert PrivateChannel(order).full_name.startswith("private-")

    class Named(Order):
        def broadcast_channel(self) -> str:
            return f"orders.{self.id}"

    assert model_channel_name(Named(9)) == "orders.9"


def test_a_model_without_get_key_still_names_a_channel() -> None:
    class Plain:
        id = 5

    assert model_channel_name(Plain()).endswith("Plain.5")


def test_channels_are_normalized_from_whatever_an_event_returned() -> None:
    assert to_channel("orders").full_name == "orders"
    assert to_channel(Channel("orders")).full_name == "orders"
    assert to_channel(Order(2)).full_name.startswith("private-")
    assert to_channels(None) == []
    assert channel_names([Channel("a"), Channel("a"), Channel("b")]) == ["a", "b"]
    assert channel_names("solo") == ["solo"]
    assert channel_names(Order(1))[0].startswith("private-")


def test_a_prefix_says_whether_a_channel_needs_authorizing() -> None:
    assert is_private("private-orders")
    assert is_private("presence-lobby")
    assert is_private("private-encrypted-x")
    assert not is_private("orders")
    assert is_presence("presence-lobby")
    assert strip_prefix("private-encrypted-x") == "x"
    assert strip_prefix("presence-lobby") == "lobby"
    assert strip_prefix("orders") == "orders"


# ------------------------------------------------------------------ events


def test_an_event_says_what_it_is_and_where_it_goes() -> None:
    event = OrderShipped(Order(4))
    assert is_broadcastable(event)
    assert is_broadcastable(OrderShipped)
    assert not is_broadcastable("a string")
    assert broadcast_name(event) == "OrderShipped"
    assert broadcast_channels(event) == ["shipping", "private-orders.4"]
    assert broadcast_allowed(event)


def test_a_payload_defaults_to_the_public_attributes() -> None:
    event = OrderShipped(Order(4))
    payload = broadcast_payload(event)
    assert payload["order"] == {"id": 4, "user_id": 7}
    assert payload["socket"] is None

    event._private = "hidden"
    assert "_private" not in broadcast_payload(event)


def test_a_payload_serializes_the_shapes_it_finds() -> None:
    class Mixed(ShouldBroadcast):
        def __init__(self) -> None:
            self.orders = [Order(1), Order(2)]
            self.lookup = {"first": Order(3)}
            self.count = 2

    payload = broadcast_payload(Mixed())
    assert payload["orders"][0]["id"] == 1
    assert payload["lookup"]["first"]["id"] == 3
    assert payload["count"] == 2


def test_an_event_can_name_itself_and_choose_its_payload() -> None:
    class Custom(ShouldBroadcast):
        def broadcast_on(self) -> list[str]:
            return ["news"]

        def broadcast_as(self) -> str:
            return "custom.name"

        def broadcast_with(self) -> dict[str, int]:
            return {"only": 1}

    event = Custom()
    assert broadcast_name(event) == "custom.name"
    assert broadcast_payload(event) == {"only": 1, "socket": None}


def test_an_event_can_refuse_to_broadcast_this_time() -> None:
    class Conditional(ShouldBroadcast):
        def __init__(self, ready: bool) -> None:
            self.ready = ready

        def broadcast_on(self) -> list[str]:
            return ["news"]

        def broadcast_when(self) -> bool:
            return self.ready

    assert broadcast_allowed(Conditional(True))
    assert not broadcast_allowed(Conditional(False))


def test_an_event_with_no_channels_broadcasts_nowhere() -> None:
    assert broadcast_channels(ShouldBroadcast()) == []


def test_interacting_with_sockets_leaves_the_current_client_out() -> None:
    event = OrderShipped(Order(1))
    event.socket = "123.456"
    assert broadcast_payload(event)["socket"] == "123.456"
    event.broadcast_to_everyone()
    assert event.socket is None
    # No request in flight: there is no socket to exclude.
    event.dont_broadcast_to_current_user()
    assert event.socket is None


def test_interacting_with_broadcasting_picks_the_connections() -> None:
    event = OrderShipped(Order(1))
    assert event.broadcast_connections() == [None]
    event.broadcast_via("quiet")
    assert event.broadcast_connections() == ["quiet"]
    event.broadcast_via(["quiet", "logged"])
    assert event.broadcast_connections() == ["quiet", "logged"]
    event.broadcast_via(None)
    assert event.broadcast_connections() == [None]


# ----------------------------------------------------------------- manager


def test_the_manager_resolves_every_shipped_driver() -> None:
    manager = BroadcastManager(config=default_broadcasting_config())
    assert isinstance(manager.connection("log"), LogBroadcaster)
    assert isinstance(manager.connection("null"), NullBroadcaster)
    assert isinstance(manager.connection("websocket"), WebsocketBroadcaster)
    assert isinstance(manager.connection("redis"), RedisBroadcaster)
    assert isinstance(manager.connection("pusher"), PusherBroadcaster)
    assert manager.get_default_driver() == "log"
    assert manager.connection("log") is manager.connection("log")


def test_a_connection_is_cached_until_it_is_purged(_isolated_manager: BroadcastManager) -> None:
    manager = _isolated_manager
    first = manager.connection()
    manager.purge("test")
    assert manager.connection() is not first
    manager.purge()
    assert manager.connection() is not first


def test_an_unknown_driver_or_connection_says_so() -> None:
    manager = BroadcastManager(config={"connections": {"odd": {"driver": "carrier-pigeon"}}})
    with pytest.raises(ValueError, match="carrier-pigeon"):
        manager.connection("odd")
    with pytest.raises(KeyError, match="config/broadcasting.py"):
        manager.connection("missing")


def test_a_driver_of_your_own_can_be_registered(_isolated_manager: BroadcastManager) -> None:
    manager = _isolated_manager
    manager.set_config({"default": "mine", "connections": {"mine": {"driver": "mine"}}})
    fake = FakeBroadcaster()
    manager.extend("mine", lambda name, config: fake)
    assert manager.connection() is fake


def test_the_default_driver_can_be_changed(_isolated_manager: BroadcastManager) -> None:
    manager = _isolated_manager
    manager.set_default_driver("quiet")
    assert isinstance(manager.connection(), NullBroadcaster)


def test_the_manager_stands_alone_without_an_application() -> None:
    set_broadcast_manager(None)
    manager = get_broadcast_manager()
    assert isinstance(manager.connection(), LogBroadcaster)


# ------------------------------------------------------------ authorization


def test_a_pattern_captures_one_segment_per_parameter() -> None:
    regex = compile_pattern("orders.{order}.items.{item}")
    match = regex.match("orders.3.items.9")
    assert match is not None
    assert match.groups() == ("3", "9")
    assert regex.match("orders.3.items") is None
    assert regex.match("orders.3.4.items.9") is None


@pytest.mark.asyncio
async def test_a_callback_decides_who_may_listen(_isolated_manager: BroadcastManager) -> None:
    manager = _isolated_manager
    manager.channel("orders.{order}", lambda user, order: user.get_key() == 7)

    assert await manager.authorize(User(7), "private-orders.1") is True
    assert await manager.authorize(User(8), "private-orders.1") is False
    assert await manager.authorize(None, "private-orders.1") is False
    assert await manager.authorize(User(7), "private-nobody-registered") is False


@pytest.mark.asyncio
async def test_a_channel_can_be_registered_as_a_decorator(
    _isolated_manager: BroadcastManager,
) -> None:
    manager = _isolated_manager

    @manager.channel("rooms.{room}")
    def room(user: Any, room: str) -> dict[str, Any]:
        return {"id": user.get_key(), "room": room}

    assert room.__name__ == "room"
    assert await manager.authorize(User(), "presence-rooms.lobby") == {"id": 7, "room": "lobby"}


@pytest.mark.asyncio
async def test_an_async_callback_is_awaited(_isolated_manager: BroadcastManager) -> None:
    manager = _isolated_manager

    async def slow(user: Any, order: str) -> bool:
        del order
        return user is not None

    manager.channel("orders.{order}", slow)
    assert await manager.authorize(User(), "private-orders.1") is True


@pytest.mark.asyncio
async def test_a_model_parameter_is_looked_up_before_the_callback_runs(
    _isolated_manager: BroadcastManager,
) -> None:
    manager = _isolated_manager

    def owner(user: User, order: Order) -> bool:
        return order.user_id == user.get_key()

    manager.channel("orders.{order}", owner)
    assert await manager.authorize(User(7), "private-orders.1") is True
    # A record that does not exist refuses rather than raising.
    assert await manager.authorize(User(7), "private-orders.404") is False


@pytest.mark.asyncio
async def test_a_channel_class_answers_through_its_join_method(
    _isolated_manager: BroadcastManager,
) -> None:
    manager = _isolated_manager

    class OrderChannel:
        def join(self, user: Any, order: str) -> bool:
            return order == "1" and user is not None

    manager.channel("orders.{order}", OrderChannel)
    assert await manager.authorize(User(), "private-orders.1") is True
    assert await manager.authorize(User(), "private-orders.2") is False


@pytest.mark.asyncio
async def test_a_channel_class_is_resolved_from_the_container() -> None:
    class Resolved:
        def join(self, user: Any, order: str) -> bool:
            del user, order
            return True

    class Container:
        def __init__(self) -> None:
            self.made: list[type] = []

        def make(self, what: type) -> Any:
            self.made.append(what)
            return what()

    container = Container()
    manager = BroadcastManager(app=container, config=CONFIG)
    manager.channel("orders.{order}", Resolved)
    assert await manager.authorize(User(), "private-orders.1") is True
    assert container.made == [Resolved]


@pytest.mark.asyncio
async def test_binding_survives_a_signature_it_cannot_read(
    _isolated_manager: BroadcastManager,
) -> None:
    manager = _isolated_manager

    def unresolvable(user: Any, order: NoSuchModel) -> bool:  # noqa: F821 — deliberately
        return order == "1"

    manager.channel("orders.{order}", unresolvable)
    assert await manager.authorize(User(), "private-orders.1") is True


@pytest.mark.asyncio
async def test_a_pattern_may_capture_more_than_the_callback_wants(
    _isolated_manager: BroadcastManager,
) -> None:
    manager = _isolated_manager
    manager.channel("orders.{order}.{item}", lambda user, *rest: list(rest) == ["1", "2"])
    assert await manager.authorize(User(), "private-orders.1.2") is True


def test_the_registry_can_be_listed_and_emptied(_isolated_manager: BroadcastManager) -> None:
    manager = _isolated_manager
    manager.channel("orders.{order}", lambda user, order: True, guards=["web"])
    assert [route.pattern for route in manager.channels()] == ["orders.{order}"]
    assert manager.channels()[0].guards == ["web"]
    assert manager.channel_for("private-orders.1") is not None
    assert manager.channel_for("private-nope") is None
    manager.forget_channels()
    assert manager.channels() == []


# ------------------------------------------------------------------ signing


def test_a_signature_covers_the_socket_the_channel_and_the_data() -> None:
    first = signature("secret", "1.1", "private-orders")
    assert first == signature("secret", "1.1", "private-orders")
    assert first != signature("secret", "1.2", "private-orders")
    assert first != signature("secret", "1.1", "private-orders", "{}")
    assert sign("key", "secret", "1.1", "private-orders").startswith("key:")


def test_verification_accepts_only_what_we_would_have_signed() -> None:
    auth = sign("key", "secret", "1.1", "private-orders")
    assert verify("key", "secret", auth, "1.1", "private-orders")
    assert not verify("key", "secret", auth, "1.2", "private-orders")
    assert not verify("key", "secret", "", "1.1", "private-orders")


def test_presence_data_is_signed_exactly_as_it_travels() -> None:
    assert encode_channel_data(7) == '{"user_id":"7"}'
    assert encode_channel_data(7, {"name": "Ada"}) == '{"user_id":"7","user_info":{"name":"Ada"}}'


# ------------------------------------------------------------- auth endpoint


class FakeRequest:
    """Just enough request for the authorization endpoints."""

    def __init__(self, data: dict[str, Any], user: Any = None, guards: Any = None) -> None:
        self.data = data
        self._user = user
        self._guards = guards or {}

    def input(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def user(self, guard: str | None = None) -> Any:
        return self._guards.get(guard) if guard else self._user


@pytest.mark.asyncio
async def test_authorizing_a_private_channel_returns_a_signature(
    _isolated_manager: BroadcastManager,
) -> None:
    manager = _isolated_manager
    manager.channel("orders.{order}", lambda user, order: True)

    response = await manager.auth(
        FakeRequest({"channel_name": "private-orders.1", "socket_id": "1.1"}, User())
    )
    assert verify("app-key", "app-secret", response["auth"], "1.1", "private-orders.1")


@pytest.mark.asyncio
async def test_authorizing_a_presence_channel_returns_its_member_data(
    _isolated_manager: BroadcastManager,
) -> None:
    manager = _isolated_manager
    manager.channel("rooms.{room}", lambda user, room: {"name": user.name})

    response = await manager.auth(
        FakeRequest({"channel_name": "presence-rooms.lobby", "socket_id": "1.1"}, User())
    )
    assert json.loads(response["channel_data"]) == {"user_id": "7", "user_info": {"name": "Ada"}}
    assert verify(
        "app-key",
        "app-secret",
        response["auth"],
        "1.1",
        "presence-rooms.lobby",
        response["channel_data"],
    )


@pytest.mark.asyncio
async def test_a_public_channel_needs_no_signature(_isolated_manager: BroadcastManager) -> None:
    response = await _isolated_manager.auth(
        FakeRequest({"channel_name": "news", "socket_id": "1.1"})
    )
    assert response == {"auth": ""}


@pytest.mark.asyncio
async def test_authorization_refuses_what_it_should(
    _isolated_manager: BroadcastManager,
) -> None:
    manager = _isolated_manager
    with pytest.raises(AccessDeniedException, match="required"):
        await manager.auth(FakeRequest({"channel_name": "private-orders.1"}))

    manager.channel("orders.{order}", lambda user, order: False)
    with pytest.raises(AccessDeniedException, match="private-orders.1"):
        await manager.auth(
            FakeRequest({"channel_name": "private-orders.1", "socket_id": "1.1"}, User())
        )


@pytest.mark.asyncio
async def test_a_channel_can_name_the_guards_that_may_answer_for_it(
    _isolated_manager: BroadcastManager,
) -> None:
    manager = _isolated_manager
    manager.channel("orders.{order}", lambda user, order: True, guards=["api", "web"])

    request = FakeRequest(
        {"channel_name": "private-orders.1", "socket_id": "1.1"},
        user=None,
        guards={"api": None, "web": User()},
    )
    assert "auth" in await manager.auth(request)

    nobody = FakeRequest(
        {"channel_name": "private-orders.1", "socket_id": "1.1"},
        guards={"api": None, "web": None},
    )
    with pytest.raises(AccessDeniedException):
        await manager.auth(nobody)


@pytest.mark.asyncio
async def test_signing_without_a_secret_says_what_is_missing(
    _isolated_manager: BroadcastManager,
) -> None:
    manager = _isolated_manager
    manager.set_config({"default": "bare", "connections": {"bare": {"driver": "null"}}})
    manager.channel("orders.{order}", lambda user, order: True)
    with pytest.raises(BroadcastException, match="APP_KEY"):
        await manager.auth(
            FakeRequest({"channel_name": "private-orders.1", "socket_id": "1.1"}, User())
        )


def test_user_auth_identifies_the_connection(_isolated_manager: BroadcastManager) -> None:
    response = _isolated_manager.user_auth(FakeRequest({}, User()))
    assert json.loads(response["user_data"]) == {"user_id": "7"}
    assert response["auth"].startswith("app-key:")

    with pytest.raises(AccessDeniedException, match="Unauthenticated"):
        _isolated_manager.user_auth(FakeRequest({}))


def test_a_user_key_is_read_however_the_model_spells_it(
    _isolated_manager: BroadcastManager,
) -> None:
    class Authenticatable:
        def get_auth_identifier(self) -> int:
            return 42

    class Bare:
        id = 11

    assert (
        '"user_id":"42"'
        in _isolated_manager.user_auth(FakeRequest({}, Authenticatable()))["user_data"]
    )
    assert '"user_id":"11"' in _isolated_manager.user_auth(FakeRequest({}, Bare()))["user_data"]


@pytest.mark.asyncio
async def test_the_controller_turns_a_refusal_into_a_403(
    _isolated_manager: BroadcastManager,
) -> None:
    controller = BroadcastingController()
    with pytest.raises(ForbiddenHttpException):
        await controller.auth(FakeRequest({"channel_name": "private-x", "socket_id": "1"}, User()))
    with pytest.raises(ForbiddenHttpException):
        await controller.user_auth(FakeRequest({}))

    _isolated_manager.channel("x", lambda user: True)
    ok = await controller.auth(FakeRequest({"channel_name": "private-x", "socket_id": "1"}, User()))
    assert "auth" in ok
    assert "auth" in await controller.user_auth(FakeRequest({}, User()))


# ------------------------------------------------------------------- drivers


@pytest.mark.asyncio
async def test_the_null_driver_accepts_everything_and_sends_nothing() -> None:
    assert await NullBroadcaster().broadcast(["a"], "E", {}) is None


@pytest.mark.asyncio
async def test_the_log_driver_writes_what_would_have_gone_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import almasix.log as log_module

    lines: list[str] = []

    class Logger:
        def info(self, message: str) -> None:
            lines.append(message)

    monkeypatch.setattr(log_module, "log", lambda *args, **kwargs: Logger())
    await LogBroadcaster().broadcast(["orders"], "OrderShipped", {"id": 1}, socket="1.1")
    assert "Broadcasting [OrderShipped]" in lines[0]
    assert "excluding socket 1.1" in lines[0]


@pytest.mark.asyncio
async def test_the_log_driver_falls_back_to_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import almasix.log as log_module

    def no_logger(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("no logger here")

    monkeypatch.setattr(log_module, "log", no_logger)
    await LogBroadcaster().broadcast(["orders"], "OrderShipped", {"id": 1})
    assert "Broadcasting [OrderShipped]" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_the_redis_driver_publishes_one_message_per_channel() -> None:
    published: list[tuple[str, str]] = []

    class Client:
        async def publish(self, channel: str, message: str) -> int:
            published.append((channel, message))
            return 1

    driver = RedisBroadcaster("redis", {"prefix": "app:"}, client=Client())
    await driver.broadcast(["orders", "news"], "OrderShipped", {"id": 1}, socket="1.1")

    assert [channel for channel, _ in published] == ["app:orders", "app:news"]
    body = json.loads(published[0][1])
    assert body["event"] == "OrderShipped"
    assert body["socket"] == "1.1"
    assert body["data"]["id"] == 1


@pytest.mark.asyncio
async def test_the_redis_driver_accepts_a_synchronous_client() -> None:
    seen: list[str] = []

    class SyncClient:
        def publish(self, channel: str, message: str) -> int:
            seen.append(channel)
            return 1

    driver = RedisBroadcaster()
    driver.set_client(SyncClient())
    await driver.broadcast(["orders"], "E", {})
    assert seen == ["orders"]


def test_the_redis_driver_finds_its_client_through_the_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Manager:
        def connection(self, name: str | None = None) -> str:
            return f"client:{name}"

    monkeypatch.setattr("almasix.redis.manager.RedisManager", lambda *a, **k: Manager())
    monkeypatch.setattr("almasix.framework.helpers.current_application", lambda: None)
    driver = RedisBroadcaster("redis", {"connection": "cache"})
    assert driver.client() == "client:cache"


@pytest.fixture()
def faked_http() -> Iterator[Any]:
    """A clean HTTP factory, so one pusher test cannot stub another's."""
    from almasix.client.facade import Http, set_factory

    set_factory(None)
    Http.fake()
    yield Http
    set_factory(None)


def test_the_pusher_driver_builds_a_signed_url() -> None:
    driver = PusherBroadcaster("pusher", {"app_id": "42", "key": "k", "secret": "s"})
    assert driver.base_url == "https://api-mt1.pusher.com"
    query = driver._query("/apps/42/events", "{}")
    assert "auth_key=k" in query
    assert "auth_signature=" in query

    hosted = PusherBroadcaster("pusher", {"host": "sockets.test", "port": 6001, "scheme": "http"})
    assert hosted.base_url == "http://sockets.test:6001"
    assert PusherBroadcaster("pusher", {"host": "sockets.test"}).base_url == "https://sockets.test"


@pytest.mark.asyncio
async def test_the_pusher_driver_posts_the_event(faked_http: Any) -> None:
    driver = PusherBroadcaster("pusher", {"app_id": "42", "key": "k", "secret": "s"})
    await driver.broadcast(["orders"], "OrderShipped", {"id": 1}, socket="1.1")

    recorded = faked_http.recorded()
    assert len(recorded) == 1
    request = recorded[0][0]
    assert "/apps/42/events" in request.url
    assert request.data["channels"] == ["orders"]
    assert request.data["socket_id"] == "1.1"
    assert json.loads(request.data["data"]) == {"id": 1}


@pytest.mark.asyncio
async def test_the_pusher_driver_chunks_large_channel_lists(faked_http: Any) -> None:
    driver = PusherBroadcaster("pusher", {"app_id": "42", "key": "k", "secret": "s"})
    await driver.broadcast([f"c{index}" for index in range(150)], "E", {})
    assert len(faked_http.recorded()) == 2


@pytest.mark.asyncio
async def test_the_pusher_driver_reports_a_rejection() -> None:
    from almasix.client.facade import Http, set_factory

    set_factory(None)
    Http.fake(Http.response("no", status=400))
    driver = PusherBroadcaster("pusher", {"app_id": "42", "key": "k", "secret": "s"})
    with pytest.raises(BroadcastException, match="400"):
        await driver.broadcast(["orders"], "E", {})
    set_factory(None)


def test_the_websocket_driver_signs_with_the_application_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert WebsocketBroadcaster("ws", {"secret": "explicit"}).auth_secret() == "explicit"

    monkeypatch.setattr("almasix.framework.helpers.current_application", lambda: None)
    assert WebsocketBroadcaster().auth_secret() is None

    class Config:
        def get(self, key: str) -> str:
            del key
            return "from-app"

    class App:
        def __init__(self) -> None:
            self.config = Config()

    monkeypatch.setattr("almasix.framework.helpers.current_application", lambda: App())
    assert WebsocketBroadcaster().auth_secret() == "from-app"


# ---------------------------------------------------------------- socket hub


@pytest.mark.asyncio
async def test_the_hub_delivers_to_everyone_on_a_channel() -> None:
    hub = SocketHub()
    first, second = Recorder(), Recorder()
    one = hub.connect(first)
    two = hub.connect(second)
    await hub.subscribe(one, "news")
    await hub.subscribe(two, "news")

    assert await hub.publish(["news"], "E", {"a": 1}) == 2
    assert first.frames[0] == {"event": "E", "channel": "news", "data": {"a": 1}}
    assert hub.channels() == {"news": 2}
    assert hub.connection_count == 2
    assert hub.connection(one.id) is one
    assert hub.connection("nope") is None


@pytest.mark.asyncio
async def test_the_hub_skips_the_socket_that_caused_the_broadcast() -> None:
    hub = SocketHub()
    mine, theirs = Recorder(), Recorder()
    one, two = hub.connect(mine), hub.connect(theirs)
    await hub.subscribe(one, "news")
    await hub.subscribe(two, "news")

    assert await hub.publish(["news"], "E", {}, socket=one.id) == 1
    assert mine.frames == []
    assert len(theirs.frames) == 1


@pytest.mark.asyncio
async def test_a_presence_channel_announces_arrivals_and_departures() -> None:
    hub = SocketHub()
    first, second = Recorder(), Recorder()
    one, two = hub.connect(first), hub.connect(second)

    assert await hub.subscribe(one, "presence-lobby", {"user_id": "1"}) == []
    roster = await hub.subscribe(two, "presence-lobby", {"user_id": "2"})
    assert roster == [{"user_id": "1"}]
    assert first.last("almasix:member_added")["data"] == {"user_id": "2"}

    await hub.unsubscribe(two, "presence-lobby")
    assert first.last("almasix:member_removed")["data"] == {"user_id": "2"}
    assert hub.members("presence-lobby") == [{"user_id": "1"}]


@pytest.mark.asyncio
async def test_disconnecting_leaves_every_channel() -> None:
    hub = SocketHub()
    watcher = Recorder()
    stayed = hub.connect(watcher)
    leaving = hub.connect(Recorder())
    await hub.subscribe(stayed, "presence-lobby", {"user_id": "1"})
    await hub.subscribe(leaving, "presence-lobby", {"user_id": "2"})

    await hub.disconnect(leaving)
    assert hub.connection_count == 1
    assert watcher.last("almasix:member_removed") is not None
    assert hub.channels() == {"presence-lobby": 1}


@pytest.mark.asyncio
async def test_a_connection_that_fails_to_receive_is_dropped() -> None:
    hub = SocketHub()
    broken = hub.connect(Recorder(fails=True))
    await hub.subscribe(broken, "news")
    assert await hub.publish(["news"], "E", {}) == 0
    assert hub.connection_count == 0
    assert hub.channels() == {}


@pytest.mark.asyncio
async def test_the_hub_tolerates_channels_nobody_is_on() -> None:
    hub = SocketHub()
    connection = hub.connect(Recorder())
    await hub.unsubscribe(connection, "never-joined")
    assert await hub.publish(["empty"], "E", {}) == 0
    assert hub.members("empty") == []
    hub.flush()
    assert hub.connection_count == 0


def test_socket_ids_look_like_socket_ids() -> None:
    socket_id = new_socket_id()
    left, _, right = socket_id.partition(".")
    assert len(left) == 6 and len(right) == 7
    assert new_socket_id() != new_socket_id()


def test_a_frame_that_is_not_a_frame_decodes_to_nothing() -> None:
    assert decode_frame('{"event": "ping"}') == {"event": "ping"}
    assert decode_frame("not json") == {}
    assert decode_frame("[1, 2]") == {}


def test_the_process_hub_is_created_once() -> None:
    set_hub(None)
    assert get_hub() is get_hub()


# ------------------------------------------------------------- socket server


@pytest.mark.asyncio
async def test_the_socket_endpoint_greets_subscribes_and_pings(
    _isolated_manager: BroadcastManager,
) -> None:
    hub = get_hub()
    server = BroadcastingSocket()
    client = Recorder()
    connection = hub.connect(client)

    await server.dispatch(connection, {"event": "subscribe", "data": {"channel": "news"}})
    assert client.last("almasix:subscription_succeeded")["channel"] == "news"

    await server.dispatch(connection, {"event": "ping"})
    assert client.last("almasix:pong") is not None

    await server.dispatch(connection, {"event": "unsubscribe", "data": {"channel": "news"}})
    assert connection.channels == set()

    await server.dispatch(connection, {"event": "nonsense"})
    assert "Unknown event" in client.last("almasix:error")["data"]["message"]

    await server.dispatch(connection, {"event": "subscribe", "data": "not a dict"})
    assert "channel name is required" in client.last("almasix:error")["data"]["message"]


@pytest.mark.asyncio
async def test_a_private_channel_needs_a_valid_signature(
    _isolated_manager: BroadcastManager,
) -> None:
    hub = get_hub()
    server = BroadcastingSocket()
    client = Recorder()
    connection = hub.connect(client)

    await server.dispatch(
        connection,
        {"event": "subscribe", "data": {"channel": "private-orders.1", "auth": "wrong"}},
    )
    assert "Not authorized" in client.last("almasix:error")["data"]["message"]

    auth = sign("app-key", "app-secret", connection.id, "private-orders.1")
    await server.dispatch(
        connection,
        {"event": "subscribe", "data": {"channel": "private-orders.1", "auth": auth}},
    )
    assert client.last("almasix:subscription_succeeded")["channel"] == "private-orders.1"


@pytest.mark.asyncio
async def test_a_presence_subscription_needs_channel_data(
    _isolated_manager: BroadcastManager,
) -> None:
    hub = get_hub()
    server = BroadcastingSocket()
    client = Recorder()
    connection = hub.connect(client)

    data = encode_channel_data(7, {"name": "Ada"})
    auth = sign("app-key", "app-secret", connection.id, "presence-lobby", data)
    await server.dispatch(
        connection,
        {
            "event": "subscribe",
            "data": {"channel": "presence-lobby", "auth": auth, "channel_data": data},
        },
    )
    joined = client.last("almasix:subscription_succeeded")
    assert joined["data"]["members"] == []
    assert hub.members("presence-lobby") == [{"user_id": "7", "user_info": {"name": "Ada"}}]

    # Signed, but with nothing that says who joined.
    bare = sign("app-key", "app-secret", connection.id, "presence-other")
    await server.dispatch(
        connection,
        {"event": "subscribe", "data": {"channel": "presence-other", "auth": bare}},
    )
    assert "channel_data" in client.last("almasix:error")["data"]["message"]


@pytest.mark.asyncio
async def test_presence_data_that_is_not_presence_data_is_refused(
    _isolated_manager: BroadcastManager,
) -> None:
    hub = get_hub()
    server = BroadcastingSocket()
    connection = hub.connect(Recorder())
    for junk in ("not json", '{"no": "user"}', '["a"]'):
        auth = sign("app-key", "app-secret", connection.id, "presence-lobby", junk)
        await server.dispatch(
            connection,
            {
                "event": "subscribe",
                "data": {"channel": "presence-lobby", "auth": auth, "channel_data": junk},
            },
        )
    assert hub.members("presence-lobby") == []


@pytest.mark.asyncio
async def test_a_connection_cannot_be_signed_for_without_a_secret(
    _isolated_manager: BroadcastManager,
) -> None:
    _isolated_manager.set_config({"default": "bare", "connections": {"bare": {"driver": "null"}}})
    server = BroadcastingSocket()
    assert server.verify("1.1", "private-x", "anything") is False


@pytest.mark.asyncio
async def test_client_events_reach_the_rest_of_a_private_channel(
    _isolated_manager: BroadcastManager,
) -> None:
    manager = _isolated_manager
    hub = get_hub()
    server = BroadcastingSocket()
    sender, other = Recorder(), Recorder()
    one, two = hub.connect(sender), hub.connect(other)

    frame = {"event": "client-typing", "channel": "private-chat", "data": {"who": "Ada"}}

    await server.dispatch(one, frame)
    assert "disabled" in sender.last("almasix:error")["data"]["message"]

    manager.set_config(
        {
            "default": "test",
            "connections": {
                "test": {
                    "driver": "websocket",
                    "key": "app-key",
                    "secret": "app-secret",
                    "client_events": True,
                }
            },
        }
    )
    await server.dispatch(one, frame)
    assert "only allowed on private channels" in sender.last("almasix:error")["data"]["message"]

    await hub.subscribe(one, "private-chat")
    await hub.subscribe(two, "private-chat")
    await server.dispatch(one, frame)
    assert other.last("client-typing")["data"] == {"who": "Ada"}


def test_client_events_are_off_when_nothing_is_configured(
    _isolated_manager: BroadcastManager,
) -> None:
    _isolated_manager.set_config({"default": "missing", "connections": {}})
    assert BroadcastingSocket().client_events_enabled() is False


class FakeWebSocket:
    """A websocket that plays back a script and then hangs up."""

    def __init__(self, frames: list[dict[str, Any]]) -> None:
        self.incoming = [json.dumps(frame) for frame in frames]
        self.sent: list[dict[str, Any]] = []
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))

    async def receive_text(self) -> str:
        if not self.incoming:
            raise RuntimeError("client disconnected")
        return self.incoming.pop(0)


@pytest.mark.asyncio
async def test_the_endpoint_runs_a_whole_connection(
    _isolated_manager: BroadcastManager,
) -> None:
    websocket = FakeWebSocket(
        [{"event": "subscribe", "data": {"channel": "news"}}, {"event": "ping"}]
    )
    await BroadcastingSocket()(websocket)

    assert websocket.accepted
    assert [frame["event"] for frame in websocket.sent] == [
        "almasix:connection_established",
        "almasix:subscription_succeeded",
        "almasix:pong",
    ]
    assert get_hub().connection_count == 0


# ------------------------------------------------------------------ sending


@pytest.mark.asyncio
async def test_an_event_reaches_the_broadcaster(_isolated_manager: BroadcastManager) -> None:
    fake = FakeBroadcaster()
    _isolated_manager.set_connection("test", fake)

    await _isolated_manager.broadcast_event(OrderShipped(Order(3)))
    record = fake.broadcasts[0]
    assert record.event == "OrderShipped"
    assert record.channels == ["shipping", "private-orders.3"]
    assert record.payload["order"] == {"id": 3, "user_id": 7}


@pytest.mark.asyncio
async def test_an_event_that_says_no_sends_nothing(
    _isolated_manager: BroadcastManager,
) -> None:
    fake = FakeBroadcaster()
    _isolated_manager.set_connection("test", fake)

    class Quiet(ShouldBroadcast):
        def broadcast_on(self) -> list[str]:
            return ["news"]

        def broadcast_when(self) -> bool:
            return False

    await _isolated_manager.broadcast_event(Quiet())
    await _isolated_manager.broadcast_event(ShouldBroadcast())
    await _isolated_manager.event([], "E", {})
    assert fake.broadcasts == []


@pytest.mark.asyncio
async def test_an_event_can_go_over_several_connections(
    _isolated_manager: BroadcastManager,
) -> None:
    first, second = FakeBroadcaster("one"), FakeBroadcaster("two")
    _isolated_manager.set_connection("quiet", first)
    _isolated_manager.set_connection("logged", second)

    event = OrderShipped(Order(1))
    event.broadcast_via(["quiet", "logged"])
    await _isolated_manager.broadcast_event(event)
    assert len(first.broadcasts) == 1
    assert len(second.broadcasts) == 1

    await _isolated_manager.broadcast_event(event, connection="quiet")
    assert len(first.broadcasts) == 2
    assert len(second.broadcasts) == 1


@pytest.mark.asyncio
async def test_an_encrypted_channel_travels_sealed(
    _isolated_manager: BroadcastManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "almasix.encryption.helpers.encrypt_string",
        lambda value: f"sealed:{value}",
    )
    fake = FakeBroadcaster()
    _isolated_manager.set_connection("test", fake)

    class Secret(ShouldBroadcast):
        def broadcast_on(self) -> list[Any]:
            return [Channel("news"), EncryptedPrivateChannel("vault")]

        def broadcast_with(self) -> dict[str, int]:
            return {"amount": 10}

    await _isolated_manager.broadcast_event(Secret())
    plain, sealed = fake.broadcasts
    assert plain.channels == ["news"]
    assert plain.payload["amount"] == 10
    assert sealed.channels == ["private-encrypted-vault"]
    assert sealed.payload["ciphertext"].startswith("sealed:")


@pytest.mark.asyncio
async def test_a_wholly_encrypted_event_still_travels(
    _isolated_manager: BroadcastManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "almasix.encryption.helpers.encrypt_string",
        lambda value: "sealed",
    )
    fake = FakeBroadcaster()
    _isolated_manager.set_connection("test", fake)
    await _isolated_manager.event(EncryptedPrivateChannel("vault"), "E", {"a": 1})
    assert fake.broadcasts[0].payload == {"ciphertext": "sealed"}


@pytest.mark.asyncio
async def test_an_ad_hoc_event_needs_no_class(_isolated_manager: BroadcastManager) -> None:
    fake = FakeBroadcaster()
    _isolated_manager.set_connection("test", fake)
    await _isolated_manager.event("news", "tick", {"at": 1}, socket="1.1")
    assert fake.broadcasts[0].channels == ["news"]
    assert fake.broadcasts[0].socket == "1.1"


# ------------------------------------------------------------------- queuing


def test_a_queued_broadcast_carries_plain_data() -> None:
    job = job_for(OrderShipped(Order(2)))
    assert isinstance(job, BroadcastEvent)
    assert job.channels == ["shipping", "private-orders.2"]
    assert job.event == "OrderShipped"
    assert job.queue == "default"
    assert "BroadcastEvent" in repr(job)
    assert json.dumps(job.serialize()["data"])


def test_a_queued_broadcast_honours_the_event_s_queue() -> None:
    class Slow(ShouldBroadcast):
        broadcast_queue = "broadcasts"
        broadcast_connection = "redis"

        def broadcast_on(self) -> list[str]:
            return ["news"]

    job = job_for(Slow())
    assert job.queue == "broadcasts"
    assert job.connection == "redis"


@pytest.mark.asyncio
async def test_the_queued_job_sends_when_it_runs(_isolated_manager: BroadcastManager) -> None:
    fake = FakeBroadcaster()
    _isolated_manager.set_connection("test", fake)
    await job_for(OrderShipped(Order(5))).handle()
    assert fake.broadcasts[0].event == "OrderShipped"


@pytest.mark.asyncio
async def test_dispatching_an_event_broadcasts_it(_isolated_manager: BroadcastManager) -> None:
    from almasix.events.dispatcher import Dispatcher

    fake = FakeBroadcaster()
    _isolated_manager.set_connection("test", fake)

    seen: list[Any] = []
    dispatcher = Dispatcher()
    dispatcher.listen(OrderShipped, seen.append)
    dispatcher.dispatch(OrderShipped(Order(1)))
    await flush_broadcasts()

    assert len(seen) == 1
    assert fake.broadcasts[0].event == "OrderShipped"


@pytest.mark.asyncio
async def test_a_faked_event_is_neither_heard_nor_broadcast(
    _isolated_manager: BroadcastManager,
) -> None:
    from almasix.events.dispatcher import Dispatcher

    fake = FakeBroadcaster()
    _isolated_manager.set_connection("test", fake)

    dispatcher = Dispatcher()
    dispatcher.fake()
    dispatcher.dispatch(OrderShipped(Order(1)))
    dispatcher.dispatch("plain.string.event")
    await flush_broadcasts()

    dispatcher.assert_dispatched(OrderShipped)
    assert fake.broadcasts == []


@pytest.mark.asyncio
async def test_broadcast_now_skips_the_queue(_isolated_manager: BroadcastManager) -> None:
    fake = FakeBroadcaster()
    _isolated_manager.set_connection("test", fake)

    class Immediate(ShouldBroadcastNow):
        def broadcast_on(self) -> list[str]:
            return ["news"]

    queue_broadcast(Immediate())
    await flush_broadcasts()
    assert fake.broadcasts[0].event == "Immediate"


@pytest.mark.asyncio
async def test_an_after_commit_broadcast_waits_for_the_transaction(
    _isolated_manager: BroadcastManager,
) -> None:
    fake = FakeBroadcaster()
    _isolated_manager.set_connection("test", fake)

    class Committed(ShouldBroadcastAfterCommit):
        def broadcast_on(self) -> list[str]:
            return ["news"]

    # No database configured: nothing to wait for, so it goes out.
    queue_broadcast(Committed())
    await flush_broadcasts()
    assert len(fake.broadcasts) == 1


# ------------------------------------------------------------------ helpers


@pytest.mark.asyncio
async def test_the_broadcast_helper_dispatches_through_the_event_bus(
    _isolated_manager: BroadcastManager,
) -> None:
    from almasix.events.dispatcher import Dispatcher
    from almasix.events.helpers import set_dispatcher

    fake = FakeBroadcaster()
    _isolated_manager.set_connection("test", fake)
    set_dispatcher(Dispatcher())

    pending = broadcast(OrderShipped(Order(1)))
    pending.send()
    pending.send()  # a second call does nothing
    await flush_broadcasts()
    assert len(fake.broadcasts) == 1


@pytest.mark.asyncio
async def test_a_pending_broadcast_can_be_awaited(
    _isolated_manager: BroadcastManager,
) -> None:
    from almasix.events.dispatcher import Dispatcher
    from almasix.events.helpers import set_dispatcher

    fake = FakeBroadcaster()
    _isolated_manager.set_connection("test", fake)
    set_dispatcher(Dispatcher())

    await broadcast(OrderShipped(Order(1)))
    await flush_broadcasts()
    assert len(fake.broadcasts) == 1


def test_a_pending_broadcast_configures_the_event() -> None:
    event = OrderShipped(Order(1))
    pending = broadcast(event)
    pending.to_others()
    pending.via("quiet")
    assert event.broadcast_connections() == ["quiet"]
    pending._sent = True  # let it fall out of scope without broadcasting


def test_a_pending_broadcast_works_with_a_plain_object() -> None:
    class Bare:
        pass

    event = Bare()
    pending = broadcast(event)
    pending.to_others()
    pending.via("quiet")
    assert event.socket is None
    assert event.broadcast_connections() == ["quiet"]
    pending.via(["a", "b"])
    assert event.broadcast_connections() == ["a", "b"]
    pending._sent = True


def test_a_pending_broadcast_sends_when_it_falls_out_of_scope(
    _isolated_manager: BroadcastManager,
) -> None:
    from almasix.broadcasting.helpers import PendingBroadcast

    sent: list[Any] = []
    pending = PendingBroadcast(OrderShipped(Order(1)))
    pending.send = lambda: sent.append(True)  # type: ignore[method-assign]
    pending.__del__()
    assert sent == [True]

    # A failure on the way out stays there: __del__ cannot raise usefully.
    def explode() -> None:
        raise RuntimeError("too late")

    other = PendingBroadcast(OrderShipped(Order(1)))
    other.send = explode  # type: ignore[method-assign]
    other.__del__()


def test_broadcasting_from_synchronous_code_runs_its_own_loop(
    _isolated_manager: BroadcastManager,
) -> None:
    fake = FakeBroadcaster()
    _isolated_manager.set_connection("test", fake)

    class Immediate(ShouldBroadcastNow):
        def broadcast_on(self) -> list[str]:
            return ["news"]

    queue_broadcast(Immediate())  # no running loop: this blocks until sent
    assert fake.broadcasts[0].event == "Immediate"


def test_the_current_socket_comes_from_the_request_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    from almasix.broadcasting.helpers import current_socket_id

    # `almasix.http.request` is also the name of a helper function on the
    # package, so reach the module itself rather than the attribute.
    request_module = importlib.import_module("almasix.http.request")

    monkeypatch.setattr(request_module, "get_request", lambda: None)
    assert current_socket_id() is None

    class Request:
        def header(self, key: str, default: Any = None) -> Any:
            return "9.9" if key == "X-Socket-ID" else default

    monkeypatch.setattr(request_module, "get_request", lambda: Request())
    assert current_socket_id() == "9.9"


# ------------------------------------------------------------------- testing


@pytest.mark.asyncio
async def test_the_fake_records_and_asserts(_isolated_manager: BroadcastManager) -> None:
    fake = Broadcast.fake()
    await Broadcast.send(OrderShipped(Order(1)))

    fake.assert_broadcast("OrderShipped")
    fake.assert_broadcast(OrderShipped)
    fake.assert_broadcast_on("OrderShipped", "private-orders.1")
    fake.assert_broadcast_count(1)
    fake.assert_not_broadcast("Nothing")
    assert fake.recorded("OrderShipped", lambda record: record.on("shipping"))

    with pytest.raises(AssertionError, match="was not broadcast"):
        fake.assert_broadcast("Missing")
    with pytest.raises(AssertionError, match="not as expected"):
        fake.assert_broadcast("OrderShipped", lambda record: record.on("nowhere"))
    with pytest.raises(AssertionError, match="not broadcast on channel"):
        fake.assert_broadcast_on("OrderShipped", "nowhere")
    with pytest.raises(AssertionError, match="unexpectedly"):
        fake.assert_not_broadcast("OrderShipped")
    with pytest.raises(AssertionError, match="Expected no broadcasts"):
        fake.assert_nothing_broadcast()
    with pytest.raises(AssertionError, match="Expected 5"):
        fake.assert_broadcast_count(5)

    fake.flush()
    fake.assert_nothing_broadcast()
    with pytest.raises(AssertionError, match="Broadcast: nothing"):
        fake.assert_broadcast("OrderShipped")


@pytest.mark.asyncio
async def test_the_fake_names_an_event_class_the_way_it_broadcasts() -> None:
    fake = FakeBroadcaster()

    class Aliased(ShouldBroadcast):
        @staticmethod
        def broadcast_as() -> str:
            return "aliased"

        def broadcast_on(self) -> list[str]:
            return ["news"]

    class Instance(ShouldBroadcast):
        """`broadcast_as` needs an instance, so the class name is the answer."""

        def broadcast_as(self) -> str:
            return "instance"

        def broadcast_on(self) -> list[str]:
            return ["news"]

    await fake.broadcast(["news"], "aliased", {})
    await fake.broadcast(["news"], "Instance", {})

    fake.assert_broadcast(Aliased)
    fake.assert_broadcast(Instance)
    assert len(fake.recorded()) == 2


# ------------------------------------------------------------------- façade


@pytest.mark.asyncio
async def test_the_facade_reaches_the_manager(_isolated_manager: BroadcastManager) -> None:
    Broadcast.set_manager(_isolated_manager)
    assert Broadcast.manager() is _isolated_manager
    assert isinstance(Broadcast.connection(), WebsocketBroadcaster)
    assert isinstance(Broadcast.driver("quiet"), NullBroadcaster)

    Broadcast.channel("orders.{order}", lambda user, order: True)
    assert len(Broadcast.channels()) == 1
    assert await Broadcast.authorize(User(), "private-orders.1") is True
    assert "auth" in await Broadcast.auth(
        FakeRequest({"channel_name": "private-orders.1", "socket_id": "1.1"}, User())
    )

    fake = FakeBroadcaster()
    Broadcast.extend("fake", lambda name, config: fake)
    Broadcast.purge()
    await Broadcast.event("news", "tick")
    Broadcast.purge()


def test_the_facade_finds_a_manager_when_none_was_set() -> None:
    set_broadcast_manager(None)
    Broadcast.set_manager(None)
    assert isinstance(Broadcast.manager(), BroadcastManager)


def test_the_facade_queues_an_event(_isolated_manager: BroadcastManager) -> None:
    Broadcast.set_manager(_isolated_manager)

    class Quiet(ShouldBroadcast):
        def broadcast_on(self) -> list[str]:
            return []

    Broadcast.queue(Quiet())  # no channels: nothing happens, and nothing raises


# ------------------------------------------------------------------ provider


def test_the_provider_binds_a_manager_and_adds_the_routes(tmp_path: Any) -> None:
    from almasix.broadcasting.provider import AUTH_ROUTE, USER_AUTH_ROUTE, BroadcastServiceProvider
    from almasix.framework.application import Application

    (tmp_path / "routes").mkdir()
    (tmp_path / "routes" / "channels.py").write_text(
        "from almasix.broadcasting import Broadcast\n"
        "Broadcast.channel('rooms.{room}', lambda user, room: True)\n",
        encoding="utf-8",
    )

    app = Application(base_path=tmp_path)
    app.config.set("broadcasting", CONFIG)
    provider = BroadcastServiceProvider(app)
    provider.register()
    provider.boot()

    manager = app.make(BroadcastManager)
    assert manager.config["default"] == "test"
    assert [route.pattern for route in manager.channels()] == ["rooms.{room}"]

    uris = {route.uri for route in app.router.routes}
    assert AUTH_ROUTE in uris
    assert USER_AUTH_ROUTE in uris
    assert [route.uri for route in app.router.websocket_routes] == ["/broadcasting/socket"]

    # Booting twice must not register anything a second time.
    provider.boot()
    assert len([route for route in app.router.routes if route.uri == AUTH_ROUTE]) == 1
    assert len(app.router.websocket_routes) == 1
    assert len(manager.channels()) == 1


def test_the_provider_falls_back_to_the_default_configuration(tmp_path: Any) -> None:
    from almasix.broadcasting.provider import BroadcastServiceProvider
    from almasix.framework.application import Application

    app = Application(base_path=tmp_path)
    app.config.set("broadcasting", {})
    provider = BroadcastServiceProvider(app)
    provider.register()
    provider.boot()

    manager = app.make(BroadcastManager)
    assert manager.get_default_driver() == "log"
    # The log driver hosts no socket, so no socket route is added.
    assert app.router.websocket_routes == []
    assert manager.channels() == []


def test_an_application_can_write_the_endpoints_itself(tmp_path: Any) -> None:
    from almasix.broadcasting.provider import BroadcastServiceProvider
    from almasix.framework.application import Application

    app = Application(base_path=tmp_path)
    app.config.set("broadcasting", {**CONFIG, "routes": False})
    provider = BroadcastServiceProvider(app)
    provider.register()
    provider.boot()
    assert app.router.routes == []


def test_no_socket_is_mounted_for_a_connection_that_is_not_configured(
    tmp_path: Any,
) -> None:
    from almasix.broadcasting.provider import BroadcastServiceProvider
    from almasix.framework.application import Application

    app = Application(base_path=tmp_path)
    app.config.set("broadcasting", {"default": "absent", "connections": {}})
    provider = BroadcastServiceProvider(app)
    provider.register()
    provider.boot()
    assert app.router.websocket_routes == []


def test_the_provider_does_nothing_when_nothing_is_bound(tmp_path: Any) -> None:
    from almasix.broadcasting.provider import BroadcastServiceProvider
    from almasix.framework.application import Application

    app = Application(base_path=tmp_path)
    BroadcastServiceProvider(app).boot()  # register() was never called
    assert app.router.routes == []


# -------------------------------------------------------- model broadcasting


def test_a_model_that_broadcasts_needs_to_say_where() -> None:
    class Silent(BroadcastsEvents):
        pass

    with pytest.raises(NotImplementedError, match="broadcast_on"):
        Silent().broadcast_on("created")


def test_a_model_event_names_itself_after_the_model() -> None:
    from almasix.broadcasting.model import BroadcastableModelEvent

    class Post(BroadcastsEvents):
        def to_dict(self) -> dict[str, int]:
            return {"id": 1}

        def broadcast_on(self, event: str) -> list[str]:
            return ["posts"]

    post = Post()
    event = post.new_broadcastable_event("updated")
    assert isinstance(event, BroadcastableModelEvent)
    assert event.broadcast_as() == "PostUpdated"
    assert event.broadcast_with() == {"model": {"id": 1}}
    assert event.broadcast_on() == ["posts"]
    assert event.broadcast_connections() == [None]


def test_a_model_can_name_its_own_event_and_payload() -> None:
    class Post(BroadcastsEvents):
        broadcasts_now = True

        def broadcast_on(self, event: str) -> list[str]:
            return ["posts"]

        def broadcast_as(self, event: str) -> str:
            return f"post.{event}"

        def broadcast_with(self, event: str) -> dict[str, str]:
            return {"event": event}

    event = Post().new_broadcastable_event("created")
    assert isinstance(event, ShouldBroadcastNow)
    assert event.broadcast_as() == "post.created"
    assert event.broadcast_with() == {"event": "created"}


def test_a_model_that_returns_no_channels_broadcasts_nothing() -> None:
    class Post(BroadcastsEvents):
        def broadcast_on(self, event: str) -> list[str]:
            return []

    post = Post()
    assert post.new_broadcastable_event("created") is None
    post.broadcast_change("created")  # no channels, no broadcast, no error


class Note(BroadcastsEvents, SoftDeletes, Model):
    """A model whose every write goes out, so the listeners can be watched."""

    table = "notes"
    timestamps = False
    broadcasts_now = True
    fillable = ("body",)

    def broadcast_on(self, event: str) -> list[Any]:
        return [PrivateChannel(f"notes.{self.get_key()}")]


class CommittedNote(BroadcastsEventsAfterCommit, Model):
    table = "committed_notes"
    timestamps = False
    broadcasts_now = True
    fillable = ("body",)

    def broadcast_on(self, event: str) -> list[Any]:
        return [PrivateChannel("committed")]


@pytest.fixture()
async def notes_schema(memory_db: Any) -> Any:
    del memory_db
    from almasix.orm import Schema

    await Schema.create(
        "notes",
        lambda table: (
            table.id(),
            table.string("body"),
            table.timestamp("deleted_at").nullable(),
        ),
    )
    await Schema.create(
        "committed_notes",
        lambda table: (table.id(), table.string("body")),
    )
    return None


@pytest.mark.asyncio
async def test_a_model_broadcasts_every_kind_of_write(
    notes_schema: Any,
    _isolated_manager: BroadcastManager,
) -> None:
    del notes_schema
    fake = FakeBroadcaster()
    _isolated_manager.set_connection("test", fake)

    note = await Note.create(body="first")
    await flush_broadcasts()
    assert fake.broadcasts[-1].event == "NoteCreated"
    assert fake.broadcasts[-1].channels == [f"private-notes.{note.get_key()}"]
    assert fake.broadcasts[-1].payload["model"]["body"] == "first"

    note.body = "second"
    await note.save()
    await flush_broadcasts()
    assert fake.broadcasts[-1].event == "NoteUpdated"

    await note.delete()  # soft: the row and the instance survive
    await flush_broadcasts()
    assert fake.broadcasts[-1].event == "NoteTrashed"

    await note.restore()
    await flush_broadcasts()
    assert fake.broadcasts[-1].event == "NoteRestored"

    await note.force_delete()
    await flush_broadcasts()
    assert fake.broadcasts[-1].event == "NoteDeleted"


@pytest.mark.asyncio
async def test_an_after_commit_model_waits_for_the_transaction(
    notes_schema: Any,
    _isolated_manager: BroadcastManager,
) -> None:
    del notes_schema
    from almasix.orm.facade import get_manager

    fake = FakeBroadcaster()
    _isolated_manager.set_connection("test", fake)
    connection = get_manager().connection()

    async with connection.transaction():
        await CommittedNote.create(body="held")
        await flush_broadcasts()
        assert fake.broadcasts == []

    await flush_broadcasts()
    assert fake.broadcasts[-1].event == "CommittedNoteCreated"


@pytest.mark.asyncio
async def test_a_rolled_back_transaction_broadcasts_nothing(
    notes_schema: Any,
    _isolated_manager: BroadcastManager,
) -> None:
    del notes_schema
    from almasix.orm.facade import get_manager

    fake = FakeBroadcaster()
    _isolated_manager.set_connection("test", fake)
    connection = get_manager().connection()

    with pytest.raises(RuntimeError, match="changed my mind"):
        async with connection.transaction():
            await CommittedNote.create(body="doomed")
            raise RuntimeError("changed my mind")

    await flush_broadcasts()
    assert fake.broadcasts == []


@pytest.mark.asyncio
async def test_an_after_commit_event_waits_for_the_transaction(
    notes_schema: Any,
    _isolated_manager: BroadcastManager,
) -> None:
    del notes_schema
    from almasix.orm.facade import get_manager

    fake = FakeBroadcaster()
    _isolated_manager.set_connection("test", fake)

    class Committed(ShouldBroadcastAfterCommit, ShouldBroadcastNow):
        def broadcast_on(self) -> list[str]:
            return ["news"]

    connection = get_manager().connection()
    async with connection.transaction():
        queue_broadcast(Committed())
        await flush_broadcasts()
        assert fake.broadcasts == []

    await flush_broadcasts()
    assert len(fake.broadcasts) == 1


@pytest.mark.asyncio
async def test_an_after_commit_model_with_no_channels_stays_quiet(
    notes_schema: Any,
    _isolated_manager: BroadcastManager,
) -> None:
    del notes_schema
    fake = FakeBroadcaster()
    _isolated_manager.set_connection("test", fake)

    class Quiet(BroadcastsEventsAfterCommit, Model):
        table = "committed_notes"
        timestamps = False
        fillable = ("body",)

        def broadcast_on(self, event: str) -> list[Any]:
            return []

    await Quiet.create(body="nothing to say")
    await flush_broadcasts()
    assert fake.broadcasts == []


@pytest.mark.asyncio
async def test_an_after_commit_broadcast_outside_a_transaction_goes_now(
    notes_schema: Any,
    _isolated_manager: BroadcastManager,
) -> None:
    del notes_schema
    fake = FakeBroadcaster()
    _isolated_manager.set_connection("test", fake)

    class Committed(ShouldBroadcastAfterCommit, ShouldBroadcastNow):
        def broadcast_on(self) -> list[str]:
            return ["news"]

    # A database is configured, but nothing is in flight to wait for.
    queue_broadcast(Committed())
    await flush_broadcasts()
    assert len(fake.broadcasts) == 1


@pytest.mark.asyncio
async def test_a_model_falls_back_to_the_default_name_and_payload() -> None:
    class Post(BroadcastsEvents):
        def to_dict(self) -> dict[str, int]:
            return {"id": 2}

        def broadcast_on(self, event: str) -> list[str]:
            return ["posts"]

        def broadcast_as(self, event: str) -> str | None:
            return None

        def broadcast_with(self, event: str) -> None:
            return None

    event = Post().new_broadcastable_event("created")
    assert event.broadcast_as() == "PostCreated"
    assert event.broadcast_with() == {"model": {"id": 2}}
