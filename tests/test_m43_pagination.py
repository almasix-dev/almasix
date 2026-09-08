"""Paginators that know their own URL, and the cursor kind that Almasix lacked."""

from __future__ import annotations

import json
from typing import Any

import pytest
from starlette.requests import Request as StarletteRequest

from almasix.orm.collection import Collection
from almasix.orm.facade import DB
from almasix.orm.pagination import (
    Cursor,
    CursorPaginator,
    Paginator,
    SimplePaginator,
)
from almasix.orm.schema import Schema
from tests.orm_support import memory_db  # noqa: F401


def page_of(names: list[str]) -> Collection[Any]:
    return Collection([{"name": name} for name in names])


def paginator(**options: Any) -> Paginator:
    return Paginator(page_of(["a", "b"]), total=10, per_page=2, current_page=2, **options)


def as_request(path: str, query: str = "") -> Any:
    """Put a request in scope, the way the HTTP kernel does."""
    from almasix.http.request import Request, set_request

    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": [],
        "server": ("testserver", 80),
        "scheme": "http",
    }
    request = Request(
        StarletteRequest(scope),
        query=dict(pair.split("=", 1) for pair in query.split("&") if pair),
    )
    return set_request(request)


# --- URLs --------------------------------------------------------------------


def test_a_paginator_writes_the_links_around_it() -> None:
    page = paginator(path="/users")

    assert page.url(1) == "/users?page=1"
    assert page.previous_page_url() == "/users?page=1"
    assert page.next_page_url() == "/users?page=3"
    assert page.first_page_url() == "/users?page=1"
    assert page.last_page_url() == "/users?page=5"
    assert page.get_url_range(1, 3) == {
        1: "/users?page=1",
        2: "/users?page=2",
        3: "/users?page=3",
    }
    assert page.has_pages()
    assert not page.on_first_page()
    assert not page.on_last_page()


def test_the_last_page_has_nowhere_further_to_go() -> None:
    page = Paginator(page_of(["a"]), total=3, per_page=2, current_page=2, path="/users")

    assert page.next_page_url() is None
    assert page.on_last_page()
    assert not page.has_more_pages()
    assert page.first_item() == 3
    assert page.last_item() == 3


def test_an_empty_page_counts_nothing() -> None:
    page = Paginator(Collection([]), total=0, per_page=15, current_page=1, path="/users")

    assert page.from_ is None and page.to is None
    assert page.last_page == 1
    assert not page.has_pages()
    assert page.is_empty() and not page.is_not_empty()
    assert page.count() == 0


def test_what_a_link_carries_beside_the_page_number() -> None:
    page = paginator(path="/users")
    page.appends("sort", "name").appends({"filter": "active"}).fragment("results")

    assert page.url(3) == "/users?sort=name&filter=active&page=3#results"
    assert page.fragment() == "results"
    assert page.get_options() == {
        "path": "/users",
        "page_name": "page",
        "query": {"sort": "name", "filter": "active"},
        "fragment": "results",
    }


def test_a_path_that_already_asks_something() -> None:
    page = paginator(path="/users?team=1")
    assert page.url(2) == "/users?team=1&page=2"


def test_the_page_name_can_be_something_other_than_page() -> None:
    page = Paginator(page_of(["a"]), 10, 2, 2, path="/users", page_name="p")
    assert page.url(3) == "/users?p=3"


def test_a_paginator_finds_the_request_it_was_built_in() -> None:
    from almasix.http.request import reset_request

    token = as_request("/users/", "page=3&sort=name")
    try:
        page = Paginator(page_of(["a"]), total=10, per_page=2, current_page=3)
        assert page.path == "/users"
        assert page.url(1) == "/users?page=1"

        page.with_query_string()
        assert page.url(2) == "/users?sort=name&page=2"
    finally:
        reset_request(token)


def test_with_query_string_outside_a_request_adds_nothing() -> None:
    page = paginator(path="/users").with_query_string()
    assert page.url(1) == "/users?page=1"


def test_through_replaces_the_items_and_keeps_the_page() -> None:
    page = paginator(path="/users").through(lambda row: row["name"].upper())

    assert list(page) == ["A", "B"]
    assert page.current_page == 2
    assert len(page) == 2


