"""M23 API Resources — transformation, conditionals, wrapping, pagination."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from almasix.http.resources import (
    MISSING,
    AnonymousResourceCollection,
    JsonResource,
    MergeValue,
    MissingValue,
    ResourceCollection,
    ResourceJSONResponse,
    filter_data,
    is_missing,
    is_paginator,
)
from almasix.http.response import make_response
from almasix.orm import Schema
from almasix.orm.collection import Collection
from almasix.orm.model import Model
from almasix.orm.pagination import Paginator, SimplePaginator
from tests.orm_support import memory_db  # noqa: F401

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def wrapped() -> Iterator[None]:
    """Every test starts from Laravel's default `data` wrapping."""
    JsonResource.wrap_with("data")
    yield
    JsonResource.wrap_with("data")


def body(response: Any) -> Any:
    return json.loads(response.body.decode())


# --- fixtures -----------------------------------------------------------


class UserResource(JsonResource):
    def to_dict(self, request: Any = None) -> dict[str, Any]:
        return {"id": self.id, "name": self.name}


class UserCollection(ResourceCollection):
    collects = UserResource


class GuessingCollection(ResourceCollection):
    """No ``collects``; the guess should find ``GuessingResource`` below."""


class GuessingResource(JsonResource):
    def to_dict(self, request: Any = None) -> dict[str, Any]:
        return {"guessed": True}


ADA = {"id": 1, "name": "Ada"}
BOB = {"id": 2, "name": "Bob"}


# --- the transformation --------------------------------------------------


def test_a_resource_shapes_one_record() -> None:
    assert UserResource(ADA).resolve() == {"id": 1, "name": "Ada"}


def test_attributes_fall_through_to_the_underlying_object() -> None:
    resource = UserResource(ADA)
    assert resource.name == "Ada"
    assert resource["id"] == 1
    with pytest.raises(AttributeError):
        resource.nope  # noqa: B018


def test_attributes_fall_through_to_an_object_too() -> None:
    class Plain:
        title = "Post"

    resource = JsonResource(Plain())
    assert resource.title == "Post"
    assert resource["title"] == "Post"


def test_the_default_transformation_serializes_what_it_was_given() -> None:
    assert JsonResource(ADA).resolve() == ADA
    assert JsonResource(None).resolve() == {}
    assert JsonResource("plain").resolve() == "plain"

    class Serializable:
        def to_dict(self) -> dict[str, int]:
            return {"n": 1}

    assert JsonResource(Serializable()).resolve() == {"n": 1}


def test_a_nested_resource_is_resolved_and_filtered_too() -> None:
    class ProfileResource(JsonResource):
        def to_dict(self, request: Any = None) -> dict[str, Any]:
            return {"name": self.name, "secret": self.when(False, "hidden")}

    class AccountResource(JsonResource):
        def to_dict(self, request: Any = None) -> dict[str, Any]:
            return {
                "id": self.id,
                "profile": ProfileResource(self.resource),
                "friends": [ProfileResource(BOB)],
            }

    assert AccountResource(ADA).resolve() == {
        "id": 1,
        "profile": {"name": "Ada"},
        "friends": [{"name": "Bob"}],
    }


def test_make_and_repr() -> None:
    assert UserResource.make(ADA).resolve() == {"id": 1, "name": "Ada"}
    assert "UserResource" in repr(UserResource(ADA))


# --- conditional attributes ----------------------------------------------


def test_when_includes_a_value_only_if_the_condition_holds() -> None:
    class Conditional(JsonResource):
        def to_dict(self, request: Any = None) -> dict[str, Any]:
            return {
                "always": 1,
                "admin": self.when(self.resource["admin"], "secret"),
                "lazy": self.when(lambda: self.resource["admin"], lambda: "computed"),
                "fallback": self.when(False, "no", "yes"),
                "lazy_fallback": self.when(False, "no", lambda: "computed default"),
            }

    assert Conditional({"admin": False}).resolve() == {
        "always": 1,
        "fallback": "yes",
        "lazy_fallback": "computed default",
    }
    assert Conditional({"admin": True}).resolve() == {
        "always": 1,
        "admin": "secret",
        "lazy": "computed",
        "fallback": "yes",
        "lazy_fallback": "computed default",
    }


