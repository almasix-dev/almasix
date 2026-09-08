"""M30 — generator stubs live in files, and an application can override them."""

from __future__ import annotations

from pathlib import Path

import pytest

from avalon.console.kernel import ConsoleKernel
from avalon.console.stub import FRAMEWORK_STUBS, StubError, names, path_for, publish, render
from avalon.grail.make import command_name, make
from avalon.orm.migration import make_migration


def test_the_framework_ships_a_stub_for_every_generator() -> None:
    shipped = names()

    for expected in (
        "controller.stub",
        "middleware.stub",
        "provider.stub",
        "request.stub",
        "model.stub",
        "seeder.stub",
        "command.stub",
        "component.stub",
        "component-class.stub",
        "migration.stub",
        "migration.create.stub",
        "migration.update.stub",
        "policy.stub",
        "policy.plain.stub",
        "policy-resource.stub",
        "event.stub",
        "listener.stub",
        "listener-queued.stub",
        "listener-duck.stub",
        "listener-queued-duck.stub",
    ):
        assert expected in shipped


def test_no_generator_builds_its_template_in_python() -> None:
    """The stubs moved out of f-strings; they must not creep back in."""
    for module in (
        "src/avalon/grail/make.py",
        "src/avalon/orm/migration.py",
        "src/avalon/console/commands/make_policy.py",
        "src/avalon/console/commands/make_event.py",
    ):
        source = Path(module).read_text(encoding="utf-8")
        assert "_stub(" not in source, f"{module} still renders a stub inline"


def test_render_fills_the_placeholders() -> None:
    body = render("model.stub", {"class": "Post"})

    assert '"""Post model."""' in body
    assert "class Post(Model):" in body
    assert "{{" not in body


def test_an_unknown_placeholder_is_left_alone() -> None:
    """A hand-edited stub keeps what its author wrote."""
    assert render("model.stub", {}) .count("{{ class }}") > 0


def test_an_unknown_stub_says_what_there_is() -> None:
    with pytest.raises(StubError) as excinfo:
        render("nope.stub", {})

    assert "controller.stub" in str(excinfo.value)


def test_a_published_stub_wins_over_the_frameworks(tmp_path: Path) -> None:
    published = publish(tmp_path)

    assert {path.name for path in published} == set(names())
    assert path_for("model.stub", base_path=tmp_path) == tmp_path / "stubs" / "model.stub"
    assert path_for("model.stub") == FRAMEWORK_STUBS / "model.stub"


def test_publishing_twice_leaves_edits_alone(tmp_path: Path) -> None:
    publish(tmp_path)
    edited = tmp_path / "stubs" / "model.stub"
    edited.write_text("edited\n", encoding="utf-8")

    assert publish(tmp_path) == []
    assert edited.read_text(encoding="utf-8") == "edited\n"

    assert publish(tmp_path, force=True) != []
    assert edited.read_text(encoding="utf-8") != "edited\n"


def test_a_generator_reads_the_published_stub(tmp_path: Path) -> None:
    publish(tmp_path)
    stub = tmp_path / "stubs" / "controller.stub"
    stub.write_text('"""{{ class }} — house style."""\n', encoding="utf-8")

    path = make("controller", "PostController", base_path=tmp_path)

    assert path.read_text(encoding="utf-8") == '"""PostController — house style."""\n'


def test_a_published_migration_stub_is_read_too(tmp_path: Path) -> None:
    publish(tmp_path)
    (tmp_path / "stubs" / "migration.create.stub").write_text(
        "# {{ class }} creates {{ table }}\n", encoding="utf-8"
    )

    path = make_migration(
        "create_posts_table",
        tmp_path / "database" / "migrations",
        base_path=tmp_path,
    )

    assert path.read_text(encoding="utf-8") == "# CreatePostsTable creates posts\n"


def test_the_command_stub_starts_with_a_usable_signature(tmp_path: Path) -> None:
    path = make("command", "SendEmails", base_path=tmp_path)

    assert 'signature = "send-emails"' in path.read_text(encoding="utf-8")
    assert command_name("SendEmails") == "send-emails"
    assert command_name("Command") == "command"


