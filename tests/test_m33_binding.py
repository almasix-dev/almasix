"""M33 — route model binding, close up.

`tests/test_m33_http.py` proves binding works through the kernel. This proves
the rules it follows: which column, which parent, soft deletes, enums, and
what an explicit binding overrides.
"""

from __future__ import annotations

import enum
from typing import Any

import pytest

from almasix.http.exceptions import NotFoundHttpException
from almasix.routing.binding import (
    BindingMissing,
    is_bindable,
    parent_of,
    relationship_name,
    resolve,
    route_key_name,
)


class Colour(enum.Enum):
    RED = "red"
    BLUE = "blue"


class Rank(enum.IntEnum):
    FIRST = 1
    SECOND = 2


class FakeQuery:
    """The slice of the ORM query builder binding actually touches."""

    def __init__(self, rows: list[Any], *, trashed: list[Any] | None = None) -> None:
        self.rows = rows
        self.trashed = trashed or []
        self.including_trashed = False
        self.filters: list[tuple[str, Any]] = []

    def with_trashed(self) -> FakeQuery:
        self.including_trashed = True
        return self

    def where(self, key: str, value: Any) -> FakeQuery:
        self.filters.append((key, value))
        return self

    async def first(self) -> Any:
        pool = [*self.rows, *(self.trashed if self.including_trashed else [])]
        for row in pool:
            # Compared as strings because a path segment is a string and the
            # real driver coerces it against the column type.
            if all(
                str(getattr(row, key, None)) == str(value) for key, value in self.filters
            ):
                return row
        return None


class Post:
    primary_key = "id"

    def __init__(self, id: int, slug: str = "") -> None:
        self.id = id
        self.slug = slug

    rows: list[Post] = []
    deleted: list[Post] = []

    @classmethod
    def query(cls) -> FakeQuery:
        return FakeQuery(cls.rows, trashed=cls.deleted)


class Slugged(Post):
    @staticmethod
    def get_route_key_name() -> str:
        return "slug"


class InstanceKeyed(Post):
    def get_route_key_name(self) -> str:
        return "slug"


class NoPrimaryKey:
    primary_key = None

    @classmethod
    def query(cls) -> FakeQuery:
        return FakeQuery([])


@pytest.fixture(autouse=True)
def rows() -> Any:
    Post.rows = [Post(1, "first"), Post(2, "second")]
    Post.deleted = [Post(9, "gone")]
    yield
    Post.rows = []
    Post.deleted = []


# --- which column -----------------------------------------------------------


def test_the_route_key_is_the_primary_key_unless_the_model_says_otherwise() -> None:
    assert route_key_name(Post) == "id"
    assert route_key_name(Slugged) == "slug"


def test_a_route_key_name_that_needs_an_instance_falls_back_to_the_key() -> None:
    # `get_route_key_name(self)` cannot be called off the class, and the
    # primary key is the right answer rather than a TypeError at routing time.
    assert route_key_name(InstanceKeyed) == "id"


def test_a_model_with_no_primary_key_still_has_a_route_key() -> None:
    assert route_key_name(NoPrimaryKey) == "id"


# --- what is bindable -------------------------------------------------------


@pytest.mark.parametrize("annotation", [str, int, float, bool, bytes, "Post", None, 7])
def test_a_scalar_hint_is_not_a_binding(annotation: Any) -> None:
    assert is_bindable(annotation) is False


@pytest.mark.parametrize("annotation", [Post, Colour, Rank])
def test_a_model_or_enum_hint_is_a_binding(annotation: Any) -> None:
    assert is_bindable(annotation) is True


def test_a_plain_class_is_not_a_binding() -> None:
    class Plain:
        pass

    assert is_bindable(Plain) is False


# --- resolving --------------------------------------------------------------


async def test_a_value_resolves_to_the_row_it_names() -> None:
    found = await resolve(Post, "1")

    assert found.slug == "first"


async def test_a_binding_field_chooses_the_column() -> None:
    found = await resolve(Post, "second", field="slug")

    assert found.id == 2


async def test_nothing_found_is_a_model_not_found() -> None:
    from almasix.orm.builder import ModelNotFoundError

    with pytest.raises(ModelNotFoundError, match="No Post with id '404'"):
        await resolve(Post, "404")


async def test_with_trashed_finds_a_soft_deleted_row() -> None:
    from almasix.orm.builder import ModelNotFoundError

    with pytest.raises(ModelNotFoundError):
        await resolve(Post, "9")

    found = await resolve(Post, "9", trashed=True)
    assert found.slug == "gone"


# --- enums ------------------------------------------------------------------