def test_the_json_a_length_aware_paginator_produces() -> None:
    page = Paginator(page_of(["a", "b"]), total=4, per_page=2, current_page=1, path="/users")

    shape = page.to_dict()
    assert shape["current_page"] == 1
    assert shape["data"] == [{"name": "a"}, {"name": "b"}]
    assert shape["first_page_url"] == "/users?page=1"
    assert shape["last_page_url"] == "/users?page=2"
    assert shape["next_page_url"] == "/users?page=2"
    assert shape["prev_page_url"] is None
    assert shape["from"] == 1 and shape["to"] == 2
    assert shape["total"] == 4 and shape["per_page"] == 2
    assert [link["label"] for link in shape["links"]] == [
        "&laquo; Previous",
        "1",
        "2",
        "Next &raquo;",
    ]
    assert shape["links"][1]["active"] is True
    assert json.loads(page.to_json())["path"] == "/users"


def test_the_json_a_simple_paginator_produces() -> None:
    page = SimplePaginator(page_of(["a"]), per_page=1, current_page=2, has_more=True, path="/u")

    shape = page.to_dict()
    assert shape["next_page_url"] == "/u?page=3"
    assert shape["prev_page_url"] == "/u?page=1"
    assert shape["from"] == 2 and shape["to"] == 2
    assert shape["has_more"] is True
    assert page.first_item() == 2 and page.last_item() == 2

    last = SimplePaginator(Collection([]), 1, 1, False, path="/u")
    assert last.next_page_url() is None
    assert last.from_ is None and last.to is None
    assert not last.has_pages()


# --- rendering ----------------------------------------------------------------


def test_the_links_a_paginator_renders(tmp_path) -> None:
    from almasix.prism.engine import Engine
    from almasix.prism.helpers import set_engine
    from pathlib import Path as FilePath

    engine = Engine(paths=[FilePath("src/almasix/prism/views")], cache_enabled=False)
    set_engine(engine)
    try:
        html = Paginator(page_of(["a"]), total=4, per_page=2, current_page=1, path="/u").links()
        assert 'aria-label="Pagination"' in html
        assert 'href="/u?page=2"' in html
        assert "Showing 1 to 1 of 4 results" in html

        simple = SimplePaginator(page_of(["a"]), 2, 2, True, path="/u").links()
        assert 'rel="prev"' in simple and 'rel="next"' in simple

        # One page is no pages worth linking.
        assert Paginator(page_of(["a"]), 1, 15, 1, path="/u").render().strip() == ""

        # The Bootstrap pair ships too, for an application on that stack.
        Paginator.use_bootstrap_five()
        try:
            bootstrap = Paginator(page_of(["a"]), 4, 2, 1, path="/u").links()
            assert 'class="page-link" href="/u?page=2"' in bootstrap
            simple_bootstrap = SimplePaginator(page_of(["a"]), 2, 1, True, path="/u").links()
            assert 'class="page-item disabled"' in simple_bootstrap
            assert 'rel="next"' in simple_bootstrap
        finally:
            Paginator.use_tailwind()
    finally:
        set_engine(None)


# --- cursors -------------------------------------------------------------------


def test_a_cursor_survives_the_round_trip_through_a_url() -> None:
    cursor = Cursor({"id": 12, "name": "Ada"}, True)
    encoded = cursor.encode()

    assert "=" not in encoded
    assert Cursor.from_encoded(encoded) == cursor
    assert Cursor.from_encoded(encoded).parameter("id") == 12
    assert cursor != "not a cursor"
    assert "id" in repr(cursor)


def test_a_cursor_that_is_not_one() -> None:
    assert Cursor.from_encoded(None) is None
    assert Cursor.from_encoded("") is None
    assert Cursor.from_encoded("not base64 at all!") is None
    assert Cursor.from_encoded("WzEsIDJd") is None  # valid base64, but a list

    with pytest.raises(ValueError, match="Unable to find cursor parameter"):
        Cursor({"id": 1}).parameter("name")


