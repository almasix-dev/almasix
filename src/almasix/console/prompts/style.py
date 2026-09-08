"""Visual language for Almasix Prompts (Laravel Prompts-inspired)."""

from __future__ import annotations

from prompt_toolkit.styles import Style

# Box / list symbols
BULLET = "❯"
CHECK = "✔"
CROSS = "✘"
RADIO_ON = "●"
RADIO_OFF = "○"
CHECK_ON = "◼"
CHECK_OFF = "◻"

STYLE = Style.from_dict(
    {
        "label": "bold ansicyan",
        "hint": "ansibrightblack",
        "placeholder": "ansibrightblack italic",
        "error": "bold ansired",
        "selected": "bold ansigreen",
        "pointer": "bold ansimagenta",
        "item": "",
        "muted": "ansibrightblack",
        "success": "ansigreen",
        "warn": "ansiyellow",
        "info": "ansicyan",
    }
)


def label_html(label: str, hint: str = "") -> str:
    body = f"<label>{html_escape(label)}</label>"
    if hint:
        body += f"\n<hint>  {html_escape(hint)}</hint>"
    return body


def html_escape(value: str) -> str:
    """Escape dynamic text for prompt_toolkit ``HTML()`` (XML)."""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def tagged(style: str, text: str) -> str:
    """Build ``<style>escaped text</style>`` for prompt_toolkit HTML."""
    return f"<{style}>{html_escape(text)}</{style}>"
