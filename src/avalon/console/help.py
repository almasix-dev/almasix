"""Render a command's signature as help.

One renderer, two readers: Typer asks for it when you type ``--help``, and
``grail help <command>`` prints the same thing. Both read the signature, so a
description written in ``{user : The user ID}`` reaches the terminal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from avalon.console.command import parse_signature

if TYPE_CHECKING:
    from avalon.console.command import Command


def usage(command_cls: type[Command]) -> str:
    """The one-line invocation, e.g. ``mail:send <user> [--queue=QUEUE]``."""
    name, _, _ = parse_signature(command_cls.signature)
    return f"{name} {metavar(command_cls)}".rstrip()


def metavar(command_cls: type[Command]) -> str:
    """Everything after the command name, for Click's own usage line."""
    _, arguments, options = parse_signature(command_cls.signature)
    parts = [_argument_usage(meta) for meta in arguments]
    parts.extend(f"[{_option_flags(meta)}]" for meta in options)
    return " ".join(parts)


def arguments_of(command_cls: type[Command]) -> list[tuple[str, str]]:
    """Argument name and description pairs, in signature order."""
    _, arguments, _ = parse_signature(command_cls.signature)
    return [(_argument_usage(meta), meta["description"]) for meta in arguments]


def options_of(command_cls: type[Command]) -> list[tuple[str, str]]:
    """Option spelling and description pairs, in signature order."""
    _, _, options = parse_signature(command_cls.signature)
    return [(_option_flags(meta), _option_description(meta)) for meta in options]


def help_text(command_cls: type[Command]) -> str:
    """The full help body: description, usage, then arguments and options."""
    if not command_cls.signature:
        return command_cls.description or ""

    lines: list[str] = []
    if command_cls.description:
        lines.append(command_cls.description)

    for heading, rows in (
        ("Arguments:", arguments_of(command_cls)),
        ("Options:", options_of(command_cls)),
    ):
        if not rows:
            continue
        width = max(len(spelling) for spelling, _ in rows)
        lines.extend(["", "\b", heading])
        lines.extend(f"  {spelling:<{width}}  {text}".rstrip() for spelling, text in rows)

    if command_cls.aliases:
        lines.extend(["", "\b", "Aliases:", f"  {', '.join(command_cls.aliases)}"])

    return "\n".join(lines)


def _argument_usage(meta: dict[str, Any]) -> str:
    name = meta["name"]
    if meta["array"]:
        return f"[<{name}>...]"
    if meta["optional"]:
        return f"[<{name}>]"
    return f"<{name}>"


def _option_flags(meta: dict[str, Any]) -> str:
    flags = f"--{meta['name']}"
    if meta["shortcut"]:
        flags = f"-{meta['shortcut']}, {flags}"
    if meta["is_flag"]:
        return flags
    value = meta["name"].replace("-", "_").upper()
    return f"{flags}={value}{'...' if meta['array'] else ''}"


def _option_description(meta: dict[str, Any]) -> str:
    description = meta["description"]
    default = meta["default"]
    if default in (None, "", [], False):
        return description
    return f"{description} [default: {default}]".strip()
