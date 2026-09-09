"""Attribute casting — Laravel `$casts` / `casts()` parity.

Casts may be declared as strings (``"int"``, ``"decimal:2"``, ``"encrypted:array"``),
an ``Enum`` subclass, a :class:`CastsAttributes` class or instance, or any class
exposing ``cast_using()`` (Laravel's ``Castable``).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any

_TRUE = {"1", "true", "t", "yes", "on"}

_JSON_CASTS = {"json", "array", "dict", "object", "collection"}
# Python's date/datetime are already immutable, so Laravel's immutable_* casts
# are aliases here rather than a separate type. Documented as a deviation.
_DATETIME_CASTS = {"datetime", "immutable_datetime"}
_DATE_CASTS = {"date", "immutable_date"}
# One-way casts: the write half runs, the read half cannot undo it.
_WRITE_ONLY = {"encrypted", "hashed"}


class CastError(ValueError):
    """Raised when a value cannot be cast to the declared type."""


class CastsAttributes:
    """Base class for custom casts — Laravel's ``CastsAttributes``.

    Subclasses implement :meth:`get` to transform a stored value on read and
    :meth:`set` to transform it on write. ``set`` may return a mapping to write
    several columns at once.
    """

    def get(self, model: Any, key: str, value: Any, attributes: Mapping[str, Any]) -> Any:
        raise NotImplementedError

    def set(
        self, model: Any, key: str, value: Any, attributes: Mapping[str, Any]
    ) -> Any | Mapping[str, Any]:
        raise NotImplementedError


class CastsInboundAttributes(CastsAttributes):
    """A write-only cast — reads pass the stored value through untouched."""

    def get(self, model: Any, key: str, value: Any, attributes: Mapping[str, Any]) -> Any:
        return value


def resolve_cast(cast: Any) -> Any:
    """Normalize a cast declaration into something the pipeline can use."""
    if isinstance(cast, CastsAttributes):
        return cast
    if isinstance(cast, type):
        if issubclass(cast, CastsAttributes):
            return cast()
        if issubclass(cast, Enum):
            return cast
        cast_using = getattr(cast, "cast_using", None)
        if callable(cast_using):
            resolved = cast_using()
            if isinstance(resolved, type) and issubclass(resolved, CastsAttributes):
                return resolved()
            return resolved
    return cast


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, tz=UTC).replace(tzinfo=None)
    text = str(value)
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise CastError(f"Cannot cast {value!r} to datetime") from exc


def _split(cast: Any) -> tuple[str, str]:
    base, _, parameter = str(cast).partition(":")
    return base.strip().lower(), parameter


def cast_format(cast: Any) -> str | None:
    """The serialization format declared on a date cast, if any."""
    if isinstance(cast, (CastsAttributes, type)):
        return None
    base, parameter = _split(cast)
    if base in _DATETIME_CASTS or base in _DATE_CASTS:
        return parameter or None
    return None


def _crypt() -> Any:
    from almasix.encryption.facade import Crypt

    return Crypt


def _hash() -> Any:
    from almasix.hashing import Hash

    return Hash


def cast_value(value: Any, cast: Any) -> Any:
    """Cast a raw database value into its declared Python type."""
    if value is None:
        return None

    cast = resolve_cast(cast)

    if isinstance(cast, CastsAttributes):
        return value  # class casts are applied by the model, which has context

    if isinstance(cast, type) and issubclass(cast, Enum):
        return cast(value)

    base, parameter = _split(cast)

    if base in {"int", "integer"}:
        return int(value)
    if base in {"float", "double", "real"}:
        return float(value)
    if base in {"str", "string"}:
        return str(value)
    if base in {"bool", "boolean"}:
        if isinstance(value, str):
            return value.strip().lower() in _TRUE
        return bool(value)
    if base == "decimal":
        quantized = Decimal(str(value))
        if parameter:
            exponent = Decimal(1).scaleb(-int(parameter))
            return quantized.quantize(exponent)
        return quantized
    if base in _JSON_CASTS:
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError) as exc:
            raise CastError(f"Cannot cast {value!r} to {base}") from exc
    if base == "encrypted":
        return _decrypt(value, parameter)
    if base == "hashed":
        return str(value)
    if base in _DATETIME_CASTS:
        return _parse_datetime(value)
    if base in _DATE_CASTS:
        parsed = _parse_datetime(value)
        return parsed.date() if parsed else None
    if base == "time":
        if isinstance(value, time):
            return value
        return time.fromisoformat(str(value))
    if base == "timestamp":
        parsed = _parse_datetime(value)
        return int(parsed.timestamp()) if parsed else None
    return value


def uncast_value(value: Any, cast: Any) -> Any:
    """Convert a cast Python value back into something the driver accepts."""
    if value is None:
        return None

    cast = resolve_cast(cast)

    if isinstance(cast, CastsAttributes):
        return value

    if isinstance(value, Enum):
        return value.value

    base, parameter = _split(cast)

    if base in _JSON_CASTS:
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return value
    if base == "decimal":
        return str(value)
    if base in {"bool", "boolean"}:
        return bool(value)
    if base == "encrypted":
        return _encrypt(value, parameter)
    if base == "hashed":
        hasher = _hash()
        text = str(value)
        return text if hasher.is_hashed(text) else hasher.make(text)
    return value


def prepare_for_storage(value: Any, cast: Any) -> Any:
    """Transform a value on write.

    Symmetric casts round-trip (``"yes"`` becomes ``True`` becomes a stored
    bool) so input is normalized. One-way casts — ``encrypted`` and ``hashed``
    — only run the write half, since reading plaintext back is impossible.
    """
    resolved = resolve_cast(cast)
    if isinstance(resolved, CastsAttributes) or isinstance(resolved, type):
        return uncast_value(value, resolved)
    base, _ = _split(resolved)
    if base in _WRITE_ONLY:
        return uncast_value(value, resolved)
    return uncast_value(cast_value(value, resolved), resolved)


def _encrypt(value: Any, parameter: str) -> str:
    """Encrypt on write, JSON-encoding structured payloads first."""
    crypt = _crypt()
    if parameter and parameter.strip().lower() in _JSON_CASTS:
        if isinstance(value, str):
            return crypt.encrypt_string(value)
        return crypt.encrypt_string(json.dumps(value))
    return crypt.encrypt_string(str(value))


def _decrypt(value: Any, parameter: str) -> Any:
    """Decrypt on read, decoding structured payloads afterwards."""
    plain = _crypt().decrypt_string(str(value))
    if parameter and parameter.strip().lower() in _JSON_CASTS:
        try:
            return json.loads(plain)
        except (TypeError, ValueError) as exc:
            raise CastError(f"Cannot decode encrypted {parameter}") from exc
    return plain


def serialize_value(value: Any, cast: Any = None) -> Any:
    """Make a cast value JSON-safe for `to_dict()` / responses.

    A date cast carrying a format (``"date:%d/%m/%Y"``) serializes with it;
    everything else uses ISO-8601.
    """
    fmt = cast_format(cast) if cast is not None else None
    if fmt and isinstance(value, (datetime, date, time)):
        return value.strftime(fmt)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {key: serialize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_value(item) for item in value]
    return value


class EnumCollection(CastsAttributes):
    """Cast a JSON array of scalars to a list of enums — ``AsEnumCollection``."""

    def __init__(self, enum: type[Enum]) -> None:
        self.enum = enum

    @classmethod
    def of(cls, enum: type[Enum]) -> EnumCollection:
        return cls(enum)

    def get(self, model: Any, key: str, value: Any, attributes: Mapping[str, Any]) -> Any:
        if value is None:
            return None
        raw = value if isinstance(value, list) else json.loads(value)
        return [item if isinstance(item, self.enum) else self.enum(item) for item in raw]

    def set(
        self, model: Any, key: str, value: Any, attributes: Mapping[str, Any]
    ) -> Any | Mapping[str, Any]:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if not isinstance(value, Sequence):
            raise CastError(f"{key} expects a sequence of {self.enum.__name__}")
        return json.dumps(
            [item.value if isinstance(item, self.enum) else self.enum(item).value for item in value]
        )
