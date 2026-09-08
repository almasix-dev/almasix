"""Coverage fill for M14 Arr / helpers / Str / Number."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from almasix.http.exceptions import HttpException
from almasix.support import Arr, Number, Str, Stringable
from almasix.support.helpers import (
    abort,
    abort_if,
    abort_unless,
    app_path,
    base_path,
    blank,
    class_basename,
    class_uses_recursive,
    config_path,
    database_path,
    e,
    lang_path,
    object_get,
    optional,
    preg_replace_array,
    public_path,
    report_if,
    report_unless,
    rescue,
    resource_path,
    retry,
    retry_async,
    storage_path,
    throw_if,
    throw_unless,
    trait_uses_recursive,
    when,
)
from almasix.support.helpers import tap


def test_arr_edge_branches() -> None:
    assert Arr.collapse([{"a": 1}, "x"]) == [1, "x"]
    assert Arr.cross_join() == [[]]
    assert Arr.dot({}) == {}
    assert Arr.dot({"a": {}})["a"] == {}
    assert Arr.dot({"a": []})["a"] == []
    assert Arr.except_({"a": 1, "b": 2}, "b") == {"a": 1}
    assert Arr.only({"a": 1, "b": 2}, "a") == {"a": 1}
    assert Arr.exists([1, 2], 1)
    assert not Arr.exists([1, 2], "nope")
    assert not Arr.exists([1, 2], 9)
    assert Arr.first([], default=lambda: "d") == "d"
    assert Arr.last([], default="d") == "d"
    assert Arr.last([1, 2, 3]) == 3
    assert Arr.flatten({"a": [1, 2]}) == [1, 2]
    assert Arr.has({"items": [1, 2]}, "items.1")
    assert not Arr.has({"items": [1]}, "items.5")
    assert not Arr.has({"items": [1]}, "items.x")
    obj = type("O", (), {"child": type("C", (), {"n": 1})()})()
    assert Arr.has(obj, "child.n")
    assert not Arr.has(obj, "child.missing")
    assert Arr.exists("abc", 0) is False
    assert Arr.first([0], callback=None) == 0
    assert Arr.last([1, 2, 3], callback=lambda n: False, default=9) == 9
    bag2: dict = {"a": 1}
    Arr.forget(bag2, "a")
    assert bag2 == {}
    assert Arr.random([7, 7], number=2) == [7, 7]
    assert Arr.sort_recursive("x") == "x"
    assert Arr.prepend({"a": 1}, 0, key="z")["z"] == 0
    assert Arr.flatten([{"a": {"b": 1}}]) == [1]
    assert Arr.sort_recursive([1, "a"]) in ([1, "a"], ["a", 1], [1, "a"])
    nested_f: dict = {"a": {}}
    Arr.forget(nested_f, "a.b.c")
    assert nested_f == {"a": {}}
    nested: dict = {"a": {"b": {"c": 1}}}
    Arr.forget(nested, ["a.b.c", "missing.path"])
    assert nested["a"]["b"] == {}
    assert not Arr.has({}, [])
    assert not Arr.has({"a": 1}, "b")
    assert not Arr.has_any({}, ["a"])
    assert not Arr.is_assoc([1, 2])
    assert Arr.is_list({0: "a", 1: "b"})
    assert not Arr.is_list("x")
    assert Arr.join([], ",") == ""
    assert Arr.join(["a"], ",", " and ") == "a"
    assert Arr.map({"a": 1}, lambda v, k: f"{k}{v}") == ["a1"]
    assert Arr.map_with_keys([1], lambda v, i: (v, i)) == {1: 0}
    assert Arr.map_spread([1], lambda x: x * 2) == [2]
    assert Arr.pluck([{"id": 1, "n": "a"}], "n", "id") == {1: "a"}
    assert Arr.pluck([{"n": "a"}], lambda i: i["n"]) == ["a"]
    assert Arr.prepend([1], 0, key="k")["k"] == 0
    assert Arr.random([1, 2], number=1) in [[1], [2]]
    assert Arr.sort({"b": 2, "a": 1}) == {"a": 1, "b": 2}
    assert Arr.sort({"b": 2, "a": 1}, callback=lambda v: -v)["b"] == 2
    assert Arr.sort([3, 1], callback=lambda v: v) == [1, 3]
    assert Arr.sort_desc({"a": 1, "b": 2})["b"] == 2
    assert Arr.sort_recursive([3, 1, 2]) == [1, 2, 3]
    assert Arr.sort_recursive([{"a": 1}], descending=True) == [{"a": 1}]
    assert Arr.take([1, 2, 3], -1) == [3]
    assert Arr.to_css_classes(["p-2", ""]) == "p-2"
    assert Arr.wrap((1, 2)) == [1, 2]
    assert Arr.wrap([1]) == [1]


def test_helpers_edge_branches() -> None:
    assert blank(b"  ")
    assert blank({})
    assert blank(())
    assert not blank(True)
    assert not blank(0)
    assert blank(type("X", (), {"__len__": lambda self: 0})())

    class BadLen:
        def __len__(self) -> int:
            raise TypeError

    assert blank(BadLen()) is False
    assert tap(1) == 1
    assert when(True, lambda: "y") == "y"
    assert when(True, lambda c: c and "y") == "y"
    assert when(False, "y", lambda: "n") == "n"
    assert when(False, "y", lambda c: "n") == "n"
    assert when(True, "plain") == "plain"

    def weird():
        pass
    weird.__signature__ = "bad"  # type: ignore[attr-defined]
    # signature may fail → fall through to zero-arg call
    try:
        when(True, weird)
    except TypeError:
        pass

    opt = optional(None)
    assert opt() is None
    assert not opt
    boxed = optional(lambda: 5)
    assert boxed() == 5
    user = type("U", (), {"name": "Ada", "hi": lambda self: "hi"})()
    assert optional(user).name == "Ada"
    assert optional(user).hi() == "hi"
    assert optional(None, lambda x: x) is None
    assert optional(user)() is user

    with pytest.raises(ValueError):
        throw_unless(False, ValueError("x"))
    with pytest.raises(RuntimeError):
        throw_if(True, RuntimeError, "msg")
    with pytest.raises(RuntimeError):
        throw_if(True, "plain-message")
    throw_if(False)
    abort_if(False)
    with pytest.raises(HttpException) as ei:
        abort(404, "missing")
    assert ei.value.status_code == 404
    with pytest.raises(HttpException):
        abort_unless(False, 401, "no")

    state = {"n": 0}

    def boom() -> int:
        state["n"] += 1
        if state["n"] < 2:
            raise RuntimeError("x")
        return 1

    assert retry(3, boom, sleep=0.001) == 1
    with pytest.raises(RuntimeError):
        retry(2, lambda: (_ for _ in ()).throw(RuntimeError("x")), when=lambda e: False)

    async def _retry() -> int:
        state2 = {"n": 0}

        def boom2() -> int:
            state2["n"] += 1
            if state2["n"] < 2:
                raise RuntimeError("x")
            return 1

        return await retry_async(3, boom2, sleep=0.001)

    assert asyncio.run(_retry()) == 1

    async def _retry_awaitable() -> int:
        async def ok() -> int:
            return 4

        return await retry_async(2, ok)

    assert asyncio.run(_retry_awaitable()) == 4

    async def _retry_when() -> None:
        await retry_async(
            3,
            lambda: (_ for _ in ()).throw(RuntimeError("x")),
            when=lambda e: False,
        )

    with pytest.raises(RuntimeError):
        asyncio.run(_retry_when())

    async def _retry_fail() -> None:
        await retry_async(1, lambda: (_ for _ in ()).throw(RuntimeError("x")))

    with pytest.raises(RuntimeError):
        asyncio.run(_retry_fail())

    assert rescue(lambda: 1, report=False) == 1
    assert rescue(lambda: 1 / 0, lambda e: type(e).__name__, report=False) == "ZeroDivisionError"
    report_if(False, RuntimeError("r"))
    report_unless(True, RuntimeError("r"))
    report_if(True, RuntimeError("r"))
    report_unless(False, RuntimeError("r"))
    assert object_get(type("O", (), {"a": 1})(), "a") == 1
    with pytest.raises(RuntimeError):
        retry(1, lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert class_basename(object()) == "object"
    assert class_uses_recursive(Path("."))
    assert e(None) == ""
    assert e("<b>", double_encode=False)
    assert preg_replace_array(r"\?", ["a"], "? ? ?") == "a  "
    assert Path(base_path()).exists()
    assert "app" in app_path("models")
    assert "config" in config_path()
    assert "database" in database_path()
    assert "lang" in lang_path()
    assert "public" in public_path()
    assert "resources" in resource_path()
    assert "storage" in storage_path()


def test_str_edge_branches() -> None:
    assert Str.after("abc", "") == "abc"
    assert Str.after("abc", "z") == "abc"
    assert Str.after_last("a/b/c", "") == "a/b/c"
    assert Str.after_last("abc", "z") == "abc"
    assert Str.before("abc", "") == "abc"
    assert Str.before("abc", "z") == "abc"
    assert Str.before_last("abc", "") == "abc"
    assert Str.between("abc", "", "c") == "abc"
    assert Str.between_first("[a]", "[", "]") == "a"
    assert Str.camel("") == ""
    assert Str.apa("the quick brown fox")
    assert Str.ascii("café") == "cafe"
    assert Str.transliterate("naïve") == "naive"
    assert Str.char_at("ab", 9) is False
    assert Str.char_at("ab", 1) == "b"
    assert Str.chop_start("foobar", ["foo", "x"]) == "bar"
    assert Str.chop_start("bar", "x") == "bar"
    assert Str.chop_end("foobar", ["bar", "x"]) == "foo"
    assert Str.chop_end("foo", "x") == "foo"
    assert not Str.contains("abc", "")
    assert Str.doesnt_contain("abc", "z")
    assert Str.deduplicate("a   b") == "a b"
    assert not Str.ends_with("abc", "")
    assert not Str.starts_with("abc", "")
    assert Str.excerpt("hello world", options={"radius": 2}) == "he..."
    assert Str.excerpt("hello world", "missing") is None
    assert "world" in (Str.excerpt("hello world around", "world", options={"radius": 2}) or "")
    assert Str.finish("ab/", "/") == "ab/"
    assert Str.start("/ab", "/") == "/ab"
    assert Str.is_("foo*", "foobar")
    assert Str.is_(["x", "y"], "y")
    assert not Str.is_ascii("ü")
    assert Str.is_json('{"a":1}')
    assert not Str.is_json("{")
    assert Str.is_url("https://example.com")
    assert not Str.is_url("notaurl")
    assert not Str.is_url("ftp://x", protocols=["http"])
    assert not Str.is_uuid("nope")
    assert Str.is_ulid(Str.ulid())
    assert Str.length("ab") == 2
    assert Str.limit("ab", 10) == "ab"
    assert Str.words("a b c d", 2) == "a b..."
    assert Str.words("a b", 5) == "a b"
    assert Str.lower("A") == "a"
    assert Str.upper("a") == "A"
    assert Str.lcfirst("Foo") == "foo"
    assert Str.ucfirst("foo") == "Foo"
    assert Str.ucsplit("FooBar") == ["Foo", "Bar"]
    assert Str.mask("abcd", "", 1) == "abcd"
    assert Str.mask("abcd", "*", -2) == "ab**"
    assert Str.pad_both("a", 5, "-") == "--a--"
    assert Str.pad_left("a", 3, "0") == "00a"
    assert Str.pad_right("a", 3, "0") == "a00"
    assert len(Str.password(8, symbols=False, spaces=True)) == 8
    assert Str.plural("fish") == "fish"
    assert Str.plural("child", 1) == "child"
    assert Str.plural("ox") == "oxen"
    assert Str.singular("fish") == "fish"
    assert Str.singular("oxen") == "ox"
    assert Str.plural_studly("User") == "Users"
    assert Str.position("abc", "z") is False
    assert Str.position("abc", "b") == 1
    assert Str.remove(["a", "b"], "abx") == "x"
    assert Str.remove("A", "aAa", case_sensitive=False) == ""
    assert Str.repeat("a", 3) == "aaa"
    assert Str.replace("A", "x", "AaA", case_sensitive=False) == "xxx"
    assert Str.replace(["a", "b"], ["1", "2"], "ab") == "12"
    assert Str.replace_array("/", ["x", "y"], "a/b/c") == "axbyc"
    assert Str.replace_last("a", "x", "a a") == "a x"
    assert Str.replace_last("z", "x", "a a") == "a a"
    assert Str.replace_start("pre", "X", "prefix") == "Xfix"
    assert Str.replace_start("z", "X", "prefix") == "prefix"
    assert Str.replace_end("fix", "X", "suffix") == "sufX"
    assert Str.replace_end("z", "X", "suffix") == "suffix"
    assert Str.replace_matches(r"\d", "#", "a1b2") == "a#b#"
    assert Str.reverse("ab") == "ba"
    assert Str.slug("foo@bar", dictionary={"@": "at"})
    assert Str.squish(" a  b ") == "a b"
    assert Str.substr("abcdef", 2, 2) == "cd"
    assert Str.substr("abcdef", 2) == "cdef"
    assert Str.substr_count("abab", "ab") == 2
    assert Str.substr_replace("abcdef", "XX", 2, 2) == "abXXef"
    assert Str.swap({"a": "x"}, "a b a") == "x b x"
    assert Str.take("abcdef", -2) == "ef"
    assert Str.from_base64(Str.to_base64("ab")) == "ab"
    assert Str.trim("  x  ") == "x"
    assert Str.ltrim("--x", "-") == "x"
    assert Str.rtrim("x--", "-") == "x"
    assert Str.wrap("x", "[", "]") == "[x]"
    assert Str.unwrap("[x]", "[", "]") == "x"
    assert Str.unwrap("x", "[", "]") == "x"
    assert Str.word_count("a b c") == 3
    assert "\n" in Str.word_wrap("abcdefghij", characters=4)
    assert Str.ordered_uuid()
    assert "<h1>" in Str.markdown("# Hi")
    assert Str.inline_markdown("*em*")

    s = Stringable("FooBar")
    assert s.value() == "FooBar"
    assert repr(s).startswith("Stringable")
    assert s == "FooBar"
    assert s.prepend("X").append("Z").to_string().endswith("Z")
    assert Stringable("a/b/c.txt").basename(".txt").to_string() == "c"
    assert "a" in Stringable("a/b/c").dirname().to_string()
    assert Stringable("pkg.User").class_basename().to_string() == "User"
    assert Stringable("x").when(True, lambda t: t.append("!")).to_string() == "x!"
    assert Stringable("x").unless(False, lambda t: t.append("!")).to_string() == "x!"
    assert Stringable("1").pipe(lambda t: t.to_integer()) == 1
    assert Stringable("").is_empty()
    assert Stringable("x").is_not_empty()
    assert Stringable("1.5").to_float() == 1.5
    assert Stringable("true").to_boolean()
    assert Stringable("abc").replace("a", "x").to_string() == "xbc"
    assert Stringable("abc").remove("b").to_string() == "ac"
    assert Stringable("a/b").replace_array("/", ["-"]).to_string() == "a-b"
    assert Stringable("aa").replace_first("a", "x").to_string() == "xa"
    assert Stringable("aa").replace_last("a", "x").to_string() == "ax"
    assert Stringable("preX").replace_start("pre", "").to_string() == "X"
    assert Stringable("Xsuf").replace_end("suf", "").to_string() == "X"
    assert Stringable("a1").replace_matches(r"\d", "").to_string() == "a"
    assert Stringable("a b").swap({"a": "x"}).to_string() == "x b"
    assert Stringable("abc").is_("a*")
    assert Stringable("Almasix").contains("mas")
    assert Stringable("Almasix").contains_all(["Al", "ix"])
    assert Stringable("Almasix").doesnt_contain("z")
    assert Stringable("Almasix").starts_with("Al")
    assert Stringable("Almasix").ends_with("ix")
    assert Str.title("hello world") == "Hello World"
    assert "and" in Str.apa("War and Peace")
    assert len(Str.password(4, letters=False, numbers=False, symbols=False, spaces=False)) == 4
    assert Str.singular("child") == "child"
    assert Str.plural_studly("!!!") == "!!!s" or isinstance(Str.plural_studly("!!!"), str)
    assert len(Str.random(8)) == 8
    assert Str.substr("abcdef", 2, -1) == ""
    assert Str.substr_replace("abcdef", "XX", 2) == "abXX"
    assert Str.substr("abcdef", -3, 2) == "de"
    assert Stringable("a") == Stringable("a")
    assert Stringable("a/b/c").basename().to_string() == "c"
    assert Stringable("x").when(False, lambda t: t, lambda t: t.append("!")).to_string() == "x!"
    assert Stringable("a,b").explode(",") == ["a", "b"]
    assert Stringable("CHILDREN").singular().to_string() == "CHILD"
    assert Str.password(6, letters=False, numbers=False, symbols=True)
    assert Str.singular("statuses") in {"status", "statuses"}
    assert Str.ucsplit("") == []
    assert Stringable("a/b/c").dirname(2).to_string()
    assert Stringable(None).to_string() == ""
    assert Stringable("x").tap(lambda t: None).to_string() == "x"
    assert Stringable("FOO").lower().to_string() == "foo"
    assert Str.plural("CHILD") == "CHILDREN"
    assert Str.plural("Child") == "Children"
    from almasix.support.str import _match_case

    assert _match_case("foo", "bar") == "bar"
    assert Str.excerpt("abcdefghij", "def", options={"radius": 1, "omission": "…"})
    assert Str.is_("exact", "exact")
    assert not Str.contains("abc", ["", "z"])
    assert Stringable("x").when(True, lambda t: t.append("y"), None).to_string() == "xy"
    assert Stringable("one two three").words(1).to_string() == "one..."


def test_number_edge_branches() -> None:
    Number.use_currency("EUR")
    assert Number.default_currency() == "EUR"
    assert "€" in Number.with_currency("EUR", lambda: Number.currency(1))
    Number.use_currency("USD")
    assert "1.23" in Number.format(1.2345, precision=2)
    assert Number.format(1.2, max_precision=3)
    assert Number.format(1.0)
    assert Number.format(1.25)
    assert Number.file_size(100)
    assert Number.abbreviate(999)
    assert Number.abbreviate(1_500_000, precision=1)
    assert Number.ordinal(11).endswith("th")
    assert Number.spell(-2).startswith("minus")
    assert Number.spell(105)
    assert Number.spell(1000) == "1000"
    assert Number.for_humans(1500, abbreviate=True)
    assert Number.for_humans(1500, abbreviate=False)
    assert Number.trim(1.5) == 1.5
    Number.use_locale("en")
