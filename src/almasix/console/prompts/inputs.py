"""Text / password / textarea / number prompts."""

from __future__ import annotations

from typing import Any

from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.validation import ValidationError, Validator

from almasix.console.prompts.style import STYLE, html_escape
from almasix.console.prompts.types import Required, ValidateFn, is_interactive, run_validation


def text(
    label: str,
    *,
    placeholder: str = "",
    default: str = "",
    required: Required = False,
    validate: ValidateFn | None = None,
    hint: str = "",
) -> str:
    """Prompt for a single line of text (Laravel ``text``)."""
    return _prompt_line(
        label,
        placeholder=placeholder,
        default=default,
        required=required,
        validate=validate,
        hint=hint,
        password=False,
    )


def password(
    label: str,
    *,
    placeholder: str = "",
    required: Required = False,
    validate: ValidateFn | None = None,
    hint: str = "",
) -> str:
    """Prompt for a hidden value (Laravel ``password``)."""
    return _prompt_line(
        label,
        placeholder=placeholder,
        default="",
        required=required,
        validate=validate,
        hint=hint,
        password=True,
    )


def textarea(
    label: str,
    *,
    placeholder: str = "",
    default: str = "",
    required: Required = False,
    validate: ValidateFn | None = None,
    hint: str = "",
) -> str:
    """Multi-line text. End input with a line containing only ``.`` (or Ctrl-D)."""
    if not is_interactive():
        err = run_validation(default, required=required, validate=validate)
        if err:
            raise RuntimeError(err)
        return default

    from almasix.console.prompts.messages import note

    note(
        (hint + "\n" if hint else "")
        + "Enter lines of text. Finish with a single '.' on its own line, or Ctrl-D.",
        title=label,
    )
    if placeholder and not default:
        print(f"  ({placeholder})")
    lines: list[str] = []
    if default:
        lines.extend(default.splitlines())
        print(default)
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == ".":
            break
        lines.append(line)
    value = "\n".join(lines)
    err = run_validation(value, required=required, validate=validate)
    if err:
        from almasix.console.prompts.messages import error

        error(err)
        return textarea(
            label,
            placeholder=placeholder,
            default=default,
            required=required,
            validate=validate,
            hint=hint,
        )
    return value


def number(
    label: str,
    *,
    placeholder: str = "",
    default: int | float | None = None,
    required: Required = False,
    validate: ValidateFn | None = None,
    hint: str = "",
    min: int | float | None = None,  # noqa: A002
    max: int | float | None = None,  # noqa: A002
) -> int | float:
    """Prompt for a number (Laravel ``number``)."""

    def _validate(raw: Any) -> str | None:
        text_value = str(raw).strip()
        if not text_value:
            return None
        try:
            value: int | float = float(text_value) if "." in text_value else int(text_value)
        except ValueError:
            return "Please enter a valid number."
        if min is not None and value < min:
            return f"Must be at least {min}."
        if max is not None and value > max:
            return f"Must be at most {max}."
        if validate is not None:
            return validate(value)
        return None

    default_str = "" if default is None else str(default)
    raw = text(
        label,
        placeholder=placeholder,
        default=default_str,
        required=required,
        validate=_validate,
        hint=hint,
    )
    if not raw.strip():
        return 0 if default is None else default
    return float(raw) if "." in raw else int(raw)


def _prompt_line(
    label: str,
    *,
    placeholder: str,
    default: str,
    required: Required,
    validate: ValidateFn | None,
    hint: str,
    password: bool,
) -> str:
    if not is_interactive():
        err = run_validation(default, required=required, validate=validate)
        if err:
            raise RuntimeError(err)
        return default

    class _Validator(Validator):
        def validate(self, document) -> None:  # noqa: ANN001
            err = run_validation(document.text, required=required, validate=validate)
            if err:
                raise ValidationError(message=err, cursor_position=len(document.text))

    # Keep the prompt message single-line — multiline HTML confuses cursor reporting.
    if hint:
        from rich.console import Console

        Console().print(f"[dim]  {hint}[/]")
    message = HTML(f"<label>{html_escape(label)}</label> ")
    kwargs: dict[str, Any] = {
        "default": default,
        "validator": _Validator(),
        "validate_while_typing": False,
        "style": STYLE,
        "is_password": password,
    }
    if placeholder:
        kwargs["placeholder"] = placeholder
    return pt_prompt(message, **kwargs)
