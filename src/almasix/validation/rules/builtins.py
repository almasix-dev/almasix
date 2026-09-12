"""Every Laravel 12 validation rule (`LARAVEL_RULES`), Almasix-shaped.

Each rule is a small :class:`~almasix.validation.rules.base.RuleBase`
subclass. Rules that only *mark* a field (``bail``, ``nullable``,
``sometimes``, the ``exclude*`` family) always ``passes()``; the engine that
walks a field's rule list reads their intent off plain attributes
(``is_bail``, ``is_nullable``, ``is_sometimes``, ``exclude``, ``exclude_if``,
...) instead.

``register_all()`` — called once at import time — registers every name in
:data:`~almasix.validation.rules.registry.LARAVEL_RULES` and raises if one is
missing, so this file cannot silently drift from the canonical rule list.
"""

from __future__ import annotations

import inspect
import io
import ipaddress
import json
import mimetypes
import operator
import re
import socket
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from almasix.validation.rules.base import RuleBase, data_get, is_blank
from almasix.validation.rules.registry import LARAVEL_RULES, register

try:  # Optional — used for lenient date parsing beyond ISO/common formats.
    from dateutil import parser as _dateutil_parser
except ImportError:  # pragma: no cover - exercised where dateutil is absent
    _dateutil_parser = None

try:  # Optional — used for the `dimensions` rule.
    from PIL import Image as _PILImage
except ImportError:  # pragma: no cover - exercised where Pillow is absent
    _PILImage = None

try:  # 3.9+ stdlib; guarded for completeness on older runtimes.
    from zoneinfo import available_timezones as _available_timezones
except ImportError:  # pragma: no cover
    _available_timezones = None


# ============================================================================
# Shared helpers
# ============================================================================


def _field_present(data: Mapping[str, Any], key: str) -> bool:
    """Whether ``key`` exists in ``data`` at all (dotted paths included).

    Distinct from :func:`is_blank` — a key holding ``None`` or ``""`` is
    still *present*, which is what ``present``/``missing``/``filled`` care
    about.
    """
    if key in data:
        return True
    current: Any = data
    for part in key.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        else:
            return False
    return True


def _looks_like_file(value: Any) -> bool:
    """Duck-type an uploaded file (``almasix.http.request.UploadedFile`` or a test double)."""
    try:
        from almasix.http.request import UploadedFile

        if isinstance(value, UploadedFile):
            return True
    except Exception:  # pragma: no cover - defensive against import cycles
        pass
    return (
        hasattr(value, "filename")
        and hasattr(value, "content_type")
        and hasattr(value, "size")
        and not isinstance(value, (str, bytes))
    )


def _filename_of(value: Any) -> str | None:
    return getattr(value, "filename", None) or getattr(value, "name", None)


def _file_extension(value: Any) -> str:
    name = _filename_of(value) or ""
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _is_empty(value: Any) -> bool:
    """Laravel's ``empty`` for validation purposes — blank, or a fileless upload."""
    if is_blank(value):
        return True
    if _looks_like_file(value) and not _filename_of(value):
        return True
    return False


_ACCEPTED_VALUES = {"yes", "on", "1", "true"}
_DECLINED_VALUES = {"no", "off", "0", "false"}


def _is_accepted(value: Any) -> bool:
    if isinstance(value, bool):
        return value is True
    return str(value).strip().lower() in _ACCEPTED_VALUES


def _is_declined(value: Any) -> bool:
    if isinstance(value, bool):
        return value is False
    return str(value).strip().lower() in _DECLINED_VALUES


def _is_numeric_string(text: str) -> bool:
    try:
        float(text)
    except (TypeError, ValueError):
        return False
    return True


def detect_kind(value: Any) -> str:
    """``"string" | "array" | "numeric" | "file"`` — the size-rule dispatch key."""
    if _looks_like_file(value):
        return "file"
    if isinstance(value, (list, dict, tuple, set)):
        return "array"
    if not isinstance(value, bool) and isinstance(value, (int, float)):
        return "numeric"
    return "string"


def _measure(value: Any, kind: str) -> float | None:
    """The number a size rule compares — length, count, numeric value, or KB."""
    if kind == "numeric":
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if kind == "array":
        try:
            return float(len(value))
        except TypeError:
            return None
    if kind == "file":
        size = getattr(value, "size", None)
        if size is None:
            return None
        try:
            return float(size) / 1024.0
        except (TypeError, ValueError):
            return None
    try:
        return float(len(str(value)))
    except TypeError:  # pragma: no cover - str() essentially never raises here
        return None


def _await_sync(coro: Any) -> Any:
    """Run a coroutine from sync ``passes()`` code, on or off an event loop."""
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


# --- date parsing -----------------------------------------------------------

_COMMON_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
)

_PHP_TO_STRPTIME = {
    "Y": "%Y",
    "y": "%y",
    "m": "%m",
    "n": "%m",
    "d": "%d",
    "j": "%d",
    "H": "%H",
    "G": "%H",
    "h": "%I",
    "g": "%I",
    "i": "%M",
    "s": "%S",
    "A": "%p",
    "a": "%p",
    "D": "%a",
    "l": "%A",
    "M": "%b",
    "F": "%B",
    "u": "%f",
    "T": "%Z",
    "e": "%Z",
    "P": "%z",
    "O": "%z",
}


def _php_date_format(php_format: str) -> str:
    """Translate a PHP ``DateTime`` format string into a ``strptime`` one."""
    out: list[str] = []
    for char in php_format:
        if char == "%":
            out.append("%%")
        else:
            out.append(_PHP_TO_STRPTIME.get(char, char))
    return "".join(out)


def _relative_date(text: str) -> datetime | None:
    key = text.strip().lower()
    now = datetime.now()
    if key == "now":
        return now
    if key == "today":
        return datetime.combine(now.date(), datetime.min.time())
    if key == "tomorrow":
        return datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
    if key == "yesterday":
        return datetime.combine(now.date() - timedelta(days=1), datetime.min.time())
    return None


