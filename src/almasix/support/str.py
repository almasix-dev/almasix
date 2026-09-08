"""Laravel-shaped ``Str`` / ``Stringable`` helpers."""

from __future__ import annotations

import base64
import inspect
import json
import re
import secrets
import string
import unicodedata
import uuid
from collections.abc import Callable, Iterable, Sequence
from typing import Any, Self
from urllib.parse import urlparse

_UNCOUNTABLE = {
    "equipment",
    "information",
    "rice",
    "money",
    "species",
    "series",
    "fish",
    "sheep",
    "deer",
    "moose",
    "aircraft",
    "data",
}

_IRREGULAR = {
    "move": "moves",
    "foot": "feet",
    "goose": "geese",
    "sex": "sexes",
    "child": "children",
    "man": "men",
    "woman": "women",
    "tooth": "teeth",
    "person": "people",
    "ox": "oxen",
}

_PLURAL_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(quiz)$", re.I), r"\1zes"),
    (re.compile(r"^(ox)$", re.I), r"\1en"),
    (re.compile(r"([m|l])ouse$", re.I), r"\1ice"),
    (re.compile(r"(matr|vert|ind)ix|ex$", re.I), r"\1ices"),
    (re.compile(r"(x|ch|ss|sh)$", re.I), r"\1es"),
    (re.compile(r"([^aeiouy]|qu)y$", re.I), r"\1ies"),
    (re.compile(r"(hive)$", re.I), r"\1s"),
    (re.compile(r"(?:([^f])fe|([lr])f)$", re.I), r"\1\2ves"),
    (re.compile(r"sis$", re.I), "ses"),
    (re.compile(r"([ti])um$", re.I), r"\1a"),
    (re.compile(r"(buffal|tomat)o$", re.I), r"\1oes"),
    (re.compile(r"(bu)s$", re.I), r"\1ses"),
    (re.compile(r"(alias|status)$", re.I), r"\1es"),
    (re.compile(r"(octop|vir)us$", re.I), r"\1i"),
    (re.compile(r"(ax|test)is$", re.I), r"\1es"),
    (re.compile(r"s$", re.I), "s"),
    (re.compile(r"$"), "s"),
]

_SINGULAR_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(quiz)zes$", re.I), r"\1"),
    (re.compile(r"(matr)ices$", re.I), r"\1ix"),
    (re.compile(r"(vert|ind)ices$", re.I), r"\1ex"),
    (re.compile(r"^(ox)en", re.I), r"\1"),
    (re.compile(r"(alias|status)es$", re.I), r"\1"),
    (re.compile(r"(octop|vir)i$", re.I), r"\1us"),
    (re.compile(r"(cris|ax|test)es$", re.I), r"\1is"),
    (re.compile(r"(shoe)s$", re.I), r"\1"),
    (re.compile(r"(o)es$", re.I), r"\1"),
    (re.compile(r"(bus)es$", re.I), r"\1"),
    (re.compile(r"([m|l])ice$", re.I), r"\1ouse"),
    (re.compile(r"(x|ch|ss|sh)es$", re.I), r"\1"),
    (re.compile(r"(m)ovies$", re.I), r"\1ovie"),
    (re.compile(r"(s)eries$", re.I), r"\1eries"),
    (re.compile(r"([^aeiouy]|qu)ies$", re.I), r"\1y"),
    (re.compile(r"([lr])ves$", re.I), r"\1f"),
    (re.compile(r"(tive)s$", re.I), r"\1"),
    (re.compile(r"(hive)s$", re.I), r"\1"),
    (re.compile(r"(^analy)ses$", re.I), r"\1sis"),
    (re.compile(r"((a)naly|(b)a|(d)iagno|(p)arenthe|(p)rogno|(s)ynop|(t)he)ses$", re.I), r"\1\2sis"),
    (re.compile(r"([ti])a$", re.I), r"\1um"),
    (re.compile(r"(n)ews$", re.I), r"\1ews"),
    (re.compile(r"s$", re.I), ""),
]


