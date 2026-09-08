"""M41 part 1 — has-one-of-many, default models, and chaperone."""

from __future__ import annotations

import pytest

from avalon.orm import Collection, Model, Schema, relation
from tests.orm_support import memory_db  # noqa: F401


class User(Model):
    table = "users"
    fillable = ("name",)

    @relation
    def orders(self):
        return self.has_many(Order)

    @relation
    def latest_order(self):
        return self.has_many(Order).latest_of_many()

    @relation
    def oldest_order(self):
        return self.has_many(Order).oldest_of_many()

    @relation
    def largest_order(self):
        return self.has_many(Order).of_many("price", "max")

    @relation
    def largest_published_order(self):
        return self.has_many(Order).of_many(
            "price", "max", lambda query: query.where("published", "=", 1)
        )

    @relation
    def newest_priciest_order(self):
        return self.has_many(Order).of_many({"price": "max", "id": "min"})

    @relation
    def single_order(self):
        return self.has_many(Order).one()

    @relation
    def chaperoned_orders(self):
        return self.has_many(Order).chaperone()

    @relation
    def named_chaperoned_orders(self):
        return self.has_many(Order).chaperone("buyer")

    @relation
    def profile(self):
        return self.has_one(Profile)

    @relation
    def profile_or_default(self):
        return self.has_one(Profile).with_default({"bio": "No bio yet"})

    @relation
    def profile_or_zero_arg_default(self):
        return self.has_one(Profile).with_default(lambda: {"bio": "Nothing"})

    @relation
    def chaperoned_profile(self):
        return self.has_one(Profile).chaperone()


class Order(Model):
    table = "orders"
    fillable = ("user_id", "price", "published")

    @relation
    def user(self):
        return self.belongs_to(User)

    @relation
    def buyer(self):
        return self.belongs_to(User, "user_id")

    @relation
    def user_or_guest(self):
        return self.belongs_to(User).with_default({"name": "Guest"})

    @relation
    def user_or_empty(self):
        return self.belongs_to(User).with_default()

    @relation
    def user_or_callable(self):
        return self.belongs_to(User).with_default(
            lambda default, order: default.force_fill({"name": f"Buyer of {order.price}"})
        )

    @relation
    def user_or_one_arg(self):
        return self.belongs_to(User).with_default(
            lambda default: default.force_fill({"name": "One arg"})
        )

    @relation
    def user_or_mapping_callable(self):
        return self.belongs_to(User).with_default(lambda default, order: {"name": "Mapped"})


class Profile(Model):
    table = "profiles"
    fillable = ("user_id", "bio")

    @relation
    def user(self):
        return self.belongs_to(User)


class Post(Model):
    table = "posts"
    fillable = ("title",)

    @relation
    def comments(self):
        return self.morph_many(Comment, "commentable")

    @relation
    def chaperoned_comments(self):
        return self.morph_many(Comment, "commentable").chaperone("commentable")

    @relation
    def latest_comment(self):
        return self.morph_many(Comment, "commentable").latest_of_many()

    @relation
    def image(self):
        return self.morph_one(Image, "imageable")

    @relation
    def image_or_default(self):
        return self.morph_one(Image, "imageable").with_default({"url": "placeholder.png"})


class Comment(Model):
    table = "comments"
    fillable = ("commentable_id", "commentable_type", "body")


class Image(Model):
    table = "images"
    fillable = ("imageable_id", "imageable_type", "url")


async def _schema() -> None:
    await Schema.create("users", lambda t: (t.id(), t.string("name"), t.timestamps()))
    await Schema.create(
        "orders",
        lambda t: (
            t.id(),
            t.foreign_id("user_id"),
            t.integer("price"),
            t.integer("published").default(1),
            t.timestamps(),
        ),
    )
    await Schema.create(
        "profiles",
        lambda t: (t.id(), t.foreign_id("user_id"), t.string("bio"), t.timestamps()),
    )
    await Schema.create("posts", lambda t: (t.id(), t.string("title"), t.timestamps()))
    await Schema.create(
        "comments",
        lambda t: (
            t.id(),
            t.integer("commentable_id"),
            t.string("commentable_type"),
            t.string("body"),
            t.timestamps(),
        ),
    )
    await Schema.create(
        "images",
        lambda t: (
            t.id(),
            t.integer("imageable_id"),
            t.string("imageable_type"),
            t.string("url"),
            t.timestamps(),
        ),
    )


