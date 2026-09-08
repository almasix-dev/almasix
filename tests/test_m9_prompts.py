"""M9 Almasix Prompts — non-interactive fallbacks and helpers."""

from __future__ import annotations

import time

import pytest

from almasix.console.command import Command
from almasix.console.prompts import (
    alert,
    clear,
    confirm,
    error,
    info,
    intro,
    multiselect,
    note,
    number,
    outro,
    password,
    pause,
    progress,
    search,
    select,
    spin,
    suggest,
    table,
    text,
    textarea,
    warning,
)
from almasix.console.prompts.busy import Progress
from almasix.console.prompts.types import is_interactive, required_message, run_validation


@pytest.fixture(autouse=True)
def _force_noninteractive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALMASIX_PROMPTS_INTERACTIVE", "0")


def test_is_interactive_env_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALMASIX_PROMPTS_INTERACTIVE", "0")
    assert is_interactive() is False
    monkeypatch.delenv("ALMASIX_PROMPTS_INTERACTIVE", raising=False)
    monkeypatch.setenv("CI", "true")
    assert is_interactive() is False


def test_validation_helpers() -> None:
    assert required_message(False) is None
    assert required_message(True) == "Required."
    assert required_message("Need it") == "Need it"
    assert run_validation("", required=True, validate=None) == "Required."
    assert run_validation("ok", required=True, validate=lambda v: "bad" if v == "x" else None) is None


def test_text_password_number_fallbacks() -> None:
    assert text("Name", default="Ada") == "Ada"
    assert password("Secret", required=False) == ""
    assert number("N", default=3) == 3
    assert number("N", default=1.5) == 1.5
    with pytest.raises(RuntimeError):
        text("Name", required=True, default="")


def test_textarea_fallback() -> None:
    assert textarea("Story", default="once") == "once"
    with pytest.raises(RuntimeError):
        textarea("Story", required=True, default="")


def test_confirm_select_multi_suggest_search() -> None:
    assert confirm("Go?", default=True) is True
    assert confirm("Go?", default=False) is False
    assert select("Pick", ["a", "b"], default="b") == "b"
    assert select("Pick", {"x": "X", "y": "Y"}, default="y") == "y"
    assert select("Pick", ["only"]) == "only"
    assert multiselect("Pick", ["a", "b"], default=["b"]) == ["b"]
    assert suggest("City", ["Paris", "Rome"], default="Paris") == "Paris"
    assert search("Find", lambda q: ["alpha", "beta"]) == "alpha"
    assert search("Find", lambda q: []) is None
    with pytest.raises(ValueError):
        select("Empty", [])
    with pytest.raises(ValueError):
        multiselect("Empty", [])
    with pytest.raises(RuntimeError):
        multiselect("Need", ["a"], required=True, default=[])
    with pytest.raises(RuntimeError):
        suggest("City", ["Paris"], required=True, default="")


def test_messages_and_table(capsys: pytest.CaptureFixture[str]) -> None:
    intro("Hello")
    outro("Bye")
    note("n")
    info("i")
    warning("w")
    error("e")
    alert("a")
    table(["A", "B"], [[1, 2]])
    clear()
    pause("noop")
    out = capsys.readouterr().out
    assert "Hello" in out
    assert "Bye" in out


def test_spin_and_progress() -> None:
    assert spin(lambda: 42, "x") == 42
    with pytest.raises(ValueError):
        spin(lambda: (_ for _ in ()).throw(ValueError("boom")), "x")

    results = progress("steps", ["a", "b"], lambda item: item.upper())
    assert results == ["A", "B"]

    bar = progress("manual", steps=2)
    assert isinstance(bar, Progress)
    bar.hint("halfway").label("manual").advance()
    bar.advance()
    bar.finish()


def test_command_ask_choice_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    class Demo(Command):
        signature = "demo:ask"

        def handle(self) -> int:
            assert self.ask("Name", default="Sam") == "Sam"
            assert self.choice("Role", ["admin", "user"], default="user") == "user"
            assert self.anticipate("City", ["Paris"], default="Paris") == "Paris"
            assert self.secret("Pass") == ""
            assert self.confirm("Ok?", default=True) is True
            return 0

    assert Demo().run() == 0


def test_html_escape_ampersand_options() -> None:
    """Option labels with ``&`` must not blow up prompt_toolkit HTML parsing."""
    from prompt_toolkit.formatted_text import HTML

    from almasix.console.prompts.style import html_escape, tagged

    assert "&amp;" in html_escape("Bold & bright")
    HTML(
        "\n".join(
            [
                tagged("label", "Pick a tone"),
                tagged("selected", "❯ Bold & bright"),
                tagged("item", "  Calm & clear"),
                tagged("hint", "  up/down navigate · enter select"),
            ]
        )
    )
