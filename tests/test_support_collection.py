"""Support Collection unit tests — Laravel Available Methods exhaust."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from almasix.support import (
    Collection,
    ItemNotFoundError,
    MultipleItemsFoundError,
    collect,
    data_get,
)
from almasix.support.collection import value_get

# --- helpers / construction -------------------------------------------------


def test_data_get_and_value_get() -> None:
    assert data_get(None, None) is None
    assert data_get({"a": {"b": 1}}, "a.b") == 1
    assert data_get({"a": None}, "a.b", "x") == "x"
    assert data_get({"a": {}}, "a.missing", "d") == "d"
    assert data_get([10, 20], "1") == 20
    assert data_get([10], "9", "d") == "d"
    assert data_get("nope", "x", "d") == "d"
    obj = SimpleNamespace(name="Ada")
    assert data_get(obj, "name") == "Ada"
    assert data_get(obj, "missing", "d") == "d"

    class AttrModel:
        def get_attribute(self, key: str) -> str:
            return f"attr:{key}"

    assert data_get(AttrModel(), "email") == "attr:email"
    assert value_get({"n": 1}, None) == {"n": 1}
    assert value_get({"n": 1}, "n") == 1
    assert value_get(5, lambda x: x * 2) == 10


def test_construction_and_protocol() -> None:
    assert Collection.make([1, 2]).all() == [1, 2]
    assert Collection.wrap(None).all() == []
    assert Collection.wrap(collect([1])).all() == [1]
    assert Collection.wrap([1, 2]).all() == [1, 2]
    assert Collection.wrap("x").all() == ["x"]
    assert Collection.unwrap(collect([1])) == [1]
    assert Collection.unwrap([1, 2]) == [1, 2]
    assert Collection.times(3, lambda i: i * 10).all() == [10, 20, 30]
    assert Collection.range(1, 3).all() == [1, 2, 3]
    empty = collect()
    assert len(empty) == 0 and not empty and bool(collect([1]))
    assert list(collect([1, 2])) == [1, 2]
    assert collect([1, 2])[1] == 2
    assert collect({"a": 1})["a"] == 1
    assert collect([1, 2, 3])[1:3].all() == [2, 3]
    with pytest.raises(KeyError):
        _ = collect([1])[9]
    c = collect([1])
    c[0] = 9
    assert c[0] == 9
    assert 9 in c
    assert collect([1, 2]) == collect([1, 2])
    assert collect([1]) != collect([2])
    assert collect([1]) == [1]
    assert collect({"a": 1}) == {"a": 1}
    assert collect([1]) != "x"
    assert "Collection" in repr(collect([1]))
    assert collect({"a": 1}).all() == {"a": 1}
    assert collect({"a": 1}).to_array() == {"a": 1}


def test_json_roundtrip() -> None:
    c = collect({"a": 1, "b": [2]})
    assert json.loads(c.to_json()) == {"a": 1, "b": [2]}
    pretty = c.to_pretty_json()
    assert "\n" in pretty
    assert Collection.from_json(c.to_json()).get("a") == 1


def test_keys_values_get_has() -> None:
    c = collect({"a": 1, "b": 2})
    assert c.get("a") == 1 and c.get("z", 9) == 9
    assert c.has("a", "b") and not c.has("a", "z")
    assert c.has_any("z", "a") and c.has_any(["z", "a"])
    assert not c.has_any("z")
    assert c.keys().all() == ["a", "b"]
    assert c.values().all() == [1, 2]


def test_first_last_value_compat() -> None:
    assert collect([]).first() is None
    assert collect([]).first("d") == "d"
    assert collect([1, 2, 3]).first(lambda n: n > 1) == 2
    assert collect([1]).first(lambda n: n > 9, "d") == "d"
    assert collect([1, 2, 3]).last() == 3
    assert collect([]).last("d") == "d"
    assert collect([1, 2, 3]).last(lambda n: n < 3) == 2
    assert collect([1]).last(lambda n: n > 9, "d") == "d"
    assert collect([{"n": 1}]).value("n") == 1
    assert collect([]).value("n", "d") == "d"
    assert collect([]).is_empty() and collect([1]).is_not_empty()


# --- contains / map / filter -------------------------------------------------


def test_contains_family() -> None:
    c = collect([1, 2, 3])
    assert c.contains(2) and c.some(2)
    assert c.contains(lambda n: n == 3)
    assert c.contains(0)  # key present in list-like collection
    rows = collect([{"n": 1}, {"n": 2}])
    assert rows.contains("n", 2)
    assert rows.contains("n", ">", 1)
    x = object()
    assert collect([x]).contains_strict(x)
    assert not collect([1]).contains_strict(True)
    assert collect([1]).contains_one_item()
    assert c.doesnt_contain(9)
    assert collect([1]).doesnt_contain_strict(True)


def test_map_filter_reject_each() -> None:
    assert collect([1, 2]).map(lambda n: n * 2).all() == [2, 4]
    assert collect({"a": 1}).map(lambda v, k: f"{k}{v}").all() == {"a": "a1"}
    mapped = collect([1, 2]).map_with_keys(lambda n: {n: n * 10})
    assert mapped.all() == {1: 10, 2: 20}
    assert collect([1]).map_with_keys(lambda n: (n, n * 10)).all() == {1: 10}
    assert collect([1]).map_with_keys(lambda n, k: (k, n)).all() == [1]
    assert collect([1]).map_into(str).all() == ["1"]
    groups = collect([1, 2, 3]).map_to_groups(lambda n: {"even" if n % 2 == 0 else "odd": n})
    assert groups.get("odd").values().all() == [1, 3]
    assert collect([1, 2]).map_to_groups(lambda n, k: (k, n)).get(0).all() == [1]
    assert collect([[1, 2], [3, 4]]).map_spread(lambda a, b: a + b).all() == [3, 7]
    assert collect([1, 2]).map_spread(lambda n: n * 2).all() == [2, 4]
    assert collect([1, 2]).flat_map(lambda n: [n, n]).all() == [1, 1, 2, 2]
    assert collect(["", "a", None]).filter().values().all() == ["a"]
    assert collect([1, 2, 3]).filter(lambda n: n > 1).values().all() == [2, 3]
    assert collect({"a": 1, "b": 2}).filter(lambda v, k: k == "b").all() == {"b": 2}
    assert collect([1, 2, 3]).reject(lambda n: n == 2).values().all() == [1, 3]
    assert collect([1, False, 2]).reject(False).values().all() == [1, 2]
    seen: list[int] = []
    collect([1, 2]).each(lambda n: seen.append(n))
    assert seen == [1, 2]
    seen_keys: list[Any] = []
    collect({"a": 1}).each(lambda v, k: seen_keys.append(k))
    assert seen_keys == ["a"]
    collect([1, 2]).each(lambda n: False)
    seen2: list[tuple[int, int]] = []
    collect([[1, 2], [3, 4]]).each_spread(lambda a, b: seen2.append((a, b)) or False)
    assert seen2 == [(1, 2)]
    collect([1]).each_spread(lambda n: False)
    c = collect([1, 2])
    c.transform(lambda n: n * 3)
    assert c.all() == [3, 6]
    c2 = collect({"a": 1})
    c2.transform(lambda v, k: f"{k}{v}")
    assert c2.all() == {"a": "a1"}


def test_reduce_multiply_pipe() -> None:
    assert collect([1, 2, 3]).reduce(lambda c, n: c + n) == 6
    assert collect([1, 2]).reduce(lambda c, n: c + n, 10) == 13
    assert collect([]).reduce(lambda c, n: c) is None
    assert collect([[1, 2], [3, 4]]).reduce_spread(lambda c, a, b: c + a + b, 0) == 10
    assert collect([1]).reduce_spread(lambda c, n: c + n, 0) == 1
    assert collect([1, 2]).multiply(3).all() == [1, 2, 1, 2, 1, 2]
    assert collect([1]).multiply(0).all() == []
    assert collect([1]).pipe(lambda c: c.count()) == 1
    assert collect([1]).pipe_into(list) == [1]
    assert collect([1]).pipe_through([lambda c: c.push(2), lambda c: c.sum()]) == 3
    tapped: list[int] = []
    assert collect([1]).tap(lambda c: tapped.append(c.first())).first() == 1
    assert tapped == [1]
    assert collect([1]).collect().all() == [1]


# --- where / aggregates / grouping ------------------------------------------


def test_where_family() -> None:
    rows = collect(
        [
            {"name": "Ada", "votes": 10, "active": True},
            {"name": "Grace", "votes": 5, "active": False},
            {"name": "Alan", "votes": 10, "active": True},
            {"name": None, "votes": None},
        ]
    )
    assert rows.where("votes", 10).count() == 2
    assert rows.where_strict("votes", 10).count() == 2
    assert rows.where("votes", ">", 5).pluck("name").values().all() == ["Ada", "Alan"]
    assert rows.where_in("name", ["Ada", "Alan"]).count() == 2
    assert rows.where_in_strict("votes", [10]).count() == 2
    assert rows.where_not_in("name", ["Ada"]).count() == 3
    assert rows.where_not_in_strict("votes", [10]).count() == 2
    assert rows.where_between("votes", [5, 10]).count() == 3
    assert rows.where_not_between("votes", [6, 9]).count() == 4
    assert rows.where_null("name").count() == 1
    assert rows.where_not_null("name").count() == 3
    assert collect([1, "a"]).where_instance_of(str).values().all() == ["a"]
    assert rows.first_where("name", "Ada")["votes"] == 10
    assert rows.first_or_fail(lambda r: r.get("name") == "Ada")["votes"] == 10
    with pytest.raises(ItemNotFoundError):
        rows.first_or_fail(lambda r: False)
    assert collect([1]).sole() == 1
    with pytest.raises(MultipleItemsFoundError):
        collect([1, 2]).sole()
    with pytest.raises(ItemNotFoundError):
        collect([]).sole()


def test_aggregates() -> None:
    rows = collect([{"n": 1}, {"n": 2}, {"n": 2}, {"n": 4}])
    assert rows.sum("n") == 9
    assert collect([1, 2, 3]).sum() == 6
    assert rows.avg("n") == 2.25
    assert collect([]).avg() is None
    assert rows.median("n") == 2
    assert collect([]).median() is None
    assert rows.mode("n") == [2]
    assert collect([]).mode() is None
    assert rows.min("n") == 1 and rows.max("n") == 4
    assert collect([3, 1]).min() == 1 and collect([3, 1]).max() == 3
    assert rows.count_by("n").get(2) == 2
    assert collect([1, 2, 3]).count_by(lambda n: n % 2).get(1) == 2
    assert collect([1, 2]).count_by().get(1) == 1
    assert collect([1, 2, 3, 4]).percentage(lambda n: n % 2 == 0) == 50.0
    assert collect([]).percentage(lambda n: True) == 0.0


def test_pluck_group_key_sort() -> None:
    rows = collect(
        [
            {"name": "Ada", "votes": 10},
            {"name": "Grace", "votes": 5},
            {"name": "Alan", "votes": 10},
        ]
    )
    assert rows.pluck("name").values().all() == ["Ada", "Grace", "Alan"]
    assert rows.pluck("name", "votes")[10] == "Alan"
    grouped = rows.group_by("votes")
    assert grouped.get(10).count() == 2
    assert rows.key_by("name").get("Ada")["votes"] == 10
    assert collect([3, 1, 2]).sort().all() == [1, 2, 3]
    assert collect([1, 3, 2]).sort_desc().all() == [3, 2, 1]
    assert collect([3, 1]).sort(lambda n: -n).all() == [3, 1]
    assert rows.sort_by("votes").first()["name"] == "Grace"
    assert rows.sort_by_desc("votes").first()["votes"] == 10
    assert collect({"b": 1, "a": 2}).sort_keys().keys().all() == ["a", "b"]
    assert collect({"a": 1, "b": 2}).sort_keys_desc().keys().all() == ["b", "a"]
    assert collect({"b": 1, "aa": 2}).sort_keys_using(len).keys().all() == ["b", "aa"]
    assert collect([1, 2, 3]).reverse().all() == {2: 3, 1: 2, 0: 1}
    shuffled = collect([1, 2, 3, 4, 5]).shuffle()
    assert sorted(shuffled.values().all()) == [1, 2, 3, 4, 5]


# --- slicing / chunking / mutation ------------------------------------------


def test_slice_splice_take_skip() -> None:
    assert collect([1, 2, 3, 4]).slice(1, 2).all() == [2, 3]
    assert collect([1, 2, 3]).slice(1).all() == [2, 3]
    c = collect([1, 2, 3, 4, 5])
    removed = c.splice(1, 2, [9, 8])
    assert removed.all() == [2, 3]
    assert c.all() == [1, 9, 8, 4, 5]
    c2 = collect([1, 2, 3])
    assert c2.splice(1).all() == [2, 3]
    assert c2.all() == [1]
    assert collect([1, 2, 3]).take(2).all() == [1, 2]
    assert collect([1, 2, 3]).take(-1).all() == [3]
    assert collect([1, 2, 3, 4]).take_until(lambda n: n == 3).all() == [1, 2]
    assert collect([1, 2, 3]).take_until(2).all() == [1]
    assert collect([1, 2, 3]).take_while(lambda n: n < 3).all() == [1, 2]
    assert collect([1, 2, 3]).skip(1).all() == [2, 3]
    assert collect([1, 2, 3, 4]).skip_until(lambda n: n == 3).all() == [3, 4]
    assert collect([1, 2, 3]).skip_until(2).all() == [2, 3]
    assert collect([1, 2, 3]).skip_while(lambda n: n < 3).all() == [3]


def test_chunk_split_page_nth() -> None:
    assert collect([1, 2, 3, 4]).chunk(2).map(lambda c: c.all()).all() == [[1, 2], [3, 4]]
    assert collect([]).chunk(2).all() == []
    chunks = collect([1, 2, 2, 3]).chunk_while(lambda cur, prev, chunk: cur == prev)
    assert chunks.count() == 3
    assert collect([1, 2, 3, 4, 5]).sliding(3, 2).map(lambda c: c.all()).all() == [
        [1, 2, 3],
        [3, 4, 5],
    ]
    assert collect([1, 2, 3]).sliding(5).all() == []
    parts = collect([1, 2, 3, 4, 5]).split(2)
    assert parts.count() == 2
    assert collect([]).split(2).count() == 2
    assert all(part.is_empty() for part in collect([]).split(2))
    assert collect([1, 2, 3, 4]).split_in(2).count() == 2
    assert collect(range(10)).for_page(2, 3).all() == [3, 4, 5]
    assert collect([1, 2, 3, 4, 5]).nth(2).all() == [1, 3, 5]
    assert collect([1, 2, 3, 4, 5]).nth(2, 1).all() == [2, 4]


def test_push_put_pop_shift_merge() -> None:
    assert collect([1]).push(2, 3).all() == [1, 2, 3]
    assert collect({"a": 1}).put("b", 2).all() == {"a": 1, "b": 2}
    assert collect([2, 3]).prepend(1).all() == [1, 2, 3]
    assert collect({"b": 2}).prepend(1, "a").all() == {"a": 1, "b": 2}
    c = collect([1, 2, 3])
    assert c.pop() == 3 and c.all() == [1, 2]
    c = collect([1, 2, 3, 4])
    assert c.pop(2).all() == [3, 4] and c.all() == [1, 2]
    assert collect([]).pop() is None
    c = collect([1, 2, 3])
    assert c.shift() == 1 and c.all() == [2, 3]
    c = collect([1, 2, 3, 4])
    assert c.shift(2).all() == [1, 2] and c.all() == [3, 4]
    assert collect([]).shift() is None
    c = collect({"a": 1, "b": 2})
    assert c.pull("a") == 1 and c.all() == {"b": 2}
    assert c.pull("z", 9) == 9
    c = collect({"a": 1, "b": 2, "c": 3})
    c.forget("a", "c")
    assert c.all() == {"b": 2}
    assert collect([1, 2]).merge([3]).all() == [1, 2, 3]
    assert collect({"a": 1}).merge({"b": 2}).all() == {"a": 1, "b": 2}
    assert collect({"a": {"x": 1}}).merge_recursive({"a": {"y": 2}, "b": 3}).get("a") == {
        "x": 1,
        "y": 2,
    }
    assert collect({"a": 1}).union({"a": 9, "b": 2}).all() == {"a": 1, "b": 2}
    assert collect([1]).concat([2]).all() == [1, 2]
    assert collect(["a", "b"]).combine([1, 2]).all() == {"a": 1, "b": 2}


def test_collapse_flatten_flip_pad_zip() -> None:
    assert collect([[1, 2], [3]]).collapse().all() == [1, 2, 3]
    assert collect([collect([1]), [2]]).collapse().all() == [1, 2]
    assert collect([{"a": 1}, {"b": 2}]).collapse_with_keys().all() == {"a": 1, "b": 2}
    assert collect([1, [2, [3]]]).flatten().all() == [1, 2, 3]
    assert collect([1, [2, [3]]]).flatten(1).all() == [1, 2, [3]]
    assert collect({"a": 1, "b": 2}).flip().all() == {1: "a", 2: "b"}
    assert collect([1, 2]).pad(4, 0).all() == [1, 2, 0, 0]
    assert collect([1, 2, 3]).pad(-4, 0).all() == [0, 1, 2, 3]
    assert collect([1, 2]).zip([3, 4]).all() == [[1, 3], [2, 4]]
    assert collect([1, 2]).cross_join([3, 4]).all() == [[1, 3], [1, 4], [2, 3], [2, 4]]


def test_diff_intersect_unique() -> None:
    assert collect([1, 2, 3]).diff([2]).values().all() == [1, 3]
    assert collect({"a": 1, "b": 2}).diff_assoc({"a": 1, "b": 9}).all() == {"b": 2}
    assert (
        collect({"a": "A"})
        .diff_assoc_using({"a": "a"}, lambda a, b: a.lower() == b.lower())
        .count()
        == 0
    )
    assert collect({"a": 1, "b": 2}).diff_keys({"a": 9}).all() == {"b": 2}
    assert collect([1, 2, 3]).intersect([2, 9]).values().all() == [2]
    assert collect(["A", "B"]).intersect_using(
        ["a"], lambda a, b: a.lower() == b.lower()
    ).values().all() == ["A"]
    assert collect({"a": 1, "b": 2}).intersect_assoc({"a": 1, "b": 9}).all() == {"a": 1}
    assert collect({"a": "A"}).intersect_assoc_using(
        {"a": "a"}, lambda a, b: a.lower() == b.lower()
    ).all() == {"a": "A"}
    assert collect({"a": 1, "b": 2}).intersect_by_keys({"a": 9}).all() == {"a": 1}
    assert collect([1, 1, 2]).unique().values().all() == [1, 2]
    assert collect([{"n": 1}, {"n": 1}, {"n": 2}]).unique("n").pluck("n").values().all() == [1, 2]
    assert collect([1, 1]).unique_strict().values().all() == [1]
    assert collect([1, 1, 2, 2]).duplicates().values().all() == [1, 2]
    assert collect([{"n": 1}, {"n": 1}]).duplicates("n").count() == 1
    assert collect([1, 1]).duplicates_strict().values().all() == [1]


def test_only_except_replace_implode() -> None:
    assert collect({"a": 1, "b": 2, "c": 3}).only("a", "c").all() == {"a": 1, "c": 3}
    assert collect({"a": 1, "b": 2}).except_("a").all() == {"b": 2}
    assert collect({"a": 1, "b": 2}).except_keys("b").all() == {"a": 1}
    assert collect({"a": 1}).replace({"a": 9, "b": 2}).all() == {"a": 9, "b": 2}
    assert collect({"a": {"x": 1}}).replace_recursive({"a": {"y": 2}}).get("a") == {"x": 1, "y": 2}
    assert collect([{"n": "a"}, {"n": "b"}]).implode("n", ",") == "a,b"
    assert collect(["a", "b"]).implode(",") == "a,b"
    assert collect(["a", "b", "c"]).join(", ", " and ") == "a, b and c"
    assert collect(["a"]).join(", ", " and ") == "a"
    assert collect([]).join(",") == ""


def test_search_select_random_every_ensure() -> None:
    assert collect(["a", "b", "c"]).search("b") == 1
    assert collect(["a", "b"]).search(lambda v: v == "b") == 1
    assert collect([1]).search(True, strict=True) is False
    assert collect([1]).search(9) is False
    assert collect([{"a": 1, "b": 2, "c": 3}]).select("a", "c").first() == {"a": 1, "c": 3}
    assert collect([1, 2, 3]).random() in {1, 2, 3}
    assert collect([1, 2, 3]).random(2).count() == 2
    assert collect([]).random() is None
    assert collect([]).random(2).all() == []
    assert collect([1, 2]).random(9).count() == 2
    assert collect([2, 4]).every(lambda n: n % 2 == 0)
    assert collect([1]).ensure(int) is not None
    with pytest.raises(TypeError):
        collect([1, "x"]).ensure(int)


def test_when_unless_dot_partition_before_after() -> None:
    assert collect([1]).when(True, lambda c: c.push(2)).all() == [1, 2]
    assert collect([1]).when(False, lambda c: c.push(2), lambda c: c.push(9)).all() == [1, 9]
    assert collect([1]).when(False, lambda c: c.push(2)).all() == [1]
    assert collect([]).when_empty(lambda c: c.push(1)).all() == [1]
    assert collect([1]).when_not_empty(lambda c: c.push(2)).all() == [1, 2]
    assert collect([1]).unless(False, lambda c: c.push(3)).all() == [1, 3]
    assert collect([]).unless_empty(lambda c: c.push(1)).all() == []
    assert collect([1]).unless_empty(lambda c: c.push(2)).all() == [1, 2]
    assert collect([1]).unless_not_empty(lambda c: c.push(9)).all() == [1]
    assert collect([]).unless_not_empty(lambda c: c.push(1)).all() == [1]
    data = collect({"user": {"name": "Ada", "emails": ["a@b.c"]}})
    assert data.dot().get("user.name") == "Ada"
    assert data.dot().get("user.emails.0") == "a@b.c"
    assert collect({"a.b": 1, "a.c": 2}).undot().get("a") == {"b": 1, "c": 2}
    passed, failed = collect([1, 2, 3]).partition(lambda n: n > 1)
    assert passed.values().all() == [2, 3] and failed.values().all() == [1]
    assert collect([1, 2, 3]).before(2) == 1
    assert collect([1, 2, 3]).before(1) is None
    assert collect([1, 2, 3]).before(9) is None
    assert collect([1, 2, 3]).after(2) == 3
    assert collect([1, 2, 3]).after(3) is None
    assert collect([1, 2, 3]).after(9) is None


def test_macros_and_getattr_error() -> None:
    Collection.macro("to_upper_join", lambda c, glue="-": glue.join(str(i).upper() for i in c))
    assert collect(["a", "b"]).to_upper_join() == "A-B"
    with pytest.raises(AttributeError):
        collect([1]).not_a_real_method()


def test_remaining_edge_branches() -> None:
    assert collect([1, [2], 3]).collapse().all() == [1, 2, 3]
    assert collect([{"a": 1}]).collapse().all() == [1]
    assert collect([collect({"a": 1}), {"b": 2}]).collapse_with_keys().all() == {"a": 1, "b": 2}
    assert collect([collect([1, [2]]), {"a": 3}]).flatten().all() == [1, 2, 3]
    assert collect([]).chunk_while(lambda *_: True).all() == []
    assert collect([1, 2]).split(0).all() == []
    assert collect(["a", "b"]).join("-") == "a-b"
    assert collect([1]).search(1, strict=True) == 0
    assert collect([{"a": 1, "b": 2}]).select(["a"]).first() == {"a": 1}
    assert collect([{"n": 1}]).where("n", "===", 1).count() == 1
    assert collect([{"n": 1}]).where("n", "!==", 2).count() == 1
    assert collect([{"n": 1}]).where("n", "<>", 2).count() == 1
    assert collect([{"n": 1}]).where("n", "<=", 1).count() == 1
    assert collect([{"n": 1}]).where("n", ">=", 1).count() == 1
    assert collect([{"n": 1}]).where("n", "<", 2).count() == 1
    assert collect([{"n": None}]).where("n", "<", 1).count() == 0
    assert collect([{"n": 1}]).where("n", "unknown", 1).count() == 1
    nested = collect({"outer": collect({"inner": 1})})
    assert nested.dot().get("outer.inner") == 1
    assert collect({"empty": {}, "list": []}).dot().all() == {"empty": {}, "list": []}
    assert collect({"a": 1}).forget("missing").all() == {"a": 1}
    assert collect([1, 2]).pad(2, 0).all() == [1, 2]
    assert collect({"a": {"x": 1}}).merge_recursive({"a": 9}).get("a") == 9
    assert collect([1]).unique(lambda n: n).all() == [1]
    dups = collect([{"n": 1}, {"n": 1}, {"n": 2}]).duplicates(lambda r: r["n"])
    assert dups.count() == 1
    # _as_items / wrap / times branches
    assert collect([1]).merge(collect([2])).all() == [1, 2]
    assert Collection(b"x").all() == [b"x"]
    assert Collection.wrap({"a": 1}).all() == {"a": 1}
    assert Collection.times(2).all() == [1, 2]
    with pytest.raises(KeyError):
        _ = collect({"a": 1})["missing"]
    collect([1, "x"]).each_spread(lambda n: True)
    assert collect([1, 2, 3]).skip_until(lambda n: False).all() == []
    assert collect([1, 2]).skip_while(lambda n: True).all() == []
    with pytest.raises(ValueError):
        collect([1]).chunk(0)
    assert collect([1]).pop(5).all() == [1]
    assert collect([1]).shift(5).all() == [1]
    assert collect({"a": 1, "b": 2}).diff_assoc_using({"c": 1}, lambda a, b: a == b).all() == {
        "a": 1,
        "b": 2,
    }
