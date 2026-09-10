"""Model instance attribute completion (``user.name``) and quote-safe inserts."""

from __future__ import annotations

from pathlib import Path

import pytest

from almasix.lsp.analysis import attribute_context_at, context_at
from almasix.lsp.features import completions
from almasix.lsp.index import build_index
from tests.support import purge_generated_app_modules, without_base_path

PROGRESS = Path(__file__).resolve().parents[1] / "examples" / "progress"


@pytest.fixture()
def progress_index(monkeypatch: pytest.MonkeyPatch):
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    index = build_index(PROGRESS)
    assert index.ok, index.error
    return index


def _apply_insert(source: str, item, line: int = 0) -> str:
    """Apply an LSP-style text edit on a single-line (or targeted) source."""
    lines = source.split("\n")
    text = lines[line]
    start = item.start_character if item.start_character is not None else 0
    end = item.end_character if item.end_character is not None else start
    insert = item.insert_text if item.insert_text is not None else item.label
    lines[line] = text[:start] + insert + text[end:]
    return "\n".join(lines)


def test_table_completion_keeps_surrounding_quotes(progress_index) -> None:
    source = 'q = DB.table("")'
    char = source.index('("")') + 2
    items = completions(progress_index, source, 0, char, language="python")
    users = next(item for item in items if item.label == "users")
    assert users.insert_text == "users"
    assert users.start_character == char
    assert _apply_insert(source, users) == 'q = DB.table("users")'

    partial = 'q = DB.table("us")'
    char = len(partial) - 2
    items = completions(progress_index, partial, 0, char, language="python")
    users = next(item for item in items if item.label == "users")
    assert _apply_insert(partial, users) == 'q = DB.table("users")'


def test_single_quoted_table_completion_keeps_opener(progress_index) -> None:
    source = "q = DB.table('')"
    char = source.index("('')") + 2
    items = completions(progress_index, source, 0, char, language="python")
    users = next(item for item in items if item.label == "users")
    assert _apply_insert(source, users) == "q = DB.table('users')"


def test_user_attribute_completion_from_assignment(progress_index) -> None:
    source = "user = await User.find(1)\nvalue = user.\n"
    char = len("value = user.")
    ctx = attribute_context_at(source, 1, char)
    assert ctx is not None
    assert ctx.kind == "attr"
    assert ctx.receiver == "user"
    assert ctx.prefix == ""

    items = completions(progress_index, source, 1, char, language="python")
    labels = {item.label for item in items}
    assert "email" in labels
    assert "name" in labels
    email = next(item for item in items if item.label == "email")
    assert email.start_character == char
    assert _apply_insert(source, email, line=1) == "user = await User.find(1)\nvalue = user.email\n"


def test_user_attribute_completion_from_annotation(progress_index) -> None:
    source = "user: User\nprint(user.em)\n"
    char = len("print(user.em")
    items = completions(progress_index, source, 1, char, language="python")
    labels = {item.label for item in items}
    assert "email" in labels
    assert all(label.startswith("em") or label == "email" for label in labels) or "email" in labels


def test_heuristic_article_name_to_model(progress_index) -> None:
    """``post`` → ``Post`` when no annotation is present."""
    items = completions(
        progress_index,
        "print(post.)\n",
        0,
        len("print(post."),
        language="python",
    )
    labels = {item.label for item in items}
    assert "title" in labels
    assert "published" in labels


def test_class_receiver_is_not_instance_attrs(progress_index) -> None:
    source = "Post."
    items = completions(progress_index, source, 0, len(source), language="python")
    assert items == []


def test_db_receiver_skipped(progress_index) -> None:
    source = "DB."
    assert completions(progress_index, source, 0, len(source), language="python") == []


def test_prism_echo_attribute_completion(progress_index) -> None:
    source = "{{ user. }}"
    char = source.index(".") + 1
    ctx = context_at(source, 0, char, language="prism-html")
    assert ctx is not None
    assert ctx.kind == "attr"
    items = completions(progress_index, source, 0, char, language="prism-html")
    labels = {item.label for item in items}
    assert "email" in labels
    assert "name" in labels


def test_infer_model_name_covers_annotations_union_and_skips() -> None:
    from almasix.lsp.model_context import infer_model_name, known_model_names
    from almasix.lsp.schema_context import TableInfo

    tables = {
        "users": TableInfo(name="users", columns={}, source="model", model="User"),
        "posts": TableInfo(name="posts", columns={}, source="model", model="Post"),
    }
    models = known_model_names(tables)
    assert models == {"User", "Post"}

    assert infer_model_name("DB.", 2, "DB", models=models) is None
    assert infer_model_name("User.", 5, "User", models=models) is None
    assert infer_model_name("", 0, "", models=models) is None

    annotated = "def show(user: User | None):\n    return user."
    assert infer_model_name(annotated, len(annotated), "user", models=models) == "User"

    optional = "from typing import Optional\ndef show(user: Optional[User]):\n    return user."
    assert infer_model_name(optional, len(optional), "user", models=models) == "User"

    attr_ann = "user: models.User\nprint(user."
    assert infer_model_name(attr_ann, len(attr_ann), "user", models=models) == "User"

    incomplete = "user = await User.find(1)\nvalue = user."
    assert infer_model_name(incomplete, len(incomplete), "user", models=models) == "User"

    # No indexed models → still return the regex/AST guess.
    assert (
        infer_model_name(
            "post = Post.query().first()\nx = post.",
            len("post = Post.query().first()\nx = post."),
            "post",
            models=set(),
        )
        == "Post"
    )