@pytest.mark.parametrize(("value", "expected"), [("red", Colour.RED), ("BLUE", Colour.BLUE)])
async def test_an_enum_binds_by_value_or_by_name(value: str, expected: Colour) -> None:
    assert await resolve(Colour, value) is expected


async def test_an_int_backed_enum_binds_from_the_string_in_the_path() -> None:
    assert await resolve(Rank, "2") is Rank.SECOND


async def test_a_value_the_enum_does_not_have_is_a_404() -> None:
    with pytest.raises(NotFoundHttpException, match="not one of Colour"):
        await resolve(Colour, "green")


# --- scoped bindings --------------------------------------------------------


class Comment:
    def __init__(self, id: int, slug: str = "") -> None:
        self.id = id
        self.slug = slug


class Author:
    def __init__(self, comments: list[Comment] | None = None, callable_: bool = True) -> None:
        self._comments = comments if comments is not None else []
        self._callable = callable_

    @property
    def comments(self) -> Any:
        query = FakeQuery(self._comments, trashed=[Comment(9, "gone")])
        return (lambda: query) if self._callable else query


async def test_a_scoped_binding_only_finds_a_child_of_that_parent() -> None:
    from almasix.orm.builder import ModelNotFoundError

    parent = Author([Comment(1, "mine")])

    found = await resolve(Comment, "1", parent=parent, relationship="comments")
    assert found.slug == "mine"

    with pytest.raises(ModelNotFoundError):
        await resolve(Comment, "2", parent=Author([]), relationship="comments")


async def test_a_relationship_that_is_not_callable_is_read_as_the_query() -> None:
    parent = Author([Comment(1, "mine")], callable_=False)

    found = await resolve(Comment, "1", parent=parent, relationship="comments")

    assert found.slug == "mine"


async def test_a_scoped_binding_may_also_look_in_the_trash() -> None:
    parent = Author([])

    found = await resolve(
        Comment, "9", parent=parent, relationship="comments", trashed=True
    )

    assert found.slug == "gone"


async def test_a_relationship_the_parent_does_not_have_finds_nothing() -> None:
    from almasix.orm.builder import ModelNotFoundError

    with pytest.raises(ModelNotFoundError):
        await resolve(Comment, "1", parent=Author([]), relationship="nonexistent")


async def test_a_relationship_that_cannot_be_filtered_finds_nothing() -> None:
    from almasix.orm.builder import ModelNotFoundError

    class Unfilterable:
        comments = object()

    with pytest.raises(ModelNotFoundError):
        await resolve(Comment, "1", parent=Unfilterable(), relationship="comments")


def test_the_relationship_a_scoped_parameter_reads_is_its_plural() -> None:
    assert relationship_name("comment") == "comments"
    assert relationship_name("category") == "categories"


# --- finding the parent -----------------------------------------------------


def test_the_parent_is_the_nearest_model_to_the_left() -> None:
    post = Post(1)
    order = ["locale", "post", "comment"]
    resolved = {"locale": "en", "post": post}

    assert parent_of("comment", resolved, order) is post
    # A scalar to the left is not a parent, and neither is nothing at all.
    assert parent_of("post", resolved, order) is None
    assert parent_of("locale", resolved, order) is None


def test_a_parameter_not_in_the_order_has_no_parent() -> None:
    assert parent_of("stranger", {}, ["post"]) is None


# --- what the route said to do instead --------------------------------------


def test_binding_missing_carries_the_handler_the_route_named() -> None:
    def handler() -> str:
        return "gone"

    missing = BindingMissing(handler, "post")

    assert missing.handler is handler
    assert missing.parameter == "post"
    assert "No model bound for 'post'" in str(missing)


# --- a model that does not soft delete --------------------------------------


class Hard:
    """A model with no `with_trashed`, so `with_trashed()` has nothing to do."""

    rows = [type("Row", (), {"id": 1})()]

    @classmethod
    def query(cls) -> Any:
        class Plain:
            def where(self, key: str, value: Any) -> Any:
                return self

            async def first(self) -> Any:
                return Hard.rows[0]

        return Plain()


async def test_with_trashed_on_a_model_that_does_not_soft_delete_still_finds_it() -> None:
    found = await resolve(Hard, "1", trashed=True)

    assert found.id == 1


async def test_a_scoped_lookup_may_also_have_no_trash_to_include() -> None:
    class Parent:
        def comments(self) -> Any:
            class Plain:
                def where(self, key: str, value: Any) -> Any:
                    return self

                async def first(self) -> Any:
                    return Comment(1, "mine")

            return Plain()

    found = await resolve(
        Comment, "1", parent=Parent(), relationship="comments", trashed=True
    )

    assert found.slug == "mine"
