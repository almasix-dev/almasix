"""M50 part 1 — the Str gaps, and Stringable as the same surface, fluently."""

from __future__ import annotations

import inspect

import pytest

from almasix.support import Str, Stringable, str_

# --- the methods the audit found missing --------------------------------------


def test_doesnt_start_with_and_doesnt_end_with() -> None:
    assert Str.doesnt_start_with("ada lovelace", "grace") is True
    assert Str.doesnt_start_with("ada lovelace", "ada") is False
    assert Str.doesnt_start_with("ada", ["x", "y"]) is True

    assert Str.doesnt_end_with("ada lovelace", "hopper") is True
    assert Str.doesnt_end_with("ada lovelace", "lace") is False


def test_initials_takes_the_first_letter_of_each_word() -> None:
    assert Str.initials("Ada Lovelace") == "A. L."
    assert Str.initials("Grace Brewster Murray Hopper") == "G. B. M. H."
    assert Str.initials("ada") == "A."
    assert Str.initials("  spaced   out  ") == "S. O."
    assert Str.initials("") == ""


def test_match_returns_the_first_match_or_capture_group() -> None:
    assert Str.match(r"ba.", "foo bar") == "bar"
    # A capture group wins over the whole match, as in Laravel.
    assert Str.match(r"foo (bar)", "foo bar") == "bar"
    assert Str.match(r"zebra", "foo bar") == ""


def test_match_all_returns_every_match() -> None:
    assert Str.match_all(r"\d+", "a1 b22 c333") == ["1", "22", "333"]
    assert Str.match_all(r"b(\d+)", "a1 b22 b33") == ["22", "33"]
    assert Str.match_all(r"zebra", "foo") == []


def test_is_match_tests_one_or_many_patterns() -> None:
    assert Str.is_match(r"^ada", "ada lovelace") is True
    assert Str.is_match(r"^grace", "ada lovelace") is False
    assert Str.is_match([r"^grace", r"lace$"], "ada lovelace") is True
    assert Str.is_match([r"^grace", r"^hopper"], "ada lovelace") is False


def test_ucwords_leaves_the_rest_of_each_word_alone() -> None:
    assert Str.ucwords("hello world") == "Hello World"
    # This is the difference from `title`, which lower-cases the remainder.
    assert Str.ucwords("mcDonald farm") == "McDonald Farm"
    assert Str.title("mcDonald farm") == "Mcdonald Farm"
    assert Str.ucwords("hello|world", delimiters="|") == "Hello|World"


def test_the_new_methods_have_laravel_spelled_aliases() -> None:
    assert Str.doesntStartWith("ada", "x") is True
    assert Str.doesntEndWith("ada", "x") is True
    assert Str.matchAll(r"\d", "a1") == ["1"]
    assert Str.isMatch(r"a", "ada") is True


# --- immutability -------------------------------------------------------------


def test_a_fluent_call_does_not_alter_its_subject() -> None:
    name = str_("ada lovelace")

    shouted = name.upper()

    assert str(shouted) == "ADA LOVELACE"
    assert str(name) == "ada lovelace"
    assert shouted is not name


def test_appending_and_prepending_return_new_instances() -> None:
    base = str_("core")

    assert str(base.append("!")) == "core!"
    assert str(base.prepend("the ")) == "the core"
    assert str(base) == "core"


def test_chains_still_read_the_same() -> None:
    assert str(str_("Hello World App").slug().upper()) == "HELLO-WORLD-APP"
    assert str(str_(" padded ").trim().studly()) == "Padded"


# --- delegation ---------------------------------------------------------------


def test_every_str_method_is_reachable_fluently() -> None:
    """The fluent and static surfaces are the same list, not two lists."""
    for name in dir(Str):
        if name.startswith("_") or not isinstance(
            inspect.getattr_static(Str, name), staticmethod
        ):
            continue
        assert hasattr(Stringable, name), name


