"""Almasix debug helpers — ``dump()`` / ``dd()`` (Laravel-shaped, Rich + HTML)."""

from __future__ import annotations

import html
import inspect
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from almasix.console.display import describe, serialize, to_json

__all__ = [
    "Caller",
    "DumpAndDie",
    "dd",
    "dump",
    "render",
    "render_dd_html",
    "render_dump_html",
    "render_value",
    "serialize",
    "to_json",
]


@dataclass(frozen=True)
class Caller:
    file: str
    line: int
    function: str

    @property
    def short_file(self) -> str:
        path = Path(self.file)
        parts = path.parts
        if len(parts) >= 2:
            return str(Path(*parts[-2:]))
        return path.name

    def __str__(self) -> str:
        return f"{self.short_file}:{self.line}"


class DumpAndDie(Exception):
    """Raised by ``dd()`` after printing — intentional halt, not an app error.

    Subclasses ``Exception`` so HTTP / console kernels can catch it. The
    exception Handler never reports it and renders a dedicated dump page.
    """

    def __init__(self, values: tuple[Any, ...], caller: Caller | None = None) -> None:
        self.values = values
        self.caller = caller
        super().__init__("dd()")


def _caller(depth: int = 2) -> Caller | None:
    frame = inspect.currentframe()
    try:
        for _ in range(depth):
            if frame is None:
                return None
            frame = frame.f_back
        if frame is None:
            return None
        return Caller(
            file=frame.f_code.co_filename,
            line=frame.f_lineno,
            function=frame.f_code.co_name,
        )
    finally:
        del frame


def _type_label(value: Any) -> str:
    module = getattr(type(value), "__module__", "")
    name = type(value).__name__
    if module and module not in {"builtins", "typing"}:
        return f"{module}.{name}"
    return name


def render_value(
    value: Any,
    *,
    console: Any | None = None,
    index: int | None = None,
    as_json: bool = True,
) -> None:
    """Pretty-print one value with type chrome."""
    try:
        from rich.console import Console
        from rich.json import JSON
        from rich.panel import Panel
        from rich.pretty import Pretty
        from rich.text import Text
    except ImportError:
        prefix = f"#{index} " if index is not None else ""
        print(f"{prefix}{describe(value)} · {_type_label(value)}")
        print(to_json(value) if as_json else repr(value))
        return

    out = console or Console(soft_wrap=True, highlight=True)
    caption = describe(value)
    type_name = _type_label(value)
    data = serialize(value)

    title = Text()
    if index is not None:
        title.append(f"#{index} ", style="bold magenta")
    title.append(caption, style="bold cyan")
    title.append("  ")
    title.append(type_name, style="dim")

    if as_json and isinstance(data, (dict, list)):
        try:
            body = JSON.from_data(data)
        except Exception:
            body = Pretty(data, expand_all=True, indent_guides=True)
    else:
        body = Pretty(data, expand_all=True, indent_guides=True)

    out.print(
        Panel(
            body,
            title=title,
            title_align="left",
            border_style="cyan",
            padding=(0, 1),
            expand=True,
        )
    )


def _print_header(
    *,
    badge: str,
    caller: Caller | None,
    count: int,
    console: Any | None = None,
) -> None:
    try:
        from rich.console import Console
        from rich.rule import Rule
        from rich.text import Text
    except ImportError:
        loc = f" · {caller}" if caller else ""
        print(f"\n══ {badge} ({count}){loc} ══\n")
        return

    out = console or Console(soft_wrap=True)
    label = Text()
    style = "bold white on dark_red" if badge == "dd" else "bold white on dark_orange3"
    label.append(f" {badge} ", style=style)
    label.append(f" {count} value" + ("s" if count != 1 else ""), style="bold")
    if caller:
        label.append(f"  ·  {caller}", style="dim")
        if caller.function and caller.function != "<module>":
            label.append(f" in {caller.function}()", style="dim italic")
    out.print()
    out.print(Rule(label, style="bright_black"))
    out.print()


def dump(*values: Any, as_json: bool = True, _depth: int = 1) -> tuple[Any, ...]:
    """Laravel ``dump()`` — pretty-print values and continue.

    Returns the values unchanged so ``dump(x)`` can be inlined.
    """
    caller = _caller(depth=_depth + 1)
    console = None
    try:
        from rich.console import Console

        console = Console(soft_wrap=True, highlight=True, stderr=True)
    except ImportError:
        pass

    items = values if values else (None,)
    _print_header(badge="dump", caller=caller, count=len(items), console=console)
    for index, value in enumerate(items):
        render_value(
            value,
            console=console,
            index=index if len(items) > 1 else None,
            as_json=as_json,
        )
    if console is not None:
        console.print()
    else:
        print()
    return values


