"""Starter kit catalogue for ``almasix new --kit``.

Kits are **overlays** on the M32 scaffold: ``stubs/app`` + stack render first,
then ``stubs/kits/<kit>/…`` replaces and extends files. SPA kits pin a Vite +
Tailwind frontend and choose an Inertia client (React / Vue / Svelte).
"""

from __future__ import annotations

from dataclasses import dataclass

from almasix.installer.scaffold import ScaffoldError


@dataclass(frozen=True)
class Kit:
    """A starter-kit overlay the installer can apply."""

    name: str
    label: str
    description: str
    #: Directory under ``stubs/kits/`` (may equal ``name``).
    folder: str
    #: ``web`` | ``api`` | ``spa`` | ``none``
    kind: str
    #: Inertia client for SPA kits.
    frontend: str | None = None
    #: Force this CSS/bundler stack when set (SPA always uses Tailwind).
    force_stack: str | None = None
    #: Whether the kit expects npm (Inertia clients, Vite).
    needs_node: bool = False


#: Default = blank M32 scaffold (no overlay).
KITS: tuple[Kit, ...] = (
    Kit(
        name="none",
        label="None",
        description="Blank M32 scaffold — auth login/register only",
        folder="",
        kind="none",
    ),
    Kit(
        name="web",
        label="Web (Conduit)",
        description="Prism + Conduit auth, settings, teams, 2FA, notifications shell",
        folder="web",
        kind="web",
        needs_node=False,  # stack decides
    ),
    Kit(
        name="api",
        label="API (Signet)",
        description="JSON API polarity + Signet personal access tokens (no session UI)",
        folder="api",
        kind="api",
        force_stack="none",
    ),
    Kit(
        name="react",
        label="SPA — React + Inertia",
        description="Official @inertiajs/react client, same product surface as Web",
        folder="spa/react",
        kind="spa",
        frontend="react",
        force_stack="tailwind",
        needs_node=True,
    ),
    Kit(
        name="vue",
        label="SPA — Vue + Inertia",
        description="Official @inertiajs/vue3 client, same product surface as Web",
        folder="spa/vue",
        kind="spa",
        frontend="vue",
        force_stack="tailwind",
        needs_node=True,
    ),
    Kit(
        name="svelte",
        label="SPA — Svelte + Inertia",
        description="Official @inertiajs/svelte client, same product surface as Web",
        folder="spa/svelte",
        kind="spa",
        frontend="svelte",
        force_stack="tailwind",
        needs_node=True,
    ),
)

KIT_NAMES = tuple(kit.name for kit in KITS)
DEFAULT_KIT = "none"

#: CSS stacks offered when scaffolding the Web kit (user brief: Tailwind / Bootstrap / None).
WEB_STACK_NAMES = ("tailwind", "bootstrap", "none")


def find_kit(name: str) -> Kit:
    key = (name or DEFAULT_KIT).strip().lower()
    # Aliases
    aliases = {
        "spa": "react",
        "inertia": "react",
        "conduit": "web",
        "livewire": "web",
        "signet": "api",
        "breeze": "web",
    }
    key = aliases.get(key, key)
    for kit in KITS:
        if kit.name == key:
            return kit
    raise ScaffoldError(f"Unknown kit {name!r}. Choose one of: {', '.join(KIT_NAMES)}.")