@pytest.mark.parametrize(
    ("method", "subject", "expected"),
    [
        ("camel", "foo bar", "fooBar"),
        ("snake", "fooBar", "foo_bar"),
        ("kebab", "fooBar", "foo-bar"),
        ("studly", "foo bar", "FooBar"),
        ("headline", "steve_jobs", "Steve Jobs"),
        ("slug", "Hello World", "hello-world"),
        ("lower", "ADA", "ada"),
        ("upper", "ada", "ADA"),
        ("ucfirst", "ada", "Ada"),
        ("lcfirst", "Ada", "ada"),
        ("squish", "  a   b  ", "a b"),
        ("reverse", "ada", "ada"),
        ("singular", "users", "user"),
        ("initials", "Ada Lovelace", "A. L."),
        ("ucwords", "ada lovelace", "Ada Lovelace"),
    ],
)
def test_the_fluent_form_agrees_with_the_static_form(
    method: str, subject: str, expected: str
) -> None:
    assert getattr(Str, method)(subject) == expected
    assert str(getattr(str_(subject), method)()) == expected


def test_delegation_binds_the_subject_by_name_not_position() -> None:
    # Str.replace takes (search, replace, subject) — the subject is last.
    assert str(str_("ada lovelace").replace("ada", "grace")) == "grace lovelace"
    assert str(str_("a-b-c").remove("-")) == "abc"
    assert str(str_("ada").swap({"ada": "grace"})) == "grace"
    assert str_("ada lovelace").is_("ada*") is True


def test_delegation_passes_keyword_only_arguments_through() -> None:
    assert str_("ADA").contains("ada", ignore_case=True) is True
    assert str_("ADA").contains("ada") is False


def test_delegation_returns_scalars_as_themselves() -> None:
    assert str_("ada").length() == 3
    assert str_("ada lovelace").word_count() == 2
    assert str_("ada").starts_with("a") is True
    assert str_("a1b").ucsplit() == ["a1b"]
    assert isinstance(str_("ada").upper(), Stringable)


# --- fluent-only methods ------------------------------------------------------


def test_new_line_appends_newlines() -> None:
    assert str(str_("a").new_line()) == "a\n"
    assert str(str_("a").new_line(2)) == "a\n\n"


def test_strip_tags_removes_markup() -> None:
    assert str(str_("<p>Hi <b>there</b></p>").strip_tags()) == "Hi there"
    assert str(str_("<p>Hi <b>x</b></p>").strip_tags("b")) == "Hi <b>x</b>"
    assert str(str_("<p>a</p><br/>b").strip_tags("p")) == "<p>a</p>b"


def test_split_splits_on_a_pattern() -> None:
    assert str_("a1b22c").split(r"\d+") == ["a", "b", "c"]
    assert str_("a1b2c").split(r"\d", 1) == ["a", "b2c"]


def test_test_matches_a_pattern() -> None:
    assert str_("ada").test(r"^a") is True
    assert str_("ada").test(r"^z") is False


def test_base64_round_trips() -> None:
    encoded = str_("ada").to_base()

    assert str(encoded) == "YWRh"
    assert str(encoded.from_base()) == "ada"


def test_hashing_and_encryption_go_through_the_application_services() -> None:
    from almasix.hashing import Hash

    hashed = str_("secret").hash()
    assert Hash.check("secret", str(hashed))

    encrypted = str_("secret").encrypt()
    assert str(encrypted) != "secret"
    assert str(encrypted.decrypt()) == "secret"


# --- conditionals -------------------------------------------------------------


def test_when_uses_what_the_callback_returns() -> None:
    assert str(str_("ada").when(True, lambda s: s.upper())) == "ADA"
    assert str(str_("ada").when(False, lambda s: s.upper())) == "ada"
    assert str(str_("ada").when(False, lambda s: s.upper(), lambda s: s.append("!"))) == "ada!"
    # A callback that returns nothing has done nothing.
    assert str(str_("ada").when(True, lambda s: None)) == "ada"
    assert str(str_("ada").when(True)) == "ada"


