"""M50 smoke — the helper surface and the two pages that document it."""

from __future__ import annotations

import inspect
import pathlib
import re

import pytest

from almasix.support import Arr, Number, Str, Stringable, str_

pytestmark = pytest.mark.smoke

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCS = ROOT / "website" / "src" / "content" / "docs"
HELPERS = DOCS / "helpers.md"
STRINGS = DOCS / "strings.md"

# Laravel's names, kept as aliases; the Python name is the documented one.
ALIASES = {"from", "is"}


def public_names(target: type) -> set[str]:
    """Public methods on a helper class, minus the camelCase aliases."""
    found = set()
    for name, member in vars(target).items():
        if name.startswith("_") or name in ALIASES:
            continue
        function = member.__func__ if isinstance(member, (staticmethod, classmethod)) else member
        if callable(function):
            found.add(name)
    return {name for name in found if name.islower()}


def fluent_names() -> set[str]:
    """Stringable's public surface, including the delegates installed at import."""
    return {
        name
        for name in dir(Stringable)
        if not name.startswith("_") and name.islower() and callable(getattr(Stringable, name))
    }


def sections(page: pathlib.Path, heading: str) -> list[str]:
    text = page.read_text(encoding="utf-8")
    start = text.index(f"## {heading}")
    rest = text[start + 1 :]
    end = rest.find("\n## ")
    body = rest if end == -1 else rest[:end]
    return re.findall(r"^### ([a-z_0-9]+)\s*$", body, re.M)


# --- a section per method -----------------------------------------------------


@pytest.mark.parametrize(
    ("target", "page", "heading"),
    [
        (Arr, HELPERS, "Arrays and objects"),
        (Number, HELPERS, "Numbers"),
        (Str, STRINGS, "Strings"),
    ],
)
def test_every_public_method_has_its_own_section(
    target: type,
    page: pathlib.Path,
    heading: str,
) -> None:
    """Laravel documents a section per method; a new method must bring one."""
    documented = sections(page, heading)

    assert public_names(target) - set(documented) == set()
    assert set(documented) - public_names(target) == set()


def test_every_fluent_method_has_its_own_section() -> None:
    documented = sections(STRINGS, "Fluent strings")

    assert fluent_names() - set(documented) == set()
    assert set(documented) - fluent_names() == set()


@pytest.mark.parametrize(
    ("page", "heading"),
    [
        (HELPERS, "Arrays and objects"),
        (HELPERS, "Numbers"),
        (HELPERS, "Miscellaneous"),
        (STRINGS, "Strings"),
        (STRINGS, "Fluent strings"),
    ],
)
def test_each_group_is_alphabetical_and_free_of_duplicates(
    page: pathlib.Path,
    heading: str,
) -> None:
    documented = sections(page, heading)

    assert documented == sorted(documented)
    assert len(documented) == len(set(documented))


def test_every_documented_helper_can_be_imported_from_the_page_it_names() -> None:
    """The Miscellaneous group documents helpers that must actually exist."""
    import importlib

    homes = {
        "almasix.support",
        "almasix.framework",
        "almasix.http",
        "almasix.session",
        "almasix.prism",
        "almasix.log",
        "almasix.cache",
        "almasix.config",
        "almasix.auth",
        "almasix.auth.access",
        "almasix.encryption",
        "almasix.events",
        "almasix.queue",
        "almasix.hashing",
        "almasix.validation",
        "almasix.routing",
    }
    modules = [importlib.import_module(name) for name in sorted(homes)]

    for helper in sections(HELPERS, "Miscellaneous"):
        assert any(hasattr(module, helper) for module in modules), helper


# --- the concepts around the method lists -------------------------------------


def test_the_pages_cover_the_concepts_around_the_method_lists() -> None:
    helpers = HELPERS.read_text(encoding="utf-8")
    strings = STRINGS.read_text(encoding="utf-8")

    for heading in (
        "## Where each helper lives",
        "## Arrays and objects",
        "## Data paths",
        "## Numbers",
        "## Paths",
        "## URLs",
        "## Miscellaneous",
        "## Not yet built",
        "## Other utilities",
    ):
        assert heading in helpers, heading

    for heading in ("## Not ported", "## Strings", "## Fluent strings"):
        assert heading in strings, heading


def test_the_pages_name_what_almasix_has_not_built() -> None:
    """Absences are decisions, and the reader should be able to read them."""
    helpers = HELPERS.read_text(encoding="utf-8")

    for absent in ("broadcast", "context", "fake", "Benchmarking", "Lottery", "Timebox"):
        assert absent in helpers, absent

    for deferred in ("scan", "toHtmlString", "toUri"):
        assert deferred in STRINGS.read_text(encoding="utf-8"), deferred


# --- the gaps the audit found are closed --------------------------------------


