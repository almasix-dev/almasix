"""Laravel-shaped miscellaneous Support helpers."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from datetime import date, datetime, timezone
from typing import Any, TypeVar

from avalon.support.arr import Arr
from avalon.support.collection import data_get

T = TypeVar("T")


def data_set(target: MutableMapping[Any, Any], key: str, value: Any, overwrite: bool = True) -> Any:
    """Set a value with dot notation (Laravel ``data_set``)."""
    if not overwrite and _has_path(target, key):
        return target
    Arr.set(target, key, value)
    return target


def data_fill(target: MutableMapping[Any, Any], key: str, value: Any) -> Any:
    """Set only when the path is missing (Laravel ``data_fill``)."""
    return data_set(target, key, value, overwrite=False)


def data_forget(target: MutableMapping[Any, Any], keys: str | list[str]) -> Any:
    """Remove dotted keys (Laravel ``data_forget``)."""
    Arr.forget(target, keys)
    return target


def head(array: Sequence[Any] | IterableLike) -> Any:
    items = list(array)
    return items[0] if items else None


def last(array: Sequence[Any] | IterableLike) -> Any:
    items = list(array)
    return items[-1] if items else None


IterableLike = Any


def blank(value: Any) -> bool:
    """True when value is empty-ish (Laravel ``blank``)."""
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, (str, bytes)):
        return value.strip() == b"" if isinstance(value, bytes) else value.strip() == ""
    if isinstance(value, Mapping):
        return len(value) == 0
    if isinstance(value, Sequence):
        return len(value) == 0
    if hasattr(value, "__len__"):
        try:
            return len(value) == 0
        except TypeError:
            return False
    return False


def filled(value: Any) -> bool:
    return not blank(value)


def value(val: Any, *args: Any) -> Any:
    """Resolve a value or invoke a callable (Laravel ``value``)."""
    if callable(val):
        return val(*args)
    return val


def tap(target: T, callback: Callable[[T], Any] | None = None) -> T:
    """Pass ``target`` through ``callback`` and return ``target``."""
    if callback is not None:
        callback(target)
    return target


def with_(value: T, callback: Callable[[T], Any]) -> Any:
    """Pass value into callback and return the callback result (Laravel ``with``)."""
    return callback(value)


def when(condition: Any, value_if_true: Any, value_if_false: Any = None) -> Any:
    """Return one of two values based on truthiness (Laravel ``when``)."""
    if condition:
        if callable(value_if_true):
            try:
                params = inspect.signature(value_if_true).parameters
                if len(params) >= 1:
                    return value_if_true(condition)
            except (TypeError, ValueError):
                pass
            return value_if_true()
        return value_if_true
    if callable(value_if_false):
        try:
            params = inspect.signature(value_if_false).parameters
            if len(params) >= 1:
                return value_if_false(condition)
        except (TypeError, ValueError):  # pragma: no cover
            pass
        return value_if_false()
    return value_if_false


def transform(value_in: Any, callback: Callable[[Any], Any], default: Any = None) -> Any:
    """Transform a filled value; otherwise return default (Laravel ``transform``)."""
    if filled(value_in):
        return callback(value_in)
    return value(default)


class Optional:
    """Null-safe attribute/call proxy (Laravel ``optional``)."""

    def __init__(self, obj: Any = None) -> None:
        object.__setattr__(self, "_obj", obj)

    def __getattr__(self, item: str) -> Any:
        obj = object.__getattribute__(self, "_obj")
        if obj is None:
            return Optional(None)
        attr = getattr(obj, item, None)
        if callable(attr):
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                return attr(*args, **kwargs)

            return wrapper
        return attr

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        obj = object.__getattribute__(self, "_obj")
        if obj is None:
            return None
        if callable(obj):
            return obj(*args, **kwargs)
        return obj

    def __bool__(self) -> bool:
        return object.__getattribute__(self, "_obj") is not None


def optional(obj: Any = None, callback: Callable[[Any], Any] | None = None) -> Any:
    if callback is not None:
        return callback(obj) if obj is not None else None
    return Optional(obj)


def throw_if(condition: Any, exception: Any = RuntimeError, *args: Any, **kwargs: Any) -> None:
    if condition:
        if isinstance(exception, BaseException):
            raise exception
        if isinstance(exception, type) and issubclass(exception, BaseException):
            raise exception(*args, **kwargs)
        raise RuntimeError(exception)


def throw_unless(condition: Any, exception: Any = RuntimeError, *args: Any, **kwargs: Any) -> None:
    throw_if(not condition, exception, *args, **kwargs)


def abort_if(condition: Any, code: int = 404, message: str = "", headers: dict[str, str] | None = None) -> None:
    if condition:
        abort(code, message, headers=headers)


def abort_unless(
    condition: Any,
    code: int = 404,
    message: str = "",
    headers: dict[str, str] | None = None,
) -> None:
    abort_if(not condition, code, message, headers=headers)


def abort(code: int = 404, message: str = "", headers: dict[str, str] | None = None) -> None:
    from avalon.http.exceptions import HttpException

    raise HttpException(message or "Aborted", status_code=code, headers=headers or {})


def retry(
    times: int,
    callback: Callable[[], Any],
    *,
    sleep: float | Callable[[int], float] = 0,
    when: Callable[[BaseException], bool] | None = None,
) -> Any:
    """Retry a callable up to ``times`` attempts (Laravel ``retry``)."""
    attempts = max(1, int(times))
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return callback()
        except BaseException as exc:  # noqa: BLE001
            last_exc = exc
            if when is not None and not when(exc):
                raise
            if attempt >= attempts:
                raise
            delay = float(sleep(attempt)) if callable(sleep) else float(sleep)
            if delay:
                time.sleep(delay)
    raise last_exc  # pragma: no cover


async def retry_async(
    times: int,
    callback: Callable[[], Any],
    *,
    sleep: float = 0,
    when: Callable[[BaseException], bool] | None = None,
) -> Any:
    attempts = max(1, int(times))
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            result = callback()
            if inspect.isawaitable(result):
                return await result
            return result
        except BaseException as exc:  # noqa: BLE001
            last_exc = exc
            if when is not None and not when(exc):
                raise
            if attempt >= attempts:
                raise
            if sleep:
                await asyncio.sleep(float(sleep))
    raise last_exc  # pragma: no cover


def once(callback: Callable[[], Any]) -> Any:
    """Memoize a callable for the process lifetime (Laravel ``once``)."""
    attr = "__avalon_once_value__"
    if not hasattr(callback, attr):
        setattr(callback, attr, callback())
    return getattr(callback, attr)


def rescue(
    callback: Callable[[], Any],
    rescue_with: Any = None,
    *,
    report: bool = True,
) -> Any:
    """Execute callback; on exception return rescue value (Laravel ``rescue``)."""
    try:
        return callback()
    except BaseException as exc:  # noqa: BLE001
        if report:
            try:
                report_exception(exc)
            except Exception:  # pragma: no cover
                pass
        return value(rescue_with, exc) if callable(rescue_with) else rescue_with


def report(exc: BaseException) -> None:
    """Report an exception through the handler without raising (Laravel ``report``)."""
    handler = _exception_handler()
    if handler is not None:
        handler.report(exc)
        return

    import sys

    print(f"[report] {type(exc).__name__}: {exc}", file=sys.stderr)


def _exception_handler() -> Any:
    """Return the application's exception handler, or ``None`` when unbooted."""
    from avalon.framework.helpers import current_application

    application = current_application()
    if application is None:
        return None
    from avalon.exceptions.handler import Handler

    if application.container.bound(Handler):
        return application.make(Handler)
    return Handler(application)


