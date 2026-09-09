"""Visual language for Almasix Prompts (Laravel Prompts + One Dark Pro).

True-color hex values match VS Code One Dark Pro so interactive prompts and
Loupe feel like one product. Fallbacks still work on terminals without 24-bit.
"""

from __future__ import annotations

from prompt_toolkit.output import ColorDepth
from prompt_toolkit.styles import Style

# Box / list symbols (Laravel Prompts)
BULLET = "❯"
CHECK = "✔"
CROSS = "✘"
RADIO_ON = "●"
RADIO_OFF = "○"
CHECK_ON = "◼"
CHECK_OFF = "◻"

# One Dark Pro — https://github.com/Binaryify/OneDark-Pro
OD_FG = "#abb2bf"
OD_COMMENT = "#5c6370"
OD_RED = "#e06c75"
OD_GREEN = "#98c379"
OD_YELLOW = "#e5c07b"
OD_BLUE = "#61afef"
OD_MAGENTA = "#c678dd"
OD_CYAN = "#56b6c2"
OD_ORANGE = "#d19a66"

STYLE = Style.from_dict(
    {
        "label": f"bold {OD_BLUE}",
        "hint": f"{OD_COMMENT} italic",
        "placeholder": f"{OD_COMMENT} italic",
        "error": f"bold {OD_RED}",
        "selected": f"bold {OD_GREEN}",
        "pointer": f"bold {OD_MAGENTA}",
        "item": OD_FG,
        "muted": OD_COMMENT,
        "success": f"bold {OD_GREEN}",
        "warn": f"bold {OD_YELLOW}",
        "info": OD_CYAN,
        "accent": f"bold {OD_ORANGE}",
    }
)

#: Prefer 24-bit colour when the terminal supports it (Laravel Prompts beauty).
TRUE_COLOR = ColorDepth.TRUE_COLOR


def label_html(label: str, hint: str = "") -> str:
    body = f"<label>{html_escape(label)}</label>"
    if hint:
        body += f"\n<hint>  {html_escape(hint)}</hint>"
    return body


def html_escape(value: str) -> str:
    """Escape dynamic text for prompt_toolkit ``HTML()`` (XML)."""
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def tagged(style: str, text: str) -> str:
    """Build ``<style>escaped text</style>`` for prompt_toolkit HTML."""
    return f"<{style}>{html_escape(text)}</{style}>"
