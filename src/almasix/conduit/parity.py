"""Livewire 4 → Conduit parity matrix (machine-readable).

Statuses: ``complete`` | ``partial`` | ``planned``.
Exhausted means every row is ``complete``, or a named deviation is documented
in Starlight **Conduit**.
"""

from __future__ import annotations

PARITY: dict[str, str] = {
    "wire:click (+ params)": "complete",
    "wire:click.async / .renderless / .preserve-scroll": "complete",
    "wire:model / .live / .blur / .change / .debounce": "complete",
    "wire:model.deep (v4 child events)": "complete",
    "wire:submit": "complete",
    "snapshot + checksum + CSRF": "complete",
    "signed update URLs (HMAC + expiry)": "complete",
    "request coalescing / batching": "complete",
    "HTML morph (idiomorph-lite)": "complete",
    "Alpine $wire + $errors": "complete",
    "effects.data client bindings (no roundtrip)": "complete",
    "APP_BASE_PATH / subpath hosting": "complete",
    "nested components (@conduit)": "complete",
    "validation errors": "complete",
    "events ($dispatch / wire:listen)": "complete",
    "$toggle / $set / $refresh / $js / $entangle": "complete",
    "lazy / defer placeholders": "complete",
    "file uploads (+ /conduit/upload)": "complete",
    "query-string binding": "complete",
    "wire:loading + data-loading (v4)": "complete",
    "wire:dirty": "complete",
    "wire:ignore / wire:ignore.self": "complete",
    "wire:poll": "complete",
    "wire:init": "complete",
    "wire:confirm": "complete",
    "wire:key": "complete",
    "wire:offline / wire:online": "complete",
    "wire:bind (client reactive attrs)": "complete",
    "wire:text / wire:show (client)": "complete",
    "wire:intersect (+ .once/.half/.full)": "complete",
    "wire:ref": "complete",
    "wire:sort (drag-and-drop)": "complete",
    "@island / wire:island scoped updates": "complete",
    "wire:navigate + View Transitions": "complete",
    "wire:transition (View Transitions API)": "complete",
    "inline HTML render() (SFC-style)": "complete",
    "Route.conduit() full-page components": "complete",
    "CSP-safe Alpine mode (conduit.csp_safe)": "complete",
    "WithPagination helpers": "complete",
    "Computed / Locked / On attributes": "complete",
    "smith make:conduit": "complete",
}


def parity_rows() -> list[tuple[str, str]]:
    return sorted(PARITY.items())


def parity_summary() -> dict[str, int]:
    counts = {"complete": 0, "partial": 0, "planned": 0}
    for status in PARITY.values():
        counts[status] = counts.get(status, 0) + 1
    return counts
