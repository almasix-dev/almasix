"""M49 part 1 — higher order messages, and the `dd` / `dump` pair."""

from __future__ import annotations

import pytest

from avalon.support import collect
from avalon.support.collection import (
    HIGHER_ORDER_MESSAGES,
    BoundMessage,
    Collection,
    EmptyMessage,
)


class Member:
    def __init__(self, name: str, votes: int, group: str = "dev") -> None:
        self.name = name
        self.votes = votes
        self.group = group
        self.vip = False

    def mark_as_vip(self) -> Member:
        self.vip = True
        return self

    def weight(self, factor: int = 1) -> int:
        return self.votes * factor


def members() -> Collection:
    return collect([Member("Ada", 9), Member("Grace", 4, "ops"), Member("Linus", 6)])


# --- calling methods on every item -------------------------------------------


def test_each_calls_a_method_on_every_item() -> None:
    people = members()

    people.each.mark_as_vip()

    assert [person.vip for person in people] == [True, True, True]


def test_a_message_may_take_arguments() -> None:
    assert members().map.weight(2).all() == [18, 8, 12]


def test_the_method_form_still_works() -> None:
    people = members()

    assert people.map(lambda person: person.name).all() == ["Ada", "Grace", "Linus"]
    assert people.sum(lambda person: person.votes) == 19


# --- reading values from every item ------------------------------------------


def test_aggregates_read_an_attribute() -> None:
    people = members()

    assert people.sum.votes == 19
    assert people.max.votes == 9
    assert people.min.votes == 4
    assert people.avg.votes == pytest.approx(19 / 3)
    assert people.average.votes == pytest.approx(19 / 3)


def test_filters_and_sorts_read_an_attribute() -> None:
    people = members()

    assert people.filter.vip.count() == 0
    assert [p.name for p in people.sort_by.votes] == ["Grace", "Linus", "Ada"]
    assert [p.name for p in people.sort_by_desc.votes] == ["Ada", "Linus", "Grace"]
    assert people.group_by.group.keys().all() == ["dev", "ops"]
    assert people.key_by.name.keys().all() == ["Ada", "Grace", "Linus"]
    assert people.unique.group.count() == 2
    assert people.partition.vip.count() == 2


def test_predicates_read_an_attribute() -> None:
    people = members()
    people.first().mark_as_vip()

    assert people.some.vip is True
    assert people.every.vip is False
    assert people.contains.vip is True
    assert people.first.vip.name == "Ada"
    assert people.reject.vip.count() == 2
    assert people.take_while.vip.count() == 1
    assert people.skip_while.vip.count() == 2
    assert people.take_until.vip.count() == 0
    assert people.skip_until.vip.count() == 3


def test_messages_read_mapping_keys_too() -> None:
    rows = collect([{"votes": 3}, {"votes": 4}])

    assert rows.sum.votes == 7
    assert rows.map.votes.all() == [3, 4]


def test_flat_map_flattens_what_the_message_returns() -> None:
    class Team:
        def __init__(self, tags):
            self.tags = tags

    teams = collect([Team(["a", "b"]), Team(["c"])])

    assert teams.flat_map.tags.all() == ["a", "b", "c"]


# --- empty collections --------------------------------------------------------


def test_an_empty_collection_answers_value_reads() -> None:
    empty = collect([])

    assert empty.sum.votes == 0
    assert int(empty.sum.votes) == 0
    assert float(empty.sum.votes) == 0.0
    assert bool(empty.sum.votes) is False
    assert empty.max.votes == None  # noqa: E711 - EmptyMessage, not None itself
    assert empty.map.votes.all() == []
    assert len(empty.map.votes) == 0
    assert list(empty.map.votes) == []
    assert repr(empty.sum.votes) == "0"
    assert hash(empty.sum.votes) == hash(0)


def test_an_empty_collection_answers_method_calls() -> None:
    empty = collect([])

    # Neither form should blow up just because the result set came back empty.
    assert empty.each.mark_as_vip() == empty
    assert empty.map.weight(2).all() == []


def test_empty_message_hashes_a_none_result() -> None:
    assert hash(EmptyMessage(None)) == 0


def test_a_chain_past_a_message_survives_an_empty_collection() -> None:
    people = members()
    people.first().mark_as_vip()

    # `first` uses the member as a predicate, so the chain continues on a Member.
    assert people.first.vip.name == "Ada"

    # The same chain over no rows resolves to nothing rather than raising, since
    # whether the result set is empty is not the caller's business here.
    assert collect([]).first.vip.name == None  # noqa: E711 - reads as nothing
    assert collect([]).first.vip.mark_as_vip() is None

    # `.all` does exist on the result, so it is delegated rather than swallowed.
    assert collect([]).map.votes.all() == []


def test_a_message_descriptor_keeps_its_docstring() -> None:
    assert "higher order" not in (Collection.__dict__["map"].__doc__ or "")
    assert Collection.__dict__["sum"].__doc__ == Collection.sum.__doc__


# --- plumbing -----------------------------------------------------------------


def test_the_documented_messages_are_all_installed() -> None:
    people = members()

    for name in HIGHER_ORDER_MESSAGES:
        assert isinstance(getattr(people, name), BoundMessage), name


def test_reaching_a_message_through_the_class_gives_the_function() -> None:
    assert callable(Collection.map)
    assert not isinstance(Collection.map, BoundMessage)


def test_a_message_repr_names_the_method() -> None:
    assert repr(collect([1]).map) == "<higher order message 'map'>"


def test_dunder_lookups_do_not_become_messages() -> None:
    with pytest.raises(AttributeError):
        collect([1]).map.__deepcopy__  # noqa: B018


def test_model_collections_still_answer_messages() -> None:
    from avalon.orm.collection import Collection as ModelCollection

    people = ModelCollection([Member("Ada", 9), Member("Grace", 4, "ops")])

    assert people.sum.votes == 13
    assert people.unique.group.count() == 2


# --- dd / dump ----------------------------------------------------------------


def test_dump_prints_and_returns_the_collection(capsys) -> None:
    people = collect([1, 2])

    assert people.dump() is people
    printed = capsys.readouterr().err
    assert "1" in printed
    # The frame shown is the caller's, not the collection's own dump().
    assert "collection.py" not in printed


def test_dd_prints_and_halts(capsys) -> None:
    from avalon.debug import DumpAndDie

    with pytest.raises(DumpAndDie):
        collect([1, 2]).dd()