def test_unless_is_when_inverted() -> None:
    assert str(str_("ada").unless(False, lambda s: s.upper())) == "ADA"
    assert str(str_("ada").unless(True, lambda s: s.upper())) == "ada"


@pytest.mark.parametrize(
    ("method", "subject", "args", "expected"),
    [
        ("when_contains", "ada lovelace", ("ada",), "ADA LOVELACE"),
        ("when_contains", "grace", ("ada",), "grace"),
        ("when_contains_all", "ada lovelace", (["ada", "lace"],), "ADA LOVELACE"),
        ("when_empty", "", (), ""),
        ("when_not_empty", "ada", (), "ADA"),
        ("when_starts_with", "ada", ("a",), "ADA"),
        ("when_ends_with", "ada", ("a",), "ADA"),
        ("when_doesnt_start_with", "ada", ("z",), "ADA"),
        ("when_doesnt_end_with", "ada", ("z",), "ADA"),
        ("when_exactly", "ada", ("ada",), "ADA"),
        ("when_not_exactly", "ada", ("zoe",), "ADA"),
        ("when_is", "ada lovelace", ("ada*",), "ADA LOVELACE"),
        ("when_is_ascii", "ada", (), "ADA"),
        ("when_test", "ada", (r"^a",), "ADA"),
    ],
)
def test_the_when_family(method: str, subject: str, args: tuple, expected: str) -> None:
    result = getattr(str_(subject), method)(*args, lambda s: s.upper())

    assert str(result) == expected


def test_when_is_uuid_and_ulid() -> None:
    from almasix.orm.ids import ulid

    identifier = str_(Str.uuid())
    assert str(identifier.when_is_uuid(lambda s: s.append("!"))).endswith("!")
    assert not str(str_("nope").when_is_uuid(lambda s: s.append("!"))).endswith("!")

    assert str(str_(ulid()).when_is_ulid(lambda s: s.append("!"))).endswith("!")


def test_a_when_shortcut_takes_a_default_too() -> None:
    result = str_("grace").when_contains("ada", lambda s: s.upper(), lambda s: s.append("?"))

    assert str(result) == "grace?"


def test_when_shortcuts_accept_keyword_callbacks() -> None:
    result = str_("ada").when_contains("ada", callback=lambda s: s.upper())

    assert str(result) == "ADA"


# --- named deviations ---------------------------------------------------------


def test_the_three_unported_fluent_methods_are_absent_on_purpose() -> None:
    """`scan` is a PHP builtin; the other two return Laravel-only types."""
    for name in ("scan", "to_html_string", "to_uri"):
        assert not hasattr(Stringable, name), name


def test_a_stringable_hashes_and_compares_as_its_string() -> None:
    wrapped = str_("ada")

    assert wrapped == "ada"
    assert wrapped == str_("ada")
    assert hash(wrapped) == hash("ada")
    assert {wrapped: 1}["ada"] == 1
    assert {"ada": 1}[wrapped] == 1
    assert len({wrapped, "ada"}) == 1


def test_the_pad_family_repeats_the_whole_pad_string() -> None:
    assert Str.pad_left("7", 5, "ab") == "abab7"
    assert Str.pad_right("7", 5, "ab") == "7abab"
    assert Str.pad_both("x", 7, "-=") == "-=-x-=-"
    assert Str.pad_left("7", 5) == "    7"
    assert Str.pad_both("Almasix", 12, "_") == "__Almasix___"
    assert Str.pad_right("already long", 4, "-") == "already long"


def test_char_at_counts_back_from_the_end_for_a_negative_index() -> None:
    assert Str.char_at("Ada", 1) == "d"
    assert Str.char_at("Ada", -1) == "a"
    assert Str.char_at("Ada", -3) == "A"
    assert Str.char_at("Ada", -4) is False
    assert Str.char_at("Ada", 9) is False