def test_unless_is_the_inverse_of_when() -> None:
    resource = JsonResource({})
    assert resource.unless(False, "shown") == "shown"
    assert is_missing(resource.unless(True, "shown"))
    assert resource.unless(lambda: True, "no", "default") == "default"


def test_merge_when_splices_into_the_parent() -> None:
    class Merging(JsonResource):
        def to_dict(self, request: Any = None) -> dict[str, Any]:
            return {
                "id": 1,
                "merged": self.merge_when(self.resource["admin"], {"role": "admin", "level": 9}),
                "always": self.merge({"seen": True}),
                "never": self.merge_unless(self.resource["admin"], {"role": "guest"}),
            }

    assert Merging({"admin": True}).resolve() == {
        "id": 1,
        "role": "admin",
        "level": 9,
        "seen": True,
    }
    assert Merging({"admin": False}).resolve() == {"id": 1, "seen": True, "role": "guest"}


def test_merge_when_takes_a_callable_and_renumbers_lists() -> None:
    resource = JsonResource({})
    assert filter_data({"a": resource.merge_when(True, lambda: ["x", "y"])}) == {0: "x", 1: "y"}
    assert filter_data([resource.merge_when(True, ["x", "y"]), "z"]) == ["x", "y", "z"]
    assert filter_data([resource.merge_when(False, ["x"]), "z"]) == ["z"]


def test_a_scalar_merge_keeps_its_value() -> None:
    assert MergeValue("solo").items() == [(0, "solo")]


def test_when_has_reads_the_attribute_when_it_exists() -> None:
    resource = JsonResource({"name": "Ada"})
    assert resource.when_has("name") == "Ada"
    assert resource.when_has("name", "override") == "override"
    assert resource.when_has("name", lambda: "computed") == "computed"
    assert is_missing(resource.when_has("missing"))
    assert resource.when_has("missing", default="fallback") == "fallback"
    assert resource.when_has("missing", default=lambda: "lazy") == "lazy"


def test_when_has_falls_back_to_plain_attributes() -> None:
    class Plain:
        title = "Post"

    resource = JsonResource(Plain())
    assert resource.when_has("title") == "Post"
    assert is_missing(resource.when_has("nope"))


def test_when_not_null_drops_nulls() -> None:
    resource = JsonResource({})
    assert resource.when_not_null("value") == "value"
    assert resource.when_not_null(lambda: "computed") == "computed"
    assert is_missing(resource.when_not_null(None))
    assert resource.when_not_null(None, "fallback") == "fallback"
    assert resource.when_not_null(None, lambda: "lazy") == "lazy"


def test_conditionals_are_missing_without_a_model_underneath() -> None:
    resource = JsonResource({"a": 1})
    assert is_missing(resource.when_loaded("posts"))
    assert is_missing(resource.when_counted("posts"))
    assert is_missing(resource.when_aggregated("posts", "votes", "sum"))
    assert is_missing(resource.when_pivot_loaded("role_user", "x"))
    assert is_missing(resource.when_appended("full_name"))
    assert resource.when_loaded("posts", default="none") == "none"


# --- collections ---------------------------------------------------------


