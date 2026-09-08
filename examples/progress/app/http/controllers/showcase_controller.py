"""Prism showcase — exhaust surface for the living example."""

from __future__ import annotations

from almasix import __version__
from almasix.prism import view
from almasix.http import Controller, Response


class ShowcaseController(Controller):
    async def index(self) -> Response:
        return view(
            "showcase",
            {
                "version": __version__,
                "show_welcome": True,
                "directives": [
                    "@extends / @section / @yield / @include",
                    "@component / <x-*> / @props / {{ slot }}",
                    "<x-slot:name> / @slot / nested components",
                    "@aware parent → child data",
                    "class-based Component (app/view/components)",
                    "@push / @stack / @once",
                    "@if / @foreach / @forelse / @unless",
                    "@lang / __()",
                    "asset() + public/css|js|images",
                ],
            },
        )