async def _seed() -> tuple[User, User]:
    await _schema()
    ada = await User.create(name="Ada")
    grace = await User.create(name="Grace")
    await Order.create(user_id=ada.id, price=10, published=1)
    await Order.create(user_id=ada.id, price=90, published=0)
    await Order.create(user_id=ada.id, price=50, published=1)
    await Order.create(user_id=grace.id, price=30, published=1)
    return ada, grace


# --- has one of many ----------------------------------------------------------


@pytest.mark.asyncio
async def test_latest_of_many_picks_the_newest_row(memory_db) -> None:
    ada, grace = await _seed()

    assert (await ada.latest_order().get()).price == 50
    assert (await grace.latest_order().get()).price == 30


@pytest.mark.asyncio
async def test_oldest_of_many_picks_the_first_row(memory_db) -> None:
    ada, _ = await _seed()

    assert (await ada.oldest_order().get()).price == 10


@pytest.mark.asyncio
async def test_of_many_picks_by_an_aggregate_column(memory_db) -> None:
    ada, grace = await _seed()

    assert (await ada.largest_order().get()).price == 90
    assert (await grace.largest_order().get()).price == 30


@pytest.mark.asyncio
async def test_of_many_accepts_a_constraining_callback(memory_db) -> None:
    ada, _ = await _seed()

    # 90 is the biggest order but it is unpublished, so 50 wins.
    assert (await ada.largest_published_order().get()).price == 50


@pytest.mark.asyncio
async def test_of_many_breaks_ties_across_several_columns(memory_db) -> None:
    ada, _ = await _seed()
    await Order.create(user_id=ada.id, price=90, published=1)

    # Two orders cost 90; the mapping asks for the lower id of the two.
    found = await ada.newest_priciest_order().get()
    assert found.price == 90
    assert found.published == 0


@pytest.mark.asyncio
async def test_of_many_eager_loads_one_row_per_parent(memory_db) -> None:
    await _seed()

    users = await User.with_relations("latest_order", "largest_order").get()

    assert [user.latest_order.price for user in users] == [50, 30]
    assert [user.largest_order.price for user in users] == [90, 30]


@pytest.mark.asyncio
async def test_of_many_eager_load_respects_the_callback(memory_db) -> None:
    users = await _one_query_users("largest_published_order")

    assert [user.largest_published_order.price for user in users] == [50, 30]


async def _one_query_users(relation_name: str) -> Collection:
    await _seed()
    return await User.with_relations(relation_name).get()


@pytest.mark.asyncio
async def test_one_narrows_a_has_many_to_a_single_model(memory_db) -> None:
    ada, _ = await _seed()

    found = await ada.single_order().get()

    assert isinstance(found, Order)
    assert found.price == 10


@pytest.mark.asyncio
async def test_one_of_many_works_on_morph_relations(memory_db) -> None:
    await _seed()
    post = await Post.create(title="Hello")
    await Comment.create(commentable_id=post.id, commentable_type="Post", body="first")
    await Comment.create(commentable_id=post.id, commentable_type="Post", body="second")

    assert (await post.latest_comment().get()).body == "second"

    loaded = await Post.with_relations("latest_comment").first()
    assert loaded.latest_comment.body == "second"


@pytest.mark.asyncio
async def test_of_many_returns_none_without_related_rows(memory_db) -> None:
    await _seed()
    lonely = await User.create(name="Lonely")

    assert await lonely.latest_order().get() is None


# --- default models -----------------------------------------------------------


