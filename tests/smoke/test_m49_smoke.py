"""M49 smoke — the collections surface and the page that documents it."""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

from avalon.support import Collection, LazyCollection, collect
from avalon.support.collection import HIGHER_ORDER_MESSAGES

pytestmark = pytest.mark.smoke

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "avalon" / "support" / "collection.py"
PAGE = ROOT / "website" / "src" / "content" / "docs" / "collections.md"


def public_methods() -> list[str]:
    """Every public method on the Support collection, from the source itself."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in tree.body:
        if not (isinstance(node, ast.ClassDef) and node.name == "Collection"):
            continue
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not item.name.startswith("_"):
                    names.append(item.name)
            elif isinstance(item, ast.Assign):
                names += [
                    target.id
                    for target in item.targets
                    if isinstance(target, ast.Name) and not target.id.startswith("_")
                ]
    return sorted(set(names))


def documented_methods() -> list[str]:
    page = PAGE.read_text(encoding="utf-8")
    reference = page[page.index("## Available methods") :]
    return re.findall(r"^### ([a-z_0-9]+)\s*$", reference, re.M)


def test_every_public_method_has_its_own_section() -> None:
    """Laravel documents a section per method; a new method must bring one."""
    documented = documented_methods()

    assert set(public_methods()) - set(documented) == set()


def test_no_section_documents_something_that_does_not_exist() -> None:
    assert set(documented_methods()) - set(public_methods()) == set()


def test_the_reference_is_alphabetical_and_free_of_duplicates() -> None:
    documented = documented_methods()

    assert documented == sorted(documented)
    assert len(documented) == len(set(documented))


def test_the_page_covers_the_concepts_around_the_method_list() -> None:
    page = PAGE.read_text(encoding="utf-8")

    for heading in (
        "## Keys",
        "## Creating collections",
        "## Extending collections",
        "## Higher order messages",
        "## Lazy collections",
        "### Streaming from the database",
        "### Lazy-only methods",
        "## Available methods",
    ):
        assert heading in page, heading


def test_the_gaps_the_audit_found_are_closed() -> None:
    rows = collect([{"votes": 3}, {"votes": 4}])

    # The methods that were missing from the Method Listing.
    assert rows.average("votes") == 3.5
    assert callable(rows.dd)
    assert callable(rows.dump)
    assert isinstance(rows.lazy(), LazyCollection)

    # Higher order messages, which had no counterpart at all.
    assert rows.sum.votes == 7
    assert len(HIGHER_ORDER_MESSAGES) == 24


def test_lazy_collections_stream_without_materialising() -> None:
    pulled: list[int] = []

    def source():
        for value in range(1000):
            pulled.append(value)
            yield value

    assert LazyCollection(source).map(lambda v: v * 2).take(3).all() == [0, 2, 4]
    assert pulled == [0, 1, 2]


def test_the_articulate_collection_still_extends_the_support_one() -> None:
    from avalon.orm import Collection as ModelCollection

    assert issubclass(ModelCollection, Collection)
