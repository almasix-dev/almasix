"""Demo Event.dispatch / listen (M18)."""

from __future__ import annotations

from avalon.console.command import Command
from avalon.events import Event


class OrderShipped:
    def __init__(self, order_id: int) -> None:
        self.order_id = order_id


class ProgressEventsCommand(Command):
    signature = "progress:events"
    description = "Demo Event.listen / dispatch / until (M18)"

    def handle(self) -> int:
        Event.flush()
        seen: list[int] = []

        def on_shipped(event: OrderShipped) -> None:
            seen.append(event.order_id)

        Event.listen(OrderShipped, on_shipped)
        Event.listen("orders.*", lambda name, payload: seen.append(-1))

        Event.dispatch(OrderShipped(7))
        Event.dispatch("orders.created", [{"sku": "ABC"}])

        Event.listen(
            "ping",
            lambda _e: "pong",
        )
        assert Event.until("ping") == "pong"

        self.info(f"listeners saw: {seen}")
        self.success("events demo ok")
        return 0
