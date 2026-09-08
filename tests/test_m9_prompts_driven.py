"""M9 prompts, driven through a terminal instead of skipped.

Every other prompt test takes the non-interactive branch, because pytest owns
stdin. These drive the real prompt_toolkit applications over a pipe — the keys
a user would press, the widgets they would see — so the interactive half of
the module is exercised rather than assumed.
"""

from __future__ import annotations

import signal
from collections.abc import Iterator
from importlib import import_module
from typing import Any

import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import PipeInput, create_pipe_input
from prompt_toolkit.output import DummyOutput

from almasix.console.prompts import choices, inputs

# The package exports a ``confirm`` *function*, which shadows the module of
# that name — so reach for the module itself rather than the export.
confirm_module = import_module("almasix.console.prompts.confirm")

#: What prompt_toolkit sends for the arrow keys.
DOWN = "\x1b[B"
UP = "\x1b[A"
ENTER = "\r"


@pytest.fixture()
def keys(monkeypatch: pytest.MonkeyPatch) -> Iterator[PipeInput]:
    """A terminal the test types into, with the interactive gate held open.

    A prompt left waiting for a key that never comes would hang the suite, so
    the fixture arms a clock: run out of keystrokes and the test fails.
    """
    for module in (choices, confirm_module, inputs):
        monkeypatch.setattr(module, "is_interactive", lambda: True)

    def out_of_keys(*_: object) -> None:
        raise TimeoutError("the prompt is still waiting for a keystroke")

    signal.signal(signal.SIGALRM, out_of_keys)
    signal.setitimer(signal.ITIMER_REAL, 10)
    try:
        with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
            yield pipe
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, signal.SIG_DFL)


def test_select_moves_with_the_arrows_and_takes_the_row_under_the_cursor(
    keys: PipeInput,
) -> None:
    keys.send_text(DOWN + DOWN + UP + ENTER)

    assert choices.select("Pick one", ["alpha", "beta", "gamma"], hint="use the arrows") == "beta"


def test_select_wraps_around_the_top(keys: PipeInput) -> None:
    keys.send_text(UP + ENTER)

    assert choices.select("Pick one", ["alpha", "beta", "gamma"]) == "gamma"


def test_select_starts_on_the_default_and_scrolls_past_the_window(keys: PipeInput) -> None:
    keys.send_text(DOWN + ENTER)
    options = {n: f"option {n}" for n in range(8)}

    assert choices.select("Pick one", options, default=4, scroll=3) == 5


def test_select_asks_again_when_validation_rejects_the_answer(keys: PipeInput) -> None:
    keys.send_text(ENTER + DOWN + ENTER)

    def not_alpha(value: Any) -> str | None:
        return "not that one" if value == "alpha" else None

    assert choices.select("Pick one", ["alpha", "beta"], validate=not_alpha) == "beta"


def test_multiselect_toggles_with_space_and_confirms_with_enter(keys: PipeInput) -> None:
    keys.send_text(" " + DOWN + " " + DOWN + " " + " " + ENTER)

    chosen = choices.multiselect("Pick some", ["a", "b", "c"], hint="space toggles")

    # The third was toggled on and back off again.
    assert chosen == ["a", "b"]


def test_multiselect_starts_from_its_defaults_and_re_asks_when_required(
    keys: PipeInput,
) -> None:
    # Clearing the default leaves nothing, which `required` sends back for a
    # second ask — where the default is waiting again, and enter accepts it.
    keys.send_text(" " + ENTER + ENTER)

    assert choices.multiselect("Pick some", ["a", "b"], default=["a"], required=True) == ["a"]


def test_a_default_that_is_not_on_the_list_leaves_the_cursor_at_the_top(
    keys: PipeInput,
) -> None:
    keys.send_text(ENTER)

    assert choices.select("Pick one", ["alpha", "beta"], default="gone") == "alpha"


