"""Confirm and pause prompts."""

from __future__ import annotations

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl

from almasix.console.prompts.style import BULLET, STYLE, TRUE_COLOR, label_html, tagged
from almasix.console.prompts.types import is_interactive


def confirm(
    label: str,
    *,
    default: bool = True,
    yes: str = "Yes",
    no: str = "No",
    required: bool = False,
    hint: str = "",
) -> bool:
    """Yes/No confirm with arrow keys (Laravel ``confirm``)."""
    if not is_interactive():
        return default

    state = {"value": default}

    def _render() -> HTML:
        y = tagged("selected", f"{BULLET} {yes}") if state["value"] else tagged("item", f"  {yes}")
        n = (
            tagged("selected", f"{BULLET} {no}")
            if not state["value"]
            else tagged("item", f"  {no}")
        )
        return HTML(
            f"{label_html(label, hint)}\n{y}\n{n}\n"
            f"{tagged('hint', '  ↑/↓ navigate · enter select')}"
        )

    kb = KeyBindings()

    @kb.add("up")
    @kb.add("down")
    @kb.add("left")
    @kb.add("right")
    @kb.add("y")
    @kb.add("n")
    def _(event) -> None:
        key = event.key_sequence[0].key
        if key in {"y", "Y"}:
            state["value"] = True
        elif key in {"n", "N"}:
            state["value"] = False
        else:
            state["value"] = not state["value"]
        event.app.invalidate()

    @kb.add("enter")
    def _(event) -> None:
        event.app.exit(result=state["value"])

    @kb.add("c-c")
    def _(event) -> None:
        event.app.exit(exception=KeyboardInterrupt())

    control = FormattedTextControl(_render, focusable=True)
    app: Application[bool] = Application(
        layout=Layout(HSplit([Window(control)])),
        key_bindings=kb,
        style=STYLE,
        color_depth=TRUE_COLOR,
        full_screen=False,
    )
    result = app.run()
    if required and result is None:
        return confirm(label, default=default, yes=yes, no=no, required=required, hint=hint)
    return bool(result)


def pause(message: str = "Press enter to continue...") -> None:
    """Wait for Enter (Laravel ``pause``)."""
    if not is_interactive():
        return
    try:
        input(f"{message} ")
    except EOFError:
        return