def parse_date(value: Any) -> datetime | None:
    """Best-effort ``strtotime``-alike — ISO/common formats, then `dateutil` if present."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text = str(value).strip()
    if not text:
        return None
    relative = _relative_date(text)
    if relative is not None:
        return relative
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in _COMMON_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    if _dateutil_parser is not None:
        try:
            return _dateutil_parser.parse(text)
        except (ValueError, OverflowError, TypeError):
            return None
    return None


def _strip_tz(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def _parse_ratio(text: str) -> float:
    text = text.strip()
    if "/" in text:
        num, _, den = text.partition("/")
        try:
            return float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _read_file_bytes(value: Any) -> bytes | None:
    """Best-effort synchronous read of an uploaded file's bytes (for `dimensions`)."""
    raw = getattr(value, "raw", None)
    fileobj = getattr(raw, "file", None) if raw is not None else getattr(value, "file", None)
    if fileobj is not None:
        try:
            fileobj.seek(0)
            data = fileobj.read()
            fileobj.seek(0)
            return data
        except Exception:  # pragma: no cover - defensive
            return None
    reader = getattr(value, "read", None)
    if callable(reader):
        try:
            result = reader()
        except Exception:  # pragma: no cover - defensive
            return None
        if inspect.isawaitable(result):
            return None  # can't await from sync code — dimensions will pass through
        return result
    return None


# ============================================================================
# Marker rules — `bail`, `nullable`, `sometimes`, `exclude*`
#
# These never fail; the engine that walks a field's rule list reads intent
# off the plain attributes set in `__init__` (`is_bail`, `is_nullable`, ...).
# ============================================================================


class BailRule(RuleBase):
    name = "bail"

    def __init__(self, *parameters: str) -> None:
        self.is_bail = True

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return True


class NullableRule(RuleBase):
    name = "nullable"

    def __init__(self, *parameters: str) -> None:
        self.is_nullable = True

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return True


class SometimesRule(RuleBase):
    name = "sometimes"

    def __init__(self, *parameters: str) -> None:
        self.is_sometimes = True

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return True


class ExcludeRule(RuleBase):
    name = "exclude"

    def __init__(self, *parameters: str) -> None:
        self.exclude = True

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return True


class ExcludeIfRule(RuleBase):
    name = "exclude_if"

    def __init__(self, *parameters: str) -> None:
        other = parameters[0] if parameters else ""
        target = parameters[1] if len(parameters) > 1 else None
        self.exclude_if: tuple[str, str | None] = (other, target)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return True


class ExcludeUnlessRule(RuleBase):
    name = "exclude_unless"

    def __init__(self, *parameters: str) -> None:
        other = parameters[0] if parameters else ""
        target = parameters[1] if len(parameters) > 1 else None
        self.exclude_unless: tuple[str, str | None] = (other, target)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return True


class ExcludeWithRule(RuleBase):
    name = "exclude_with"

    def __init__(self, *parameters: str) -> None:
        self.exclude_with = parameters[0] if parameters else ""

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return True


class ExcludeWithoutRule(RuleBase):
    name = "exclude_without"

    def __init__(self, *parameters: str) -> None:
        self.exclude_without = parameters[0] if parameters else ""

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return True


# ============================================================================
# Presence / required family (implicit — they must run on blank/missing values)
# ============================================================================


class RequiredRule(RuleBase):
    name = "required"
    implicit = True

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return not _is_empty(value)


class FilledRule(RuleBase):
    name = "filled"
    implicit = True

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not _field_present(data, attribute):
            return True
        return not _is_empty(value)


class _ConditionalRequiredRule(RuleBase):
    """``required_if`` / ``required_unless`` shape: other field compared to values."""

    implicit = True
    negate = False  # True for *_unless (required unless other == one of values)

    def __init__(self, *parameters: str) -> None:
        self.other = parameters[0] if parameters else ""
        self.values = list(parameters[1:])

    def _triggered(self, data: Mapping[str, Any]) -> bool:
        other_value = data_get(data, self.other)
        matches = str(other_value) in self.values
        return (not matches) if self.negate else matches

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not self._triggered(data):
            return True
        return not _is_empty(value)

    def params(self) -> dict[str, Any]:
        return {"other": self.other, "value": ", ".join(self.values)}


class RequiredIfRule(_ConditionalRequiredRule):
    name = "required_if"


class RequiredUnlessRule(_ConditionalRequiredRule):
    name = "required_unless"
    negate = True


class _FieldSetRequiredRule(RuleBase):
    """``required_with(_all)`` / ``required_without(_all)`` shape."""

    implicit = True
    require_all = False
    when_present = True  # False for *_without(_all) — triggers when fields are *missing*

    def __init__(self, *parameters: str) -> None:
        self.fields = list(parameters)

    def _field_matches(self, data: Mapping[str, Any], field: str) -> bool:
        present = not _is_empty(data_get(data, field))
        return present if self.when_present else not present

    def _triggered(self, data: Mapping[str, Any]) -> bool:
        if not self.fields:
            return False
        checks = (self._field_matches(data, field) for field in self.fields)
        return all(checks) if self.require_all else any(checks)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not self._triggered(data):
            return True
        return not _is_empty(value)

    def params(self) -> dict[str, Any]:
        return {"values": ", ".join(self.fields)}


class RequiredWithRule(_FieldSetRequiredRule):
    name = "required_with"


class RequiredWithAllRule(_FieldSetRequiredRule):
    name = "required_with_all"
    require_all = True


class RequiredWithoutRule(_FieldSetRequiredRule):
    name = "required_without"
    when_present = False


class RequiredWithoutAllRule(_FieldSetRequiredRule):
    name = "required_without_all"
    require_all = True
    when_present = False


class _AcceptanceGatedRule(RuleBase):
    """``required_if_accepted`` / ``_declined``, ``prohibited_if_accepted`` / ``_declined``."""

    implicit = True
    accept_check: Callable[[Any], bool] = staticmethod(_is_accepted)
    prohibits = False  # True => must be *empty* when triggered, else must be filled

    def __init__(self, *parameters: str) -> None:
        self.fields = list(parameters)

    def _triggered(self, data: Mapping[str, Any]) -> bool:
        return any(self.accept_check(data_get(data, field)) for field in self.fields)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not self._triggered(data):
            return True
        return _is_empty(value) if self.prohibits else not _is_empty(value)

    def params(self) -> dict[str, Any]:
        return {"other": ", ".join(self.fields)}


class RequiredIfAcceptedRule(_AcceptanceGatedRule):
    name = "required_if_accepted"


class RequiredIfDeclinedRule(_AcceptanceGatedRule):
    name = "required_if_declined"
    accept_check = staticmethod(_is_declined)


class ProhibitedIfAcceptedRule(_AcceptanceGatedRule):
    name = "prohibited_if_accepted"
    prohibits = True


class ProhibitedIfDeclinedRule(_AcceptanceGatedRule):
    name = "prohibited_if_declined"
    accept_check = staticmethod(_is_declined)
    prohibits = True