def dd(*values: Any, as_json: bool = True) -> None:
    """Laravel ``dd()`` — dump and die (halt the current process / request)."""
    caller = _caller(depth=2)
    console = None
    try:
        from rich.console import Console

        console = Console(soft_wrap=True, highlight=True, stderr=True)
    except ImportError:
        pass

    items = values if values else (None,)
    _print_header(badge="dd", caller=caller, count=len(items), console=console)
    for index, value in enumerate(items):
        render_value(
            value,
            console=console,
            index=index if len(items) > 1 else None,
            as_json=as_json,
        )
    if console is not None:
        from rich.rule import Rule
        from rich.text import Text

        footer = Text(" halted ", style="bold white on dark_red")
        console.print()
        console.print(Rule(footer, style="dark_red"))
        console.print()
    else:
        print("\n*** dd() halted ***\n")

    raise DumpAndDie(items, caller=caller)


def _colorize_json(escaped: str) -> str:
    """Highlight already-escaped JSON without introducing XSS."""
    text = re.sub(
        r'(&quot;)(.*?)(&quot;)(\s*):',
        r'<span class="k">\1\2\3</span>\4:',
        escaped,
    )
    text = re.sub(
        r':\s*(-?\d+(?:\.\d+)?)([,\n\r\s\}\]])',
        r': <span class="n">\1</span>\2',
        text,
    )
    text = re.sub(
        r':\s*(true|false|null)([,\n\r\s\}\]])',
        r': <span class="b">\1</span>\2',
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r':\s*(&quot;.*?&quot;)',
        r': <span class="s">\1</span>',
        text,
    )
    return text


_DUMP_CSS = """
.almasix-dump{--bg:#0c0f14;--panel:#141a22;--panel-2:#1a222d;--fg:#e8eef7;--muted:#8b9bb0;--accent:#ff5c5c;--cyan:#5eead4;--border:#243042;--code:#0a0e14;--key:#7dd3fc;--str:#86efac;--num:#fbbf24;--bool:#f0abfc;color:var(--fg);font:14px/1.5 ui-sans-serif,system-ui,sans-serif;margin:1rem 0}
.almasix-dump .badge{display:inline-block;font:700 11px/1 ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase;padding:.3rem .5rem;border-radius:6px;background:darkorange;color:#1a0505;margin-bottom:.5rem}
.almasix-dump .badge.dd{background:var(--accent)}
.almasix-dump .meta{color:var(--muted);font-size:.85rem;margin-bottom:.75rem}
.almasix-dump .meta code{color:var(--cyan);font-family:ui-monospace,monospace;font-size:.9em}
.almasix-dump .card{background:var(--panel);border:1px solid var(--border);border-radius:12px;overflow:hidden;margin:0 0 .75rem;box-shadow:0 8px 28px rgba(0,0,0,.22)}
.almasix-dump .card header{display:flex;flex-wrap:wrap;gap:.5rem .75rem;align-items:baseline;padding:.65rem .9rem;background:var(--panel-2);border-bottom:1px solid var(--border)}
.almasix-dump .idx{color:#e879f9;font-weight:700;font-family:ui-monospace,monospace}
.almasix-dump .caption{color:var(--cyan);font-weight:650}
.almasix-dump .type{color:var(--muted);font-family:ui-monospace,monospace;font-size:.8rem;margin-left:auto}
.almasix-dump pre{margin:0;padding:.9rem 1rem;overflow:auto;background:var(--code);font:12.5px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;color:#d7e2f0}
.almasix-dump .k{color:var(--key)}.almasix-dump .s{color:var(--str)}.almasix-dump .n{color:var(--num)}.almasix-dump .b{color:var(--bool)}
""".strip()


def _dump_cards(values: tuple[Any, ...]) -> str:
    blocks: list[str] = []
    multi = len(values) > 1
    for index, value in enumerate(values if values else (None,)):
        caption = html.escape(describe(value))
        type_name = html.escape(_type_label(value))
        payload = _colorize_json(html.escape(to_json(value)))
        idx = f"#{index} " if multi else ""
        blocks.append(
            f"""<section class="card">
  <header>
    <span class="idx">{idx}</span>
    <span class="caption">{caption}</span>
    <span class="type">{type_name}</span>
  </header>
  <pre><code>{payload}</code></pre>
</section>"""
        )
    return "\n".join(blocks)


def render_dump_html(
    values: tuple[Any, ...] | Any,
    *,
    source: str = "",
    badge: str = "dump",
) -> str:
    """Inline HTML fragment for Prism ``@dump`` (embeds in the page)."""
    if not isinstance(values, tuple):
        values = (values,)
    loc = html.escape(source) if source else "—"
    label = html.escape(badge)
    badge_class = "badge dd" if badge == "dd" else "badge"
    return f"""<div class="almasix-dump" data-almasix="{label}">
<style>{_DUMP_CSS}</style>
<div class="{badge_class}">{label}</div>
<div class="meta">view · <code>{loc}</code></div>
{_dump_cards(values)}
</div>"""


