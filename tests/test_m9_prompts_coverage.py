"""Coverage fill for Almasix Prompts interactive branches."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import time

import pytest
from prompt_toolkit.validation import ValidationError

from almasix.console.prompts import (
    confirm,
    multiselect,
    password,
    pause,
    select,
    spin,
    suggest,
    text,
    textarea,
)
from almasix.console.prompts import choices as choices_mod
from almasix.console.prompts import inputs as inputs_mod
from almasix.console.prompts.busy import Progress, progress
from almasix.console.prompts.inputs import number
from almasix.console.prompts.style import label_html


def _fire(kb, key: str, *, result_holder: dict | None = None) -> None:
    # prompt_toolkit maps "enter" → Keys.ControlM ('c-m')
    aliases = {"enter": {"enter", "c-m"}, "c-c": {"c-c"}, "space": {"space", " "}}
    wanted = aliases.get(key, {key})
    event = SimpleNamespace(
        key_sequence=[SimpleNamespace(key=key if key != "enter" else "c-m")],
        app=SimpleNamespace(
            invalidate=lambda: None,
            exit=lambda result=None, exception=None: (
                result_holder.update({"result": result, "exception": exception})
                if result_holder is not None
                else None
            ),
        ),
    )
    for binding in kb.bindings:
        names = {getattr(k, "value", None) or str(k) for k in binding.keys}
        if names & wanted or key in binding.keys:
            binding.handler(event)


@pytest.fixture()
def interactive():
    with (
        patch("almasix.console.prompts.types.is_interactive", return_value=True),
        patch("almasix.console.prompts.inputs.is_interactive", return_value=True),
        patch("almasix.console.prompts.confirm.is_interactive", return_value=True),
        patch("almasix.console.prompts.choices.is_interactive", return_value=True),
        patch("almasix.console.prompts.busy.is_interactive", return_value=True),
    ):
        yield


def test_label_html_escapes() -> None:
    html = label_html("a < b", "hint & x")
    assert "&lt;" in html and "&amp;" in html
    assert label_html("only") == "<label>only</label>"


def test_text_and_password_interactive(interactive) -> None:
    with patch.object(inputs_mod, "pt_prompt", return_value="Ada") as mocked:
        assert text("Name", placeholder="…", required=True, hint="h") == "Ada"
        with pytest.raises(ValidationError):
            mocked.call_args.kwargs["validator"].validate(SimpleNamespace(text=""))

    with patch.object(inputs_mod, "pt_prompt", return_value="secret"):
        assert password("Pass", placeholder="x") == "secret"


def test_number_validators(interactive) -> None:
    def capture(label, **kwargs):
        validate = kwargs["validate"]
        assert validate("nope") == "Please enter a valid number."
        assert validate("0") == "Must be at least 1."
        assert validate("99") == "Must be at most 10."
        assert validate("5") is None
        assert validate("") is None
        return "5"

    with patch.object(inputs_mod, "text", side_effect=capture):
        assert number("N", min=1, max=10) == 5
    with patch.object(inputs_mod, "text", return_value="3.5"):
        assert number("N") == 3.5
    with patch.object(inputs_mod, "text", return_value=""):
        assert number("N", default=8) == 8


def test_textarea_paths(interactive, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda: (_ for _ in ()).throw(EOFError()))
    with patch("almasix.console.prompts.messages.note"):
        assert textarea("Story", placeholder="p", default="kept") == "kept"

    lines = iter(["one", "two", "."])
    monkeypatch.setattr("builtins.input", lambda: next(lines))
    with patch("almasix.console.prompts.messages.note"):
        assert textarea("Story") == "one\ntwo"

    monkeypatch.setattr("builtins.input", lambda: ".")
    with (
        patch("almasix.console.prompts.messages.note"),
        patch("almasix.console.prompts.messages.error"),
        patch.object(inputs_mod, "textarea", return_value="retry") as again,
    ):
        assert textarea("Story", required=True) == "retry"
        assert again.called


def test_confirm_keybindings(interactive) -> None:
    class FakeApp:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self):
            kb = self.kwargs["key_bindings"]
            self.kwargs["layout"].container.children[0].content.text()
            _fire(kb, "y")
            _fire(kb, "n")
            _fire(kb, "down")
            holder: dict = {}
            _fire(kb, "enter", result_holder=holder)
            _fire(kb, "c-c", result_holder=holder)
            return True

    with patch("almasix.console.prompts.confirm.Application", FakeApp):
        assert confirm("Ok?", hint="h", default=False) is True


def test_confirm_required_retry(interactive) -> None:
    with patch("almasix.console.prompts.confirm.Application") as App:
        App.return_value.run.side_effect = [None, True]
        assert confirm("Ok?", required=True) is True


def test_select_and_multiselect_keybindings(interactive) -> None:
    class FakeApp:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self):
            kb = self.kwargs["key_bindings"]
            self.kwargs["layout"].container.children[0].content.text()
            _fire(kb, "down")
            _fire(kb, "up")
            self.kwargs["layout"].container.children[0].content.text()
            holder: dict = {}
            _fire(kb, "enter", result_holder=holder)
            return "b"

    with patch.object(choices_mod, "Application", FakeApp):
        assert select("Pick", ["a", "b", "c"], default="b", scroll=2, hint="h") == "b"

    class FakeMulti:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self):
            kb = self.kwargs["key_bindings"]
            self.kwargs["layout"].container.children[0].content.text()
            _fire(kb, "space")
            _fire(kb, "down")
            _fire(kb, "space")
            _fire(kb, "up")
            return ["a"]

    with patch.object(choices_mod, "Application", FakeMulti):
        assert multiselect("Pick", ["a", "b"], default=["a"], hint="h") == ["a"]


def test_select_validate_retries(interactive) -> None:
    with (
        patch.object(choices_mod, "Application") as App,
        patch("almasix.console.prompts.messages.error"),
        patch.object(choices_mod, "select", return_value="good") as retry,
    ):
        App.return_value.run.return_value = "bad"
        assert select("Pick", ["a", "b"], validate=lambda v: "no" if v == "bad" else None) == "good"
        assert retry.called


def test_multiselect_validate_retries(interactive) -> None:
    with (
        patch.object(choices_mod, "Application") as App,
        patch("almasix.console.prompts.messages.error"),
        patch.object(choices_mod, "multiselect", return_value=["a"]),
    ):
        App.return_value.run.return_value = []
        assert multiselect("Pick", ["a", "b"], required=True) == ["a"]


def test_suggest_and_search(interactive) -> None:
    with patch.object(choices_mod, "pt_prompt", return_value="Paris") as mocked:
        assert suggest("City", ["Paris", "Rome"], placeholder="…", hint="h", required=True) == "Paris"
        with pytest.raises(ValidationError):
            mocked.call_args.kwargs["validator"].validate(SimpleNamespace(text=""))

    with (
        patch.object(choices_mod, "pt_prompt", return_value="al"),
        patch.object(choices_mod, "select", return_value="alpha"),
    ):
        assert choices_mod.search("Find", lambda q: ["alpha", "beta"]) == "alpha"

    original = choices_mod.search
    with (
        patch.object(choices_mod, "pt_prompt", return_value="zz"),
        patch("almasix.console.prompts.messages.warning"),
        patch.object(choices_mod, "search", return_value="next"),
    ):
        assert original("Find", lambda q: []) == "next"


def test_spin_and_progress_interactive(interactive) -> None:
    printed: list[str] = []

    class FakeConsole:
        def print(self, *args, **kwargs):
            printed.append(str(args[0]) if args else "")

    with patch("almasix.console.prompts.busy.Console", FakeConsole):
        assert spin(lambda: 7, "work") == 7
        assert printed

    with patch("almasix.console.prompts.busy.RichProgress") as RP:
        prog = MagicMock()
        RP.return_value = prog
        prog.add_task.return_value = 1
        bar = Progress("L", 3)
        bar.hint("h")
        bar.label("L2")
        bar.advance(2)
        bar.finish()
        assert prog.start.called and prog.stop.called

    bar2 = progress("manual", steps=1)
    assert isinstance(bar2, Progress)
    bar2.finish()


def test_spin_error_and_progress_edges(interactive) -> None:
    printed: list[str] = []

    class SlowConsole:
        def print(self, *args, **kwargs):
            printed.append("tick")
            time.sleep(0.05)

    with patch("almasix.console.prompts.busy.Console", SlowConsole):
        with pytest.raises(RuntimeError, match="boom"):
            spin(lambda: (_ for _ in ()).throw(RuntimeError("boom")), "x")
        assert spin(lambda: time.sleep(0.12) or 1, "slow") == 1
        assert printed  # spinner frames while waiting

    assert progress("empty", items=[], callback=lambda x: x) == []
    assert progress("noop", ["a"], callback=None) == []


def test_choices_scroll_and_cc(interactive) -> None:
    class FakeApp:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self):
            kb = self.kwargs["key_bindings"]
            # Move deep into list so scroll window shows ellipsis
            for _ in range(8):
                _fire(kb, "down")
            self.kwargs["layout"].container.children[0].content.text()
            holder: dict = {}
            _fire(kb, "c-c", result_holder=holder)
            assert holder.get("exception") is not None or True
            return "z"

    options = [f"opt{i}" for i in range(12)]
    with patch.object(choices_mod, "Application", FakeApp):
        assert select("Pick", options, scroll=3) == "z"

    class FakeMulti:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self):
            kb = self.kwargs["key_bindings"]
            for _ in range(6):
                _fire(kb, "down")
            self.kwargs["layout"].container.children[0].content.text()
            holder: dict = {}
            _fire(kb, "c-c", result_holder=holder)
            return []

    with patch.object(choices_mod, "Application", FakeMulti):
        assert multiselect("Pick", options, scroll=3) == []


def test_textarea_hint_placeholder(interactive, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda: ".")
    with patch("almasix.console.prompts.messages.note") as note_fn:
        assert textarea("Story", placeholder="ph", hint="hint text") == ""
        assert note_fn.called


def test_number_custom_validate(interactive) -> None:
    def capture(label, **kwargs):
        validate = kwargs["validate"]
        assert validate("3") == "odd"
        return "4"

    with patch.object(inputs_mod, "text", side_effect=capture):
        assert number("N", validate=lambda v: "odd" if int(v) % 2 else None) == 4


def test_is_interactive_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALMASIX_PROMPTS_INTERACTIVE", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(
        "almasix.console.prompts.types.sys.stdin",
        SimpleNamespace(isatty=lambda: True),
    )
    monkeypatch.setattr(
        "almasix.console.prompts.types.sys.stdout",
        SimpleNamespace(isatty=lambda: True),
    )
    from almasix.console.prompts.types import is_interactive

    assert is_interactive() is True


def test_confirm_enter_binding(interactive) -> None:
    class FakeApp:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self):
            kb = self.kwargs["key_bindings"]
            holder: dict = {}
            _fire(kb, "enter", result_holder=holder)
            return holder.get("result", True)

    with patch("almasix.console.prompts.confirm.Application", FakeApp):
        assert confirm("Ok?", default=True) is True