class RequiredArrayKeysRule(RuleBase):
    name = "required_array_keys"
    implicit = True

    def __init__(self, *parameters: str) -> None:
        self.keys = list(parameters)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not isinstance(value, Mapping):
            return False
        return all(key in value for key in self.keys)

    def params(self) -> dict[str, Any]:
        return {"values": ", ".join(self.keys)}


class MissingRule(RuleBase):
    name = "missing"
    implicit = True

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return not _field_present(data, attribute)


class _ConditionalMissingRule(RuleBase):
    """``missing_if`` / ``missing_unless``."""

    implicit = True
    negate = False

    def __init__(self, *parameters: str) -> None:
        self.other = parameters[0] if parameters else ""
        self.values = list(parameters[1:])

    def _triggered(self, data: Mapping[str, Any]) -> bool:
        matches = str(data_get(data, self.other)) in self.values
        return (not matches) if self.negate else matches

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not self._triggered(data):
            return True
        return not _field_present(data, attribute)

    def params(self) -> dict[str, Any]:
        return {"other": self.other, "value": ", ".join(self.values)}


class MissingIfRule(_ConditionalMissingRule):
    name = "missing_if"


class MissingUnlessRule(_ConditionalMissingRule):
    name = "missing_unless"
    negate = True


class _FieldSetMissingRule(RuleBase):
    """``missing_with`` / ``missing_with_all``."""

    implicit = True
    require_all = False

    def __init__(self, *parameters: str) -> None:
        self.fields = list(parameters)

    def _triggered(self, data: Mapping[str, Any]) -> bool:
        if not self.fields:
            return False
        checks = (not _is_empty(data_get(data, field)) for field in self.fields)
        return all(checks) if self.require_all else any(checks)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not self._triggered(data):
            return True
        return not _field_present(data, attribute)

    def params(self) -> dict[str, Any]:
        return {"values": ", ".join(self.fields)}


class MissingWithRule(_FieldSetMissingRule):
    name = "missing_with"


class MissingWithAllRule(_FieldSetMissingRule):
    name = "missing_with_all"
    require_all = True


class PresentRule(RuleBase):
    name = "present"
    implicit = True

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return _field_present(data, attribute)


class _ConditionalPresentRule(RuleBase):
    """``present_if`` / ``present_unless``."""

    implicit = True
    negate = False

    def __init__(self, *parameters: str) -> None:
        self.other = parameters[0] if parameters else ""
        self.values = list(parameters[1:])

    def _triggered(self, data: Mapping[str, Any]) -> bool:
        matches = str(data_get(data, self.other)) in self.values
        return (not matches) if self.negate else matches

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not self._triggered(data):
            return True
        return _field_present(data, attribute)

    def params(self) -> dict[str, Any]:
        return {"other": self.other, "value": ", ".join(self.values)}


class PresentIfRule(_ConditionalPresentRule):
    name = "present_if"


class PresentUnlessRule(_ConditionalPresentRule):
    name = "present_unless"
    negate = True


class _FieldSetPresentRule(RuleBase):
    """``present_with`` / ``present_with_all``."""

    implicit = True
    require_all = False

    def __init__(self, *parameters: str) -> None:
        self.fields = list(parameters)

    def _triggered(self, data: Mapping[str, Any]) -> bool:
        if not self.fields:
            return False
        checks = (_field_present(data, field) for field in self.fields)
        return all(checks) if self.require_all else any(checks)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not self._triggered(data):
            return True
        return _field_present(data, attribute)

    def params(self) -> dict[str, Any]:
        return {"values": ", ".join(self.fields)}


class PresentWithRule(_FieldSetPresentRule):
    name = "present_with"


class PresentWithAllRule(_FieldSetPresentRule):
    name = "present_with_all"
    require_all = True


class AcceptedRule(RuleBase):
    name = "accepted"
    implicit = True

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return _is_accepted(value)


class DeclinedRule(RuleBase):
    name = "declined"
    implicit = True

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return _is_declined(value)


class _ConditionalAcceptRule(RuleBase):
    """``accepted_if`` / ``declined_if``."""

    implicit = True
    check: Callable[[Any], bool] = staticmethod(_is_accepted)

    def __init__(self, *parameters: str) -> None:
        self.other = parameters[0] if parameters else ""
        self.values = list(parameters[1:])

    def _triggered(self, data: Mapping[str, Any]) -> bool:
        return str(data_get(data, self.other)) in self.values

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not self._triggered(data):
            return True
        return self.check(value)

    def params(self) -> dict[str, Any]:
        return {"other": self.other, "value": ", ".join(self.values)}


class AcceptedIfRule(_ConditionalAcceptRule):
    name = "accepted_if"


class DeclinedIfRule(_ConditionalAcceptRule):
    name = "declined_if"
    check = staticmethod(_is_declined)


class ProhibitedRule(RuleBase):
    name = "prohibited"
    implicit = True

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return _is_empty(value)


class _ConditionalProhibitedRule(RuleBase):
    """``prohibited_if`` / ``prohibited_unless``."""

    implicit = True
    negate = False

    def __init__(self, *parameters: str) -> None:
        self.other = parameters[0] if parameters else ""
        self.values = list(parameters[1:])

    def _triggered(self, data: Mapping[str, Any]) -> bool:
        matches = str(data_get(data, self.other)) in self.values
        return (not matches) if self.negate else matches

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not self._triggered(data):
            return True
        return _is_empty(value)

    def params(self) -> dict[str, Any]:
        return {"other": self.other, "value": ", ".join(self.values)}


class ProhibitedIfRule(_ConditionalProhibitedRule):
    name = "prohibited_if"


class ProhibitedUnlessRule(_ConditionalProhibitedRule):
    name = "prohibited_unless"
    negate = True


class ProhibitsRule(RuleBase):
    name = "prohibits"
    implicit = True

    def __init__(self, *parameters: str) -> None:
        self.fields = list(parameters)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if _is_empty(value):
            return True
        return all(_is_empty(data_get(data, field)) for field in self.fields)

    def params(self) -> dict[str, Any]:
        return {"values": ", ".join(self.fields)}


class ConfirmedRule(RuleBase):
    name = "confirmed"

    def __init__(self, *parameters: str) -> None:
        self.field = parameters[0] if parameters else None

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        confirmation_field = self.field or f"{attribute}_confirmation"
        return data_get(data, confirmation_field) == value

    def params(self) -> dict[str, Any]:
        return {"other": self.field or ""}


# ============================================================================
# Comparisons against another field — `same`, `different`
# ============================================================================


