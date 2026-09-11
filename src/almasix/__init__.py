"""Almasix — Python web framework (Articulate, Prism, Smith)."""

from __future__ import annotations

from pkgutil import extend_path

from almasix.debug import DumpAndDie, dd, dump, serialize, to_json

# Allow first-party extras (``almasix-conduit``, …) to contribute subpackages
# under the ``almasix`` namespace when the framework is installed editable.
__path__ = extend_path(__path__, __name__)

__version__ = "0.6.2"

__all__ = [
    "DumpAndDie",
    "__version__",
    "dd",
    "dump",
    "serialize",
    "to_json",
]
