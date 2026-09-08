"""The base an application's tests inherit — Laravel's `TestCase`.

Almasix's is written for pytest: a class whose methods pytest collects, with
`setup()` / `teardown()` hooks that may be coroutines. It builds the
application once per test, hands out a client, and puts every façade back the
way it found it afterwards.
"""

from __future__ import annotations

import contextlib
import importlib.util
from collections.abc import AsyncIterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from almasix.testing import database as db
from almasix.testing.client import TestClient
from almasix.testing.console import PendingCommand, artisan
from almasix.testing.response import TestResponse


class TestCase:
    """Boots the application under test and lends it a client.

    Override `create_application()` to build it your own way; the default
    reads the current working directory, the way `smith` does.
    """

    #: Where the application lives. `None` means the current directory.
    base_path: str | Path | None = None

    #: Run every test inside a transaction and roll it back afterwards.
    use_database_transactions: bool = False

    #: Migrate a fresh database before every test.
    use_refresh_database: bool = False

    #: Set for each test by the fixture below. Class attributes rather than
    #: an ``__init__``, because pytest will not collect a class that has one.
    app: Any = None
    client: TestClient | None = None
    _transaction: Any = None

    @pytest.fixture(autouse=True)
    async def _almasix_test_lifecycle(self, request: pytest.FixtureRequest) -> AsyncIterator[None]:
        """Boot the application around every test in the class.

        A subclass whose application lives somewhere a fixture decides — a
        `tmp_path`, say — declares a fixture named `almasix_base_path`, and it
        is read here before the application is built.
        """
        with contextlib.suppress(pytest.FixtureLookupError):
            self.base_path = request.getfixturevalue("almasix_base_path")
        await self.setup()
        try:
            yield
        finally:
            await self.teardown()

    # --- lifecycle -------------------------------------------------------------

    def create_application(self) -> Any:
        """Build the application under test (Laravel's `createApplication`)."""
        return boot_application(self.base_path)

    async def setup_application(self) -> None:
        self.app = self.create_application()
        self.client = TestClient(self.app)

    async def setup(self) -> None:
        """Runs before every test. Call `super().setup()` when overriding."""
        await self.setup_application()
        if self.use_refresh_database:
            await self.refresh_database()
        if self.use_database_transactions:
            self._transaction = db.database_transactions()
            await self._transaction.__aenter__()

    async def teardown(self) -> None:
        """Runs after every test. Call `super().teardown()` when overriding."""
        if self._transaction is not None:
            await self._transaction.__aexit__(None, None, None)
            self._transaction = None

    # --- the client -------------------------------------------------------------

    def _client(self) -> TestClient:
        if self.client is None:
            raise RuntimeError("The application is not booted; call setup() first.")
        return self.client

    async def get(self, uri: str, **kwargs: Any) -> TestResponse:
        return await self._client().get(uri, **kwargs)

    async def post(self, uri: str, data: Any = None, **kwargs: Any) -> TestResponse:
        return await self._client().post(uri, data, **kwargs)

    async def put(self, uri: str, data: Any = None, **kwargs: Any) -> TestResponse:
        return await self._client().put(uri, data, **kwargs)

    async def patch(self, uri: str, data: Any = None, **kwargs: Any) -> TestResponse:
        return await self._client().patch(uri, data, **kwargs)

    async def delete(self, uri: str, data: Any = None, **kwargs: Any) -> TestResponse:
        return await self._client().delete(uri, data, **kwargs)

    async def get_json(self, uri: str, **kwargs: Any) -> TestResponse:
        return await self._client().get_json(uri, **kwargs)

    async def post_json(self, uri: str, data: Any = None, **kwargs: Any) -> TestResponse:
        return await self._client().post_json(uri, data, **kwargs)

    async def put_json(self, uri: str, data: Any = None, **kwargs: Any) -> TestResponse:
        return await self._client().put_json(uri, data, **kwargs)

    async def patch_json(self, uri: str, data: Any = None, **kwargs: Any) -> TestResponse:
        return await self._client().patch_json(uri, data, **kwargs)

    async def delete_json(self, uri: str, data: Any = None, **kwargs: Any) -> TestResponse:
        return await self._client().delete_json(uri, data, **kwargs)

    def acting_as(self, user: Any, guard: str = "web") -> TestCase:
        self._client().acting_as(user, guard)
        return self

    def with_session(self, data: Mapping[str, Any]) -> TestCase:
        self._client().with_session(data)
        return self

    def with_headers(self, headers: Mapping[str, str]) -> TestCase:
        self._client().with_headers(headers)
        return self

    def with_token(self, token: str, kind: str = "Bearer") -> TestCase:
        self._client().with_token(token, kind)
        return self

    def following_redirects(self, follow: bool = True) -> TestCase:
        self._client().following_redirects(follow)
        return self

    def from_(self, url: str) -> TestCase:
        self._client().from_(url)
        return self

    # --- the console ---------------------------------------------------------------

    def artisan(self, command: str, arguments: Mapping[str, Any] | None = None) -> PendingCommand:
        return artisan(command, arguments, app=self.app)

    # --- authentication -------------------------------------------------------------

    def assert_authenticated(self, guard: str = "web") -> TestCase:
        if not self._session_login(guard):
            raise AssertionError(f"No user is authenticated on the [{guard}] guard.")
        return self

    def assert_authenticated_as(self, user: Any, guard: str = "web") -> TestCase:
        payload = self._session_login(guard)
        if not payload:
            raise AssertionError(f"No user is authenticated on the [{guard}] guard.")
        expected = _identifier(user)
        actual = payload.get("id") if isinstance(payload, dict) else payload
        if str(actual) != str(expected):
            raise AssertionError(f"The authenticated user is {actual!r}, not {expected!r}.")
        return self

    def assert_guest(self, guard: str = "web") -> TestCase:
        if self._session_login(guard):
            raise AssertionError(f"A user is authenticated on the [{guard}] guard.")
        return self

    def _session_login(self, guard: str) -> Any:
        from almasix.session.store import last_session

        session = last_session()
        if session is not None and session.get(f"login_{guard}"):
            return session.get(f"login_{guard}")
        return self._client().session.get(f"login_{guard}")

    # --- the database -----------------------------------------------------------------

    async def refresh_database(self, path: str | Path | None = None) -> None:
        await db.refresh_database(path=path or self._migrations())

    def _migrations(self) -> Path:
        root = Path(self.base_path) if self.base_path else Path.cwd()
        return root / "database" / "migrations"

    async def assert_database_has(self, table: Any, data: Mapping[str, Any]) -> None:
        await db.assert_database_has(table, data)

    async def assert_database_missing(self, table: Any, data: Mapping[str, Any]) -> None:
        await db.assert_database_missing(table, data)

    async def assert_database_count(self, table: Any, count: int) -> None:
        await db.assert_database_count(table, count)

    async def assert_model_exists(self, model: Any) -> None:
        await db.assert_model_exists(model)

    async def assert_model_missing(self, model: Any) -> None:
        await db.assert_model_missing(model)

    async def assert_soft_deleted(self, model: Any, data: Mapping[str, Any] | None = None) -> None:
        await db.assert_soft_deleted(model, data)

    async def assert_not_soft_deleted(
        self,
        model: Any,
        data: Mapping[str, Any] | None = None,
    ) -> None:
        await db.assert_not_soft_deleted(model, data)

    # --- the fakes ------------------------------------------------------------------

    def fake(self, *surfaces: str) -> dict[str, Any]:
        """Fake several façades at once — `self.fake("mail", "queue", "event")`."""
        from almasix.testing.fakes import fake as fake_surface

        return {name: fake_surface(name) for name in surfaces}

    def without_middleware(self, middleware: Sequence[type] | type | None = None) -> TestCase:
        """Drop middleware for the rest of this test (Laravel `withoutMiddleware`)."""
        from almasix.testing.middleware import without_middleware

        without_middleware(self.app, middleware)
        return self

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.base_path or Path.cwd()})"


def boot_application(base_path: str | Path | None = None) -> Any:
    """The application a test drives, built the way the server builds it.

    `bootstrap/app.py` is an application's own entry — its middleware aliases,
    its stacks — so it is run when there is one, exactly as Laravel's tests
    require `bootstrap/app.php`. A directory without one is simply bootstrapped.
    """
    import sys

    from almasix.framework.application import Application

    root = Path(base_path or Path.cwd())
    entry = root / "bootstrap" / "app.py"
    if not entry.exists():
        return Application(root).bootstrap()

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location("almasix_testing_bootstrap", entry)
    if spec is None or spec.loader is None:  # pragma: no cover - a file that will not load
        raise RuntimeError(f"Cannot load {entry}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    application = getattr(module, "application", None)
    if application is None:
        raise RuntimeError(f"{entry} defines no `application` to test.")
    return application


def _identifier(user: Any) -> Any:
    """The key a login would have written — from a model, a dict, or a value."""
    if hasattr(user, "get_auth_identifier"):
        return user.get_auth_identifier()
    if isinstance(user, Mapping):
        return user.get("id")
    return user
