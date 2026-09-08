"""M5 — models, CRUD, casts, events, scopes, collections, pagination."""

from __future__ import annotations

from datetime import datetime

import pytest

from almasix.orm import (
    Collection,
    DB,
    MassAssignmentError,
    Model,
    ModelNotFoundError,
    Schema,
    SoftDeletes,
    relation,
)
from tests.orm_support import memory_db  # noqa: F401

pytestmark = pytest.mark.asyncio


class User(Model):
    fillable = ("email", "name", "votes", "meta", "active")
    casts = {"votes": "int", "meta": "json", "active": "bool"}
    hidden = ("meta",)

    def get_display_attribute(self, _value=None) -> str:
        return f"{self.name} <{self.email}>"

    @relation
    def posts(self):
        return self.has_many(Post)

    @relation
    def profile(self):
        return self.has_one(Profile)

    @relation
    def roles(self):
        return self.belongs_to_many(Role).with_pivot("level")

    @relation
    def comments(self):
        return self.morph_many(Comment, "commentable")


class Post(SoftDeletes, Model):
    fillable = ("title", "user_id", "published", "views")
    casts = {"published": "bool", "views": "int"}

    def scope_published(query):
        return query.where("published", True)

    @relation
    def author(self):
        return self.belongs_to(User)

    @relation
    def comments(self):
        return self.morph_many(Comment, "commentable")


class Profile(Model):
    timestamps = False
    fillable = ("user_id", "bio")

    @relation
    def user(self):
        return self.belongs_to(User)


class Role(Model):
    timestamps = False
    fillable = ("name",)

    @relation
    def users(self):
        return self.belongs_to_many(User)


class Comment(Model):
    timestamps = False
    fillable = ("body", "commentable_id", "commentable_type")


class Country(Model):
    timestamps = False
    fillable = ("name",)

    @relation
    def posts(self):
        return self.has_many_through(Post, User, "country_id", "user_id")


async def schema(memory_db) -> None:
    await Schema.create(
        "users",
        lambda t: (
            t.id(),
            t.string("email"),
            t.string("name").nullable(),
            t.integer("votes").default(0),
            t.json("meta").nullable(),
            t.boolean("active").default(True),
            t.integer("country_id").nullable(),
            t.timestamps(),
            t.unique_index(["email"]),
        ),
    )
    await Schema.create(
        "posts",
        lambda t: (
            t.id(),
            t.string("title"),
            t.integer("user_id").nullable(),
            t.boolean("published").default(False),
            t.integer("views").default(0),
            t.timestamps(),
            t.soft_deletes(),
        ),
    )
    await Schema.create(
        "profiles",
        lambda t: (t.id(), t.integer("user_id"), t.string("bio").nullable()),
    )
    await Schema.create(
        "roles",
        lambda t: (t.id(), t.string("name")),
    )
    await Schema.create(
        "role_user",
        lambda t: (
            t.integer("role_id"),
            t.integer("user_id"),
            t.string("level").nullable(),
        ),
    )
    await Schema.create(
        "comments",
        lambda t: (
            t.id(),
            t.string("body"),
            t.morphs("commentable"),
        ),
    )
    await Schema.create(
        "countries",
        lambda t: (t.id(), t.string("name")),
    )


async def test_create_find_update_delete(memory_db) -> None:
    await schema(memory_db)
    user = await User.create(email="a@b.c", name="Ada")
    assert user.exists and user.id == 1
    found = await User.find(1)
    assert found is not None and found.email == "a@b.c"
    await found.update(name="Ada Lovelace")
    assert (await User.find(1)).name == "Ada Lovelace"
    assert await User.find_or_fail(1)
    with pytest.raises(ModelNotFoundError):
        await User.find_or_fail(99)
    await found.delete()
    assert await User.find(1) is None


async def test_mass_assignment_guard(memory_db) -> None:
    await schema(memory_db)

    class Locked(Model):
        table = "users"
        timestamps = False

    with pytest.raises(MassAssignmentError):
        Locked().fill({"email": "x"})


async def test_casts_dirty_and_serialization(memory_db) -> None:
    await schema(memory_db)
    user = await User.create(
        email="a@b.c",
        name="Ada",
        votes="3",
        meta={"lang": "py"},
        active=1,
    )
    assert user.votes == 3
    assert user.meta == {"lang": "py"}
    assert user.active is True
    user.votes = 4
    assert user.is_dirty("votes")
    await user.save()
    assert user.was_changed("votes")
    payload = user.to_dict()
    assert "meta" not in payload
    assert payload["email"] == "a@b.c"


async def test_query_builder_crud_and_aggregates(memory_db) -> None:
    await schema(memory_db)
    await User.create(email="a@b.c", name="Ada", votes=2)
    await User.create(email="b@b.c", name="Grace", votes=5)
    assert await User.query().count() == 2
    assert await User.query().sum("votes") == 7
    assert await User.query().where("votes", ">=", 5).value("name") == "Grace"
    names = await User.query().order_by("name").pluck("name")
    assert names.all() == ["Ada", "Grace"]
    await User.query().where("name", "Ada").increment("votes", 3)
    assert (await User.where("name", "Ada").first()).votes == 5
    raw = await DB.select("SELECT COUNT(*) AS n FROM users")
    assert int(raw[0]["n"]) == 2