class SameRule(RuleBase):
    name = "same"

    def __init__(self, *parameters: str) -> None:
        self.other = parameters[0] if parameters else ""

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return data_get(data, self.other) == value

    def params(self) -> dict[str, Any]:
        return {"other": self.other}


class DifferentRule(RuleBase):
    name = "different"

    def __init__(self, *parameters: str) -> None:
        self.other = parameters[0] if parameters else ""

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return data_get(data, self.other) != value

    def params(self) -> dict[str, Any]:
        return {"other": self.other}


# ============================================================================
# Size rules — `min`, `max`, `between`, `size`, `gt`, `gte`, `lt`, `lte`
# ============================================================================


class MinRule(RuleBase):
    name = "min"

    def __init__(self, *parameters: str) -> None:
        self.min = parameters[0] if parameters else "0"

    def size_kind(self, value: Any) -> str:
        return detect_kind(value)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        measured = _measure(value, self.size_kind(value))
        if measured is None:
            return False
        try:
            return measured >= float(self.min)
        except ValueError:
            return False

    def params(self) -> dict[str, Any]:
        return {"min": self.min}


class MaxRule(RuleBase):
    name = "max"

    def __init__(self, *parameters: str) -> None:
        self.max = parameters[0] if parameters else "0"

    def size_kind(self, value: Any) -> str:
        return detect_kind(value)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        measured = _measure(value, self.size_kind(value))
        if measured is None:
            return False
        try:
            return measured <= float(self.max)
        except ValueError:
            return False

    def params(self) -> dict[str, Any]:
        return {"max": self.max}


class BetweenRule(RuleBase):
    name = "between"

    def __init__(self, *parameters: str) -> None:
        self.min = parameters[0] if parameters else "0"
        self.max = parameters[1] if len(parameters) > 1 else self.min

    def size_kind(self, value: Any) -> str:
        return detect_kind(value)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        measured = _measure(value, self.size_kind(value))
        if measured is None:
            return False
        try:
            return float(self.min) <= measured <= float(self.max)
        except ValueError:
            return False

    def params(self) -> dict[str, Any]:
        return {"min": self.min, "max": self.max}


class SizeRule(RuleBase):
    name = "size"

    def __init__(self, *parameters: str) -> None:
        self.size = parameters[0] if parameters else "0"

    def size_kind(self, value: Any) -> str:
        return detect_kind(value)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        measured = _measure(value, self.size_kind(value))
        if measured is None:
            return False
        try:
            return measured == float(self.size)
        except ValueError:
            return False

    def params(self) -> dict[str, Any]:
        return {"size": self.size}


class _CompareRule(RuleBase):
    """``gt`` / ``gte`` / ``lt`` / ``lte`` — against a literal or another field."""

    op: Callable[[float, float], bool] = staticmethod(operator.gt)

    def __init__(self, *parameters: str) -> None:
        self.other = parameters[0] if parameters else "0"

    def size_kind(self, value: Any) -> str:
        return detect_kind(value)

    def _other_measure(self, value: Any, data: Mapping[str, Any]) -> float | None:
        kind = self.size_kind(value)
        if _is_numeric_string(self.other) and kind != "file":
            try:
                return float(self.other)
            except ValueError:
                return None
        other_value = data_get(data, self.other)
        return _measure(other_value, kind)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        own = _measure(value, self.size_kind(value))
        other = self._other_measure(value, data)
        if own is None or other is None:
            return False
        return self.op(own, other)

    def params(self) -> dict[str, Any]:
        return {"value": self.other}


class GtRule(_CompareRule):
    name = "gt"
    op = staticmethod(operator.gt)


class GteRule(_CompareRule):
    name = "gte"
    op = staticmethod(operator.ge)


class LtRule(_CompareRule):
    name = "lt"
    op = staticmethod(operator.lt)


class LteRule(_CompareRule):
    name = "lte"
    op = staticmethod(operator.le)


# ============================================================================
# Digits / numeric shape
# ============================================================================


class DigitsRule(RuleBase):
    name = "digits"

    def __init__(self, *parameters: str) -> None:
        self.length = parameters[0] if parameters else "0"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        text = str(value)
        try:
            return text.isdigit() and len(text) == int(self.length)
        except ValueError:
            return False

    def params(self) -> dict[str, Any]:
        return {"digits": self.length}


class DigitsBetweenRule(RuleBase):
    name = "digits_between"

    def __init__(self, *parameters: str) -> None:
        self.min = parameters[0] if parameters else "0"
        self.max = parameters[1] if len(parameters) > 1 else self.min

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        text = str(value)
        if not text.isdigit():
            return False
        try:
            return int(self.min) <= len(text) <= int(self.max)
        except ValueError:
            return False

    def params(self) -> dict[str, Any]:
        return {"min": self.min, "max": self.max}


class MinDigitsRule(RuleBase):
    name = "min_digits"

    def __init__(self, *parameters: str) -> None:
        self.min = parameters[0] if parameters else "0"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        text = str(value)
        try:
            return text.isdigit() and len(text) >= int(self.min)
        except ValueError:
            return False

    def params(self) -> dict[str, Any]:
        return {"min": self.min}


class MaxDigitsRule(RuleBase):
    name = "max_digits"

    def __init__(self, *parameters: str) -> None:
        self.max = parameters[0] if parameters else "0"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        text = str(value)
        try:
            return text.isdigit() and len(text) <= int(self.max)
        except ValueError:
            return False

    def params(self) -> dict[str, Any]:
        return {"max": self.max}


class MultipleOfRule(RuleBase):
    name = "multiple_of"

    def __init__(self, *parameters: str) -> None:
        self.value = parameters[0] if parameters else "1"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        try:
            number = Decimal(str(value))
            factor = Decimal(str(self.value))
        except InvalidOperation:
            return False
        if factor == 0:
            return False
        return (number % factor) == 0

    def params(self) -> dict[str, Any]:
        return {"value": self.value}


class DecimalRule(RuleBase):
    name = "decimal"

    def __init__(self, *parameters: str) -> None:
        self.min = parameters[0] if parameters else "0"
        self.max = parameters[1] if len(parameters) > 1 else self.min

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        text = str(value)
        if not re.fullmatch(r"-?\d+(\.\d+)?", text):
            return False
        places = len(text.split(".", 1)[1]) if "." in text else 0
        try:
            return int(self.min) <= places <= int(self.max)
        except ValueError:
            return False

    def params(self) -> dict[str, Any]:
        return {"min": self.min, "max": self.max}


