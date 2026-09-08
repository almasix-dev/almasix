"""Serialization visibility is per instance, not per class."""

from __future__ import annotations

from almasix.orm.model import Model


class Account(Model):
    table = "accounts"
    fillable = ("name", "email", "secret")
    hidden = ("secret",)


class Restricted(Model):
    table = "restricted"
    fillable = ("name", "email")
    visible = ("name",)


def test_make_hidden_does_not_leak_to_other_instances() -> None:
    first = Account(name="Ada", email="ada@example.test", secret="s3cret")
    second = Account(name="Alan", email="alan@example.test", secret="s3cret")

    first.make_hidden("email")

    assert "email" not in first.to_dict()
    assert "email" in second.to_dict(), "make_hidden must not mutate the class"
    assert Account.hidden == ("secret",)


def test_make_visible_does_not_leak_to_other_instances() -> None:
    first = Account(name="Ada", secret="s3cret")
    second = Account(name="Alan", secret="s3cret")

    first.make_visible("secret")

    assert first.to_dict()["secret"] == "s3cret"
    assert "secret" not in second.to_dict(), "make_visible must not mutate the class"
    assert Account.hidden == ("secret",)


def test_make_visible_extends_an_allowlist() -> None:
    model = Restricted(name="Ada", email="ada@example.test")
    assert set(model.to_dict()) == {"name"}

    model.make_visible("email")
    assert set(model.to_dict()) == {"name", "email"}
    assert Restricted.visible == ("name",)


def test_set_hidden_and_set_visible_replace_the_lists() -> None:
    model = Account(name="Ada", email="ada@example.test", secret="s3cret")

    model.set_hidden(["name"])
    data = model.to_dict()
    assert "name" not in data
    assert data["secret"] == "s3cret", "the class hidden list was replaced"

    model.set_visible(["email"])
    assert set(model.to_dict()) == {"email"}

    assert Account.hidden == ("secret",)
    assert Account.visible == ()


def test_effective_visibility_defaults_to_the_class() -> None:
    model = Account(name="Ada", secret="s3cret")
    assert model.get_hidden() == ("secret",)
    assert model.get_visible() == ()
    assert Restricted(name="Ada").get_visible() == ("name",)


def test_hidden_relations_follow_the_instance_override() -> None:
    parent = Account(name="Ada")
    parent._relations["notes"] = [{"body": "hi"}]
    assert "notes" in parent.to_dict()

    parent.make_hidden("notes")
    assert "notes" not in parent.to_dict()

    sibling = Account(name="Alan")
    sibling._relations["notes"] = [{"body": "still visible"}]
    assert "notes" in sibling.to_dict()