@pytest.mark.asyncio
async def test_belongs_to_with_default_returns_a_seeded_model(memory_db) -> None:
    await _schema()
    order = await Order.create(user_id=None, price=5)

    guest = await order.user_or_guest().get()

    assert guest.name == "Guest"
    assert guest.exists is False


@pytest.mark.asyncio
async def test_belongs_to_with_default_accepts_no_attributes(memory_db) -> None:
    await _schema()
    order = await Order.create(user_id=None, price=5)

    assert isinstance(await order.user_or_empty().get(), User)


@pytest.mark.asyncio
async def test_belongs_to_with_default_accepts_callables(memory_db) -> None:
    await _schema()
    order = await Order.create(user_id=None, price=5)

    assert (await order.user_or_callable().get()).name == "Buyer of 5"
    assert (await order.user_or_one_arg().get()).name == "One arg"
    assert (await order.user_or_mapping_callable().get()).name == "Mapped"


@pytest.mark.asyncio
async def test_default_model_is_skipped_when_the_relation_exists(memory_db) -> None:
    ada, _ = await _seed()
    order = await Order.where("user_id", "=", ada.id).first()

    assert (await order.user_or_guest().get()).name == "Ada"


@pytest.mark.asyncio
async def test_default_models_apply_to_eager_loads(memory_db) -> None:
    await _schema()
    await Order.create(user_id=None, price=5)

    order = await Order.with_relations("user_or_guest", "user").first()

    assert order.user_or_guest.name == "Guest"
    assert order.user is None


@pytest.mark.asyncio
async def test_has_one_and_morph_one_support_defaults(memory_db) -> None:
    await _schema()
    user = await User.create(name="Ada")
    post = await Post.create(title="Hello")

    assert (await user.profile_or_default().get()).bio == "No bio yet"
    assert (await post.image_or_default().get()).url == "placeholder.png"
    assert await user.profile().get() is None
    assert await post.image().get() is None

    loaded = await User.with_relations("profile_or_default").first()
    assert loaded.profile_or_default.bio == "No bio yet"


# --- chaperone ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_chaperone_hydrates_the_parent_on_children(memory_db) -> None:
    ada, _ = await _seed()

    orders = await ada.chaperoned_orders().get()

    assert [order.user.name for order in orders] == ["Ada", "Ada", "Ada"]
    assert orders[0].user is ada


@pytest.mark.asyncio
async def test_chaperone_hydrates_during_eager_loading(memory_db) -> None:
    await _seed()

    users = await User.with_relations("chaperoned_orders").get()

    for user in users:
        for order in user.chaperoned_orders:
            assert order.user is user


@pytest.mark.asyncio
async def test_chaperone_accepts_an_explicit_relation_name(memory_db) -> None:
    ada, _ = await _seed()

    orders = await ada.named_chaperoned_orders().get()

    assert orders[0].buyer is ada


@pytest.mark.asyncio
async def test_chaperone_works_on_morph_many(memory_db) -> None:
    await _schema()
    post = await Post.create(title="Hello")
    await Comment.create(commentable_id=post.id, commentable_type="Post", body="hi")

    comments = await post.chaperoned_comments().get()
    assert comments[0].commentable is post

    loaded = await Post.with_relations("chaperoned_comments").first()
    assert loaded.chaperoned_comments[0].commentable is loaded


@pytest.mark.asyncio
async def test_unchaperoned_children_do_not_gain_a_parent_relation(memory_db) -> None:
    ada, _ = await _seed()

    orders = await ada.orders().get()

    assert orders[0].relation_loaded("user") is False


@pytest.mark.asyncio
async def test_chaperone_hydrates_the_parent_on_a_has_one(memory_db) -> None:
    await _schema()
    user = await User.create(name="Ada")
    await Profile.create(user_id=user.id, bio="Analyst")

    profile = await user.chaperoned_profile().get()

    assert profile.user is user


@pytest.mark.asyncio
async def test_with_default_accepts_a_zero_argument_callable(memory_db) -> None:
    await _schema()
    user = await User.create(name="Ada")

    assert (await user.profile_or_zero_arg_default().get()).bio == "Nothing"