# ============================================================================
# Type rules
# ============================================================================


class StringRule(RuleBase):
    name = "string"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return isinstance(value, str)


class NumericRule(RuleBase):
    name = "numeric"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return True
        return _is_numeric_string(str(value))


class IntegerRule(RuleBase):
    name = "integer"

    def __init__(self, *parameters: str) -> None:
        self.strict = "strict" in parameters

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return True
        if self.strict:
            return False
        return bool(re.fullmatch(r"[+-]?\d+", str(value).strip()))


class BooleanRule(RuleBase):
    name = "boolean"

    def __init__(self, *parameters: str) -> None:
        self.strict = "strict" in parameters

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if isinstance(value, bool):
            return True
        if self.strict:
            return False
        return value in (0, 1, "0", "1")


class ArrayRule(RuleBase):
    name = "array"

    def __init__(self, *parameters: str) -> None:
        self.allowed_keys = list(parameters)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not isinstance(value, (list, dict)):
            return False
        if self.allowed_keys and isinstance(value, dict):
            return all(key in self.allowed_keys for key in value)
        return True

    def params(self) -> dict[str, Any]:
        return {"values": ", ".join(self.allowed_keys)}


class ListRule(RuleBase):
    name = "list"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return isinstance(value, list)


class JsonRule(RuleBase):
    name = "json"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if isinstance(value, (dict, list)):
            return True
        try:
            json.loads(value)
        except (TypeError, ValueError):
            return False
        return True


class AsciiRule(RuleBase):
    name = "ascii"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return all(ord(char) < 128 for char in str(value))


class LowercaseRule(RuleBase):
    name = "lowercase"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        text = str(value)
        return text == text.lower()


class UppercaseRule(RuleBase):
    name = "uppercase"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        text = str(value)
        return text == text.upper()


class _AlphaFamilyRule(RuleBase):
    _pattern_unicode: str
    _pattern_ascii: str

    def __init__(self, *parameters: str) -> None:
        self.ascii_only = "ascii" in parameters

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        text = str(value)
        if not text:
            return False
        pattern = self._pattern_ascii if self.ascii_only else self._pattern_unicode
        return bool(re.fullmatch(pattern, text))


class AlphaRule(_AlphaFamilyRule):
    name = "alpha"
    _pattern_unicode = r"[^\W\d_]+"
    _pattern_ascii = r"[A-Za-z]+"


class AlphaDashRule(_AlphaFamilyRule):
    name = "alpha_dash"
    _pattern_unicode = r"[\w-]+"
    _pattern_ascii = r"[A-Za-z0-9_-]+"


class AlphaNumRule(_AlphaFamilyRule):
    name = "alpha_num"
    _pattern_unicode = r"[^\W_]+"
    _pattern_ascii = r"[A-Za-z0-9]+"


_HEX_COLOR_RE = re.compile(r"^#?(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")


class HexColorRule(RuleBase):
    name = "hex_color"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return bool(_HEX_COLOR_RE.match(str(value)))


_MAC_ADDRESS_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")


class MacAddressRule(RuleBase):
    name = "mac_address"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return bool(_MAC_ADDRESS_RE.match(str(value)))


class _AffixRule(RuleBase):
    """``starts_with`` / ``ends_with`` / ``doesnt_start_with`` / ``doesnt_end_with``."""

    negate = False

    def __init__(self, *parameters: str) -> None:
        self.values = list(parameters)

    def _matches(self, text: str, prefix_or_suffix: str) -> bool:
        raise NotImplementedError

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        text = str(value)
        matched = any(self._matches(text, item) for item in self.values)
        return (not matched) if self.negate else matched

    def params(self) -> dict[str, Any]:
        return {"values": ", ".join(self.values)}


class StartsWithRule(_AffixRule):
    name = "starts_with"

    def _matches(self, text: str, prefix_or_suffix: str) -> bool:
        return text.startswith(prefix_or_suffix)


class EndsWithRule(_AffixRule):
    name = "ends_with"

    def _matches(self, text: str, prefix_or_suffix: str) -> bool:
        return text.endswith(prefix_or_suffix)


class DoesntStartWithRule(StartsWithRule):
    name = "doesnt_start_with"
    negate = True


class DoesntEndWithRule(EndsWithRule):
    name = "doesnt_end_with"
    negate = True


class _ArrayMembershipRule(RuleBase):
    """``contains`` / ``doesnt_contain``."""

    require_all = True
    negate = False

    def __init__(self, *parameters: str) -> None:
        self.values = list(parameters)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not isinstance(value, (list, tuple, set)):
            return False
        checks = (item in value for item in self.values)
        matched = all(checks) if self.require_all else any(checks)
        return (not matched) if self.negate else matched

    def params(self) -> dict[str, Any]:
        return {"values": ", ".join(self.values)}


class ContainsRule(_ArrayMembershipRule):
    name = "contains"


class DoesntContainRule(_ArrayMembershipRule):
    name = "doesnt_contain"
    require_all = False
    negate = True


class DistinctRule(RuleBase):
    name = "distinct"

    def __init__(self, *parameters: str) -> None:
        self.ignore_case = "ignore_case" in parameters

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not isinstance(value, (list, tuple)):
            return True
        seen: list[Any] = []
        for item in value:
            key = item.lower() if self.ignore_case and isinstance(item, str) else item
            if key in seen:
                return False
            seen.append(key)
        return True


class InArrayRule(RuleBase):
    name = "in_array"

    def __init__(self, *parameters: str) -> None:
        self.other = parameters[0] if parameters else ""

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        key = self.other[:-2] if self.other.endswith(".*") else self.other
        other_value = data_get(data, key)
        if isinstance(other_value, Mapping):
            other_value = list(other_value.values())
        if not isinstance(other_value, (list, tuple, set)):
            return False
        return value in other_value

    def params(self) -> dict[str, Any]:
        return {"other": self.other}


class InArrayKeysRule(RuleBase):
    name = "in_array_keys"

    def __init__(self, *parameters: str) -> None:
        self.keys = list(parameters)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not isinstance(value, Mapping):
            return False
        if not self.keys:
            return True
        return any(key in value for key in self.keys)

    def params(self) -> dict[str, Any]:
        return {"values": ", ".join(self.keys)}


class InRule(RuleBase):
    name = "in"

    def __init__(self, *parameters: str) -> None:
        self.values = list(parameters)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return str(value) in self.values or value in self.values

    def params(self) -> dict[str, Any]:
        return {"values": ", ".join(self.values)}


