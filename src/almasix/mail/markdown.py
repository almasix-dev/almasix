"""Render Markdown/HTML mail views via Prism + theme layout."""

from __future__ import annotations

import html
import re
from typing import Any

from almasix.mail.mailable import Content

# Default theme layout — Laravel mail::message shaped (CDN-free).
DEFAULT_THEME = "mail.themes.default"
_BUILTIN_THEME_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{{ subject or "Message" }}</title>
  <style>
    body { margin: 0; background: #f4f4f7; color: #24292f;
           font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .wrap { max-width: 560px; margin: 2rem auto; padding: 0 1rem; }
    .card { background: #fff; border: 1px solid #d0d7de; border-radius: 10px;
            padding: 1.5rem 1.75rem; box-shadow: 0 1px 2px rgba(0,0,0,.04); }
    .brand { font-weight: 650; letter-spacing: -.02em; margin: 0 0 1rem; color: #0969da; }
    .footer { color: #656d76; font-size: .85rem; margin-top: 1.25rem; text-align: center; }
    a.button { display: inline-block; background: #0969da; color: #fff !important;
               text-decoration: none; padding: .55rem 1rem; border-radius: 6px;
               font-weight: 600; margin: .75rem 0; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <p class="brand">{{ app_name or "Almasix" }}</p>
      {!! slot !!}
    </div>
    <p class="footer">{{ footer or "" }}</p>
  </div>
</body>
</html>
"""


def _strip_html(value: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", value)
    text = re.sub(r"(?s)<.*?>", " ", text)
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text


def _render_view(name: str, data: dict[str, Any] | None) -> str | None:
    try:
        from almasix.prism.helpers import get_engine

        return get_engine().render(name, data)
    except Exception:
        return None


def _wrap_theme(body_html: str, data: dict[str, Any], theme: str | None) -> str:
    theme_name = theme or DEFAULT_THEME
    context = {
        **data,
        "slot": body_html,
        "app_name": data.get("app_name") or _app_name(),
        "subject": data.get("subject") or "",
        "footer": data.get("footer") or "",
    }
    themed = _render_view(theme_name, context)
    if themed is not None:
        return themed
    # Builtin fallback when app has no theme view yet.
    from almasix.prism.compiler import compile_template

    render = compile_template(_BUILTIN_THEME_HTML, name="mail.builtin_theme")
    return render(context, None)


def _app_name() -> str:
    try:
        from almasix.config import config

        return str(config("app.name") or "Almasix")
    except Exception:
        return "Almasix"


def render_markdown_component(markdown_body: str) -> str:
    """Minimal Markdown → HTML (headings, bold, links, paragraphs, buttons)."""
    lines = markdown_body.strip().splitlines()
    blocks: list[str] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            text = " ".join(paragraph)
            blocks.append(f"<p>{_inline(text)}</p>")
            paragraph.clear()

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            flush()
            continue
        if line.startswith("# "):
            flush()
            blocks.append(f"<h1>{_inline(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            flush()
            blocks.append(f"<h2>{_inline(line[3:].strip())}</h2>")
        elif line.startswith("[") and "](" in line and line.endswith(")"):
            flush()
            label, _, rest = line[1:].partition("](")
            href = rest[:-1]
            blocks.append(
                f'<p><a class="button" href="{html.escape(href)}">{_inline(label)}</a></p>'
            )
        else:
            paragraph.append(line.strip())
    flush()
    return "\n".join(blocks)


def _inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2">\1</a>',
        escaped,
    )
    return escaped


def render_content(content: Content) -> tuple[str | None, str | None]:
    """Return ``(html, text)`` for a mailable content definition."""
    data = dict(content.with_data or {})
    html_body = content.html
    text_body = content.text
    theme = content.theme or data.pop("theme", None)

    view_name = content.markdown or content.view
    if view_name:
        rendered = _render_view(view_name, data)
        if rendered is not None:
            if content.markdown:
                stripped = rendered.lstrip()
                if not stripped.lower().startswith("<"):
                    rendered = render_markdown_component(rendered)
                plain_source = rendered
                html_body = _wrap_theme(rendered, data, theme)
                if text_body is None:
                    text_view = f"{view_name}.text"
                    text_rendered = _render_view(text_view, data)
                    if text_rendered is None:
                        # Also try ``mail/welcome.text`` style (dot in filename).
                        alt = view_name.rsplit(".", 1)
                        if len(alt) == 2:
                            text_rendered = _render_view_file(f"{alt[0]}/{alt[1]}.text")
                    text_body = (
                        text_rendered if text_rendered is not None else _strip_html(plain_source)
                    )
            elif view_name.endswith(".html") or ".prism.html" in view_name:
                html_body = rendered
            else:
                html_body = html_body or rendered

    if html_body and text_body is None:
        text_body = _strip_html(html_body)

    return html_body, text_body


def _render_view_file(relative_path: str) -> str | None:
    """Read a plain template file (e.g. ``mail/welcome.text``) and compile it."""
    try:
        from almasix.prism.helpers import get_engine

        engine = get_engine()
        for root in engine.paths:
            candidate = root / relative_path
            if candidate.is_file():
                source = candidate.read_text(encoding="utf-8")
                from almasix.prism.compiler import compile_template

                return compile_template(source, name=relative_path)({}, engine)
    except Exception:
        return None
    return None
