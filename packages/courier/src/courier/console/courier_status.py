"""A sample package command registered via ``ServiceProvider.commands``."""

from __future__ import annotations

from almasix.console.command import Command
from almasix.config import config


class CourierStatusCommand(Command):
    signature = "courier:status"
    description = "Show the Courier package driver"

    def handle(self) -> int:
        self.info(f"courier driver → {config('courier.driver')}")
        self.success("courier ok")
        return self.SUCCESS