def render_dd_html(
    values: tuple[Any, ...],
    *,
    caller: Caller | None = None,
    request_method: str = "",
    request_path: str = "",
    app_name: str = "Almasix",
) -> str:
    """Self-contained HTML dump page (CDN-free) for HTTP ``dd()``."""
    cards = _dump_cards(tuple(values) if values else (None,))

    loc = html.escape(str(caller)) if caller else "—"
    fn = html.escape(caller.function) if caller else "—"
    method = html.escape(request_method or "—")
    path = html.escape(request_path or "—")
    name = html.escape(app_name)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>dd() — {name}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0c0f14;
      --panel: #141a22;
      --panel-2: #1a222d;
      --fg: #e8eef7;
      --muted: #8b9bb0;
      --accent: #ff5c5c;
      --cyan: #5eead4;
      --border: #243042;
      --code: #0a0e14;
      --key: #7dd3fc;
      --str: #86efac;
      --num: #fbbf24;
      --bool: #f0abfc;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font: 14px/1.5 ui-sans-serif, system-ui, sans-serif;
      color: var(--fg);
      background:
        radial-gradient(1200px 600px at 10% -10%, rgba(255,92,92,.12), transparent 55%),
        radial-gradient(900px 500px at 100% 0%, rgba(94,234,212,.08), transparent 50%),
        var(--bg);
    }}
    .shell {{ max-width: 1080px; margin: 0 auto; padding: 0 1.5rem; }}
    .hero {{
      border-bottom: 1px solid var(--border);
      background: linear-gradient(180deg, rgba(20,26,34,.95), rgba(20,26,34,.7));
      backdrop-filter: blur(8px);
    }}
    .hero .shell {{ padding: 1.75rem 0 1.4rem; }}
    .badge {{
      display: inline-block;
      font: 700 12px/1 ui-monospace, monospace;
      letter-spacing: .08em;
      text-transform: uppercase;
      padding: .35rem .55rem;
      border-radius: 6px;
      background: var(--accent);
      color: #1a0505;
      margin-bottom: .75rem;
    }}
    h1 {{
      margin: 0 0 .4rem;
      font-size: 1.35rem;
      font-weight: 650;
      letter-spacing: -.02em;
    }}
    .meta {{ color: var(--muted); font-size: .92rem; }}
    .meta code {{
      color: var(--cyan);
      font-family: ui-monospace, monospace;
      font-size: .85em;
    }}
    main .shell {{ padding: 1.5rem 0 3rem; }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      margin: 0 0 1rem;
      box-shadow: 0 10px 40px rgba(0,0,0,.25);
    }}
    .card header {{
      display: flex;
      flex-wrap: wrap;
      gap: .5rem .75rem;
      align-items: baseline;
      padding: .75rem 1rem;
      background: var(--panel-2);
      border-bottom: 1px solid var(--border);
    }}
    .idx {{ color: #e879f9; font-weight: 700; font-family: ui-monospace, monospace; }}
    .caption {{ color: var(--cyan); font-weight: 650; }}
    .type {{
      color: var(--muted);
      font-family: ui-monospace, monospace;
      font-size: .82rem;
      margin-left: auto;
    }}
    pre {{
      margin: 0;
      padding: 1rem 1.1rem;
      overflow: auto;
      background: var(--code);
      font: 12.5px/1.55 ui-monospace, SFMono-Regular, Menlo, monospace;
      color: #d7e2f0;
    }}
    .k {{ color: var(--key); }}
    .s {{ color: var(--str); }}
    .n {{ color: var(--num); }}
    .b {{ color: var(--bool); }}
    .foot {{
      color: var(--muted);
      font-size: .8rem;
      margin-top: 1.5rem;
    }}
  </style>
</head>
<body>
  <div class="hero">
    <div class="shell">
      <div class="badge">dd</div>
      <h1>Dump and die</h1>
      <div class="meta">
        {method} {path}
        · <code>{loc}</code>
        · {fn}()
        · {name}
      </div>
    </div>
  </div>
  <main>
    <div class="shell">
      {cards}
      <p class="foot">Almasix · intentional halt via <code>dd()</code> — not an application error.</p>
    </div>
  </main>
</body>
</html>
"""


def render(value: Any, *, console: Any | None = None, as_json: bool = True) -> None:
    """Single-value pretty print (Loupe displayhook)."""
    render_value(value, console=console, as_json=as_json)
