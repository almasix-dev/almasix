"""Minimal HTML layout helper for web routes.

Prefer Prism templates via ``almasix.prism.view()``. This helper remains
for one-off strings and tests.
"""

from __future__ import annotations

_STYLE = """
  body { font: 16px/1.5 system-ui, sans-serif; margin: 2rem auto; max-width: 46rem; }
  code { background: #f3f3f3; padding: 0.1rem 0.3rem; border-radius: 3px; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border-bottom: 1px solid #ddd; padding: 0.4rem 0.6rem; text-align: left; }
  .complete { color: #157f3d; }
  .next { color: #b45309; }
  .planned { color: #666; }
"""


def layout(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>{_STYLE}</style>
</head>
<body>
{body}
</body>
</html>"""