class Str:
    """Static string helpers (Laravel ``Illuminate\\Support\\Str``)."""

    @staticmethod
    def of(value: Any = "") -> Stringable:
        return Stringable(value)

    @staticmethod
    def after(subject: str, search: str) -> str:
        if search == "":
            return subject
        idx = subject.find(search)
        return subject if idx < 0 else subject[idx + len(search) :]

    @staticmethod
    def after_last(subject: str, search: str) -> str:
        if search == "":
            return subject
        idx = subject.rfind(search)
        return subject if idx < 0 else subject[idx + len(search) :]

    @staticmethod
    def before(subject: str, search: str) -> str:
        if search == "":
            return subject
        idx = subject.find(search)
        return subject if idx < 0 else subject[:idx]

    @staticmethod
    def before_last(subject: str, search: str) -> str:
        if search == "":
            return subject
        idx = subject.rfind(search)
        return subject if idx < 0 else subject[:idx]

    @staticmethod
    def between(subject: str, from_: str, to: str) -> str:
        if from_ == "" or to == "":
            return subject
        return Str.before(Str.after(subject, from_), to)

    @staticmethod
    def between_first(subject: str, from_: str, to: str) -> str:
        return Str.between(subject, from_, to)

    @staticmethod
    def camel(value: str) -> str:
        studly = Str.studly(value)
        return studly[:1].lower() + studly[1:] if studly else ""

    @staticmethod
    def studly(value: str) -> str:
        parts = re.split(r"[^a-zA-Z0-9]+", value)
        return "".join(part[:1].upper() + part[1:] for part in parts if part)

    @staticmethod
    def snake(value: str, delimiter: str = "_") -> str:
        value = re.sub(r"([a-z\d])([A-Z])", r"\1" + delimiter + r"\2", value)
        value = re.sub(r"[^a-zA-Z0-9]+", delimiter, value)
        return value.strip(delimiter).lower()

    @staticmethod
    def kebab(value: str) -> str:
        return Str.snake(value, "-")

    @staticmethod
    def title(value: str) -> str:
        return value.title()

    @staticmethod
    def headline(value: str) -> str:
        parts = re.split(r"[_\-\s]+", Str.snake(value))
        return " ".join(part[:1].upper() + part[1:] for part in parts if part)

    @staticmethod
    def apa(value: str) -> str:
        # Approximate APA title case.
        small = {
            "a",
            "an",
            "and",
            "as",
            "at",
            "but",
            "by",
            "for",
            "in",
            "nor",
            "of",
            "on",
            "or",
            "so",
            "the",
            "to",
            "up",
            "yet",
        }
        words = value.split()
        result = []
        for index, word in enumerate(words):
            lower = word.lower()
            if index not in (0, len(words) - 1) and lower in small:
                result.append(lower)
            else:
                result.append(word[:1].upper() + word[1:])
        return " ".join(result)

    @staticmethod
    def ascii(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        return normalized.encode("ascii", "ignore").decode("ascii")

    @staticmethod
    def transliterate(value: str) -> str:
        return Str.ascii(value)

    @staticmethod
    def char_at(subject: str, index: int) -> str | bool:
        position = index if index >= 0 else len(subject) + index
        if position < 0 or position >= len(subject):
            return False
        return subject[position]

    @staticmethod
    def chop_start(subject: str, needle: str | Iterable[str]) -> str:
        needles = [needle] if isinstance(needle, str) else list(needle)
        for item in needles:
            if subject.startswith(item):
                return subject[len(item) :]
        return subject

    @staticmethod
    def chop_end(subject: str, needle: str | Iterable[str]) -> str:
        needles = [needle] if isinstance(needle, str) else list(needle)
        for item in needles:
            if subject.endswith(item):
                return subject[: -len(item)]
        return subject

    @staticmethod
    def contains(haystack: str, needles: str | Iterable[str], ignore_case: bool = False) -> bool:
        items = [needles] if isinstance(needles, str) else list(needles)
        target = haystack.lower() if ignore_case else haystack
        for needle in items:
            piece = needle.lower() if ignore_case else needle
            if piece != "" and piece in target:
                return True
        return False

    @staticmethod
    def contains_all(haystack: str, needles: Iterable[str], ignore_case: bool = False) -> bool:
        return all(Str.contains(haystack, needle, ignore_case=ignore_case) for needle in needles)

    @staticmethod
    def doesnt_contain(haystack: str, needles: str | Iterable[str], ignore_case: bool = False) -> bool:
        return not Str.contains(haystack, needles, ignore_case=ignore_case)

    @staticmethod
    def deduplicate(value: str, character: str = " ") -> str:
        return re.sub(rf"{re.escape(character)}+", character, value)

    @staticmethod
    def ends_with(haystack: str, needles: str | Iterable[str]) -> bool:
        items = [needles] if isinstance(needles, str) else list(needles)
        return any(haystack.endswith(item) for item in items if item != "")

    @staticmethod
    def starts_with(haystack: str, needles: str | Iterable[str]) -> bool:
        items = [needles] if isinstance(needles, str) else list(needles)
        return any(haystack.startswith(item) for item in items if item != "")

    @staticmethod
    def excerpt(text: str, phrase: str = "", *, options: dict[str, Any] | None = None) -> str | None:
        opts = options or {}
        radius = int(opts.get("radius", 100))
        omission = str(opts.get("omission", "..."))
        if phrase == "":
            return text[:radius] + (omission if len(text) > radius else "")
        idx = text.lower().find(phrase.lower())
        if idx < 0:
            return None
        start = max(0, idx - radius)
        end = min(len(text), idx + len(phrase) + radius)
        excerpt = text[start:end]
        if start > 0:
            excerpt = omission + excerpt
        if end < len(text):
            excerpt = excerpt + omission
        return excerpt

    @staticmethod
    def finish(value: str, cap: str) -> str:
        quoted = re.escape(cap)
        return re.sub(rf"(?:{quoted})+$", "", value) + cap

    @staticmethod
    def start(value: str, prefix: str) -> str:
        quoted = re.escape(prefix)
        return prefix + re.sub(rf"^({quoted})+", "", value)

    @staticmethod
    def is_(pattern: str | Iterable[str], value: str) -> bool:
        patterns = [pattern] if isinstance(pattern, str) else list(pattern)
        for item in patterns:
            if item == value:
                return True
            regex = re.escape(item).replace(r"\*", ".*")
            if re.fullmatch(regex, value) is not None:
                return True
        return False

    @staticmethod
    def is_ascii(value: str) -> bool:
        try:
            value.encode("ascii")
            return True
        except UnicodeEncodeError:
            return False

    @staticmethod
    def is_json(value: str) -> bool:
        try:
            json.loads(value)
            return True
        except Exception:
            return False

    @staticmethod
    def is_url(value: str, protocols: Sequence[str] | None = None) -> bool:
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            return False
        if protocols is not None and parsed.scheme not in protocols:
            return False
        return True

    @staticmethod
    def is_uuid(value: str) -> bool:
        try:
            uuid.UUID(str(value))
            return True
        except Exception:
            return False

    @staticmethod
    def is_ulid(value: str) -> bool:
        return bool(re.fullmatch(r"[0-7][0-9A-HJKMNP-TV-Z]{25}", value, re.I))

    @staticmethod
    def length(value: str, encoding: str | None = None) -> int:
        del encoding
        return len(value)

    @staticmethod
    def limit(value: str, limit: int = 100, end: str = "...") -> str:
        if len(value) <= limit:
            return value
        return value[: max(0, limit)].rstrip() + end

    @staticmethod
    def words(value: str, words: int = 100, end: str = "...") -> str:
        parts = value.split()
        if len(parts) <= words:
            return value
        return " ".join(parts[:words]) + end

    @staticmethod
    def lower(value: str) -> str:
        return value.lower()

    @staticmethod
    def upper(value: str) -> str:
        return value.upper()

    @staticmethod
    def lcfirst(value: str) -> str:
        return value[:1].lower() + value[1:]

    @staticmethod
    def ucfirst(value: str) -> str:
        return value[:1].upper() + value[1:]

    @staticmethod
    def ucsplit(value: str) -> list[str]:
        return re.findall(r"[A-Z]?[^A-Z]*", value)[:-1] or ([value] if value else [])

    @staticmethod
    def mask(value: str, character: str, index: int, length: int | None = None) -> str:
        if character == "":
            return value
        start = index if index >= 0 else max(0, len(value) + index)
        if length is None:
            length = len(value) - start
        end = min(len(value), start + max(0, length))
        return value[:start] + (character * (end - start)) + value[end:]

    @staticmethod
    def pad_both(value: str, length: int, pad: str = " ") -> str:
        short = max(0, length - len(value))
        left = short // 2
        return _fill(pad, left) + value + _fill(pad, short - left)

    @staticmethod
    def pad_left(value: str, length: int, pad: str = " ") -> str:
        return _fill(pad, max(0, length - len(value))) + value

    @staticmethod
    def pad_right(value: str, length: int, pad: str = " ") -> str:
        return value + _fill(pad, max(0, length - len(value)))

    @staticmethod
    def password(length: int = 32, letters: bool = True, numbers: bool = True, symbols: bool = True, spaces: bool = False) -> str:
        alphabet = ""
        if letters:
            alphabet += string.ascii_letters
        if numbers:
            alphabet += string.digits
        if symbols:
            alphabet += "!@#$%^&*()-_=+[]{};:,.?/"
        if spaces:
            alphabet += " "
        if not alphabet:
            alphabet = string.ascii_letters
        return "".join(secrets.choice(alphabet) for _ in range(max(1, length)))

    @staticmethod
    def plural(value: str, count: int | float = 2) -> str:
        if abs(count) in (1, 1.0):
            return value
        lower = value.lower()
        if lower in _UNCOUNTABLE:
            return value
        for singular, plural in _IRREGULAR.items():
            if lower == singular:
                return _match_case(value, plural)
            if lower == plural:
                return value
        for pattern, replacement in _PLURAL_RULES:
            if pattern.search(value):
                return pattern.sub(replacement, value)
        return value + "s"  # pragma: no cover - the last rule matches anything

    @staticmethod
    def singular(value: str) -> str:
        lower = value.lower()
        if lower in _UNCOUNTABLE:
            return value
        for singular, plural in _IRREGULAR.items():
            if lower == plural:
                return _match_case(value, singular)
            if lower == singular:
                return value
        for pattern, replacement in _SINGULAR_RULES:
            if pattern.search(value):
                return pattern.sub(replacement, value)
        return value

    @staticmethod
    def plural_studly(value: str, count: int | float = 2) -> str:
        parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", value)
        if not parts:
            return Str.plural(value, count)
        parts[-1] = Str.plural(parts[-1], count)
        return "".join(parts)

    @staticmethod
    def position(haystack: str, needle: str, offset: int = 0) -> int | bool:
        idx = haystack.find(needle, offset)
        return idx if idx >= 0 else False

    @staticmethod
    def random(length: int = 16) -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(max(0, length)))

    @staticmethod
    def remove(search: str | Iterable[str], subject: str, *, case_sensitive: bool = True) -> str:
        items = [search] if isinstance(search, str) else list(search)
        result = subject
        for item in items:
            if case_sensitive:
                result = result.replace(item, "")
            else:
                result = re.sub(re.escape(item), "", result, flags=re.I)
        return result

    @staticmethod
    def repeat(value: str, times: int) -> str:
        return value * max(0, times)

    @staticmethod
    def replace(
        search: str | Iterable[str],
        replace: str | Iterable[str],
        subject: str,
        *,
        case_sensitive: bool = True,
    ) -> str:
        if isinstance(search, str) and isinstance(replace, str):
            if case_sensitive:
                return subject.replace(search, replace)
            return re.sub(re.escape(search), replace, subject, flags=re.I)
        searches = list(search) if not isinstance(search, str) else [search]
        replacements = list(replace) if not isinstance(replace, str) else [replace] * len(searches)
        result = subject
        for item, repl in zip(searches, replacements, strict=False):
            result = Str.replace(item, repl, result, case_sensitive=case_sensitive)
        return result

    @staticmethod
    def replace_array(search: str, replace: Sequence[str], subject: str) -> str:
        parts = subject.split(search)
        result = parts[0]
        for index, part in enumerate(parts[1:]):
            repl = replace[index] if index < len(replace) else search
            result += repl + part
        return result

    @staticmethod
    def replace_first(search: str, replace: str, subject: str) -> str:
        return subject.replace(search, replace, 1)

    @staticmethod
    def replace_last(search: str, replace: str, subject: str) -> str:
        idx = subject.rfind(search)
        if idx < 0:
            return subject
        return subject[:idx] + replace + subject[idx + len(search) :]

    @staticmethod
    def replace_start(search: str, replace: str, subject: str) -> str:
        if subject.startswith(search):
            return replace + subject[len(search) :]
        return subject

    @staticmethod
    def replace_end(search: str, replace: str, subject: str) -> str:
        if subject.endswith(search):
            return subject[: -len(search)] + replace
        return subject

    @staticmethod
    def replace_matches(pattern: str, replace: str | Callable[[re.Match[str]], str], subject: str) -> str:
        return re.sub(pattern, replace, subject)

    @staticmethod
    def reverse(value: str) -> str:
        return value[::-1]

    @staticmethod
    def slug(title: str, separator: str = "-", language: str | None = None, dictionary: dict[str, str] | None = None) -> str:
        del language
        value = Str.ascii(title.lower())
        for search, repl in (dictionary or {"@": "at"}).items():
            value = value.replace(search, f" {repl} ")
        value = re.sub(rf"[^a-z0-9{re.escape(separator)}\s]+", "", value)
        value = re.sub(r"[\s_]+", separator, value)
        value = re.sub(rf"{re.escape(separator)}+", separator, value)
        return value.strip(separator)

    @staticmethod
    def squish(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def substr(value: str, start: int, length: int | None = None) -> str:
        if length is None:
            return value[start:]
        if length >= 0:
            end = start + length if start >= 0 else len(value) + start + length
            return value[start:end] if start >= 0 else value[start:end]
        return value[start : start + length]

    @staticmethod
    def substr_count(haystack: str, needle: str, offset: int = 0, length: int | None = None) -> int:
        segment = haystack[offset:] if length is None else haystack[offset : offset + length]
        return segment.count(needle)

    @staticmethod
    def substr_replace(value: str, replace: str, offset: int = 0, length: int | None = None) -> str:
        if length is None:
            length = len(value)
        start = offset if offset >= 0 else max(0, len(value) + offset)
        end = start + length
        return value[:start] + replace + value[end:]

    @staticmethod
    def swap(map_: dict[str, str], subject: str) -> str:
        for search, replace in map_.items():
            subject = subject.replace(search, replace)
        return subject

    @staticmethod
    def take(value: str, limit: int) -> str:
        if limit < 0:
            return value[limit:]
        return value[:limit]

    @staticmethod
    def to_base64(value: str) -> str:
        return base64.b64encode(value.encode("utf-8")).decode("ascii")

    @staticmethod
    def from_base64(value: str) -> str:
        return base64.b64decode(value.encode("ascii")).decode("utf-8")

    @staticmethod
    def trim(value: str, characters: str | None = None) -> str:
        return value.strip() if characters is None else value.strip(characters)

    @staticmethod
    def ltrim(value: str, characters: str | None = None) -> str:
        return value.lstrip() if characters is None else value.lstrip(characters)

    @staticmethod
    def rtrim(value: str, characters: str | None = None) -> str:
        return value.rstrip() if characters is None else value.rstrip(characters)

    @staticmethod
    def wrap(value: str, before: str, after: str | None = None) -> str:
        return f"{before}{value}{after if after is not None else before}"

    @staticmethod
    def unwrap(value: str, before: str, after: str | None = None) -> str:
        after = before if after is None else after
        if value.startswith(before) and value.endswith(after):
            return value[len(before) : len(value) - len(after) if after else None]
        return value

    @staticmethod
    def word_count(value: str) -> int:
        return len(value.split())

    @staticmethod
    def word_wrap(value: str, characters: int = 75, break_str: str = "\n", cut: bool = False) -> str:
        del cut
        return re.sub(rf"(.{{{characters}}})", rf"\1{break_str}", value)

    @staticmethod
    def uuid() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def ordered_uuid() -> str:
        return str(uuid.uuid1())

    @staticmethod
    def ulid() -> str:
        # Crockford Base32 ULID (26 chars) — timestamp + randomness.
        alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
        import time as time_mod

        ts = int(time_mod.time() * 1000)
        chars = ["0"] * 26
        for i in range(9, -1, -1):
            chars[i] = alphabet[ts & 31]
            ts >>= 5
        for i in range(10, 26):
            chars[i] = alphabet[secrets.randbelow(32)]
        return "".join(chars)

    @staticmethod
    def doesnt_start_with(haystack: str, needles: str | Iterable[str]) -> bool:
        """Whether the string starts with none of the needles."""
        return not Str.starts_with(haystack, needles)

    @staticmethod
    def doesnt_end_with(haystack: str, needles: str | Iterable[str]) -> bool:
        """Whether the string ends with none of the needles."""
        return not Str.ends_with(haystack, needles)

    @staticmethod
    def initials(value: str, separator: str = " ") -> str:
        """The first letter of each word, as initials: ``Ada Lovelace`` -> ``A. L.``."""
        words = [word for word in re.split(r"[\s]+", value.strip()) if word]
        return separator.join(f"{word[0].upper()}." for word in words)

    @staticmethod
    def match(pattern: str, subject: str) -> str:
        """The first match for the pattern, or the first capture group if there is one."""
        found = re.search(pattern, subject)
        if found is None:
            return ""
        return found.group(1) if found.groups() else found.group(0)

    @staticmethod
    def match_all(pattern: str, subject: str) -> list[str]:
        """Every match for the pattern, or every first capture group."""
        found = re.finditer(pattern, subject)
        return [match.group(1) if match.groups() else match.group(0) for match in found]

    @staticmethod
    def is_match(pattern: str | Iterable[str], value: str) -> bool:
        """Whether the string matches any of the given regular expressions."""
        patterns = [pattern] if isinstance(pattern, str) else list(pattern)
        return any(re.search(one, value) is not None for one in patterns)

    @staticmethod
    def ucwords(value: str, delimiters: str = " \t\r\n\f\v") -> str:
        """Upper-case the first letter of every word, leaving the rest alone.

        Unlike :meth:`title`, the remaining characters are untouched, so
        ``McDonald`` survives.
        """
        result = list(value)
        capitalise = True
        for index, character in enumerate(result):
            if capitalise and character not in delimiters:
                result[index] = character.upper()
                capitalise = False
            elif character in delimiters:
                capitalise = True
        return "".join(result)

    @staticmethod
    def markdown(value: str, *, options: dict[str, Any] | None = None) -> str:
        del options
        from almasix.mail.markdown import render_markdown_component

        return render_markdown_component(value)

    @staticmethod
    def inline_markdown(value: str, *, options: dict[str, Any] | None = None) -> str:
        del options
        escaped = (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
        escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
        escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
        return escaped


class Stringable:
    """Fluent wrapper around ``Str`` methods (Laravel ``Stringable``)."""

    def __init__(self, value: Any = "") -> None:
        self._value = "" if value is None else str(value)

    def __str__(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"Stringable({self._value!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Stringable):
            return self._value == other._value
        return self._value == other

    def __hash__(self) -> int:
        """Hash as the string does, so either can key the same dict entry."""
        return hash(self._value)

    def _new(self, value: Any) -> Self:
        """A new instance, because a fluent call must not alter its subject."""
        return type(self)(value)

    def value(self) -> str:
        return self._value

    def to_string(self) -> str:
        return self._value

    def exactly(self, value: Any) -> bool:
        return self._value == str(value)

    def append(self, *values: str) -> Self:
        return self._new(self._value + "".join(values))

    def prepend(self, *values: str) -> Self:
        return self._new("".join(values) + self._value)

    def explode(self, delimiter: str) -> list[str]:
        return self._value.split(delimiter)

    def basename(self, suffix: str = "") -> Self:
        from pathlib import Path

        name = Path(self._value).name
        if suffix and name.endswith(suffix):
            name = name[: -len(suffix)]
        return self._new(name)

    def dirname(self, levels: int = 1) -> Self:
        from pathlib import Path

        path = Path(self._value)
        for _ in range(max(1, levels)):
            path = path.parent
        return self._new(str(path))

    def class_basename(self) -> Self:
        from almasix.support.helpers import class_basename

        return self._new(class_basename(self._value))

    def when(self, condition: Any, callback: Callable[[Self], Any] | None = None, default: Callable[[Self], Any] | None = None) -> Self:
        """Apply a callback when the condition holds, otherwise the default."""
        chosen = callback if condition else default
        if chosen is None:
            return self
        result = chosen(self)
        # A callback that returns nothing is treated as having done nothing,
        # since a fluent call no longer alters its subject.
        return result if result is not None else self

    def unless(self, condition: Any, callback: Callable[[Self], Any], default: Callable[[Self], Any] | None = None) -> Self:
        return self.when(not condition, callback, default)

    def pipe(self, callback: Callable[[Self], Any]) -> Any:
        return callback(self)

    def tap(self, callback: Callable[[Self], Any]) -> Self:
        callback(self)
        return self

    def is_empty(self) -> bool:
        return self._value == ""

    def is_not_empty(self) -> bool:
        return not self.is_empty()

    def to_integer(self) -> int:
        return int(self._value)

    def to_float(self) -> float:
        return float(self._value)

    def to_boolean(self) -> bool:
        return self._value.lower() in {"1", "true", "yes", "on"}

    def replace(
        self,
        search: str | Iterable[str],
        replace: str | Iterable[str],
        *,
        case_sensitive: bool = True,
    ) -> Self:
        return self._new(Str.replace(search, replace, self._value, case_sensitive=case_sensitive))

    def remove(self, search: str | Iterable[str], *, case_sensitive: bool = True) -> Self:
        return self._new(Str.remove(search, self._value, case_sensitive=case_sensitive))

    def replace_array(self, search: str, replace: Sequence[str]) -> Self:
        return self._new(Str.replace_array(search, replace, self._value))

    def replace_first(self, search: str, replace: str) -> Self:
        return self._new(Str.replace_first(search, replace, self._value))

    def replace_last(self, search: str, replace: str) -> Self:
        return self._new(Str.replace_last(search, replace, self._value))

    def replace_start(self, search: str, replace: str) -> Self:
        return self._new(Str.replace_start(search, replace, self._value))

    def replace_end(self, search: str, replace: str) -> Self:
        return self._new(Str.replace_end(search, replace, self._value))

    def replace_matches(self, pattern: str, replace: str | Callable[[Any], str]) -> Self:
        return self._new(Str.replace_matches(pattern, replace, self._value))

    def swap(self, map_: dict[str, str]) -> Self:
        return self._new(Str.swap(map_, self._value))

    def is_(self, pattern: str | Iterable[str]) -> bool:
        return Str.is_(pattern, self._value)

    def contains(self, needles: str | Iterable[str], ignore_case: bool = False) -> bool:
        return Str.contains(self._value, needles, ignore_case=ignore_case)

    def contains_all(self, needles: Iterable[str], ignore_case: bool = False) -> bool:
        return Str.contains_all(self._value, needles, ignore_case=ignore_case)

    def doesnt_contain(self, needles: str | Iterable[str], ignore_case: bool = False) -> bool:
        return Str.doesnt_contain(self._value, needles, ignore_case=ignore_case)

    def starts_with(self, needles: str | Iterable[str]) -> bool:
        return Str.starts_with(self._value, needles)

    def ends_with(self, needles: str | Iterable[str]) -> bool:
        return Str.ends_with(self._value, needles)

    def new_line(self, count: int = 1) -> Self:
        """Append newlines."""
        return self._new(self._value + "\n" * count)

    def strip_tags(self, allowed: str = "") -> Self:
        """Remove HTML and XML tags, keeping the text between them."""
        import re as _re

        keep = {tag.strip().lower() for tag in allowed.split(",") if tag.strip()}
        if not keep:
            return self._new(_re.sub(r"<[^>]*>", "", self._value))

        def drop(match: _re.Match[str]) -> str:
            name = _re.match(r"</?\s*([a-zA-Z0-9]+)", match.group(0))
            return match.group(0) if name and name.group(1).lower() in keep else ""

        return self._new(_re.sub(r"<[^>]*>", drop, self._value))

    def split(self, pattern: str, limit: int = 0) -> list[str]:
        """Split on a regular expression."""
        import re as _re

        return _re.split(pattern, self._value, maxsplit=limit)

    def test(self, pattern: str) -> bool:
        """Whether the string matches the regular expression."""
        return Str.is_match(pattern, self._value)

    def to_base(self) -> Self:
        """Base64-encode the string."""
        return self._new(Str.to_base64(self._value))

    def from_base(self) -> Self:
        """Base64-decode the string."""
        return self._new(Str.from_base64(self._value))

    def hash(self, driver: str | None = None) -> Self:
        """Hash the string with the application's hasher."""
        from almasix.hashing import Hash

        return self._new(Hash.make(self._value) if driver is None else Hash.driver(driver).make(self._value))

    def encrypt(self) -> Self:
        """Encrypt the string with the application key."""
        from almasix.encryption.facade import Crypt

        return self._new(Crypt.encrypt_string(self._value))

    def decrypt(self) -> Self:
        """Decrypt a string encrypted with the application key."""
        from almasix.encryption.facade import Crypt

        return self._new(Crypt.decrypt_string(self._value))

    def dd(self) -> None:  # pragma: no cover - debug helper
        from almasix.debug import dd

        dd(self._value)

    def dump(self) -> Self:  # pragma: no cover - debug helper
        from almasix.debug import dump

        dump(self._value)
        return self


#: Parameter names ``Str`` uses for the string being operated on. The subject is
#: not always the first argument — ``Str.replace(search, replace, subject)`` —
#: so delegation binds it by name rather than by position.
_SUBJECT_PARAMETERS = frozenset(
    {"value", "subject", "haystack", "title", "text", "string"}
)

#: The conditional shortcuts Laravel puts on ``Stringable``, as name -> test.
_WHEN_TESTS: dict[str, Callable[[Stringable, tuple[Any, ...]], bool]] = {
    "when_contains": lambda s, a: s.contains(*a),
    "when_contains_all": lambda s, a: s.contains_all(*a),
    "when_empty": lambda s, a: s.is_empty(),
    "when_not_empty": lambda s, a: s.is_not_empty(),
    "when_starts_with": lambda s, a: s.starts_with(*a),
    "when_ends_with": lambda s, a: s.ends_with(*a),
    "when_doesnt_start_with": lambda s, a: s.doesnt_start_with(*a),
    "when_doesnt_end_with": lambda s, a: s.doesnt_end_with(*a),
    "when_exactly": lambda s, a: s.exactly(*a),
    "when_not_exactly": lambda s, a: not s.exactly(*a),
    "when_is": lambda s, a: s.is_(*a),
    "when_is_ascii": lambda s, a: s.is_ascii(),
    "when_is_ulid": lambda s, a: s.is_ulid(),
    "when_is_uuid": lambda s, a: s.is_uuid(),
    "when_test": lambda s, a: s.test(*a),
}


def _delegate(name: str, str_method: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a ``Str`` function as a fluent ``Stringable`` method."""
    try:
        parameters = inspect.signature(str_method).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins only
        parameters = {}
    subject = next((n for n in parameters if n in _SUBJECT_PARAMETERS), None)

    def method(self: Stringable, *args: Any, **kwargs: Any) -> Any:
        if subject is None:  # pragma: no cover - constructors like `uuid`
            result = str_method(*args, **kwargs)
        else:
            call = {subject: self._value}
            positional = [
                n
                for n, p in parameters.items()
                if n != subject and p.kind is not inspect.Parameter.KEYWORD_ONLY
            ]
            call.update(dict(zip(positional, args, strict=False)))
            call.update(kwargs)
            result = str_method(**call)
        return self._new(result) if isinstance(result, str) else result

    method.__name__ = name
    method.__doc__ = str_method.__doc__
    return method


def _install_delegates() -> None:
    """Give ``Stringable`` every ``Str`` method it does not define itself.

    Laravel's fluent strings are the same surface as the static ones, so listing
    them by hand only creates a way for the two to drift.
    """
    for name in dir(Str):
        if name.startswith("_") or hasattr(Stringable, name):
            continue
        member = inspect.getattr_static(Str, name)
        if isinstance(member, staticmethod):
            setattr(Stringable, name, _delegate(name, getattr(Str, name)))


def _install_when_tests() -> None:
    """Install the ``when_*`` conditional shortcuts."""
    for name, test in _WHEN_TESTS.items():

        def shortcut(
            self: Stringable,
            *args: Any,
            _test: Callable[..., bool] = test,
            **kwargs: Any,
        ) -> Any:
            callback = kwargs.pop("callback", None)
            default = kwargs.pop("default", None)
            arguments = list(args)
            # The callback is the last positional argument; whatever precedes it
            # belongs to the test.
            if callback is None and arguments and callable(arguments[-1]):
                callback = arguments.pop()
            if default is None and arguments and callable(arguments[-1]):
                callback, default = arguments.pop(), callback
            return self.when(_test(self, tuple(arguments)), callback, default)

        shortcut.__name__ = name
        setattr(Stringable, name, shortcut)


def str_(value: Any = "") -> Stringable:
    """Laravel ``str()`` helper."""
    return Str.of(value)


def _fill(pad: str, width: int) -> str:
    """``width`` characters of ``pad``, repeating and then cutting it short."""
    if width <= 0 or not pad:
        return ""
    return (pad * (width // len(pad) + 1))[:width]


def _match_case(source: str, target: str) -> str:
    if source.isupper():
        return target.upper()
    if source[:1].isupper():
        return target[:1].upper() + target[1:]
    return target


# CamelCase aliases for Laravel method names.
Str.afterLast = Str.after_last  # type: ignore[attr-defined]
Str.beforeLast = Str.before_last  # type: ignore[attr-defined]
Str.betweenFirst = Str.between_first  # type: ignore[attr-defined]
Str.charAt = Str.char_at  # type: ignore[attr-defined]
Str.chopStart = Str.chop_start  # type: ignore[attr-defined]
Str.chopEnd = Str.chop_end  # type: ignore[attr-defined]
Str.containsAll = Str.contains_all  # type: ignore[attr-defined]
Str.doesntContain = Str.doesnt_contain  # type: ignore[attr-defined]
Str.endsWith = Str.ends_with  # type: ignore[attr-defined]
Str.startsWith = Str.starts_with  # type: ignore[attr-defined]
Str.isAscii = Str.is_ascii  # type: ignore[attr-defined]
Str.isJson = Str.is_json  # type: ignore[attr-defined]
Str.isUrl = Str.is_url  # type: ignore[attr-defined]
Str.isUlid = Str.is_ulid  # type: ignore[attr-defined]
Str.isUuid = Str.is_uuid  # type: ignore[attr-defined]
Str.orderedUuid = Str.ordered_uuid  # type: ignore[attr-defined]
Str.padBoth = Str.pad_both  # type: ignore[attr-defined]
Str.padLeft = Str.pad_left  # type: ignore[attr-defined]
Str.padRight = Str.pad_right  # type: ignore[attr-defined]
Str.pluralStudly = Str.plural_studly  # type: ignore[attr-defined]
Str.replaceArray = Str.replace_array  # type: ignore[attr-defined]
Str.replaceFirst = Str.replace_first  # type: ignore[attr-defined]
Str.replaceLast = Str.replace_last  # type: ignore[attr-defined]
Str.replaceMatches = Str.replace_matches  # type: ignore[attr-defined]
Str.replaceStart = Str.replace_start  # type: ignore[attr-defined]
Str.replaceEnd = Str.replace_end  # type: ignore[attr-defined]
Str.substrCount = Str.substr_count  # type: ignore[attr-defined]
Str.substrReplace = Str.substr_replace  # type: ignore[attr-defined]
Str.toBase64 = Str.to_base64  # type: ignore[attr-defined]
Str.fromBase64 = Str.from_base64  # type: ignore[attr-defined]
Str.wordCount = Str.word_count  # type: ignore[attr-defined]
Str.wordWrap = Str.word_wrap  # type: ignore[attr-defined]
Str.inlineMarkdown = Str.inline_markdown  # type: ignore[attr-defined]
Str.doesntStartWith = Str.doesnt_start_with  # type: ignore[attr-defined]
Str.doesntEndWith = Str.doesnt_end_with  # type: ignore[attr-defined]
Str.matchAll = Str.match_all  # type: ignore[attr-defined]
Str.isMatch = Str.is_match  # type: ignore[attr-defined]
# ``is`` is reserved in Python — expose Laravel name via getattr-friendly alias.
setattr(Str, "is", Str.is_)

# Installed last, so the camelCase aliases above are already in place and get
# skipped: the fluent surface uses Python names only.
_install_delegates()
_install_when_tests()
