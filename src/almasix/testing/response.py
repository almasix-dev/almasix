"""The response a test gets back, and everything it can be asked to prove.

Laravel's `TestResponse`, spelled for Python. Every assertion says what it
wanted and what it actually got, because a failing test is read once and has
to explain itself the first time.
"""

from __future__ import annotations

import json as json_module
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import httpx

from almasix.support.collection import data_get

#: Sentinel for "any value will do" — `None` is a value a payload may hold.
_ANY = object()


class TestResponse:
    """An HTTP response under test.

    Wraps the raw `httpx.Response` (reachable as `.raw`) and adds Laravel's
    assertion vocabulary. Anything not asserted is still there: `.status`,
    `.content`, `.text`, `.headers`, `.cookies`.
    """

    #: Named `Test*` after Laravel, so tell pytest not to collect it.
    __test__ = False

    def __init__(
        self,
        response: httpx.Response,
        *,
        session: Mapping[str, Any] | None = None,
        views: Sequence[tuple[str, dict[str, Any]]] = (),
    ) -> None:
        self.raw = response
        self.session_data: dict[str, Any] = dict(session or {})
        self.views: list[tuple[str, dict[str, Any]]] = list(views)

    # --- reading ------------------------------------------------------------

    @property
    def status(self) -> int:
        return self.raw.status_code

    @property
    def content(self) -> bytes:
        return self.raw.content

    @property
    def text(self) -> str:
        return self.raw.text

    @property
    def headers(self) -> httpx.Headers:
        return self.raw.headers

    @property
    def cookies(self) -> httpx.Cookies:
        return self.raw.cookies

    def json(self, key: str | None = None, default: Any = None) -> Any:
        """The decoded body, or one dotted path out of it (Laravel `json()`)."""
        payload = self._decoded()
        if key is None:
            return payload
        return data_get(payload, key, default)

    def header(self, name: str, default: Any = None) -> Any:
        return self.raw.headers.get(name, default)

    def cookie(self, name: str, default: Any = None) -> Any:
        return self.raw.cookies.get(name, default)

    def session(self, key: str | None = None, default: Any = None) -> Any:
        """The session the request finished with."""
        if key is None:
            return dict(self.session_data)
        return data_get(self.session_data, key, default)

    def errors(self) -> dict[str, Any]:
        """The validation errors, from the JSON body or the session bag."""
        payload = self._decoded()
        if isinstance(payload, dict) and isinstance(payload.get("errors"), dict):
            return dict(payload["errors"])
        bag = self.session_data.get("errors")
        return dict(bag) if isinstance(bag, dict) else {}

    def dump(self) -> TestResponse:
        """Print the response — the assertion you reach for while writing one."""
        print(f"HTTP {self.status}")
        for name, value in self.raw.headers.items():
            print(f"{name}: {value}")
        print(self.text)
        return self

    # --- status -------------------------------------------------------------

    def assert_status(self, status: int) -> TestResponse:
        if self.status != status:
            raise AssertionError(
                f"Expected status {status}; got {self.status}.{self._body_hint()}"
            )
        return self

    def assert_ok(self) -> TestResponse:
        return self.assert_status(200)

    def assert_created(self) -> TestResponse:
        return self.assert_status(201)

    def assert_accepted(self) -> TestResponse:
        return self.assert_status(202)

    def assert_no_content(self, status: int = 204) -> TestResponse:
        self.assert_status(status)
        if self.content:
            raise AssertionError(f"Expected no content; got {self.text!r}.")
        return self

    def assert_bad_request(self) -> TestResponse:
        return self.assert_status(400)

    def assert_unauthorized(self) -> TestResponse:
        return self.assert_status(401)

    def assert_payment_required(self) -> TestResponse:
        return self.assert_status(402)

    def assert_forbidden(self) -> TestResponse:
        return self.assert_status(403)

    def assert_not_found(self) -> TestResponse:
        return self.assert_status(404)

    def assert_method_not_allowed(self) -> TestResponse:
        return self.assert_status(405)

    def assert_not_acceptable(self) -> TestResponse:
        return self.assert_status(406)

    def assert_conflict(self) -> TestResponse:
        return self.assert_status(409)

    def assert_gone(self) -> TestResponse:
        return self.assert_status(410)

    def assert_unprocessable(self) -> TestResponse:
        return self.assert_status(422)

    def assert_too_many_requests(self) -> TestResponse:
        return self.assert_status(429)

    def assert_server_error(self) -> TestResponse:
        if not 500 <= self.status < 600:
            raise AssertionError(f"Expected a server error; got {self.status}.")
        return self

    def assert_successful(self) -> TestResponse:
        if not 200 <= self.status < 300:
            raise AssertionError(
                f"Expected a successful status; got {self.status}.{self._body_hint()}"
            )
        return self

    def assert_redirect(self, uri: str | None = None) -> TestResponse:
        if not 300 <= self.status < 400:
            raise AssertionError(f"Expected a redirect; got {self.status}.")
        if uri is not None:
            self.assert_location(uri)
        return self

    def assert_redirect_contains(self, fragment: str) -> TestResponse:
        self.assert_redirect()
        location = str(self.header("location", ""))
        if fragment not in location:
            raise AssertionError(f"Redirected to [{location}], which does not contain [{fragment}].")
        return self

    def assert_location(self, uri: str) -> TestResponse:
        location = str(self.header("location", ""))
        if location != uri and not location.endswith(uri):
            raise AssertionError(f"Expected a location of [{uri}]; got [{location}].")
        return self

    # --- headers and cookies -------------------------------------------------

    def assert_header(self, name: str, value: Any = _ANY) -> TestResponse:
        if name not in self.raw.headers:
            present = ", ".join(sorted(self.raw.headers.keys())) or "nothing"
            raise AssertionError(f"Header [{name}] is missing. Sent: {present}.")
        if value is not _ANY and str(self.raw.headers[name]) != str(value):
            raise AssertionError(
                f"Header [{name}] is [{self.raw.headers[name]}], not [{value}]."
            )
        return self

    def assert_header_missing(self, name: str) -> TestResponse:
        if name in self.raw.headers:
            raise AssertionError(f"Header [{name}] is present, with [{self.raw.headers[name]}].")
        return self

    def assert_cookie(self, name: str, value: Any = _ANY) -> TestResponse:
        if name not in self.raw.cookies:
            present = ", ".join(sorted(self.raw.cookies.keys())) or "nothing"
            raise AssertionError(f"Cookie [{name}] was not set. Set: {present}.")
        if value is not _ANY and self.raw.cookies[name] != str(value):
            raise AssertionError(f"Cookie [{name}] is [{self.raw.cookies[name]}], not [{value}].")
        return self

    def assert_cookie_missing(self, name: str) -> TestResponse:
        if name in self.raw.cookies:
            raise AssertionError(f"Cookie [{name}] was set, to [{self.raw.cookies[name]}].")
        return self

    def assert_content_type(self, kind: str) -> TestResponse:
        actual = str(self.raw.headers.get("content-type", ""))
        if kind not in actual:
            raise AssertionError(f"Expected a content type of [{kind}]; got [{actual}].")
        return self

    def assert_download(self, filename: str | None = None) -> TestResponse:
        """The response is an attachment (Laravel `assertDownload`)."""
        disposition = str(self.raw.headers.get("content-disposition", ""))
        if "attachment" not in disposition:
            raise AssertionError(f"Expected a download; content-disposition is [{disposition}].")
        if filename is not None and filename not in disposition:
            raise AssertionError(f"Expected the download [{filename}]; got [{disposition}].")
        return self

    # --- the body -------------------------------------------------------------

    def assert_see(self, value: str, escape: bool = True) -> TestResponse:
        wanted = _escape(value) if escape else value
        if wanted not in self.text:
            raise AssertionError(f"[{wanted}] is not in the response.")
        return self

    def assert_dont_see(self, value: str, escape: bool = True) -> TestResponse:
        wanted = _escape(value) if escape else value
        if wanted in self.text:
            raise AssertionError(f"[{wanted}] is in the response, and should not be.")
        return self

    def assert_see_text(self, value: str, escape: bool = True) -> TestResponse:
        wanted = _escape(value) if escape else value
        if wanted not in _strip_tags(self.text):
            raise AssertionError(f"[{wanted}] is not in the response text.")
        return self

    def assert_dont_see_text(self, value: str, escape: bool = True) -> TestResponse:
        wanted = _escape(value) if escape else value
        if wanted in _strip_tags(self.text):
            raise AssertionError(f"[{wanted}] is in the response text, and should not be.")
        return self

    def assert_see_in_order(self, values: Sequence[str], escape: bool = True) -> TestResponse:
        position = 0
        for value in values:
            wanted = _escape(value) if escape else value
            found = self.text.find(wanted, position)
            if found < 0:
                raise AssertionError(f"[{wanted}] is not in the response, in that order.")
            position = found + len(wanted)
        return self

    def assert_content(self, value: str) -> TestResponse:
        if self.text != value:
            raise AssertionError(f"Expected the body {value!r}; got {self.text!r}.")
        return self

    def assert_streamed_content(self, value: str) -> TestResponse:
        return self.assert_content(value)

    # --- JSON -----------------------------------------------------------------

    def assert_json(self, expected: Mapping[str, Any], strict: bool = False) -> TestResponse:
        """Every key in `expected` is in the payload — exactly, when strict."""
        payload = self._decoded()
        if strict:
            return self.assert_exact_json(expected)
        missing = {
            key: value
            for key, value in expected.items()
            if data_get(payload, key, _ANY) != value
        }
        if missing:
            raise AssertionError(f"The JSON is missing {missing}. Got: {self._json_text()}.")
        return self

    def assert_exact_json(self, expected: Any) -> TestResponse:
        payload = self._decoded()
        if payload != expected:
            raise AssertionError(f"Expected the JSON {expected}; got {payload}.")
        return self

    def assert_json_path(self, path: str, expected: Any = _ANY) -> TestResponse:
        actual = data_get(self._decoded(), path, _ANY)
        if actual is _ANY:
            raise AssertionError(f"The JSON has no path [{path}]. Got: {self._json_text()}.")
        if expected is _ANY:
            return self
        if callable(expected) and not isinstance(expected, type):
            if not expected(actual):
                raise AssertionError(f"The value at [{path}] is {actual!r}, which was refused.")
            return self
        if actual != expected:
            raise AssertionError(f"The value at [{path}] is {actual!r}, not {expected!r}.")
        return self

    def assert_json_missing_path(self, path: str) -> TestResponse:
        if data_get(self._decoded(), path, _ANY) is not _ANY:
            raise AssertionError(f"The JSON has the path [{path}], and should not.")
        return self

    def assert_json_fragment(self, fragment: Mapping[str, Any]) -> TestResponse:
        """Somewhere in the payload, a dict holds every one of these pairs."""
        if not _contains_fragment(self._decoded(), fragment):
            raise AssertionError(
                f"The fragment {dict(fragment)} is not in the JSON. Got: {self._json_text()}."
            )
        return self

    def assert_json_missing(self, fragment: Mapping[str, Any]) -> TestResponse:
        if _contains_fragment(self._decoded(), fragment):
            raise AssertionError(f"The fragment {dict(fragment)} is in the JSON, and should not be.")
        return self

    def assert_json_count(self, count: int, key: str | None = None) -> TestResponse:
        payload = self._decoded() if key is None else data_get(self._decoded(), key)
        if payload is None or isinstance(payload, (str, bytes, int, float, bool)):
            raise AssertionError(f"There is nothing countable at [{key or 'the root'}].")
        if len(payload) != count:
            where = f"[{key}]" if key else "the JSON"
            raise AssertionError(f"Expected {count} items in {where}; got {len(payload)}.")
        return self

    def assert_json_structure(self, structure: Any, payload: Any = _ANY) -> TestResponse:
        """Laravel's shape check — keys, with `*` for "every item like this"."""
        actual = self._decoded() if payload is _ANY else payload
        _assert_structure(structure, actual, "")
        return self

    def assert_json_is_array(self, key: str | None = None) -> TestResponse:
        payload = self._decoded() if key is None else data_get(self._decoded(), key)
        if not isinstance(payload, list):
            #: A shape that is not the shape asserted is a failure, not a type error.
            raise AssertionError(f"Expected a JSON array; got {type(payload).__name__}.")  # noqa: TRY004
        return self

    def assert_json_is_object(self, key: str | None = None) -> TestResponse:
        payload = self._decoded() if key is None else data_get(self._decoded(), key)
        if not isinstance(payload, dict):
            raise AssertionError(f"Expected a JSON object; got {type(payload).__name__}.")  # noqa: TRY004
        return self

    # --- validation ------------------------------------------------------------

    def assert_valid(self, keys: str | Sequence[str] | None = None) -> TestResponse:
        """No validation errors — for all of them, or for these keys."""
        errors = self.errors()
        if keys is None:
            if errors:
                raise AssertionError(f"Expected no validation errors; got {sorted(errors)}.")
            return self
        offending = [key for key in _as_list(keys) if key in errors]
        if offending:
            raise AssertionError(f"Expected no errors for {offending}; got {errors}.")
        return self

    def assert_invalid(
        self,
        keys: str | Sequence[str] | Mapping[str, str] | None = None,
    ) -> TestResponse:
        errors = self.errors()
        if not errors:
            raise AssertionError("Expected validation errors; the response has none.")
        if keys is None:
            return self
        if isinstance(keys, Mapping):
            for key, message in keys.items():
                messages = " ".join(str(item) for item in _as_list(errors.get(key, [])))
                if key not in errors or message not in messages:
                    raise AssertionError(
                        f"Expected [{key}] to fail with [{message}]; got {errors.get(key)}."
                    )
            return self
        missing = [key for key in _as_list(keys) if key not in errors]
        if missing:
            raise AssertionError(f"Expected errors for {missing}; got {sorted(errors)}.")
        return self

    # --- the session ------------------------------------------------------------

    def assert_session_has(self, key: str, value: Any = _ANY) -> TestResponse:
        actual = data_get(self.session_data, key, _ANY)
        if actual is _ANY:
            present = ", ".join(sorted(self.session_data)) or "nothing"
            raise AssertionError(f"The session has no [{key}]. It holds: {present}.")
        if value is not _ANY:
            if callable(value) and not isinstance(value, type):
                if not value(actual):
                    raise AssertionError(f"The session's [{key}] is {actual!r}, which was refused.")
            elif actual != value:
                raise AssertionError(f"The session's [{key}] is {actual!r}, not {value!r}.")
        return self

    def assert_session_missing(self, key: str) -> TestResponse:
        if data_get(self.session_data, key, _ANY) is not _ANY:
            raise AssertionError(f"The session has [{key}], and should not.")
        return self

    def assert_session_has_all(self, values: Mapping[str, Any]) -> TestResponse:
        for key, value in values.items():
            self.assert_session_has(key, value)
        return self

    def assert_session_has_errors(
        self,
        keys: str | Sequence[str] | Mapping[str, str] | None = None,
    ) -> TestResponse:
        return self.assert_invalid(keys)

    def assert_session_has_no_errors(self) -> TestResponse:
        return self.assert_valid()

    # --- views --------------------------------------------------------------------

    def assert_view_is(self, name: str) -> TestResponse:
        rendered = [view for view, _ in self.views]
        if name not in rendered:
            seen = ", ".join(rendered) or "nothing"
            raise AssertionError(f"The view [{name}] was not rendered. Rendered: {seen}.")
        return self

    def assert_view_has(self, key: str, value: Any = _ANY) -> TestResponse:
        for _, data in self.views:
            actual = data_get(data, key, _ANY)
            if actual is _ANY:
                continue
            if value is _ANY or actual == value:
                return self
            raise AssertionError(f"The view's [{key}] is {actual!r}, not {value!r}.")
        raise AssertionError(f"No rendered view was given [{key}].")

    def assert_view_missing(self, key: str) -> TestResponse:
        for _, data in self.views:
            if data_get(data, key, _ANY) is not _ANY:
                raise AssertionError(f"A rendered view was given [{key}], and should not have been.")
        return self

    # --- internals --------------------------------------------------------------

    def _decoded(self) -> Any:
        try:
            return self.raw.json()
        except (json_module.JSONDecodeError, ValueError) as exc:
            raise AssertionError(f"The response is not JSON: {self.text!r}") from exc

    def _json_text(self) -> str:
        """The payload, for a failure message — only ever called after decoding."""
        return json_module.dumps(self.raw.json(), default=str)

    def _body_hint(self) -> str:
        """A failing status is nearly always explained by the body."""
        body = self.text.strip()
        if not body:
            return ""
        return f" The body was: {body[:400]}"

    def __repr__(self) -> str:
        return f"TestResponse({self.status} {self.raw.request.method} {self.raw.request.url})"