class NotInRule(InRule):
    name = "not_in"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return not super().passes(attribute, value, data)


class EnumRule(RuleBase):
    name = "enum"

    def __init__(self, *parameters: str) -> None:
        self.values = list(parameters)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not self.values:
            return True
        candidate = getattr(value, "value", getattr(value, "name", value))
        return str(candidate) in self.values or value in self.values

    def params(self) -> dict[str, Any]:
        return {"values": ", ".join(self.values)}


def _split_regex_flags(raw: str) -> tuple[str, int]:
    """Strip Laravel/PHP ``/pattern/flags`` delimiters, if present."""
    if len(raw) >= 2 and raw[0] == "/":
        end = raw.rfind("/")
        if end > 0:
            body, mods = raw[1:end], raw[end + 1 :]
            flags = 0
            if "i" in mods:
                flags |= re.IGNORECASE
            if "m" in mods:
                flags |= re.MULTILINE
            if "s" in mods:
                flags |= re.DOTALL
            return body, flags
    return raw, 0


class RegexRule(RuleBase):
    name = "regex"
    negate = False

    def __init__(self, *parameters: str) -> None:
        raw = ",".join(parameters)
        self.pattern, self.flags = _split_regex_flags(raw)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        try:
            matched = re.search(self.pattern, str(value), self.flags) is not None
        except re.error:
            return False
        return (not matched) if self.negate else matched

    def params(self) -> dict[str, Any]:
        return {"regex": self.pattern}


class NotRegexRule(RegexRule):
    name = "not_regex"
    negate = True


# ============================================================================
# Format rules — email, url, uuid, ulid, ip, timezone, encoding
# ============================================================================

_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


class EmailRule(RuleBase):
    name = "email"

    def __init__(self, *parameters: str) -> None:
        self.modes = set(parameters)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        text = str(value)
        if not _EMAIL_RE.match(text):
            return False
        if "dns" in self.modes:
            domain = text.rsplit("@", 1)[-1]
            try:
                socket.getaddrinfo(domain, None)
            except (socket.gaierror, UnicodeError):
                return False
        return True


class UrlRule(RuleBase):
    name = "url"

    def __init__(self, *parameters: str) -> None:
        self.schemes = [p.lower() for p in parameters]

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        text = str(value)
        try:
            parsed = urlparse(text)
        except ValueError:
            return False
        if not parsed.scheme or not (parsed.netloc or parsed.path):
            return False
        if self.schemes and parsed.scheme.lower() not in self.schemes:
            return False
        return True


class ActiveUrlRule(RuleBase):
    name = "active_url"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        host = urlparse(str(value)).hostname or str(value)
        try:
            socket.getaddrinfo(host, None)
        except (socket.gaierror, UnicodeError):
            return False
        return True


_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class UuidRule(RuleBase):
    name = "uuid"

    def __init__(self, *parameters: str) -> None:
        self.version = parameters[0] if parameters else None

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        text = str(value)
        if not _UUID_RE.match(text):
            return False
        if self.version:
            import uuid as uuid_module

            try:
                parsed = uuid_module.UUID(text)
            except ValueError:
                return False
            return str(parsed.version) == str(self.version)
        return True


_ULID_RE = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Za-hjkmnp-tv-z]{25}$")


class UlidRule(RuleBase):
    name = "ulid"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return bool(_ULID_RE.match(str(value)))


class IpRule(RuleBase):
    name = "ip"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        try:
            ipaddress.ip_address(str(value))
        except ValueError:
            return False
        return True


class Ipv4Rule(RuleBase):
    name = "ipv4"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        try:
            ipaddress.IPv4Address(str(value))
        except ValueError:
            return False
        return True


class Ipv6Rule(RuleBase):
    name = "ipv6"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        try:
            ipaddress.IPv6Address(str(value))
        except ValueError:
            return False
        return True


class TimezoneRule(RuleBase):
    name = "timezone"

    def __init__(self, *parameters: str) -> None:
        self.group = parameters[0] if parameters else None

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if _available_timezones is None:  # pragma: no cover - py<3.9
            return True
        names = _available_timezones()
        text = str(value)
        if self.group and self.group not in {"all", "per_country"}:
            return text in names and text.startswith(f"{self.group}/")
        return text in names


class EncodingRule(RuleBase):
    name = "encoding"

    def __init__(self, *parameters: str) -> None:
        self.encoding = parameters[0] if parameters else "utf-8"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        try:
            if isinstance(value, (bytes, bytearray)):
                value.decode(self.encoding)
            else:
                str(value).encode(self.encoding)
        except (LookupError, UnicodeDecodeError, UnicodeEncodeError):
            return False
        return True


# ============================================================================
# Date rules
# ============================================================================


class DateRule(RuleBase):
    name = "date"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return parse_date(value) is not None


class DateFormatRule(RuleBase):
    name = "date_format"

    def __init__(self, *parameters: str) -> None:
        self.formats = list(parameters) or ["Y-m-d"]

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        text = str(value)
        for php_format in self.formats:
            try:
                datetime.strptime(text, _php_date_format(php_format))
                return True
            except ValueError:
                continue
        return False

    def params(self) -> dict[str, Any]:
        return {"format": ", ".join(self.formats)}


class _DateCompareRule(RuleBase):
    """``after`` / ``after_or_equal`` / ``before`` / ``before_or_equal`` / ``date_equals``."""

    op: Callable[[datetime, datetime], bool] = staticmethod(operator.gt)

    def __init__(self, *parameters: str) -> None:
        self.other = parameters[0] if parameters else ""

    def _target(self, data: Mapping[str, Any]) -> datetime | None:
        if _field_present(data, self.other):
            return parse_date(data_get(data, self.other))
        return parse_date(self.other)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        own = parse_date(value)
        target = self._target(data)
        if own is None or target is None:
            return False
        try:
            return self.op(_strip_tz(own), _strip_tz(target))
        except TypeError:  # pragma: no cover - defensive
            return False

    def params(self) -> dict[str, Any]:
        return {"date": self.other}


class AfterRule(_DateCompareRule):
    name = "after"
    op = staticmethod(operator.gt)


class AfterOrEqualRule(_DateCompareRule):
    name = "after_or_equal"
    op = staticmethod(operator.ge)


class BeforeRule(_DateCompareRule):
    name = "before"
    op = staticmethod(operator.lt)


class BeforeOrEqualRule(_DateCompareRule):
    name = "before_or_equal"
    op = staticmethod(operator.le)


class DateEqualsRule(_DateCompareRule):
    name = "date_equals"
    op = staticmethod(operator.eq)


