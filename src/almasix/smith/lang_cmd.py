"""Smith lang:* commands — publish, make, missing-key report."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from almasix.translation.provider import framework_lang_path

_LOCALE_RE = re.compile(r"^[A-Za-z]{2,3}(?:[_-][A-Za-z0-9]+)?$")


class LangError(ValueError):
    """Invalid language tooling request."""


def publish_lang(base_path: Path, *, force: bool = False) -> Path:
    """Scaffold `lang/` and copy framework catalogs (Laravel `lang:publish`)."""
    dest = base_path / "lang"
    dest.mkdir(parents=True, exist_ok=True)
    source = framework_lang_path()
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        target = dest / relative
        if target.exists() and not force:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return dest


def make_lang(locale: str, base_path: Path, *, force: bool = False) -> Path:
    """Create an empty locale tree under `lang/<locale>/`."""
    if not _LOCALE_RE.match(locale):
        raise LangError(f"Invalid locale {locale!r}. Use a BCP 47-ish tag like en, en_US, or sw.")
    root = base_path / "lang" / locale
    if root.exists() and any(root.iterdir()) and not force:
        raise LangError(f"Locale directory already exists: {root}")
    root.mkdir(parents=True, exist_ok=True)
    (root / "messages.py").write_text(
        '"""Application messages."""\n\ntranslations = {}\n',
        encoding="utf-8",
    )
    json_path = base_path / "lang" / f"{locale}.json"
    if not json_path.exists() or force:  # pragma: no branch
        json_path.write_text("{}\n", encoding="utf-8")
    return root


def missing_keys(
    base_path: Path,
    *,
    locale: str,
    fallback: str = "en",
) -> list[str]:
    """Report keys present in `fallback` but absent in `locale`."""
    lang_root = base_path / "lang"
    fallback_keys = _collect_keys(lang_root, fallback)
    target_keys = _collect_keys(lang_root, locale)
    return sorted(fallback_keys - target_keys)


def _collect_keys(lang_root: Path, locale: str) -> set[str]:
    keys: set[str] = set()
    locale_dir = lang_root / locale
    if locale_dir.is_dir():
        for file in locale_dir.glob("*.py"):
            data = _load_py_dict(file)
            for dotted in _flatten(data):
                keys.add(f"{file.stem}.{dotted}" if dotted else file.stem)
    json_file = lang_root / f"{locale}.json"
    if json_file.is_file():
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        if isinstance(data, dict):
            keys.update(str(key) for key in data)
    return keys


def _load_py_dict(path: Path) -> dict:
    import importlib.util
    import sys

    module_name = f"almasix_lang_scan_{abs(hash(path))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return {}
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        return {}
    data = getattr(module, "translations", None)
    return data if isinstance(data, dict) else {}


def _flatten(data: dict, prefix: str = "") -> list[str]:
    keys: list[str] = []
    for key, value in data.items():
        dotted = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            keys.extend(_flatten(value, dotted))
        else:
            keys.append(dotted)
    return keys
