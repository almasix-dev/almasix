"""AuthorController."""

from __future__ import annotations

from almasix.http import Controller, Request

from app.models.author import Author


class AuthorController(Controller):
    """The seven actions `Route.resource` registers, bound to Author.

    The type hints are what implicit binding reads: a request for
    `/authors/7` arrives here with the Author already loaded,
    or 404s before it does.
    """

    async def index(self):
        """GET — a listing."""
        return await Author.query().get()

    async def create(self):
        """GET /create — the form that stores one."""

    async def store(self, request: Request):
        """POST — persist a new author."""

    async def show(self, author: Author):
        """GET /{id} — one author."""
        return author

    async def edit(self, author: Author):
        """GET /{id}/edit — the form that updates one."""

    async def update(self, request: Request, author: Author):
        """PUT|PATCH /{id} — persist a change."""

    async def destroy(self, author: Author):
        """DELETE /{id} — remove one."""
