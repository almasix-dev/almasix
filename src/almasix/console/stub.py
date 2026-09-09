"""Generator stubs — the files ``make:*`` writes from.

Stubs live as real files rather than f-strings inside the generators, so an
application can publish them with ``smith stub:publish`` and edit them. A stub
in the application's ``stubs/`` directory wins over the framework's copy of the
same name, which is how a team changes what every new controller looks like.

Placeholders are Laravel-shaped: ``{{ class }}`` and friends.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Mapping
from pathlib import Path

#: The stubs Almasix ships.
FRAMEWORK_STUBS = Path(__file__).parent / "stubs"

#: Where an application's overrides live, relative to its root.
PUBLISHED_DIRECTORY = "stubs"

_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class StubError(ValueError):
    """A stub was asked for that does not exist."""


def names() -> list[str]:
    """Every stub the framework ships, sorted."""
    return sorted(path.name for path in FRAMEWORK_STUBS.glob("*.stub"))


def path_for(name: str, *, base_path: Path | None = None) -> Path:
    """Resolve ``name``, preferring the application's published copy."""
    if base_path is not None:
        published = Path(base_path) / PUBLISHED_DIRECTORY / name
        if published.is_file():
            return published
    framework = FRAMEWORK_STUBS / name
    if not framework.is_file():
        raise StubError(f"No stub named {name!r}. Available: {', '.join(names())}")
    return framework


def render_text(body: str, replacements: Mapping[str, str] | None = None) -> str:
    """Fill the placeholders in ``body``.

    An unknown placeholder is left as it was written, so a hand-edited stub
    keeps whatever the author meant by it instead of collapsing to an empty
    string — and a Prism template's own ``{{ slot }}`` survives being generated.
    """
    values = dict(replacements or {})
    return _PLACEHOLDER_RE.sub(lambda match: values.get(match.group(1), match.group(0)), body)


def render(
    name: str,
    replacements: Mapping[str, str] | None = None,
    *,
    base_path: Path | None = None,
) -> str:
    """Read a stub and fill its placeholders."""
    body = path_for(name, base_path=base_path).read_text(encoding="utf-8")
    return render_text(body, replacements)


def publish(base_path: Path | str, *, force: bool = False) -> list[Path]:
    """Copy the framework stubs into ``<base_path>/stubs``, returning what landed."""
    target = Path(base_path) / PUBLISHED_DIRECTORY
    target.mkdir(parents=True, exist_ok=True)
    published: list[Path] = []
    for source in sorted(FRAMEWORK_STUBS.glob("*.stub")):
        destination = target / source.name
        if destination.exists() and not force:
            continue
        shutil.copy2(source, destination)
        published.append(destination)
    return published