def _generate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str, argv: list[str], relative: str
) -> str:
    """Run a generator that works off ``Path.cwd()`` and read back what it wrote."""
    monkeypatch.chdir(tmp_path)
    kernel = ConsoleKernel.for_cwd(tmp_path)
    kernel.discover_framework_commands()

    assert kernel.run_argv(command, argv) == 0
    return (tmp_path / relative).read_text(encoding="utf-8")


def test_a_bare_policy_gets_the_plain_stub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _generate(
        tmp_path, monkeypatch, "make:policy", ["Post"], "app/policies/post_policy.py"
    )

    assert body == render("policy.plain.stub", {"class": "PostPolicy"})
    assert "class PostPolicy(Policy):" in body
    assert "    pass\n" in body


def test_a_resource_policy_without_a_model_leaves_its_parameter_untyped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _generate(
        tmp_path,
        monkeypatch,
        "make:policy",
        ["Post", "--resource"],
        "app/policies/post_policy.py",
    )

    assert body == render("policy-resource.stub", {"class": "PostPolicy"})
    assert "def update(self, user, model) -> bool:" in body
    assert ": model" not in body


def test_a_model_policy_imports_and_types_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _generate(
        tmp_path,
        monkeypatch,
        "make:policy",
        ["Post", "--model=BlogPost"],
        "app/policies/post_policy.py",
    )

    assert "from app.models.blog_post import BlogPost" in body
    assert "def view(self, user, blog_post: BlogPost) -> bool:" in body
    assert "{{" not in body


def test_the_event_stub_carries_the_payload_constructor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _generate(
        tmp_path, monkeypatch, "make:event", ["OrderShipped"], "app/events/order_shipped.py"
    )

    assert body == render("event.stub", {"class": "OrderShipped"})
    assert "class OrderShipped:" in body
    assert "self.__dict__.update(payload)" in body


@pytest.mark.parametrize(
    ("argv", "stub", "typed", "queued"),
    [
        ([], "listener-duck.stub", False, False),
        (["--queued"], "listener-queued-duck.stub", False, True),
        (["--event=OrderShipped"], "listener.stub", True, False),
        (["--queued", "--event=OrderShipped"], "listener-queued.stub", True, True),
    ],
)
def test_each_listener_variant_has_its_own_stub(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    stub: str,
    typed: bool,
    queued: bool,
) -> None:
    body = _generate(
        tmp_path, monkeypatch, "make:listener", ["SendNote", *argv], "app/listeners/send_note.py"
    )

    assert stub in names()
    assert ("(ShouldQueue)" in body) is queued
    assert ("from avalon.events import ShouldQueue" in body) is queued
    assert ("from app.events.order_shipped import OrderShipped" in body) is typed
    assert ("def handle(self, event: OrderShipped) -> None:" in body) is typed
    assert "{{" not in body


def test_a_published_policy_stub_is_read_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish(tmp_path)
    (tmp_path / "stubs" / "policy.stub").write_text(
        "# {{ class }} guards {{ model }} ({{ modelVariable }}) from {{ namespacedModel }}\n",
        encoding="utf-8",
    )

    body = _generate(
        tmp_path,
        monkeypatch,
        "make:policy",
        ["Post", "--model=BlogPost"],
        "app/policies/post_policy.py",
    )

    assert body == "# PostPolicy guards BlogPost (blog_post) from app.models.blog_post\n"


def test_a_published_listener_stub_is_read_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish(tmp_path)
    (tmp_path / "stubs" / "listener-queued.stub").write_text(
        "# {{ class }} handles {{ event }} from {{ namespacedEvent }}\n", encoding="utf-8"
    )

    body = _generate(
        tmp_path,
        monkeypatch,
        "make:listener",
        ["SendNote", "--queued", "--event=OrderShipped"],
        "app/listeners/send_note.py",
    )

    assert body == "# SendNote handles OrderShipped from app.events.order_shipped\n"


def test_stub_publish_reports_what_it_wrote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    kernel = ConsoleKernel.for_cwd(tmp_path)
    kernel.discover_framework_commands()

    assert kernel.run_argv("stub:publish", []) == 0
    assert (tmp_path / "stubs" / "controller.stub").is_file()
    assert kernel.run_argv("stub:publish", []) == 0
    assert kernel.run_argv("stub:publish", ["--force"]) == 0