def test_the_string_gaps_the_audit_found_are_closed() -> None:
    assert Str.doesnt_start_with("ada", "grace") is True
    assert Str.doesnt_end_with("ada", "grace") is True
    assert Str.initials("Ada Lovelace") == "A. L."
    assert Str.match(r"\d+", "order 42") == "42"
    assert Str.match_all(r"\d+", "1 and 2") == ["1", "2"]
    assert Str.is_match(r"^ada$", "ada") is True
    assert Str.ucwords("ada lovelace") == "Ada Lovelace"


def test_the_fluent_wrapper_delegates_the_whole_static_surface() -> None:
    """Str.slug(value) used to work while str_(value).slug() did not."""
    missing = {
        name
        for name in public_names(Str)
        if not hasattr(Stringable, name)
    }

    assert missing == set()
    assert str_("Ada Lovelace").slug().value() == "ada-lovelace"
    assert str_("ada lovelace").ucwords().value() == "Ada Lovelace"


def test_a_fluent_call_leaves_its_subject_alone() -> None:
    name = str_("ada")

    assert name.upper().value() == "ADA"
    assert name.value() == "ada"


def test_the_array_and_number_gaps_the_audit_found_are_closed() -> None:
    assert Arr.integer({"count": 2}, "count") == 2
    assert Arr.has_all({"a": 1, "b": 2}, ["a", "b"]) is True
    assert Arr.some([1, 2], lambda item: item > 1) is True
    assert Arr.every([1, 2], lambda item: item > 0) is True
    assert Arr.sole([1], lambda item: item == 1) == 1
    assert Arr.partition([1, 2, 3], lambda item: item > 1) == ([2, 3], [1])
    assert Arr.select([{"a": 1, "b": 2}], "a") == [{"a": 1}]
    assert Arr.from_({"a": 1}) == {"a": 1}

    assert Number.spell_ordinal(1) == "first"
    assert Number.parse_int("1,234") == 1234
    assert Number.parse_float("1,234.5") == 1234.5


def test_the_global_helpers_that_had_no_counterpart_now_exist() -> None:
    from almasix.auth.access import policy
    from almasix.framework import app, resolve
    from almasix.hashing import bcrypt
    from almasix.http import back, request, response
    from almasix.log import info, logger
    from almasix.session import cookie, old, session
    from almasix.support import report
    from almasix.validation import validator

    for helper in (
        app,
        resolve,
        request,
        response,
        back,
        session,
        old,
        cookie,
        logger,
        info,
        bcrypt,
        policy,
        report,
        validator,
    ):
        assert callable(helper)

    assert request() is None  # outside a request, and honest about it


# --- the living example ------------------------------------------------------

PROGRESS = ROOT / "examples" / "progress"


@pytest.fixture()
def progress_cwd(monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    from almasix.console.kernel import ConsoleKernel
    from almasix.smith.cli import app as smith_app
    from tests.support import purge_generated_app_modules, without_base_path

    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    ConsoleKernel.from_cwd(PROGRESS).register_on_typer(smith_app)
    return PROGRESS


def test_the_helpers_demo_shows_the_surface_m50_added(progress_cwd: pathlib.Path) -> None:
    del progress_cwd
    from typer.testing import CliRunner

    from almasix.smith.cli import app as smith_app

    result = CliRunner().invoke(smith_app, ["progress:helpers"])
    output = result.stdout + (result.stderr or "")

    assert result.exit_code == 0, output
    assert "helpers demo ok" in output.lower()
    # The fluent chain, the wildcard, and the Arr / Number gaps all ran.
    assert "Almasix Framework!" in output
    assert "[30, 12]" in output
    assert "third" in output


def test_the_collections_demo_shows_the_surface_m49_added(progress_cwd: pathlib.Path) -> None:
    del progress_cwd
    from typer.testing import CliRunner

    from almasix.smith.cli import app as smith_app

    result = CliRunner().invoke(smith_app, ["progress:collections"])
    output = result.stdout + (result.stderr or "")

    assert result.exit_code == 0, output
    assert "collections demo ok" in output.lower()
    # A lazy pipeline read a handful of items, not the million behind them.
    assert "[3, 6, 9, 12] after reading 12" in output


def test_the_board_marks_the_support_exhaust_complete(progress_cwd: pathlib.Path) -> None:
    del progress_cwd
    from app.http.controllers.progress_controller import _milestones

    board = {milestone["id"]: milestone for milestone in _milestones()}

    for identifier in ("M49", "M50"):
        assert board[identifier]["status"] == "complete", identifier
    # The proof points at something a reader can run, not just a claim.
    assert "smith progress:collections" in board["M49"]["proof"]
    assert "smith progress:helpers" in board["M50"]["proof"]