# ============================================================================
# File rules
# ============================================================================


class FileRule(RuleBase):
    name = "file"

    def size_kind(self, value: Any) -> str:
        return detect_kind(value)

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        return _looks_like_file(value) and bool(_filename_of(value))


_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "bmp", "gif", "webp"}


class ImageRule(RuleBase):
    name = "image"

    def __init__(self, *parameters: str) -> None:
        self.allow_svg = "allow_svg" in parameters

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not _looks_like_file(value):
            return False
        content_type = (getattr(value, "content_type", None) or "").lower()
        if content_type == "image/svg+xml":
            return self.allow_svg
        if content_type.startswith("image/"):
            return True
        ext = _file_extension(value)
        allowed = _IMAGE_EXTENSIONS | ({"svg"} if self.allow_svg else set())
        return ext in allowed


class ExtensionsRule(RuleBase):
    name = "extensions"

    def __init__(self, *parameters: str) -> None:
        self.extensions = {p.lower().lstrip(".") for p in parameters}

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not _looks_like_file(value):
            return False
        return _file_extension(value) in self.extensions

    def params(self) -> dict[str, Any]:
        return {"values": ", ".join(sorted(self.extensions))}


class MimesRule(ExtensionsRule):
    """Laravel guesses MIME from content, but almasix approximates via extension."""

    name = "mimes"


class MimetypesRule(RuleBase):
    name = "mimetypes"

    def __init__(self, *parameters: str) -> None:
        self.patterns = [p.lower() for p in parameters]

    def _content_type(self, value: Any) -> str:
        content_type = (getattr(value, "content_type", None) or "").lower()
        if content_type:
            return content_type
        guessed, _ = mimetypes.guess_type(_filename_of(value) or "")
        return (guessed or "").lower()

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not _looks_like_file(value):
            return False
        content_type = self._content_type(value)
        for pattern in self.patterns:
            if pattern.endswith("/*"):
                if content_type.startswith(pattern[:-1]):
                    return True
            elif content_type == pattern:
                return True
        return False

    def params(self) -> dict[str, Any]:
        return {"values": ", ".join(self.patterns)}


_DIMENSION_KEYS = (
    "width",
    "height",
    "min_width",
    "max_width",
    "min_height",
    "max_height",
    "ratio",
    "min_ratio",
    "max_ratio",
)


class DimensionsRule(RuleBase):
    name = "dimensions"

    def __init__(self, *parameters: str) -> None:
        self.constraints: dict[str, str] = {}
        for part in parameters:
            if "=" in part:
                key, _, val = part.partition("=")
                key = key.strip()
                if key in _DIMENSION_KEYS:
                    self.constraints[key] = val.strip()

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not _looks_like_file(value):
            return False
        if _PILImage is None or not self.constraints:
            return True  # no way (or nothing) to verify — don't block validation
        raw_bytes = _read_file_bytes(value)
        if not raw_bytes:
            return True
        try:
            with _PILImage.open(io.BytesIO(raw_bytes)) as image:
                width, height = image.size
        except Exception:
            return False
        checks = self.constraints
        if "width" in checks and width != int(checks["width"]):
            return False
        if "height" in checks and height != int(checks["height"]):
            return False
        if "min_width" in checks and width < int(checks["min_width"]):
            return False
        if "max_width" in checks and width > int(checks["max_width"]):
            return False
        if "min_height" in checks and height < int(checks["min_height"]):
            return False
        if "max_height" in checks and height > int(checks["max_height"]):
            return False
        if height:
            actual_ratio = width / height
            if "ratio" in checks and abs(actual_ratio - _parse_ratio(checks["ratio"])) > 1e-3:
                return False
            if "min_ratio" in checks and actual_ratio < _parse_ratio(checks["min_ratio"]):
                return False
            if "max_ratio" in checks and actual_ratio > _parse_ratio(checks["max_ratio"]):
                return False
        return True

    def params(self) -> dict[str, Any]:
        return dict(self.constraints)


# ============================================================================
# Database rules — `exists`, `unique`
# ============================================================================


class ExistsRule(RuleBase):
    name = "exists"

    def __init__(self, *parameters: str) -> None:
        self.table = parameters[0] if parameters else ""
        self.column = parameters[1] if len(parameters) > 1 else None

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if is_blank(value) or not self.table:
            return True
        column = self.column or attribute
        try:
            return bool(self.query_exists(self.table, column, value))
        except Exception:
            # No database configured (or the driver rejected the query) —
            # skip rather than fail a rule that has nothing to check against.
            return True

    def query_exists(self, table: str, column: str, value: Any) -> bool:
        """Row lookup hook — override in tests/subclasses for a fake backend."""
        from almasix.orm.facade import DB

        async def _check() -> bool:
            return bool(await DB.table(table).where(column, value).exists())

        return bool(_await_sync(_check()))

    def params(self) -> dict[str, Any]:
        return {"other": self.table}


class UniqueRule(RuleBase):
    name = "unique"

    def __init__(self, *parameters: str) -> None:
        self.table = parameters[0] if parameters else ""
        self.column = parameters[1] if len(parameters) > 1 else None
        self.ignore_value = parameters[2] if len(parameters) > 2 else None
        self.ignore_column = parameters[3] if len(parameters) > 3 else "id"

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if is_blank(value) or not self.table:
            return True
        column = self.column or attribute
        try:
            return not bool(self.query_exists(self.table, column, value))
        except Exception:
            return True

    def query_exists(self, table: str, column: str, value: Any) -> bool:
        """Row lookup hook — override in tests/subclasses for a fake backend."""
        from almasix.orm.facade import DB

        async def _check() -> bool:
            query = DB.table(table).where(column, value)
            if self.ignore_value is not None:
                query = query.where(self.ignore_column, "!=", self.ignore_value)
            return bool(await query.exists())

        return bool(_await_sync(_check()))

    def params(self) -> dict[str, Any]:
        return {"other": self.table}


# ============================================================================
# Auth rule — `current_password`
# ============================================================================


def _password_of(user: Any) -> str | None:
    if isinstance(user, Mapping):
        return user.get("password")
    if hasattr(user, "get_attribute"):
        try:
            return user.get_attribute("password")
        except Exception:  # pragma: no cover - defensive
            pass
    return getattr(user, "password", None)


