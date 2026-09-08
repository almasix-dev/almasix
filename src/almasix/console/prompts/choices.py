"""Select / multiselect / suggest / search prompts."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.application import Application
from prompt_toolkit.completion import FuzzyWordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl

from almasix.console.prompts.style import (
    BULLET,
    CHECK_OFF,
    CHECK_ON,
    STYLE,
    html_escape,
    label_html,
    tagged,
)
from almasix.console.prompts.types import Required, ValidateFn, is_interactive, run_validation

Options = Sequence[Any] | Mapping[Any, str]


def _normalize_options(options: Options) -> list[tuple[Any, str]]:
    if isinstance(options, Mapping):
        return [(key, str(label)) for key, label in options.items()]
    return [(item, str(item)) for item in options]


def select(
    label: str,
    options: Options,
    *,
    default: Any = None,
    scroll: int = 5,
    validate: ValidateFn | None = None,
    hint: str = "",
) -> Any:
    """Single-choice list with arrow keys (Laravel ``select``)."""
    items = _normalize_options(options)
    if not items:
        raise ValueError("select() requires at least one option")

    if not is_interactive():
        if default is not None:
            return default
        return items[0][0]

    index = 0
    if default is not None:
        for i, (value, text) in enumerate(items):
            if value == default or text == default:
                index = i
                break
    state = {"index": index}

    def _render() -> HTML:
        start = max(0, state["index"] - scroll + 1)
        end = min(len(items), start + scroll)
        lines = [label_html(label, hint)]
        if start > 0:
            lines.append(tagged("muted", "  ..."))
        for i in range(start, end):
            _value, text = items[i]
            marker = f"{BULLET} " if i == state["index"] else "  "
            style = "selected" if i == state["index"] else "item"
            lines.append(tagged(style, f"{marker}{text}"))
        if end < len(items):
            lines.append(tagged("muted", "  ..."))
        lines.append(tagged("hint", "  up/down navigate · enter select"))
        return HTML("\n".join(lines))

    kb = KeyBindings()

    @kb.add("up")
    def _(event) -> None:  # noqa: ANN001
        state["index"] = (state["index"] - 1) % len(items)
        event.app.invalidate()

    @kb.add("down")
    def _(event) -> None:  # noqa: ANN001
        state["index"] = (state["index"] + 1) % len(items)
        event.app.invalidate()

    @kb.add("enter")
    def _(event) -> None:  # noqa: ANN001
        event.app.exit(result=items[state["index"]][0])

    @kb.add("c-c")
    def _(event) -> None:  # noqa: ANN001
        event.app.exit(exception=KeyboardInterrupt())

    app: Application[Any] = Application(
        layout=Layout(HSplit([Window(FormattedTextControl(_render, focusable=True))])),
        key_bindings=kb,
        style=STYLE,
        full_screen=False,
    )
    value = app.run()
    err = run_validation(value, required=False, validate=validate)
    if err:
        from almasix.console.prompts.messages import error

        error(err)
        return select(label, options, default=default, scroll=scroll, validate=validate, hint=hint)
    return value


def multiselect(
    label: str,
    options: Options,
    *,
    default: Sequence[Any] | None = None,
    scroll: int = 5,
    required: Required = False,
    validate: ValidateFn | None = None,
    hint: str = "",
) -> list[Any]:
    """Multi-choice list with space to toggle (Laravel ``multiselect``)."""
    items = _normalize_options(options)
    if not items:
        raise ValueError("multiselect() requires at least one option")

    defaults = set(default or [])
    if not is_interactive():
        chosen = [v for v, _ in items if v in defaults]
        err = run_validation(chosen, required=required, validate=validate)
        if err:
            raise RuntimeError(err)
        return chosen

    selected = {i for i, (v, _) in enumerate(items) if v in defaults}
    state = {"index": 0, "selected": selected}

    def _render() -> HTML:
        start = max(0, state["index"] - scroll + 1)
        end = min(len(items), start + scroll)
        lines = [label_html(label, hint)]
        if start > 0:
            lines.append(tagged("muted", "  ..."))
        for i in range(start, end):
            _, text = items[i]
            box = CHECK_ON if i in state["selected"] else CHECK_OFF
            marker = f"{BULLET} " if i == state["index"] else "  "
            style = "selected" if i == state["index"] else "item"
            lines.append(tagged(style, f"{marker}{box} {text}"))
        if end < len(items):
            lines.append(tagged("muted", "  ..."))
        lines.append(tagged("hint", "  up/down navigate · space toggle · enter confirm"))
        return HTML("\n".join(lines))

    kb = KeyBindings()

    @kb.add("up")
    def _(event) -> None:  # noqa: ANN001
        state["index"] = (state["index"] - 1) % len(items)
        event.app.invalidate()

    @kb.add("down")
    def _(event) -> None:  # noqa: ANN001
        state["index"] = (state["index"] + 1) % len(items)
        event.app.invalidate()

    @kb.add("space")
    def _(event) -> None:  # noqa: ANN001
        i = state["index"]
        if i in state["selected"]:
            state["selected"].remove(i)
        else:
            state["selected"].add(i)
        event.app.invalidate()

    @kb.add("enter")
    def _(event) -> None:  # noqa: ANN001
        values = [items[i][0] for i in sorted(state["selected"])]
        event.app.exit(result=values)

    @kb.add("c-c")
    def _(event) -> None:  # noqa: ANN001
        event.app.exit(exception=KeyboardInterrupt())

    app: Application[list[Any]] = Application(
        layout=Layout(HSplit([Window(FormattedTextControl(_render, focusable=True))])),
        key_bindings=kb,
        style=STYLE,
        full_screen=False,
    )
    value = app.run()
    err = run_validation(value, required=required, validate=validate)
    if err:
        from almasix.console.prompts.messages import error

        error(err)
        return multiselect(
            label,
            options,
            default=default,
            scroll=scroll,
            required=required,
            validate=validate,
            hint=hint,
        )
    return list(value)


def suggest(
    label: str,
    options: Sequence[str],
    *,
    placeholder: str = "",
    default: str = "",
    required: Required = False,
    validate: ValidateFn | None = None,
    hint: str = "",
) -> str:
    """Text input with autocomplete suggestions (Laravel ``suggest``)."""
    if not is_interactive():
        err = run_validation(default, required=required, validate=validate)
        if err:
            raise RuntimeError(err)
        return default

    from prompt_toolkit.validation import ValidationError, Validator

    from almasix.console.prompts.types import run_validation as _run

    class _Validator(Validator):
        def validate(self, document) -> None:  # noqa: ANN001
            err = _run(document.text, required=required, validate=validate)
            if err:
                raise ValidationError(message=err, cursor_position=len(document.text))

    kwargs: dict[str, Any] = {
        "default": default,
        "completer": FuzzyWordCompleter(list(options)),
        "complete_while_typing": True,
        "validator": _Validator(),
        "validate_while_typing": False,
        "style": STYLE,
    }
    if placeholder:
        kwargs["placeholder"] = placeholder
    if hint:
        from rich.console import Console

        Console().print(f"[dim]  {hint}[/]")
    return pt_prompt(HTML(f"<label>{html_escape(label)}</label> "), **kwargs)


def search(
    label: str,
    options: Callable[[str], Sequence[Any] | Mapping[Any, str]],
    *,
    placeholder: str = "",
    scroll: int = 5,
    validate: ValidateFn | None = None,
    hint: str = "",
) -> Any:
    """Type-to-filter then select (Laravel ``search``)."""
    if not is_interactive():
        results = _normalize_options(options(""))
        return results[0][0] if results else None

    if hint:
        from rich.console import Console

        Console().print(f"[dim]  {hint}[/]")
    query = pt_prompt(
        HTML(f"<label>{html_escape(label)}</label> "),
        placeholder=placeholder or "Search...",
        style=STYLE,
    )
    matches = _normalize_options(options(query))
    if not matches:
        from almasix.console.prompts.messages import warning

        warning("No matches.")
        return search(
            label,
            options,
            placeholder=placeholder,
            scroll=scroll,
            validate=validate,
            hint=hint,
        )
    return select(
        label,
        {value: text for value, text in matches},
        scroll=scroll,
        validate=validate,
        hint=hint,
    )
