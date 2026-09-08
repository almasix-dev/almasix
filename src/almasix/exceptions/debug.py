"""Debug HTML page for web exceptions when ``APP_DEBUG`` is true."""

from __future__ import annotations

import html
import linecache
import traceback
from pathlib import Path
from typing import Any


def render_debug_html(
    exc: BaseException,
    *,
    request_method: str = "",
    request_path: str = "",
    route_name: str | None = None,
    app_name: str = "Almasix",
) -> str:
    """Build a self-contained debug HTML document (no secrets / env dump)."""
    title = html.escape(f"{type(exc).__name__}: {exc}")
    frames = _frames(exc)
    frames_html = "\n".join(_frame_block(frame) for frame in frames)
    route = html.escape(route_name or "—")
    method = html.escape(request_method or "—")
    path = html.escape(request_path or "—")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light dark; --bg:#0f1419; --panel:#1a2332; --fg:#e7ecf3;
            --muted:#9aa7b8; --accent:#f07178; --code:#0b1220; --border:#2a3548; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font:14px/1.5 ui-sans-serif,system-ui,sans-serif;
           background:var(--bg); color:var(--fg); }}
    .shell {{ max-width:1100px; margin:0 auto; padding:0 2rem; width:100%; }}
    header {{ border-bottom:1px solid var(--border); background:var(--panel); }}
    header .shell {{ padding:1.5rem 0; }}
    h1 {{ margin:0 0 .35rem; font-size:1.25rem; color:var(--accent); font-weight:600; }}
    .meta {{ color:var(--muted); font-size:.9rem; }}
    main .shell {{ padding:1.5rem 0 3rem; }}
    .frame {{ background:var(--panel); border:1px solid var(--border); border-radius:8px;
              margin:0 0 1rem; overflow:hidden; }}
    .frame-head {{ padding:.65rem 1rem; border-bottom:1px solid var(--border);
                   color:var(--muted); font-family:ui-monospace,monospace; font-size:.85rem; }}
    pre {{ margin:0; padding:.75rem 1rem; overflow:auto; background:var(--code);
           font:12px/1.45 ui-monospace,monospace; }}
    .hl {{ background:rgba(240,113,120,.18); }}
    .app {{ color:var(--muted); margin-top:2rem; font-size:.8rem; }}
  </style>
</head>
<body>
  <header>
    <div class="shell">
      <h1>{title}</h1>
      <div class="meta">{method} {path} · route {route} · {html.escape(app_name)}</div>
    </div>
  </header>
  <main>
    <div class="shell">
      {frames_html or "<p class='meta'>No traceback frames.</p>"}
      <p class="app">Almasix debug page — shown only when APP_DEBUG is true.</p>
    </div>
  </main>
</body>
</html>
"""


def _frames(exc: BaseException) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    tb = traceback.extract_tb(exc.__traceback__)
    for entry in tb:
        frames.append(
            {
                "filename": entry.filename,
                "lineno": entry.lineno,
                "name": entry.name,
                "line": entry.line or "",
            }
        )
    return frames


def _frame_block(frame: dict[str, Any]) -> str:
    filename = str(frame["filename"])
    lineno = int(frame["lineno"] or 0)
    name = html.escape(str(frame["name"]))
    path = html.escape(filename)
    excerpt = _source_excerpt(filename, lineno)
    return f"""<div class="frame">
  <div class="frame-head">{path}:{lineno} in {name}</div>
  <pre>{excerpt}</pre>
</div>"""


def _source_excerpt(filename: str, lineno: int, context: int = 5) -> str:
    path = Path(filename)
    if not path.is_file():
        return html.escape(linecache.getline(filename, lineno).rstrip() or "")
    start = max(1, lineno - context)
    end = lineno + context
    lines: list[str] = []
    for number in range(start, end + 1):
        text = linecache.getline(filename, number)
        if not text and number != lineno:
            continue
        css = " class='hl'" if number == lineno else ""
        lines.append(
            f"<span{css}>{number:>4} | {html.escape(text.rstrip())}</span>"
        )
    return "\n".join(lines) if lines else html.escape(f"(source unavailable: {filename})")
