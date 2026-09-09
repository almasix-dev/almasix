"""Generate ``.pyi`` stubs for Articulate models and named routes."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from almasix.lsp.index import build_index, discover_models, find_app_root

_CASTS_RE = re.compile(
    r"casts\s*=\s*\{(?P<body>.*?)\}",
    re.DOTALL,
)
_STRING_RE = re.compile(r"""['"]([^'"]+)['"]""")

_CAST_TYPES: dict[str, str] = {
    "int": "int",
    "integer": "int",
    "float": "float",
    "double": "float",
    "decimal": "float",
    "bool": "bool",
    "boolean": "bool",
    "str": "str",
    "string": "str",
    "array": "list[Any]",
    "json": "Any",
    "object": "dict[str, Any]",
    "collection": "Any",
    "date": "Any",
    "datetime": "Any",
    "immutable_date": "Any",
    "immutable_datetime": "Any",
    "timestamp": "Any",
}


@dataclass
class StubResult:
    """Outcome of :func:`generate_stubs`."""

    base_path: Path
    output_dir: Path
    model_files: list[Path] = field(default_factory=list)
    routes_file: Path | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def generate_stubs(
    base_path: Path | str | None = None,
    *,
    output: Path | str | None = None,
) -> StubResult:
    """Write model attribute stubs and a route-name ``Literal`` union.

    Column names come from ``fillable`` / ``casts`` declared on each model
    file (AST / regex). Live schema inspection is optional and not required
    for a useful stub set.
    """
    root = Path(base_path) if base_path else find_app_root()
    if root is None or not (Path(root) / "bootstrap" / "app.py").is_file():
        return StubResult(
            base_path=Path(base_path) if base_path else Path.cwd(),
            output_dir=Path.cwd(),
            error="No Almasix application found (missing bootstrap/app.py).",
        )
    root = Path(root).resolve()
    out = Path(output) if output else root / ".almasix" / "stubs"
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    model_files: list[Path] = []
    models_root = root / "app" / "models"
    for stem, path in discover_models(models_root).items():
        columns = extract_model_columns(path)
        class_name = _guess_class_name(path, stem)
        content = render_model_stub(class_name, columns)
        target = out / "models" / f"{stem}.pyi"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        model_files.append(target)

    route_names = _route_names(root)
    routes_path = out / "routes.pyi"
    routes_path.write_text(render_routes_stub(route_names), encoding="utf-8")

    (out / "README.md").write_text(
        _stubs_readme(out.relative_to(root) if out.is_relative_to(root) else out),
        encoding="utf-8",
    )

    return StubResult(
        base_path=root,
        output_dir=out,
        model_files=model_files,
        routes_file=routes_path,
    )


def extract_model_columns(path: Path) -> dict[str, str]:
    """Map attribute name → Python type annotation from fillable/casts."""
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return {"id": "Any"}

    columns: dict[str, str] = {"id": "Any"}
    for name in _tuple_strings(source, "fillable"):
        columns.setdefault(name, "Any")
    for name, cast in _dict_casts(source).items():
        columns[name] = _CAST_TYPES.get(cast.lower(), "Any")
    return columns


def render_model_stub(class_name: str, columns: dict[str, str]) -> str:
    """Render a minimal ``.pyi`` for one model class."""
    lines = [
        "from __future__ import annotations",
        "",
        "from typing import Any",
        "",
        "from almasix.orm import Model",
        "",
        "",
        f"class {class_name}(Model):",
    ]
    if not columns:
        lines.append("    id: Any")
    else:
        for name, annotation in sorted(columns.items()):
            lines.append(f"    {name}: {annotation}")
    lines.append("")
    return "\n".join(lines)


def render_routes_stub(names: list[str]) -> str:
    """Render ``RouteName`` as a ``Literal`` union of known route names."""
    unique = sorted({n for n in names if n})
    lines = [
        "from __future__ import annotations",
        "",
        "from typing import Literal",
        "",
    ]
    if not unique:
        lines.append('RouteName = Literal[""]')
    elif len(unique) == 1:
        lines.append(f'RouteName = Literal["{unique[0]}"]')
    else:
        lines.append("RouteName = Literal[")
        for name in unique:
            lines.append(f'    "{name}",')
        lines.append("]")
    lines.append("")
    return "\n".join(lines)


def _route_names(root: Path) -> list[str]:
    index = build_index(root)
    if index.ok and index.routes:
        return list(index.routes.keys())
    # Fall back to static parse when boot fails (e.g. missing deps in CI unit).
    from almasix.lsp.index import discover_route_locations

    return list(discover_route_locations(root / "routes").keys())


def _guess_class_name(path: Path, stem: str) -> str:
    expected = _pascal(stem)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return expected
    classes = [
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
    ]
    if expected in classes:
        return expected
    return classes[0] if classes else expected


def _pascal(stem: str) -> str:
    return "".join(part.capitalize() for part in stem.split("_") if part)


def _tuple_strings(source: str, attr: str) -> list[str]:
    pattern = re.compile(rf"{attr}\s*=\s*\((?P<body>.*?)\)", re.DOTALL)
    match = pattern.search(source)
    if not match:
        return []
    return _STRING_RE.findall(match.group("body"))


def _dict_casts(source: str) -> dict[str, str]:
    match = _CASTS_RE.search(source)
    if not match:
        return {}
    body = match.group("body")
    found: dict[str, str] = {}
    for key_match in re.finditer(
        r"""['"](?P<key>[^'"]+)['"]\s*:\s*['"](?P<val>[^'"]+)['"]""",
        body,
    ):
        found[key_match.group("key")] = key_match.group("val")
    return found


def _stubs_readme(rel: Path | str) -> str:
    return (
        "# Almasix IDE stubs\n\n"
        "Generated by `smith ide:stubs`.\n\n"
        f"Point your type checker at `{rel}` "
        "(pyright `stubPath` / mypy `mypy_path`).\n"
    )