# --- helpers -------------------------------------------------------------------


def _as_list(value: Any) -> list[Any]:
    """One key or many — a string, a set, a list, or a lone value."""
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        return [value]
    return list(value)


def _escape(value: str) -> str:
    """The response holds escaped HTML, so the needle must be escaped too."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def _strip_tags(html: str) -> str:
    out: list[str] = []
    depth = 0
    for character in html:
        if character == "<":
            depth += 1
        elif character == ">":
            depth = max(depth - 1, 0)
        elif depth == 0:
            out.append(character)
    return "".join(out)


def _contains_fragment(payload: Any, fragment: Mapping[str, Any]) -> bool:
    """Is there a dict anywhere in here holding every pair in `fragment`?"""
    if isinstance(payload, Mapping):
        if all(payload.get(key, _ANY) == value for key, value in fragment.items()):
            return True
        return any(_contains_fragment(value, fragment) for value in payload.values())
    if isinstance(payload, (list, tuple)):
        return any(_contains_fragment(item, fragment) for item in payload)
    return False


def _assert_structure(structure: Any, payload: Any, path: str) -> None:
    where = path or "the root"
    if isinstance(structure, Mapping):
        for key, nested in structure.items():
            if key == "*":
                if not isinstance(payload, (list, tuple)):
                    raise AssertionError(f"Expected a list at [{where}]; got {type(payload).__name__}.")
                for index, item in enumerate(payload):
                    _assert_structure(nested, item, f"{path}.{index}".lstrip("."))
                continue
            if not isinstance(payload, Mapping) or key not in payload:
                raise AssertionError(f"The JSON is missing [{key}] at [{where}].")
            _assert_structure(nested, payload[key], f"{path}.{key}".lstrip("."))
        return
    if isinstance(structure, (list, tuple)):
        for key in structure:
            if not isinstance(payload, Mapping) or key not in payload:
                raise AssertionError(f"The JSON is missing [{key}] at [{where}].")
        return
    if not isinstance(payload, Mapping) or structure not in payload:
        raise AssertionError(f"The JSON is missing [{structure}] at [{where}].")
