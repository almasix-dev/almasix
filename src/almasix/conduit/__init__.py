"""Conduit — Livewire 4-class reactive components for Almasix.

Import::

    from almasix.conduit import Component, Conduit, conduit
"""

from __future__ import annotations

from almasix.conduit.attributes import Computed, Locked, Modelable, On
from almasix.conduit.component import Component
from almasix.conduit.manager import Conduit, conduit
from almasix.conduit.pagination import WithPagination
from almasix.conduit.parity import PARITY, parity_rows, parity_summary
from almasix.conduit.provider import ConduitServiceProvider

__all__ = [
    "PARITY",
    "Component",
    "Computed",
    "Conduit",
    "ConduitServiceProvider",
    "Locked",
    "Modelable",
    "On",
    "WithPagination",
    "conduit",
    "parity_rows",
    "parity_summary",
]
