"""Starter-kit catalogue for ``almasix new --kit``.

``none`` is built into core. Conduit (web), Signet (api), and Inertia SPA
kits live in ``almasix-starter-kit-*`` packages and register via the
``almasix.kits`` entry-point group.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import entry_points
from pathlib import Path

from almasix.installer.scaffold import ScaffoldError

# Known kit name → pip package (for missing-install errors).
_KIT_PACKAGES: dict[str, str] = {
    "web": "almasix-starter-kit-web",
    "api": "almasix-starter-kit-api",
    "react": "almasix-starter-kit-spa",
    "vue": "almasix-starter-kit-spa",
    "svelte": "almasix-starter-kit-spa",
}


@dataclass(frozen=True, slots=True)
class Kit:
    name: str
    label: str
    description: str
    kind: str  # none | web | api | spa
    frontend: str | None = None
    force_stack: str | None = None
    needs_node: bool = False
    # Package resource root containing ``_common/`` (+ variant overlays).
    # Built-in ``none`` leaves this unset; discovered kits must set it.
    stub_root: Path | None = None
    # Legacy field retained for older call sites; unused when stub_root is set.
    folder: str = ""


NONE_KIT = Kit(
    name="none",
    label="None",
    description="Blank Almasix app (no starter overlay).",
    kind="none",
    force_stack=None,
    needs_node=False,
    stub_root=None,
    folder="",
)

# Historical CLI aliases → canonical kit name.
ALIASES: dict[str, str] = {
    "blank": "none",
    "conduit": "web",
    "livewire": "web",
    "signet": "api",
    "api-only": "api",
    "inertia": "react",
    "spa": "react",
    "react-spa": "react",
    "vue-spa": "vue",
    "svelte-spa": "svelte",
}

WEB_STACK_NAMES = ("tailwind", "bootstrap", "none")


def _load_entry_point(ep: object) -> Kit:
    loaded = ep.load()  # type: ignore[attr-defined]
    kit = loaded() if callable(loaded) else loaded
    if not isinstance(kit, Kit):
        raise TypeError(
            f"almasix.kits entry point {getattr(ep, 'name', '?')!r} "
            f"must return almasix.installer.kits.Kit, got {type(kit)!r}"
        )
    if kit.stub_root is None and kit.kind != "none":
        raise TypeError(
            f"Kit {kit.name!r} from entry points must set stub_root "
            f"(package data directory for overlays)."
        )
    return kit


@lru_cache(maxsize=1)
def _discovered() -> dict[str, Kit]:
    """Load kits from installed ``almasix.kits`` entry points."""
    eps = entry_points()
    if hasattr(eps, "select"):
        group = eps.select(group="almasix.kits")
    else:  # pragma: no cover — Python <3.10 style
        group = eps.get("almasix.kits", ())  # type: ignore[union-attr]
    out: dict[str, Kit] = {}
    for ep in group:
        kit = _load_entry_point(ep)
        out[kit.name] = kit
    return out


def clear_kit_cache() -> None:
    """Drop the entry-point cache (tests / after installing a kit package)."""
    _discovered.cache_clear()


def get_kits() -> tuple[Kit, ...]:
    """Built-in ``none`` plus every discovered starter kit (sorted by name)."""
    discovered = sorted(_discovered().values(), key=lambda k: k.name)
    return (NONE_KIT, *discovered)


def kit_names() -> tuple[str, ...]:
    return tuple(k.name for k in get_kits())


def __getattr__(name: str) -> object:
    """Lazy ``KITS`` / ``KIT_NAMES`` so discovery stays current after installs."""
    if name == "KITS":
        return get_kits()
    if name == "KIT_NAMES":
        return kit_names()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _hint_for(name: str) -> str:
    pkg = _KIT_PACKAGES.get(name)
    if pkg:
        return (
            f" Kit {name!r} is provided by {pkg}. "
            f"Install it with: pip install {pkg}   (or: pip install 'almasix[kits]')"
        )
    if not _discovered():
        return (
            " Only the blank kit is built into Almasix. "
            "Install starter kits with: pip install 'almasix[kits]' "
            "(or almasix-starter-kit-web / -api / -spa)."
        )
    return ""


def find_kit(name: str) -> Kit:
    key = ALIASES.get(name, name)
    if key == "none":
        return NONE_KIT
    discovered = _discovered()
    if key in discovered:
        return discovered[key]
    available = ", ".join(kit_names())
    raise ScaffoldError(f"Unknown kit {name!r}. Choose one of: {available}.{_hint_for(key)}")