async def test_cursor_paging_walks_forwards_and_back(memory_db) -> None:
    await Schema.create("posts", lambda table: (table.id(), table.string("title")))
    await DB.table("posts").insert([{"title": f"Post {number}"} for number in range(1, 8)])
    query = lambda: DB.table("posts").order_by("id")  # noqa: E731

    first = await query().cursor_paginate(3)
    assert [row["title"] for row in first] == ["Post 1", "Post 2", "Post 3"]
    assert first.on_first_page()
    assert first.has_more_pages()
    assert first.previous_page_url() is None

    second = await query().cursor_paginate(3, first.next_cursor())
    assert [row["title"] for row in second] == ["Post 4", "Post 5", "Post 6"]
    assert not second.on_first_page()

    third = await query().cursor_paginate(3, second.next_cursor())
    assert [row["title"] for row in third] == ["Post 7"]
    assert not third.has_more_pages()
    assert third.next_cursor() is None
    assert third.on_last_page()

    # Back the way we came.
    back = await query().cursor_paginate(3, third.previous_cursor())
    assert [row["title"] for row in back] == ["Post 4", "Post 5", "Post 6"]
    assert (await query().cursor_paginate(3, back.previous_cursor())) is not None


async def test_a_cursor_reads_the_encoded_string_as_happily_as_the_object(memory_db) -> None:
    await Schema.create("posts", lambda table: (table.id(), table.string("title")))
    await DB.table("posts").insert([{"title": f"Post {number}"} for number in range(1, 5)])

    first = await DB.table("posts").order_by("id").cursor_paginate(2)
    encoded = first.next_cursor().encode()

    second = await DB.table("posts").order_by("id").cursor_paginate(2, encoded)
    assert [row["title"] for row in second] == ["Post 3", "Post 4"]
    assert second.to_dict()["next_cursor"] is None
    assert second.to_dict()["prev_cursor"] is not None


async def test_a_cursor_over_several_ordered_columns(memory_db) -> None:
    """Ties in the first column are broken by the second, both ways."""
    await Schema.create(
        "posts",
        lambda table: (table.id(), table.string("author"), table.string("title")),
    )
    await DB.table("posts").insert(
        [
            {"author": "Ada", "title": "B"},
            {"author": "Ada", "title": "A"},
            {"author": "Grace", "title": "C"},
            {"author": "Grace", "title": "A"},
        ]
    )
    query = lambda: DB.table("posts").order_by("author").order_by("title", "desc")  # noqa: E731

    first = await query().cursor_paginate(2)
    assert [(row["author"], row["title"]) for row in first] == [("Ada", "B"), ("Ada", "A")]

    second = await query().cursor_paginate(2, first.next_cursor())
    assert [(row["author"], row["title"]) for row in second] == [
        ("Grace", "C"),
        ("Grace", "A"),
    ]


async def test_cursor_paging_needs_an_ordering(memory_db) -> None:
    await Schema.create("posts", lambda table: (table.id(), table.string("title")))

    with pytest.raises(ValueError, match="needs an order_by"):
        await DB.table("posts").cursor_paginate(2)


async def test_a_cursor_paginator_reads_the_request_it_was_built_in(memory_db) -> None:
    from almasix.http.request import reset_request

    await Schema.create("posts", lambda table: (table.id(), table.string("title")))
    await DB.table("posts").insert([{"title": f"Post {number}"} for number in range(1, 5)])
    first = await DB.table("posts").order_by("id").cursor_paginate(2)

    token = as_request("/posts", f"cursor={first.next_cursor().encode()}")
    try:
        page = await DB.table("posts").order_by("id").cursor_paginate(2)
        assert [row["title"] for row in page] == ["Post 3", "Post 4"]
        assert page.path == "/posts"
    finally:
        reset_request(token)

    # Without a request there is no cursor to find, so it starts at the top.
    page = await DB.table("posts").order_by("id").cursor_paginate(2)
    assert [row["title"] for row in page] == ["Post 1", "Post 2"]


def test_what_a_cursor_paginator_says_about_itself() -> None:
    page = CursorPaginator(
        page_of(["a", "b"]),
        per_page=2,
        cursor=None,
        has_more=True,
        parameters=["name"],
        path="/posts",
    )

    assert page.has_pages()
    assert page.url(None) == "/posts"
    assert page.url("abc") == "/posts?cursor=abc"
    assert page.url(page.next_cursor()).startswith("/posts?cursor=")
    assert page.previous_cursor() is None

    empty = CursorPaginator(Collection([]), 2, None, False, parameters=["name"], path="/posts")
    assert empty.next_cursor() is None
    assert not empty.has_pages()