def test_collection_wraps_every_item() -> None:
    collection = UserResource.collection([ADA, BOB])
    assert isinstance(collection, AnonymousResourceCollection)
    assert collection.resolve() == [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Bob"}]
    assert len(collection) == 2
    assert collection.count() == 2
    assert [item.name for item in collection] == ["Ada", "Bob"]
    assert "2 items" in repr(collection)


def test_a_declared_collection_uses_its_collects() -> None:
    assert UserCollection([ADA]).resolve() == [{"id": 1, "name": "Ada"}]
    assert UserCollection.resource_class() is UserResource


def test_a_collection_guesses_its_resource_class_from_its_name() -> None:
    assert GuessingCollection.resource_class() is GuessingResource
    assert GuessingCollection([ADA]).resolve() == [{"guessed": True}]


def test_a_collection_without_a_match_falls_back_to_the_base_resource() -> None:
    class OrphanCollection(ResourceCollection):
        pass

    class Nameless(ResourceCollection):
        pass

    assert OrphanCollection.resource_class() is JsonResource
    assert Nameless.resource_class() is JsonResource
    assert OrphanCollection([ADA]).resolve() == [ADA]


def test_preserve_keys_keeps_a_keyed_collection_keyed() -> None:
    class Keyed(ResourceCollection):
        collects = UserResource
        preserve_keys = True

    keyed = Keyed({"first": ADA, "second": BOB})
    assert keyed.resolve() == {
        "first": {"id": 1, "name": "Ada"},
        "second": {"id": 2, "name": "Bob"},
    }
    assert [item.name for item in keyed] == ["Ada", "Bob"]


def test_a_keyed_collection_renumbers_without_preserve_keys() -> None:
    assert UserCollection({"first": ADA}).resolve() == [{"id": 1, "name": "Ada"}]


def test_an_anonymous_collection_can_preserve_keys_too() -> None:
    class Keyed(AnonymousResourceCollection):
        preserve_keys = True

    keyed = Keyed({"first": ADA}, UserResource)
    assert keyed.resolve() == {"first": {"id": 1, "name": "Ada"}}
    assert Keyed({"first": ADA}, UserResource).resource_class() is JsonResource
    assert AnonymousResourceCollection({"a": ADA}, UserResource).resolve() == [
        {"id": 1, "name": "Ada"}
    ]


def test_resources_nest_inside_other_resources() -> None:
    class PostResource(JsonResource):
        def to_dict(self, request: Any = None) -> dict[str, Any]:
            return {
                "title": self.resource["title"],
                "author": UserResource(self.resource["author"]),
            }

    resolved = PostResource({"title": "Hello", "author": ADA}).response()
    # Nested resources are not wrapped — only the outermost one is.
    assert body(resolved) == {"data": {"title": "Hello", "author": {"id": 1, "name": "Ada"}}}


# --- responses and wrapping ----------------------------------------------


def test_the_outermost_resource_is_wrapped_in_data() -> None:
    assert body(UserResource(ADA).response()) == {"data": {"id": 1, "name": "Ada"}}


def test_wrapping_can_be_disabled_and_renamed() -> None:
    JsonResource.without_wrapping()
    assert body(UserResource(ADA).response()) == {"id": 1, "name": "Ada"}

    JsonResource.wrap_with("record")
    assert body(UserResource(ADA).response()) == {"record": {"id": 1, "name": "Ada"}}


def test_one_resource_can_wrap_differently_from_the_rest() -> None:
    class Wrapped(JsonResource):
        wrap = "user"

    assert body(Wrapped(ADA).response()) == {"user": ADA}
    assert body(JsonResource(ADA).response()) == {"data": ADA}


def test_data_is_not_wrapped_twice() -> None:
    class AlreadyWrapped(JsonResource):
        def to_dict(self, request: Any = None) -> dict[str, Any]:
            return {"data": [1, 2]}

    assert body(AlreadyWrapped(ADA).response()) == {"data": [1, 2]}


def test_with_adds_meta_to_every_response() -> None:
    class Metadata(JsonResource):
        def with_(self, request: Any = None) -> dict[str, Any]:
            return {"meta": {"version": 1}}

    assert body(Metadata(ADA).response()) == {"data": ADA, "meta": {"version": 1}}


def test_additional_adds_meta_to_one_response() -> None:
    resource = UserResource(ADA).additional({"meta": {"key": "value"}})
    assert body(resource.response()) == {
        "data": {"id": 1, "name": "Ada"},
        "meta": {"key": "value"},
    }


def test_additional_data_survives_disabled_wrapping() -> None:
    JsonResource.without_wrapping()
    assert body(UserResource(ADA).additional({"meta": 1}).response()) == {
        "id": 1,
        "name": "Ada",
        "meta": 1,
    }

    class Listing(JsonResource):
        def to_dict(self, request: Any = None) -> list[int]:
            return [1, 2]

    assert body(Listing(ADA).additional({"meta": 1}).response()) == {"data": [1, 2], "meta": 1}
    assert body(Listing(ADA).response()) == [1, 2]


def test_status_and_headers_are_configurable() -> None:
    response = UserResource(ADA).status(201).header("X-Made", "yes").headers({"X-More": "1"}).response()
    assert response.status_code == 201
    assert response.headers["x-made"] == "yes"
    assert response.headers["x-more"] == "1"


def test_with_response_can_tweak_the_response() -> None:
    class Tweaked(JsonResource):
        def with_response(self, request: Any, response: Any) -> None:
            response.headers["X-Tweaked"] = "1"

    assert Tweaked(ADA).response().headers["x-tweaked"] == "1"


def test_a_resource_returned_from_a_controller_becomes_a_response() -> None:
    response = make_response(UserResource(ADA))
    assert response.status_code == 200
    assert body(response) == {"data": {"id": 1, "name": "Ada"}}
    assert body(make_response(UserResource.collection([ADA]))) == {
        "data": [{"id": 1, "name": "Ada"}]
    }


def test_the_renderer_handles_dates_decimals_and_uuids() -> None:
    payload = {
        "when": datetime(2026, 9, 8, 12, 30, tzinfo=UTC),
        "day": date(2026, 9, 8),
        "amount": Decimal("1.50"),
        "id": UUID("00000000-0000-0000-0000-000000000001"),
        "tags": {"a"},
        "other": object(),
    }
    rendered = json.loads(ResourceJSONResponse(payload).render(payload).decode())
    assert rendered["when"] == "2026-09-08T12:30:00+00:00"
    assert rendered["day"] == "2026-09-08"
    assert rendered["amount"] == 1.5
    assert rendered["id"] == "00000000-0000-0000-0000-000000000001"
    assert rendered["tags"] == ["a"]
    assert "object" in rendered["other"]


def test_the_renderer_serializes_nested_objects_that_know_how() -> None:
    class Node:
        def to_dict(self) -> dict[str, int]:
            return {"n": 1}

    rendered = json.loads(ResourceJSONResponse({"node": Node()}).render({"node": Node()}).decode())
    assert rendered == {"node": {"n": 1}}


# --- missing values ------------------------------------------------------


def test_the_missing_marker_is_a_falsy_singleton() -> None:
    assert MissingValue() is MISSING
    assert not MISSING
    assert repr(MISSING) == "<missing>"
    assert is_missing(MISSING)
    assert not is_missing("value")


def test_filtering_reaches_into_nested_structures() -> None:
    assert filter_data({"a": {"b": MISSING, "c": 1}}) == {"a": {"c": 1}}
    assert filter_data([{"b": MISSING}, [MISSING, 2]]) == [{}, [2]]
    assert filter_data("scalar") == "scalar"


def test_a_merge_drops_the_missing_values_inside_it() -> None:
    assert filter_data({"a": MergeValue({"keep": 1, "drop": MISSING})}) == {"keep": 1}
    assert filter_data({"a": MergeValue([MISSING, "kept"])}) == {0: "kept"}


# --- edges ---------------------------------------------------------------


def test_conditions_may_be_callables() -> None:
    resource = JsonResource({})
    assert resource.merge_when(lambda: True, {"a": 1}).items() == [("a", 1)]
    assert is_missing(resource.merge_unless(lambda: True, {"a": 1}))


def test_resolve_serializes_a_transformation_that_returns_an_object() -> None:
    class Wrapper:
        def to_dict(self) -> dict[str, int]:
            return {"n": 1}

    class Indirect(JsonResource):
        def to_dict(self, request: Any = None) -> Any:
            return Wrapper()

    assert Indirect(ADA).resolve() == {"n": 1}


def test_dunder_lookups_do_not_reach_the_underlying_object() -> None:
    resource = UserResource(ADA)
    assert not hasattr(resource, "__deepcopy__")
    with pytest.raises(AttributeError):
        JsonResource.__getattr__(resource, "resource")


def test_a_response_accepts_an_explicit_request() -> None:
    class FakeRequest:
        url = "https://example.test/api/users"

    assert body(UserResource(ADA).response(FakeRequest())) == {"data": {"id": 1, "name": "Ada"}}


def test_a_pivot_that_is_not_an_orm_pivot_reports_its_table() -> None:
    from almasix.http.resources.resource import _pivot_table

    class Plain:
        table = "role_user"

    assert _pivot_table(Plain()) == "role_user"


def test_a_collection_exposes_the_paginator_behind_it() -> None:
    paginator = Paginator(Collection([ADA]), total=1, per_page=1, current_page=1)
    assert UserCollection(paginator).paginator() is paginator
    assert UserCollection([ADA]).paginator() is None


# --- pagination ----------------------------------------------------------


def test_a_paginator_is_recognised_by_shape() -> None:
    assert is_paginator(Paginator(Collection([]), 0, 15, 1))
    assert is_paginator(SimplePaginator(Collection([]), 15, 1, False))
    assert not is_paginator([ADA])


def test_a_paginated_collection_carries_meta() -> None:
    paginator = Paginator(Collection([ADA, BOB]), total=12, per_page=2, current_page=2)
    payload = body(UserCollection(paginator).response())
    assert payload["data"] == [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Bob"}]
    assert payload["meta"] == {
        "current_page": 2,
        "per_page": 2,
        "from": 3,
        "last_page": 6,
        "to": 4,
        "total": 12,
    }
    assert "links" not in payload


def test_a_simple_paginator_reports_whether_there_is_more() -> None:
    paginator = SimplePaginator(Collection([ADA]), per_page=1, current_page=1, has_more=True)
    payload = body(UserCollection(paginator).response())
    assert payload["meta"] == {"current_page": 1, "per_page": 1, "has_more": True}


def test_pagination_wins_over_disabled_wrapping() -> None:
    JsonResource.without_wrapping()
    paginator = Paginator(Collection([ADA]), total=1, per_page=15, current_page=1)
    payload = body(UserCollection(paginator).response())
    assert payload["data"] == [{"id": 1, "name": "Ada"}]
    assert payload["meta"]["total"] == 1


def test_pagination_information_is_a_hook() -> None:
    class Trimmed(ResourceCollection):
        collects = UserResource

        def pagination_information(
            self, request: Any, paginated: Any, default: dict[str, Any]
        ) -> dict[str, Any]:
            return {"meta": {"total": default["meta"]["total"]}}

    paginator = Paginator(Collection([ADA]), total=3, per_page=1, current_page=1)
    assert body(Trimmed(paginator).response())["meta"] == {"total": 3}


def test_links_appear_once_a_request_url_is_known() -> None:
    from almasix.http.resources.response import pagination_information

    class FakeRequest:
        url = "https://example.test/api/users?page=2&q=ada"

    paginator = Paginator(Collection([ADA]), total=30, per_page=10, current_page=2)
    information = pagination_information(FakeRequest(), paginator)
    assert information["meta"]["path"] == "https://example.test/api/users"
    assert information["links"] == {
        "first": "https://example.test/api/users?page=1",
        "last": "https://example.test/api/users?page=3",
        "prev": "https://example.test/api/users?page=1",
        "next": "https://example.test/api/users?page=3",
    }


def test_the_first_page_has_no_previous_link() -> None:
    from almasix.http.resources.response import pagination_information

    class FakeRequest:
        url = "https://example.test/api/users"

    paginator = Paginator(Collection([ADA]), total=1, per_page=10, current_page=1)
    links = pagination_information(FakeRequest(), paginator)["links"]
    assert links["prev"] is None
    assert links["next"] is None


def test_a_simple_paginator_has_no_last_link() -> None:
    from almasix.http.resources.response import pagination_information

    class FakeRequest:
        url = "https://example.test/api/users"

    paginator = SimplePaginator(Collection([ADA]), per_page=1, current_page=1, has_more=True)
    links = pagination_information(FakeRequest(), paginator)["links"]
    assert links["last"] is None
    assert links["next"] == "https://example.test/api/users?page=2"


def test_a_url_with_a_query_string_keeps_one_separator() -> None:
    from almasix.http.resources.response import _page_url

    assert _page_url("https://x.test/a?b=1", 2) == "https://x.test/a?b=1&page=2"


# --- against real models -------------------------------------------------


class Author(Model):
    table = "authors"
    fillable = ("name", "email")
    hidden = ("email",)
    timestamps = False


class Book(Model):
    table = "books"
    fillable = ("author_id", "title")
    timestamps = False

    def author(self) -> Any:
        return self.belongs_to(Author)


async def _schema() -> None:
    await Schema.create(
        "authors",
        lambda table: (table.id(), table.string("name"), table.string("email").nullable()),
    )
    await Schema.create(
        "books",
        lambda table: (table.id(), table.integer("author_id"), table.string("title")),
    )


async def test_a_resource_over_a_model_uses_its_attributes(memory_db: Any) -> None:  # noqa: F811
    del memory_db
    await _schema()
    author = await Author.create({"name": "Ada", "email": "ada@example.test"})

    class AuthorResource(JsonResource):
        def to_dict(self, request: Any = None) -> dict[str, Any]:
            return {"id": self.id, "name": self.name, "email": self.email}

    assert AuthorResource(author).resolve() == {
        "id": author.id,
        "name": "Ada",
        "email": "ada@example.test",
    }
    # The default shape honours the model's own hidden list.
    assert "email" not in JsonResource(author).resolve()


async def test_when_loaded_only_includes_eager_loaded_relations(memory_db: Any) -> None:  # noqa: F811
    del memory_db
    await _schema()
    author = await Author.create({"name": "Ada"})
    await Book.create({"author_id": author.id, "title": "Analytical Engine"})

    class BookResource(JsonResource):
        def to_dict(self, request: Any = None) -> dict[str, Any]:
            return {
                "title": self.title,
                "author": self.when_loaded("author"),
                "author_name": self.when_loaded("author", lambda author: author.name),
                "static": self.when_loaded("author", lambda: "loaded"),
            }

    lean = await Book.query().first()
    assert BookResource(lean).resolve() == {"title": "Analytical Engine"}

    eager = await Book.query().with_("author").first()
    resolved = BookResource(eager).resolve()
    assert resolved["author_name"] == "Ada"
    assert resolved["static"] == "loaded"
    assert resolved["author"]["name"] == "Ada"


async def test_when_counted_and_when_aggregated(memory_db: Any) -> None:  # noqa: F811
    del memory_db
    await _schema()
    author = await Author.create({"name": "Ada"})
    await Book.create({"author_id": author.id, "title": "One"})
    await Book.create({"author_id": author.id, "title": "Two"})

    class Counting(JsonResource):
        def to_dict(self, request: Any = None) -> dict[str, Any]:
            return {
                "books": self.when_counted("books"),
                "labelled": self.when_counted("books", lambda: "counted"),
                "missing": self.when_counted("chapters"),
                "fallback": self.when_counted("chapters", default=0),
            }

    class Writer(Author):
        table = "authors"

        def books(self) -> Any:
            return self.has_many(Book, "author_id")

    lean = await Writer.query().first()
    assert Counting(lean).resolve() == {"fallback": 0}

    counted = await Writer.query().with_count("books").first()
    resolved = Counting(counted).resolve()
    assert resolved["books"] == 2
    assert resolved["labelled"] == "counted"


async def test_when_has_reads_a_models_attributes(memory_db: Any) -> None:  # noqa: F811
    del memory_db
    await _schema()
    author = await Author.create({"name": "Ada"})
    resource = JsonResource(author)
    assert resource.when_has("name") == "Ada"
    assert is_missing(resource.when_has("nickname"))


async def test_when_loaded_accepts_a_plain_replacement_value(memory_db: Any) -> None:  # noqa: F811
    del memory_db
    await _schema()
    author = await Author.create({"name": "Ada"})
    await Book.create({"author_id": author.id, "title": "One"})
    book = await Book.query().with_("author").first()

    resource = JsonResource(book)
    assert resource.when_loaded("author", "present") == "present"
    assert resource.when_loaded("author", lambda relation, extra=None: relation.name) == "Ada"


async def test_when_pivot_loaded_reads_the_intermediate_row(memory_db: Any) -> None:  # noqa: F811
    del memory_db
    await Schema.create(
        "posts", lambda table: (table.id(), table.string("title"))
    )
    await Schema.create("tags", lambda table: (table.id(), table.string("name")))
    await Schema.create(
        "post_tag",
        lambda table: (
            table.id(),
            table.integer("post_id"),
            table.integer("tag_id"),
            table.string("added_by").nullable(),
        ),
    )

    class Tag(Model):
        table = "tags"
        fillable = ("name",)
        timestamps = False

    class Post(Model):
        table = "posts"
        fillable = ("title",)
        timestamps = False

        def tags(self) -> Any:
            return self.belongs_to_many(Tag, "post_tag", "post_id", "tag_id").with_pivot(
                "added_by"
            )

    post = await Post.create({"title": "Hello"})
    tag = await Tag.create({"name": "python"})
    await post.tags().attach(tag.id, {"added_by": "ada"})

    loaded = await Post.query().with_("tags").first()
    tagged = loaded.get_relations()["tags"][0]

    class TagResource(JsonResource):
        def to_dict(self, request: Any = None) -> dict[str, Any]:
            return {
                "name": self.name,
                "added_by": self.when_pivot_loaded(
                    "post_tag", lambda pivot: pivot.added_by
                ),
                "renamed": self.when_pivot_loaded_as("pivot", "post_tag", "yes"),
                "other_table": self.when_pivot_loaded("something_else", "no"),
            }

    assert TagResource(tagged).resolve() == {
        "name": "python",
        "added_by": "ada",
        "renamed": "yes",
    }
    # A tag loaded without its pivot has nothing to report.
    plain = await Tag.query().first()
    assert TagResource(plain).resolve() == {"name": "python"}


async def test_when_appended_follows_the_models_appends(memory_db: Any) -> None:  # noqa: F811
    del memory_db
    await _schema()

    class Loud(Author):
        table = "authors"
        appends = ("shouted",)

        def get_shouted_attribute(self) -> str:
            return str(self.name).upper()

    author = await Loud.create({"name": "Ada"})

    class Appending(JsonResource):
        def to_dict(self, request: Any = None) -> dict[str, Any]:
            return {
                "shouted": self.when_appended("shouted"),
                "override": self.when_appended("shouted", "given"),
                "absent": self.when_appended("nope"),
            }

    assert Appending(author).resolve() == {"shouted": "ADA", "override": "given"}


async def test_a_collection_over_a_real_paginator(memory_db: Any) -> None:  # noqa: F811
    del memory_db
    await _schema()
    for index in range(5):
        await Author.create({"name": f"Author {index}"})

    class NameResource(JsonResource):
        def to_dict(self, request: Any = None) -> dict[str, Any]:
            return {"name": self.name}

    paginator = await Author.query().paginate(per_page=2, page=1)
    payload = body(NameResource.collection(paginator).response())
    assert payload["data"] == [{"name": "Author 0"}, {"name": "Author 1"}]
    assert payload["meta"]["total"] == 5
    assert payload["meta"]["last_page"] == 3
