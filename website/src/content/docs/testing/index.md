---
title: 'Testing: Getting Started'
description: Almasix's testing toolkit — a TestCase that boots the application, a client that drives the real middleware stack, and assertions that explain their own failures.
---

## Introduction

Almasix is built to be tested. `almasix new` writes a `tests/` directory, a
`pytest` configuration, and two example tests; `smith test` runs them. The
toolkit lives in `almasix.testing` and is optional — a plain pytest suite works
perfectly well — but what it adds is the vocabulary: a client that drives the
real middleware stack in-process, assertions that say what went wrong, console
commands that answer their own questions, and one door to every fake.

```python
from almasix.testing import TestCase


class PostTest(TestCase):
    async def test_the_index_lists_posts(self) -> None:
        response = await self.get("/posts")

        response.assert_ok().assert_see("Hello")
```

Tests are pytest tests. There is no test runner of Almasix's own, no `assert`
that is not Python's, and no magic in the collection: a class pytest collects,
methods pytest calls, and coroutines pytest awaits.

## File map

| Piece | Path |
| --- | --- |
| Base class | `src/almasix/testing/case.py` — `TestCase`, `boot_application()` |
| HTTP client | `src/almasix/testing/client.py` — `TestClient` |
| Response assertions | `src/almasix/testing/response.py` — `TestResponse` |
| Console assertions | `src/almasix/testing/console.py` — `smith()`, `PendingCommand` |
| Database helpers | `src/almasix/testing/database.py` |
| Fakes | `src/almasix/testing/fakes.py` — `fake()`, `fakeable()`, `restore_fakes()` |
| Middleware | `src/almasix/testing/middleware.py` |
| Time | `src/almasix/testing/time.py` — `travel`, `freeze_time` |
| Generator | `smith make:test` |
| Runner | `smith test` |

## The environment

`smith test` runs `pytest` with `APP_ENV=testing`, so `config/*.py` can read
`env("APP_ENV")` and choose a different database, mailer, or queue for a test
run. A `.env.testing` file, when there is one, is read in preference to `.env`.

```bash
smith test                      # every test
smith test tests/feature        # one directory
smith test -k posts             # pytest's -k
smith test --coverage           # with coverage
smith test --parallel           # with pytest-xdist, if installed
smith test --stop               # stop at the first failure
```

Anything `smith test` does not recognise is handed to pytest untouched.

## Creating tests

```bash
smith make:test PostTest        # tests/feature/post_test.py
smith make:test PostTest --unit # tests/unit/post_test.py
```

A feature test boots the application and drives it through HTTP; a unit test
does not, and should not need to. The generated file is a class named the way
Laravel names them — `PostTest`, not `TestPost` — which the scaffolded pytest
configuration collects through `python_classes = ["Test*", "*Test"]`.

## The test case

`TestCase` boots the application once per test and hands you a client:

```python
class PostTest(TestCase):
    use_refresh_database = True

    async def setup(self) -> None:
        await super().setup()
        self.author = await User.create({"email": "ada@example.com"})

    async def test_a_post_can_be_written(self) -> None:
        response = await self.acting_as(self.author).post("/posts", {"title": "Hi"})

        response.assert_redirect("/posts")
        await self.assert_database_has("posts", {"title": "Hi"})
```

| Attribute | What it does |
| --- | --- |
| `base_path` | Where the application lives. Defaults to the working directory. |
| `use_refresh_database` | Migrate a fresh database before every test. |
| `use_database_transactions` | Run each test in a transaction, and roll it back. |

| Hook | When it runs |
| --- | --- |
| `create_application()` | Builds the application under test. |
| `setup_application()` | Assigns `self.app` and `self.client`. |
| `setup()` | Before every test. Call `super().setup()` when overriding. |
| `teardown()` | After every test. Call `super().teardown()` when overriding. |

`create_application()` runs the application's own `bootstrap/app.py` when there
is one, exactly as Laravel's tests require `bootstrap/app.php`, so a test drives
the same middleware stack a server would. `boot_application(path)` does the same
thing outside a `TestCase`.

When the application's path is decided by a fixture — a `tmp_path`, say —
declare a fixture named `almasix_base_path` and it is read before the
application is built:

```python
class PostTest(TestCase):
    @pytest.fixture
    def almasix_base_path(self, tmp_path: Path) -> Path:
        return tmp_path
```

## Without the test case

Every piece works on its own. A test that already has an application can make
its own client, and the assertion helpers are plain functions:

```python
from almasix.testing import TestClient, assert_database_has


async def test_the_home_page(app):
    response = await TestClient(app).get("/")

    response.assert_ok()
    await assert_database_has("visits", {"path": "/"})
```

## Where to go next

| Page | What it covers |
| --- | --- |
| [HTTP Tests](/testing/http-tests/) | The client, and everything a response can be asked |
| [Console Tests](/testing/console-tests/) | Running commands, answering their prompts |
| [Database Testing](/testing/database/) | Fresh databases, transactions, row assertions |
| [Mocking](/testing/mocking/) | Fakes for mail, queues, storage, time, and the rest |