async def test_first_or_create_and_upsert(memory_db) -> None:
    await schema(memory_db)
    first = await User.query().first_or_create({"email": "a@b.c"}, {"name": "Ada"})
    again = await User.query().first_or_create({"email": "a@b.c"}, {"name": "Other"})
    assert first.is_(again) and again.name == "Ada"
    await User.query().upsert(
        {"email": "a@b.c", "name": "Updated"},
        unique_by=["email"],
        update=["name"],
    )
    assert (await User.where("email", "a@b.c").first()).name == "Updated"


async def test_transactions_rollback(memory_db) -> None:
    await schema(memory_db)
    try:
        async with DB.transaction():
            await User.create(email="a@b.c", name="Ada")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert await User.query().count() == 0


async def test_has_many_belongs_to_and_eager_load(memory_db) -> None:
    await schema(memory_db)
    ada = await User.create(email="a@b.c", name="Ada")
    grace = await User.create(email="g@b.c", name="Grace")
    await Post.create(title="One", user_id=ada.id, published=True)
    await Post.create(title="Two", user_id=ada.id, published=False)
    await Post.create(title="Three", user_id=grace.id, published=True)

    posts = await ada.posts().order_by("title").get()
    assert [post.title for post in posts] == ["One", "Two"]
    author = await posts[0].author().first()
    assert author is not None and author.is_(ada)

    loaded = await Post.query().with_("author").order_by("title").get()
    assert loaded[0].relation_loaded("author")
    assert loaded[0].author.name == "Ada"

    counted = await User.query().with_count("posts").order_by("id").get()
    assert counted[0]._extra["posts_count"] == 2
    has = await User.query().has("posts", ">=", 2).get()
    assert len(has) == 1 and has[0].is_(ada)


async def test_belongs_to_many_attach_sync(memory_db) -> None:
    await schema(memory_db)
    ada = await User.create(email="a@b.c", name="Ada")
    admin = await Role.create(name="admin")
    editor = await Role.create(name="editor")
    await ada.roles().attach(admin, {"level": "lead"})
    await ada.roles().attach(editor)
    names = [role.name for role in await ada.roles().get()]
    assert set(names) == {"admin", "editor"}
    await ada.roles().sync([admin.id])
    remaining = await ada.roles().get()
    assert [role.name for role in remaining] == ["admin"]


async def test_soft_deletes_and_restore(memory_db) -> None:
    await schema(memory_db)
    ada = await User.create(email="a@b.c", name="Ada")
    post = await Post.create(title="Gone", user_id=ada.id, published=True)
    await post.delete()
    assert await Post.query().count() == 0
    assert await Post.with_trashed().count() == 1
    assert await Post.only_trashed().count() == 1
    trashed = await Post.only_trashed().first()
    await trashed.restore()
    assert await Post.query().count() == 1


async def test_local_scopes_and_events(memory_db) -> None:
    await schema(memory_db)
    seen: list[str] = []
    Post.listen("creating", lambda model: seen.append("creating"))
    Post.listen("created", lambda model: seen.append("created"))
    ada = await User.create(email="a@b.c", name="Ada")
    await Post.create(title="Pub", user_id=ada.id, published=True)
    await Post.create(title="Draft", user_id=ada.id, published=False)
    assert seen == ["creating", "created", "creating", "created"]
    published = await Post.query().published().get()
    assert [post.title for post in published] == ["Pub"]


async def test_morph_many(memory_db) -> None:
    await schema(memory_db)
    ada = await User.create(email="a@b.c", name="Ada")
    post = await Post.create(title="Hello", user_id=ada.id, published=True)
    await post.comments().create(body="nice")
    await ada.comments().create(body="from user")
    comments = await post.comments().get()
    assert [c.body for c in comments] == ["nice"]


async def test_has_many_through(memory_db) -> None:
    await schema(memory_db)
    tz = await Country.create(name="TZ")
    ada = User()
    ada.force_fill({"email": "a@b.c", "name": "Ada", "country_id": tz.id})
    await ada.save()
    await Post.create(title="From TZ", user_id=ada.id, published=True)
    posts = await tz.posts().get()
    assert [post.title for post in posts] == ["From TZ"]


async def test_pagination_and_collection(memory_db) -> None:
    await schema(memory_db)
    for index in range(5):
        await User.create(email=f"u{index}@b.c", name=f"U{index}", votes=index)
    page = await User.query().order_by("id").paginate(2, page=2)
    assert page.current_page == 2 and page.total == 5
    assert len(page.items) == 2
    payload = page.to_dict()
    assert payload["last_page"] == 3
    names = Collection([user.name for user in await User.query().order_by("id").get()])
    assert names.filter(lambda n: n.endswith("1")).values().all() == ["U1"]


async def test_unloaded_relation_fails_loudly(memory_db) -> None:
    await schema(memory_db)
    ada = await User.create(email="a@b.c", name="Ada")
    from almasix.orm import RelationNotLoadedError

    with pytest.raises(RelationNotLoadedError):
        len(ada.posts)