async def test_paginate_takes_the_page_from_the_request(memory_db) -> None:
    from almasix.http.request import reset_request

    await Schema.create("posts", lambda table: (table.id(), table.string("title")))
    await DB.table("posts").insert([{"title": f"Post {number}"} for number in range(1, 8)])

    token = as_request("/posts", "page=2")
    try:
        page = await DB.table("posts").order_by("id").paginate(3)
        assert [row["title"] for row in page] == ["Post 4", "Post 5", "Post 6"]
        assert page.next_page_url() == "/posts?page=3"

        simple = await DB.table("posts").order_by("id").simple_paginate(3)
        assert simple.current_page == 2
    finally:
        reset_request(token)


async def test_a_page_number_that_is_not_one(memory_db) -> None:
    from almasix.http.request import reset_request

    await Schema.create("posts", lambda table: (table.id(), table.string("title")))
    await DB.table("posts").insert([{"title": "Post 1"}])

    token = as_request("/posts", "page=nowhere")
    try:
        assert (await DB.table("posts").paginate(3)).current_page == 1
    finally:
        reset_request(token)

    token = as_request("/posts", "page=-4")
    try:
        assert (await DB.table("posts").paginate(3)).current_page == 1
    finally:
        reset_request(token)


async def test_paging_models_rather_than_rows(memory_db) -> None:
    """A cursor reads a model's attributes as readily as a row's keys."""
    from almasix.orm.model import Model

    class Post(Model):
        table = "posts"
        fillable = ["title"]

    await Schema.create("posts", lambda table: (table.id(), table.string("title")))
    await DB.table("posts").insert([{"title": f"Post {number}"} for number in range(1, 5)])

    first = await Post.query().order_by("id").cursor_paginate(2)
    assert [post.title for post in first] == ["Post 1", "Post 2"]

    second = await Post.query().order_by("id").cursor_paginate(2, first.next_cursor())
    assert [post.title for post in second] == ["Post 3", "Post 4"]

    page = await Post.query().order_by("id").paginate(2)
    assert page.current_page == 1
    assert page.total == 4
    assert page.path == "/"  # nothing to read a path from, outside a request


def test_a_paginator_can_be_told_where_it_lives() -> None:
    page = paginator(path="/users").with_path("/team/users/")
    assert page.url(1) == "/team/users?page=1"
    assert page.set_path("/x").url(1) == "/x?page=1"


async def test_a_count_that_has_already_been_taken(memory_db) -> None:
    """Passing the total in skips the count query, as Laravel's fifth argument does."""
    await Schema.create("posts", lambda table: (table.id(), table.string("title")))
    await DB.table("posts").insert([{"title": f"Post {number}"} for number in range(1, 4)])

    page = await DB.table("posts").order_by("id").paginate(2, 1, total=99)
    assert page.total == 99
    assert page.last_page == 50


def test_the_link_bar_elides_the_middle_of_a_long_run() -> None:
    """Laravel shows the ends and a window around here, with ... between."""
    page = Paginator(page_of(["a"]), total=400, per_page=10, current_page=20, path="/u")

    labels = [link["label"] for link in page.link_collection()]
    assert labels[:4] == ["&laquo; Previous", "1", "2", "..."]
    assert labels[-4:] == ["...", "39", "40", "Next &raquo;"]
    assert "20" in labels and labels.count("...") == 2

    # Near either end there is only one gap, and a short run has none at all.
    assert [link["label"] for link in page.on_each_side(1).link_collection()].count("...") == 2
    front = Paginator(page_of(["a"]), 400, 10, 2, path="/u").link_collection()
    assert [link["label"] for link in front].count("...") == 1
    back = Paginator(page_of(["a"]), 400, 10, 39, path="/u").link_collection()
    assert [link["label"] for link in back].count("...") == 1
    short = Paginator(page_of(["a"]), 40, 10, 1, path="/u").link_collection()
    assert [link["label"] for link in short] == [
        "&laquo; Previous", "1", "2", "3", "4", "Next &raquo;"
    ]
