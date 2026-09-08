"""M30 — ``model:show``: one model, as it is declared and as it is stored.

The application under test is written into a temporary directory, model files
and all, because that is the only way to hold the line these tests exist for:
``model:show`` must find a model the way the application's own imports do, and
must report what it can check rather than what it can assume.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from avalon.console import repl
from avalon.console.command import Command
from avalon.console.commands import model_show
from avalon.console.kernel import ConsoleKernel
from avalon.orm import DB
from avalon.orm.schema import Schema

CONFIG: dict[str, str] = {
    "app.py": (
        'config = {"name": "Showcase", "env": "testing", "debug": False, "providers": []}\n'
    ),
    "logging.py": "config = {'default': 'null', 'channels': {'null': {'driver': 'null'}}}\n",
    "database.py": (
        "config = {'default': 'sqlite', 'connections': "
        "{'sqlite': {'driver': 'sqlite', 'database': ':memory:'}}}\n"
    ),
}

POST_MODEL = '''
"""The richest model in the test application."""

from enum import Enum

from avalon.orm import EnumCollection, Model, SoftDeletes, relation


class Status(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class PostObserver:
    def created(self, post):
        return None

    def deleting(self, post):
        return None


class Tally:
    """A listener that is an object rather than a function."""

    def __call__(self, post):
        return None


def log_saving(post):
    return None


class Post(SoftDeletes, Model):
    table = "posts"
    fillable = ("title", "body", "status", "meta", "published_at")
    hidden = ("body",)
    appends = ("excerpt",)
    casts = {
        "status": Status,
        "meta": "json",
        "published_at": "datetime",
        "labels": EnumCollection.of(Status),
    }

    @classmethod
    def scope_published(cls, query):
        return query.where("status", "=", Status.PUBLISHED.value)

    def get_excerpt_attribute(self, value=None):
        return str(self.get_raw_attribute("body") or "")[:20]

    @relation
    def author(self):
        from app.models.user import User

        return self.belongs_to(User)

    @relation
    def comments(self):
        from app.models.support import Comment

        return self.has_many(Comment)

    @relation
    def tags(self):
        from app.models.support import Tag

        return self.belongs_to_many(Tag)

    @relation
    def cover(self):
        from app.models.support import Image

        return self.morph_one(Image, "imageable")

    @relation
    def broken(self):
        raise RuntimeError("this relation needs a loaded row")


Post.observe(PostObserver)
Post.listen("saving", log_saving)
Post.listen("updating", Tally())
Post.resolve_relation_using("editor", lambda post: post.belongs_to(Post))
'''

USER_MODEL = '''
"""A user, with an accessor object and no timestamps of its own."""

from avalon.orm import Attribute, Model, relation


class User(Model):
    table = "users"
    fillable = ("name", "email")
    hidden = ("password",)

    display_name = Attribute(get=lambda value: str(value or "").title())

    @relation
    def posts(self):
        from app.models.post import Post

        return self.has_many(Post)
'''

SUPPORT_MODELS = '''
"""The models the others point at, plus a class that is not a model at all."""

from avalon.orm import Model, relation


class Comment(Model):
    table = "comments"


class Tag(Model):
    table = "tags"


class Image(Model):
    table = "images"

    @relation
    def imageable(self):
        return self.morph_to("imageable")


class Widget(Model):
    table = "widgets"
    primary_key = "uuid"
    key_type = "str"
    incrementing = False
    timestamps = False


class Helper:
    """Not a model — ``model:show`` must say so rather than describe it."""
'''

BROKEN_MODULE = "raise RuntimeError('this module does not import')\n"

DRAFT_MODULE = '''
"""A private module: ``_draft`` is scratch work, not part of the application."""

from avalon.orm import Model


class Draft(Model):
    table = "drafts"
'''


def write_app(root: Path) -> None:
    """The smallest tree ``ConsoleKernel.from_cwd`` boots, plus ``app/models``."""
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "bootstrap").mkdir(exist_ok=True)
    (root / "bootstrap" / "app.py").write_text("# stub\n", encoding="utf-8")
    for name, body in CONFIG.items():
        (root / "config" / name).write_text(body, encoding="utf-8")

    models = root / "app" / "models"
    models.mkdir(parents=True, exist_ok=True)
    (root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (models / "__init__.py").write_text("", encoding="utf-8")
    (models / "post.py").write_text(POST_MODEL, encoding="utf-8")
    (models / "user.py").write_text(USER_MODEL, encoding="utf-8")
    (models / "support.py").write_text(SUPPORT_MODELS, encoding="utf-8")
    (models / "broken.py").write_text(BROKEN_MODULE, encoding="utf-8")
    (models / "_draft.py").write_text(DRAFT_MODULE, encoding="utf-8")


def create_tables() -> None:
    """Only ``posts``, ``users`` and ``comments`` exist; the rest are unmigrated."""

    async def build() -> None:
        await Schema.create(
            "posts",
            lambda table: (
                table.id(),
                table.string("title"),
                table.text("body").nullable(),
                table.string("status").default("draft"),
                table.json("meta").nullable(),
                table.date_time("published_at").nullable(),
                table.soft_deletes(),
                table.timestamps(),
            ),
        )
        await Schema.create(
            "users",
            lambda table: (table.id(), table.string("name"), table.string("email")),
        )
        # Blueprint defaults are applied in Python, so a column default only
        # reaches the table itself when the DDL carries one.
        await DB.statement(
            "CREATE TABLE comments (id INTEGER PRIMARY KEY, "
            "body TEXT NOT NULL DEFAULT 'no comment')"
        )

    asyncio.run(build())


@pytest.fixture()
def kernel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_app_modules: None
) -> ConsoleKernel:
    write_app(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    built = ConsoleKernel.from_cwd(tmp_path)
    create_tables()
    return built


def show(kernel: ConsoleKernel, *argv: str) -> int:
    return kernel.run_argv("model:show", list(argv))


def payload(kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str], *argv: str) -> dict:
    assert show(kernel, *argv, "--json") == 0
    return json.loads(capsys.readouterr().out)


def row(out: str, name: str) -> str:
    """The one output line that starts with ``name`` in a table column."""
    matches = [line for line in out.splitlines() if line.split(" ")[0] == name]
    assert matches, f"no row for {name!r} in:\n{out}"
    return matches[0]


# --- the model at a glance -------------------------------------------------


def test_model_show_reports_the_table_connection_and_key_the_model_declares(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert show(kernel, "Post") == 0

    out = capsys.readouterr().out
    assert "Class         app.models.post.Post" in out
    assert "Table         posts" in out
    assert "Connection    sqlite" in out
    assert "Primary Key   id" in out
    assert "Key Type      int" in out
    assert "Incrementing  yes" in out
    assert "Timestamps    created_at / updated_at" in out


def test_model_show_reports_a_model_that_keeps_no_timestamps_and_no_trash(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert show(kernel, "Widget") == 0

    out = capsys.readouterr().out
    assert "Primary Key   uuid" in out
    assert "Key Type      str" in out
    assert "Incrementing  no" in out
    assert "Timestamps    off" in out
    assert "Soft Deletes  off" in out


def test_model_show_reports_soft_deletes_by_the_column_that_carries_them(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert show(kernel, "Post") == 0
    assert "Soft Deletes  deleted_at" in capsys.readouterr().out


# --- attributes ------------------------------------------------------------


def test_model_show_merges_the_real_columns_with_the_declared_shape(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    """Type, nullability and default are the table's answers, not the class's."""
    assert show(kernel, "Post") == 0

    out = capsys.readouterr().out
    assert "VARCHAR" in row(out, "title")
    assert row(out, "title").split()[-1] == "fillable"
    body = row(out, "body")
    assert "TEXT" in body and "yes" in body
    excerpt = row(out, "excerpt")
    assert "appended" in excerpt and "accessor" in excerpt


def test_model_show_reports_the_column_default_the_table_actually_carries(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    data = payload(kernel, capsys, "Comment")
    attributes = {attribute["name"]: attribute for attribute in data["attributes"]}

    assert attributes["body"]["default"] == "'no comment'"
    assert attributes["body"]["nullable"] is False


def test_model_show_marks_the_key_the_hidden_and_the_appended_attributes(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    data = payload(kernel, capsys, "Post")
    attributes = {attribute["name"]: attribute for attribute in data["attributes"]}

    assert attributes["id"]["primary"] is True
    assert attributes["id"]["increments"] is True
    assert attributes["id"]["fillable"] is False
    assert attributes["title"]["fillable"] is True
    assert attributes["body"]["hidden"] is True
    assert attributes["excerpt"]["appended"] is True
    assert attributes["excerpt"]["accessor"] is True
    assert attributes["excerpt"]["type"] is None


def test_model_show_names_every_cast_the_model_declares(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    data = payload(kernel, capsys, "Post")
    casts = {
        attribute["name"]: attribute["cast"]
        for attribute in data["attributes"]
        if attribute["cast"]
    }

    assert casts == {
        "status": "Status",
        "meta": "json",
        "published_at": "datetime",
        "labels": "EnumCollection",
    }


def test_model_show_counts_an_attribute_object_as_an_accessor(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    """``display_name = Attribute(get=...)`` has no column and must still show."""
    data = payload(kernel, capsys, "User")
    attributes = {attribute["name"]: attribute for attribute in data["attributes"]}

    assert attributes["display_name"]["accessor"] is True
    assert attributes["display_name"]["type"] is None
    assert attributes["email"]["type"] is not None


# --- relations -------------------------------------------------------------


def test_model_show_lists_every_relationship_with_its_related_model(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    data = payload(kernel, capsys, "Post")
    relations = {relation["name"]: relation for relation in data["relations"]}

    assert relations["author"]["type"] == "BelongsTo"
    assert relations["author"]["related"] == "app.models.user.User"
    assert relations["comments"]["type"] == "HasMany"
    assert relations["comments"]["related"] == "app.models.support.Comment"
    assert relations["tags"]["type"] == "BelongsToMany"
    assert relations["tags"]["related"] == "app.models.support.Tag"
    assert relations["cover"]["type"] == "MorphOne"
    assert relations["cover"]["related"] == "app.models.support.Image"


def test_model_show_lists_a_relation_declared_from_outside_the_class(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    """``resolve_relation_using`` relations are as real as the declared ones."""
    data = payload(kernel, capsys, "Post")
    relations = {relation["name"]: relation for relation in data["relations"]}

    assert relations["editor"]["type"] == "BelongsTo"
    assert relations["editor"]["related"] == "app.models.post.Post"


def test_model_show_names_a_relation_it_cannot_build_without_guessing_its_target(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    data = payload(kernel, capsys, "Post")
    relations = {relation["name"]: relation for relation in data["relations"]}

    assert relations["broken"] == {"name": "broken", "type": None, "related": None}


def test_model_show_leaves_a_polymorphic_relation_without_a_related_model(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    """A ``morph_to`` points wherever the row says, so no one model is right."""
    data = payload(kernel, capsys, "Image")
    relations = {relation["name"]: relation for relation in data["relations"]}

    assert relations["imageable"] == {"name": "imageable", "type": "MorphTo", "related": None}


def test_model_show_says_when_a_model_has_no_relations_at_all(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert show(kernel, "Tag") == 0

    out = capsys.readouterr().out
    assert "Relations" in out
    assert "(none)" in out


# --- scopes and events -----------------------------------------------------


def test_model_show_lists_local_scopes_beside_the_global_ones(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    data = payload(kernel, capsys, "Post")

    assert data["scopes"] == {"global": ["soft_deletes"], "local": ["published"]}


def test_model_show_shows_the_scopes_table_with_the_kind_of_each(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert show(kernel, "Post") == 0

    out = capsys.readouterr().out
    assert "soft_deletes" in row(out, "soft_deletes")
    assert row(out, "soft_deletes").split()[-1] == "global"
    assert row(out, "published").split()[-1] == "local"


def test_model_show_lists_every_observer_against_the_event_it_answers(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    """A listener may be an observer method, a function, or a callable object."""
    data = payload(kernel, capsys, "Post")
    listeners = [(row["event"], row["listener"]) for row in data["observers"]]

    assert listeners[0] == ("created", "PostObserver.created")
    assert listeners[1][0] == "updating"
    assert listeners[1][1].startswith("<app.models.post.Tally object")
    assert listeners[2] == ("saving", "app.models.post.log_saving")
    assert listeners[3] == ("deleting", "PostObserver.deleting")


def test_model_show_says_when_a_model_listens_for_nothing(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert show(kernel, "Tag") == 0

    out = capsys.readouterr().out
    assert "Observers" in out
    assert "Scopes" in out
    assert out.count("(none)") == 3


# --- resolving the model ---------------------------------------------------


def test_model_show_resolves_a_model_by_its_short_name(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert show(kernel, "User") == 0

    out = capsys.readouterr().out
    assert "Class" in out.splitlines()[0]
    assert "app.models.user.User" in out.splitlines()[0]


def test_model_show_resolves_a_model_by_its_dotted_path(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert show(kernel, "app.models.user.User") == 0
    assert "Table         users" in capsys.readouterr().out


def test_model_show_fails_on_a_model_the_application_does_not_have(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    """The module that will not import costs its own models and no others."""
    assert show(kernel, "Ghost") == Command.FAILURE

    captured = capsys.readouterr()
    assert "Model [Ghost] was not found." in captured.err
    assert "Known models: Comment, Image, Post, Tag, User, Widget." in captured.out


def test_model_show_looks_past_a_private_module_and_a_broken_one(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    """``_draft.py`` is scratch work, and a module that raises costs only itself."""
    assert show(kernel, "Draft") == Command.FAILURE

    captured = capsys.readouterr()
    assert "Model [Draft] was not found." in captured.err
    assert "Known models: Comment, Image, Post, Tag, User, Widget." in captured.out


def test_model_discovery_finds_nothing_when_there_is_no_models_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A directory that is not an application still answers the question."""

    def missing(name: str) -> object:
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(repl.importlib, "import_module", missing)

    assert repl.discover_app_classes() == {}