# Laravel names the helper ``report``; the older name stays as an alias.
report_exception = report


def report_if(condition: Any, exc: BaseException) -> None:
    if condition:
        report(exc)


def report_unless(condition: Any, exc: BaseException) -> None:
    if not condition:
        report(exc)


def class_basename(class_or_object: Any) -> str:
    if isinstance(class_or_object, type):
        return class_or_object.__name__
    if isinstance(class_or_object, str):
        return class_or_object.rsplit(".", 1)[-1].rsplit("\\", 1)[-1]
    return type(class_or_object).__name__


def object_get(obj: Any, key: str, default: Any = None) -> Any:
    return data_get(obj, key, default)


def now(tz: timezone | None = None) -> datetime:
    return datetime.now(tz or timezone.utc)


def today(tz: timezone | None = None) -> date:
    return now(tz).date()


def literal(**kwargs: Any) -> Any:
    """Build a simple namespace object (Laravel ``literal``)."""
    return type("Literal", (), kwargs)()


def class_uses_recursive(obj: Any) -> set[type]:
    """Collect mixin / base classes recursively (Python stand-in for PHP traits)."""
    cls = obj if isinstance(obj, type) else type(obj)
    bases: set[type] = set()
    for base in cls.__mro__:
        if base not in (cls, object):
            bases.add(base)
    return bases


trait_uses_recursive = class_uses_recursive


def e(value: Any, double_encode: bool = True) -> str:
    """HTML-escape a string (Laravel ``e``)."""
    import html as html_lib

    text = "" if value is None else str(value)
    escaped = html_lib.escape(text, quote=True)
    if not double_encode:
        escaped = (
            escaped.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#x27;", "'")
        )
        escaped = html_lib.escape(escaped, quote=True)
    return escaped


def preg_replace_array(pattern: str, replacements: Sequence[str], subject: str) -> str:
    """Replace successive regex matches with successive replacements."""
    import re

    iterator = iter(replacements)

    def repl(_match: Any) -> str:
        try:
            return next(iterator)
        except StopIteration:
            return ""

    return re.sub(pattern, repl, subject)


def _has_path(target: Any, key: str) -> bool:
    from avalon.support.arr import _has_path as arr_has_path

    return arr_has_path(target, key)


# Path helpers — resolve against the booted Application when available.
def base_path(*paths: str) -> str:
    from pathlib import Path

    root = _app_base()
    return str(Path(root, *paths))


def app_path(*paths: str) -> str:
    return base_path("app", *paths)


def config_path(*paths: str) -> str:
    return base_path("config", *paths)


def database_path(*paths: str) -> str:
    return base_path("database", *paths)


def lang_path(*paths: str) -> str:
    return base_path("lang", *paths)


def public_path(*paths: str) -> str:
    return base_path("public", *paths)


def resource_path(*paths: str) -> str:
    return base_path("resources", *paths)


def storage_path(*paths: str) -> str:
    return base_path("storage", *paths)


def _app_base() -> str:
    from pathlib import Path

    from avalon.framework.helpers import current_application

    application = current_application()
    if application is not None:
        return str(application.base_path)
    return str(Path.cwd())