class CurrentPasswordRule(RuleBase):
    name = "current_password"

    def __init__(self, *parameters: str) -> None:
        self.guard = parameters[0] if parameters else None

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        try:
            from almasix.auth.guard import get_auth
            from almasix.hashing import Hash
        except Exception:  # pragma: no cover - defensive against import cycles
            return True
        manager = get_auth()
        if manager is None:
            return True
        user = manager.guard(self.guard).user() if self.guard else manager.user()
        if user is None:
            return False
        hashed = _password_of(user)
        if not hashed:
            return False
        try:
            return Hash.check(str(value), hashed)
        except Exception:
            return False


# ============================================================================
# `Rule::anyOf` — evaluate each ruleset with the parser, pass if any fully pass
# ============================================================================


class AnyOfRule(RuleBase):
    name = "any_of"

    def __init__(self, *parameters: str) -> None:
        self.is_any_of = True
        self.rulesets: list[str] = [p for p in parameters if p]

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        if not self.rulesets:
            return True
        from almasix.validation.parser import parse_rule_string

        for expression in self.rulesets:
            try:
                candidates: list[str]
                try:
                    parsed = json.loads(expression)
                    candidates = (
                        [str(item) for item in parsed] if isinstance(parsed, list) else [expression]
                    )
                except (TypeError, ValueError):
                    candidates = [expression]
                rules = [rule for expr in candidates for rule in parse_rule_string(expr)]
            except ValueError:
                continue
            if rules and all(rule.passes(attribute, value, data) for rule in rules):
                return True
        return False


# ============================================================================
# Registration
# ============================================================================

_RULE_CLASSES: dict[str, type[RuleBase]] = {
    "accepted": AcceptedRule,
    "accepted_if": AcceptedIfRule,
    "active_url": ActiveUrlRule,
    "after": AfterRule,
    "after_or_equal": AfterOrEqualRule,
    "alpha": AlphaRule,
    "alpha_dash": AlphaDashRule,
    "alpha_num": AlphaNumRule,
    "any_of": AnyOfRule,
    "array": ArrayRule,
    "ascii": AsciiRule,
    "bail": BailRule,
    "before": BeforeRule,
    "before_or_equal": BeforeOrEqualRule,
    "between": BetweenRule,
    "boolean": BooleanRule,
    "confirmed": ConfirmedRule,
    "contains": ContainsRule,
    "current_password": CurrentPasswordRule,
    "date": DateRule,
    "date_equals": DateEqualsRule,
    "date_format": DateFormatRule,
    "decimal": DecimalRule,
    "declined": DeclinedRule,
    "declined_if": DeclinedIfRule,
    "different": DifferentRule,
    "digits": DigitsRule,
    "digits_between": DigitsBetweenRule,
    "dimensions": DimensionsRule,
    "distinct": DistinctRule,
    "doesnt_contain": DoesntContainRule,
    "doesnt_end_with": DoesntEndWithRule,
    "doesnt_start_with": DoesntStartWithRule,
    "email": EmailRule,
    "encoding": EncodingRule,
    "ends_with": EndsWithRule,
    "enum": EnumRule,
    "exclude": ExcludeRule,
    "exclude_if": ExcludeIfRule,
    "exclude_unless": ExcludeUnlessRule,
    "exclude_with": ExcludeWithRule,
    "exclude_without": ExcludeWithoutRule,
    "exists": ExistsRule,
    "extensions": ExtensionsRule,
    "file": FileRule,
    "filled": FilledRule,
    "gt": GtRule,
    "gte": GteRule,
    "hex_color": HexColorRule,
    "image": ImageRule,
    "in": InRule,
    "in_array": InArrayRule,
    "in_array_keys": InArrayKeysRule,
    "integer": IntegerRule,
    "ip": IpRule,
    "ipv4": Ipv4Rule,
    "ipv6": Ipv6Rule,
    "json": JsonRule,
    "list": ListRule,
    "lowercase": LowercaseRule,
    "lt": LtRule,
    "lte": LteRule,
    "mac_address": MacAddressRule,
    "max": MaxRule,
    "max_digits": MaxDigitsRule,
    "mimes": MimesRule,
    "mimetypes": MimetypesRule,
    "min": MinRule,
    "min_digits": MinDigitsRule,
    "missing": MissingRule,
    "missing_if": MissingIfRule,
    "missing_unless": MissingUnlessRule,
    "missing_with": MissingWithRule,
    "missing_with_all": MissingWithAllRule,
    "multiple_of": MultipleOfRule,
    "not_in": NotInRule,
    "not_regex": NotRegexRule,
    "nullable": NullableRule,
    "numeric": NumericRule,
    "present": PresentRule,
    "present_if": PresentIfRule,
    "present_unless": PresentUnlessRule,
    "present_with": PresentWithRule,
    "present_with_all": PresentWithAllRule,
    "prohibited": ProhibitedRule,
    "prohibited_if": ProhibitedIfRule,
    "prohibited_if_accepted": ProhibitedIfAcceptedRule,
    "prohibited_if_declined": ProhibitedIfDeclinedRule,
    "prohibited_unless": ProhibitedUnlessRule,
    "prohibits": ProhibitsRule,
    "regex": RegexRule,
    "required": RequiredRule,
    "required_array_keys": RequiredArrayKeysRule,
    "required_if": RequiredIfRule,
    "required_if_accepted": RequiredIfAcceptedRule,
    "required_if_declined": RequiredIfDeclinedRule,
    "required_unless": RequiredUnlessRule,
    "required_with": RequiredWithRule,
    "required_with_all": RequiredWithAllRule,
    "required_without": RequiredWithoutRule,
    "required_without_all": RequiredWithoutAllRule,
    "same": SameRule,
    "size": SizeRule,
    "sometimes": SometimesRule,
    "starts_with": StartsWithRule,
    "string": StringRule,
    "timezone": TimezoneRule,
    "ulid": UlidRule,
    "unique": UniqueRule,
    "uppercase": UppercaseRule,
    "url": UrlRule,
    "uuid": UuidRule,
}


def register_all() -> None:
    """Register every :data:`LARAVEL_RULES` name — raises if this file drifts from it."""
    missing = sorted(set(LARAVEL_RULES) - set(_RULE_CLASSES))
    if missing:
        raise RuntimeError(f"almasix.validation.rules.builtins is missing rules: {missing}")
    extra = sorted(set(_RULE_CLASSES) - set(LARAVEL_RULES))
    if extra:  # pragma: no cover - defensive against a stale registry list
        raise RuntimeError(f"almasix.validation.rules.builtins has unknown rules: {extra}")
    for rule_name, factory in _RULE_CLASSES.items():
        register(rule_name, factory)


register_all()


__all__ = ["register_all"]