@pytest.mark.parametrize("prompt", [choices.select, choices.multiselect])
def test_ctrl_c_interrupts_a_list_rather_than_answering_it(keys: PipeInput, prompt: Any) -> None:
    keys.send_text("\x03")

    with pytest.raises(KeyboardInterrupt):
        prompt("Pick one", ["alpha", "beta"])


def test_suggest_completes_a_word_the_caller_offered(keys: PipeInput) -> None:
    keys.send_text("ala" + ENTER)

    answer = choices.suggest("Which fruit", ["alaska", "banana"], placeholder="type…", hint="fuzzy")

    assert answer == "ala"


def test_suggest_needs_neither_a_placeholder_nor_a_hint(keys: PipeInput) -> None:
    keys.send_text("banana" + ENTER)

    assert choices.suggest("Which fruit", ["alaska", "banana"]) == "banana"


def test_search_filters_then_selects_a_match(keys: PipeInput) -> None:
    keys.send_text("be" + ENTER + ENTER)

    found = choices.search(
        "Find one",
        lambda query: [name for name in ("alpha", "beta") if query in name],
        hint="type to filter",
    )

    assert found == "beta"


def test_search_says_so_and_asks_again_when_nothing_matches(
    keys: PipeInput, capsys: pytest.CaptureFixture[str]
) -> None:
    keys.send_text("zzz" + ENTER + "be" + ENTER + ENTER)

    found = choices.search(
        "Find one", lambda query: [name for name in ("alpha", "beta") if query in name]
    )

    assert found == "beta"
    assert "No matches." in capsys.readouterr().out


def test_text_and_password_read_a_line(keys: PipeInput) -> None:
    keys.send_text("Ada" + ENTER + "hunter2" + ENTER)

    assert inputs.text("Name", placeholder="your name", hint="as it appears") == "Ada"
    assert inputs.password("Secret") == "hunter2"


def test_text_will_not_take_an_answer_its_validation_rejects(keys: PipeInput) -> None:
    keys.send_text(ENTER + "Ada" + ENTER)

    assert inputs.text("Name", required=True) == "Ada"


def typed(monkeypatch: pytest.MonkeyPatch, *lines: str) -> None:
    """Script the lines ``textarea`` reads — it takes them off stdin itself."""
    monkeypatch.setattr(inputs, "is_interactive", lambda: True)
    remaining = iter(lines)
    monkeypatch.setattr("builtins.input", lambda: next(remaining))


def test_textarea_ends_on_a_lone_dot(monkeypatch: pytest.MonkeyPatch) -> None:
    typed(monkeypatch, "first", "second", ".")

    notes = inputs.textarea("Notes", placeholder="markdown welcome", hint="two lines will do")

    assert notes == "first\nsecond"


def test_textarea_ends_on_a_closed_stdin_too(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inputs, "is_interactive", lambda: True)

    def closed() -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", closed)

    assert inputs.textarea("Notes", default="a draft") == "a draft"


def test_textarea_asks_again_when_it_is_handed_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    typed(monkeypatch, ".", "second thoughts", ".")

    assert inputs.textarea("Notes", required=True) == "second thoughts"


def test_number_refuses_what_is_not_a_number_and_takes_the_correction(
    keys: PipeInput,
) -> None:
    # Enter on "nope" is refused, so the answer is corrected in place.
    keys.send_text("nope" + ENTER + "\x7f" * 4 + "42" + ENTER)

    assert inputs.number("How many", min=1, max=100) == 42


def test_number_falls_back_to_its_default_when_nothing_is_typed(keys: PipeInput) -> None:
    keys.send_text(ENTER + ENTER)

    assert inputs.number("How many", default=7) == 7
    assert inputs.number("How many") == 0


def test_pause_waits_for_the_key_it_names(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(confirm_module, "is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda message: message)

    confirm_module.pause("Press enter to go on...")


def test_pause_gives_up_on_a_closed_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pipe that has been closed must not hang or raise at the user."""
    monkeypatch.setattr(confirm_module, "is_interactive", lambda: True)

    def closed(message: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", closed)

    confirm_module.pause()
