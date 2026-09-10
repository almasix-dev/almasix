"""Courier package routes."""

from almasix.routing import Route


def courier_home() -> dict[str, str]:
    return {"package": "courier", "status": "ok"}


Route.get("/courier", courier_home)
