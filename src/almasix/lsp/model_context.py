"""Resolve a local name to a model class for attribute completion.

Used for ``user.name`` / ``article.is_active`` suggestions. Inference is
heuristic (annotations, assignments, name→Class) — not a full type checker.
"""

from __future__ import annotations

import ast
import re

#: Receivers that are never model instances.
_SKIP_RECEIVERS = frozenset(
    {
        "DB",
        "Schema",
        "Blueprint",
        "Migration",
        "Path",
        "Model",
        "self",
        "cls",
        "os",
        "re",
        "sys",
        "ast",
        "json",
        "typing",
        "Optional",
        "List",
        "Dict",
        "Any",
    }
)

_ANN_RE = re.compile(
    r"\b(?P<name>[A-Za-z_][\w]*)\s*:\s*(?:Optional\[)?(?P<model>[A-Z][A-Za-z0-9_]*)"
)
_ASSIGN_CALL_RE = re.compile(
    r"\b(?P<name>[A-Za-z_][\w]*)\s*=\s*(?:await\s+)?"
    r"(?P<model>[A-Z][A-Za-z0-9_]*)\s*(?:\(|\.)"
)


def known_model_names(tables: dict) -> set[str]:
    """Class names declared on indexed tables."""
    return {info.model for info in tables.values() if getattr(info, "model", None)}


def infer_model_name(
    source: str,
    offset: int,
    receiver: str,
    *,
    models: set[str],
) -> str | None:
    """Best-effort model class for ``receiver`` at ``offset``.

    Prefer annotations / assignments before the caret; fall back to a
    ``user`` → ``User`` name heuristic when that class is indexed.
    """
    if not receiver or receiver in _SKIP_RECEIVERS:
        return None
    # Class names used as receivers (``User.where``) are not instances.
    if receiver[0].isupper() and receiver in models:
        return None

    before = source[:offset]
    inferred = _infer_from_ast(before, receiver) or _infer_from_regex(before, receiver)
    if inferred is not None and (not models or inferred in models):
        return inferred
    if inferred is not None and not models:
        return inferred

    return _heuristic_model(receiver, models)


def _heuristic_model(receiver: str, models: set[str]) -> str | None:
    if not models:
        return None
    camel = "".join(part.capitalize() for part in receiver.split("_") if part)
    if camel in models:
        return camel
    return None


def _infer_from_regex(before: str, receiver: str) -> str | None:
    found: list[tuple[int, str]] = []
    for pattern in (_ANN_RE, _ASSIGN_CALL_RE):
        for match in pattern.finditer(before):
            if match.group("name") != receiver:
                continue
            model = match.group("model")
            if model in _SKIP_RECEIVERS:
                continue
            found.append((match.start(), model))
    if not found:
        return None
    found.sort(key=lambda item: item[0])
    return found[-1][1]


def _infer_from_ast(before: str, receiver: str) -> str | None:
    """Parse as much of ``before`` as possible and read annotations / assigns."""
    tree = _parse_prefix(before)
    if tree is None:
        return None
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
                if arg.arg != receiver or arg.annotation is None:
                    continue
                model = _annotation_model(arg.annotation)
                if model is not None:
                    found.append((arg.lineno, model))
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id != receiver or node.annotation is None:
                continue
            model = _annotation_model(node.annotation)
            if model is not None:
                found.append((node.lineno, model))
        if isinstance(node, ast.Assign):
            model = _rhs_model(node.value)
            if model is None:
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == receiver:
                    found.append((node.lineno, model))
    if not found:
        return None
    found.sort(key=lambda item: item[0])
    return found[-1][1]


def _parse_prefix(source: str) -> ast.AST | None:
    text = source
    for _ in range(8):
        try:
            return ast.parse(text)
        except SyntaxError:
            # Drop the incomplete last line and retry.
            cut = text.rfind("\n")
            if cut < 0:
                return None
            text = text[:cut]
    return None


def _annotation_model(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id if node.id[0].isupper() else None
    if isinstance(node, ast.Attribute):
        return node.attr if node.attr[0].isupper() else None
    if isinstance(node, ast.Subscript):
        # ``User | None`` is BinOp in 3.10+; Optional[User] / list[User] here.
        return _annotation_model(node.slice) or _annotation_model(node.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _annotation_model(node.left) or _annotation_model(node.right)
    if isinstance(node, ast.Constant) and node.value is None:
        return None
    if isinstance(node, ast.Tuple):
        for elt in node.elts:
            found = _annotation_model(elt)
            if found is not None:
                return found
    return None


def _rhs_model(node: ast.AST) -> str | None:
    """``User(…)``, ``await User.find(…)``, ``User.query().first()`` → ``User``."""
    if isinstance(node, ast.Await):
        return _rhs_model(node.value)
    if isinstance(node, ast.Call):
        return _rhs_model(node.func)
    if isinstance(node, ast.Attribute):
        return _rhs_model(node.value)
    if isinstance(node, ast.Name) and node.id[0].isupper():
        return node.id
    return None