def test_model_show_fails_on_a_dotted_path_that_imports_nothing(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert show(kernel, "app.models.nowhere.Ghost") == Command.FAILURE
    assert "Model [app.models.nowhere.Ghost] was not found." in capsys.readouterr().err


def test_model_show_refuses_a_class_that_is_not_a_model(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert show(kernel, "app.models.support.Helper") == Command.FAILURE
    assert "[app.models.support.Helper] is not an Avalon model." in capsys.readouterr().err


def test_model_show_says_how_to_name_a_model_when_the_application_has_none(
    kernel: ConsoleKernel, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(model_show, "discover_app_classes", dict)

    assert show(kernel, "Post") == Command.FAILURE

    captured = capsys.readouterr()
    assert "Model [Post] was not found." in captured.err
    assert "Name a class under app.models" in captured.out


# --- what needs a database -------------------------------------------------


def test_model_show_shows_the_declared_shape_when_the_database_is_unreachable(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert show(kernel, "Post", "--database=ghost") == 0

    out = capsys.readouterr().out
    assert "Column details need a database connection" in out
    assert "ghost" in out
    assert "app.models.post.Post" in out
    assert "author" in out
    assert row(out, "title").split() == ["title", "fillable"]
    assert row(out, "id").split() == ["id", "primary,", "increments"]
    assert row(out, "deleted_at").split() == ["deleted_at"]
    assert row(out, "created_at").split() == ["created_at"]


def test_model_show_says_when_the_table_has_not_been_created_yet(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert show(kernel, "Tag") == 0
    assert "Table [tags] does not exist yet" in capsys.readouterr().out


def test_model_show_carries_the_reason_for_missing_columns_in_json_too(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    """JSON output stays JSON: the warning is a field, not a line above it."""
    data = payload(kernel, capsys, "Tag")

    assert data["schema_error"] == "Table [tags] does not exist yet, so it has no columns to show."
    assert [attribute["name"] for attribute in data["attributes"]] == [
        "created_at",
        "id",
        "updated_at",
    ]
    assert all(attribute["type"] is None for attribute in data["attributes"])


def test_model_show_rejects_a_database_option_with_no_connection_name(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert show(kernel, "Post", "--database") == Command.INVALID
    assert "Invalid value for '--database'" in capsys.readouterr().err


# --- json ------------------------------------------------------------------


def test_model_show_json_carries_every_section_the_table_view_prints(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    data = payload(kernel, capsys, "Post")

    assert data["class"] == "app.models.post.Post"
    assert data["table"] == "posts"
    assert data["connection"] == "sqlite"
    assert data["primary_key"] == "id"
    assert data["key_type"] == "int"
    assert data["incrementing"] is True
    assert data["timestamps"] == ["created_at", "updated_at"]
    assert data["soft_deletes"] == "deleted_at"
    assert data["schema_error"] is None
    assert [attribute["name"] for attribute in data["attributes"]][:2] == ["id", "title"]
    assert {relation["name"] for relation in data["relations"]} == {
        "author",
        "broken",
        "comments",
        "cover",
        "editor",
        "tags",
    }
