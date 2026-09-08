"""M31 — the scheduler: frequencies, constraints, hooks, output, and the runner."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from almasix.cache import set_manager
from almasix.cache.manager import CacheManager
from almasix.console.mutex import Mutex
from almasix.console.scheduling import (
    Event,
    Schedule,
    ScheduledBackgroundTaskFinished,
    ScheduledTaskFailed,
    ScheduledTaskFinished,
    ScheduledTaskSkipped,
    ScheduledTaskStarting,
    clear_cache,
    interrupt,
    interrupted,
    run_due_events,
    run_event,
    run_schedule,
    run_task,
)
from almasix.console.scheduling.cron import cron_matches, field_matches, next_run_at

MONDAY = datetime(2026, 9, 7, 9, 0, 0)
SATURDAY = datetime(2026, 9, 5, 9, 0, 0)


@pytest.fixture()
def array_cache() -> Any:
    manager = CacheManager(config={"default": "array", "stores": {"array": {"driver": "array"}}})
    set_manager(manager)
    yield manager
    set_manager(None)


@pytest.fixture()
def no_cache() -> Any:
    set_manager(None)
    yield None
    set_manager(None)


def task(**kwargs: Any) -> Event:
    return Event("demo", command="demo:run", **kwargs)


# --- frequency vocabulary ----------------------------------------------------


@pytest.mark.parametrize(
    ("method", "expression"),
    [
        ("every_minute", "* * * * *"),
        ("every_two_minutes", "*/2 * * * *"),
        ("every_three_minutes", "*/3 * * * *"),
        ("every_four_minutes", "*/4 * * * *"),
        ("every_five_minutes", "*/5 * * * *"),
        ("every_ten_minutes", "*/10 * * * *"),
        ("every_fifteen_minutes", "*/15 * * * *"),
        ("every_thirty_minutes", "0,30 * * * *"),
        ("hourly", "0 * * * *"),
        ("daily", "0 0 * * *"),
        ("weekly", "0 0 * * 0"),
        ("monthly", "0 0 1 * *"),
        ("quarterly", "0 0 1 1-12/3 *"),
        ("yearly", "0 0 1 1 *"),
        ("weekdays", "* * * * 1,2,3,4,5"),
        ("weekends", "* * * * 6,0"),
        ("mondays", "* * * * 1"),
        ("sundays", "* * * * 0"),
        ("saturdays", "* * * * 6"),
    ],
)
def test_every_frequency_writes_the_expression_laravel_writes(
    method: str, expression: str
) -> None:
    assert getattr(task(), method)().expression == expression


@pytest.mark.parametrize(
    ("call", "expression"),
    [
        (lambda event: event.hourly_at(17), "17 * * * *"),
        (lambda event: event.hourly_at([15, 45]), "15,45 * * * *"),
        (lambda event: event.every_odd_hour(), "0 1-23/2 * * *"),
        (lambda event: event.every_two_hours(30), "30 */2 * * *"),
        (lambda event: event.every_three_hours(), "0 */3 * * *"),
        (lambda event: event.every_four_hours(), "0 */4 * * *"),
        (lambda event: event.every_six_hours(), "0 */6 * * *"),
        (lambda event: event.daily_at("13:00"), "0 13 * * *"),
        (lambda event: event.at("2:30"), "30 2 * * *"),
        (lambda event: event.twice_daily(1, 13), "0 1,13 * * *"),
        (lambda event: event.twice_daily_at(1, 13, 15), "15 1,13 * * *"),
        (lambda event: event.days_of_month([1, 10, 20]), "* * 1,10,20 * *"),
        (lambda event: event.weekly_on(1, "8:00"), "0 8 * * 1"),
        (lambda event: event.monthly_on(4, "15:00"), "0 15 4 * *"),
        (lambda event: event.twice_monthly(1, 16, "13:00"), "0 13 1,16 * *"),
        (lambda event: event.quarterly_on(4, "14:00"), "0 14 4 1-12/3 *"),
        (lambda event: event.yearly_on(6, 1, "17:00"), "0 17 1 6 *"),
        (lambda event: event.days(0, 3), "* * * * 0,3"),
        (lambda event: event.days([Schedule.SUNDAY, Schedule.WEDNESDAY]), "* * * * 0,3"),
    ],
)
def test_the_parameterised_frequencies_match_laravels_table(call: Any, expression: str) -> None:
    assert call(task()).expression == expression


@pytest.mark.parametrize(
    ("method", "seconds"),
    [
        ("every_second", 1),
        ("every_two_seconds", 2),
        ("every_five_seconds", 5),
        ("every_ten_seconds", 10),
        ("every_fifteen_seconds", 15),
        ("every_twenty_seconds", 20),
        ("every_thirty_seconds", 30),
    ],
)
def test_sub_minute_frequencies_repeat_within_the_minute(method: str, seconds: int) -> None:
    event = getattr(task(), method)()

    assert event.repeat_seconds == seconds
    assert event.expression == "* * * * *"
    assert event.should_repeat_now(datetime(2026, 9, 7, 9, 0, 0)) is True
    assert event.should_repeat_now(MONDAY.replace(second=seconds)) is True
    assert event.frequency().startswith("every ")


def test_a_task_without_sub_minute_repeats_never_repeats_now() -> None:
    assert task().every_minute().should_repeat_now(MONDAY) is False


def test_last_day_of_month_asks_the_calendar_rather_than_the_expression() -> None:
    event = task().last_day_of_month("15:00")

    assert event.is_due(datetime(2026, 9, 30, 15, 0)) is True
    assert event.is_due(datetime(2026, 9, 29, 15, 0)) is False
    # February, which is the month Laravel's splice-at-definition gets wrong.
    assert event.is_due(datetime(2027, 2, 28, 15, 0)) is True


def test_camel_case_spellings_reach_the_same_methods() -> None:
    assert task().everyFiveMinutes().expression == "*/5 * * * *"
    assert task().dailyAt("13:00").expression == "0 13 * * *"
    assert task().lastDayOfMonth("15:00").expression == "0 15 * * *"
    assert task().withoutOverlapping(10).overlapping_expires_at == 10
    assert task().onOneServer().runs_on_one_server is True
    assert task().runInBackground().runs_in_background is True
    assert task().evenInMaintenanceMode().runs_in_maintenance_mode is True


# --- constraints -------------------------------------------------------------


def test_between_and_unless_between_bound_the_time_of_day() -> None:
    window = task().hourly().between("8:00", "17:00")
    outside = task().hourly().unless_between("23:00", "4:00")

    assert window.is_due(datetime(2026, 9, 7, 9, 0)) is True
    assert window.is_due(datetime(2026, 9, 7, 19, 0)) is False
    assert outside.is_due(datetime(2026, 9, 7, 2, 0)) is False
    assert outside.is_due(datetime(2026, 9, 7, 9, 0)) is True


def test_a_between_window_can_cross_midnight() -> None:
    event = task().hourly().between("22:00", "2:00")

    assert event.is_due(datetime(2026, 9, 7, 23, 0)) is True
    assert event.is_due(datetime(2026, 9, 7, 1, 0)) is True
    assert event.is_due(datetime(2026, 9, 7, 12, 0)) is False


def test_when_and_skip_decide_outside_the_clock() -> None:
    assert task().when(lambda: True).filters_pass() is True
    assert task().when(lambda: False).filters_pass() is False
    assert task().skip(lambda: True).filters_pass() is False
    assert task().skip(lambda: False).filters_pass() is True
    # Every when must pass, and a plain bool is accepted for both.
    assert task().when(True).when(lambda: False).filters_pass() is False
    assert task().skip(False).filters_pass() is True


def test_environments_limits_the_task_to_the_named_app_env(monkeypatch: Any) -> None:
    monkeypatch.setattr("almasix.console.scheduling.event._environment", lambda: "staging")

    assert task().environments("staging", "production").filters_pass() is True
    assert task().environments(["local"]).filters_pass() is False


def test_the_environment_reader_falls_back_when_no_app_is_booted() -> None:
    from almasix.console.scheduling.event import _environment

    assert isinstance(_environment(), str)


def test_a_timezone_moves_the_clock_the_task_is_read_against() -> None:
    event = task().daily_at("02:00").timezone("Australia/Sydney")
    naive = task().daily_at("02:00")

    # 16:00 UTC on the 7th is 02:00 on the 8th in Sydney (UTC+10).
    moment = datetime(2026, 9, 7, 16, 0, tzinfo=__import__("datetime").timezone.utc)
    assert event.is_due(moment) is True
    assert naive.is_due(moment) is False


def test_a_naive_moment_is_read_as_local_time_before_conversion() -> None:
    event = task().every_minute().timezone("UTC")

    assert event.is_due(datetime(2026, 9, 7, 9, 0)) is True


# --- cron --------------------------------------------------------------------


def test_cron_reads_lists_ranges_steps_and_names() -> None:
    assert cron_matches("*/5 * * * *", datetime(2026, 9, 7, 9, 5)) is True
    assert cron_matches("0 0 1 1-12/3 *", datetime(2026, 10, 1, 0, 0)) is True
    assert cron_matches("0 0 1 1-12/3 *", datetime(2026, 11, 1, 0, 0)) is False
    assert cron_matches("0 9 * * mon", MONDAY) is True
    assert cron_matches("0 9 * * sat", MONDAY) is False
    assert cron_matches("0 0 1 jan *", datetime(2026, 1, 1)) is True
    assert cron_matches("0 9 * * 7", datetime(2026, 9, 6, 9, 0)) is True  # 7 is Sunday too
    assert field_matches("?", 5, 0, 59) is True
    assert field_matches("10/5", 20, 0, 59) is True
    assert field_matches("10/5", 22, 0, 59) is False


def test_a_restricted_day_of_month_and_weekday_are_read_as_either() -> None:
    # Cron's own rule: "the 1st, or any Monday", not "a Monday the 1st".
    expression = "0 0 1 * mon"

    assert cron_matches(expression, datetime(2026, 9, 1)) is True  # a Tuesday the 1st
    assert cron_matches(expression, datetime(2026, 9, 7)) is True  # a Monday
    assert cron_matches(expression, datetime(2026, 9, 8)) is False


def test_a_malformed_expression_is_refused() -> None:
    with pytest.raises(ValueError, match="Invalid cron expression"):
        cron_matches("* * *", MONDAY)
    with pytest.raises(ValueError, match="Invalid cron step"):
        field_matches("*/0", 1, 0, 59)


def test_next_run_at_finds_the_following_due_minute() -> None:
    assert next_run_at("0 2 * * *", datetime(2026, 9, 7, 3, 0)) == datetime(2026, 9, 8, 2, 0)
    assert task().daily_at("02:00").next_run_at(datetime(2026, 9, 7, 1, 0)) == datetime(
        2026, 9, 7, 2, 0
    )
    # A filtered task skips the minutes its filters turn away.
    monthly = task().last_day_of_month("15:00")
    assert monthly.next_run_at(datetime(2026, 9, 1, 0, 0)) == datetime(2026, 9, 30, 15, 0)


def test_a_sub_minute_task_is_next_due_on_its_next_second() -> None:
    event = task().every_ten_seconds()

    assert event.next_run_at(datetime(2026, 9, 7, 9, 0, 25)) == datetime(2026, 9, 7, 9, 0, 30)
    # Standing on a boundary, the next run is now.
    assert event.next_run_at(datetime(2026, 9, 7, 9, 0, 30)) == datetime(2026, 9, 7, 9, 0, 30)
    # The last boundary of the minute rolls into the next minute's own tick.
    assert event.next_run_at(datetime(2026, 9, 7, 9, 0, 55)) == datetime(2026, 9, 7, 9, 1)


def test_an_expression_nothing_matches_gives_the_moment_back(monkeypatch: Any) -> None:
    assert next_run_at("0 0 30 2 *", MONDAY) == MONDAY

    # A constraint no minute can satisfy: the 15th is never the last of a month.
    monkeypatch.setattr("almasix.console.scheduling.event._SCAN_LIMIT", 120)
    impossible = task().last_day_of_month("15:00").days_of_month(15)
    assert impossible.next_run_at(MONDAY) == MONDAY


def test_a_sub_minute_task_outside_its_own_hour_waits_for_that_hour() -> None:
    hourly_seconds = task().every_ten_seconds().hourly()

    assert hourly_seconds.next_run_at(datetime(2026, 9, 7, 9, 5, 20)) == datetime(
        2026, 9, 7, 10, 0
    )


# --- identity ----------------------------------------------------------------


def test_a_task_names_itself_after_what_it_runs() -> None:
    assert task().summary() == "demo:run"
    assert Event("shell", shell="node script.js").summary() == "node script.js"
    assert Event("closure", callback=lambda: None).summary() == "closure"
    assert Event("named").name("nightly").mutex_name() == "nightly"
    assert Event("purposeful").purpose("Send the digest").description == "Send the digest"
    assert repr(task().daily()) == "<Event 'demo:run' '0 0 * * *'>"


def test_a_job_task_is_summarised_by_its_class() -> None:
    class Heartbeat:
        pass

    schedule = Schedule()
    event = schedule.job(Heartbeat(), "heartbeats", "redis").every_five_minutes()

    assert event.summary() == "Heartbeat"
    assert (event.job_queue, event.job_connection) == ("heartbeats", "redis")


# --- the schedule ------------------------------------------------------------


def test_the_schedule_collects_every_kind_of_task() -> None:
    schedule = Schedule()
    schedule.call(lambda: None, description="closure").daily()
    schedule.command("mail:digest").hourly()
    schedule.command("emails:send", ["taylor", "--force"]).daily()
    schedule.exec("node script.js").weekly()

    assert [event.summary() for event in schedule.events] == [
        "closure",
        "mail:digest",
        "emails:send taylor --force",
        "node script.js",
    ]
    assert schedule.due_events(datetime(2026, 9, 7, 9, 0)) == [schedule.events[1]]


def test_a_group_shares_its_attributes_with_every_task_inside() -> None:
    schedule = Schedule()

    def tasks() -> None:
        schedule.command("emails:send --force")
        schedule.command("emails:prune")

    schedule.daily().on_one_server().timezone("America/New_York").group(tasks)

    assert len(schedule.events) == 2
    for event in schedule.events:
        assert event.expression == "0 0 * * *"
        assert event.runs_on_one_server is True
        assert event._timezone == "America/New_York"


def test_a_group_stops_sharing_once_it_closes() -> None:
    schedule = Schedule()
    schedule.daily().group(lambda: schedule.command("inside"))
    schedule.command("outside").hourly()

    assert schedule.events[0].expression == "0 0 * * *"
    assert schedule.events[1].expression == "0 * * * *"


def test_groups_nest_and_the_inner_frequency_is_spliced_over_the_outer() -> None:
    schedule = Schedule()

    def outer() -> None:
        schedule.command("plain")
        schedule.every_five_minutes().group(lambda: schedule.command("often"))

    schedule.daily().on_one_server().group(outer)

    assert schedule.events[0].expression == "0 0 * * *"
    # Frequencies write cron fields rather than replacing the expression, so
    # the inner five minutes lands on the outer midnight hour — as in Laravel.
    assert schedule.events[1].expression == "*/5 0 * * *"
    assert all(event.runs_on_one_server for event in schedule.events)


def test_the_empty_group_is_allowed_and_the_camel_spelling_works() -> None:
    schedule = Schedule()
    schedule.group(lambda: schedule.command("plain"))
    schedule.everyFiveMinutes().group(lambda: schedule.command("often"))

    assert schedule.events[0].expression == "* * * * *"
    assert schedule.events[1].expression == "*/5 * * * *"


def test_the_schedule_refuses_names_it_does_not_know() -> None:
    schedule = Schedule()

    with pytest.raises(AttributeError):
        schedule.every_blue_moon
    with pytest.raises(AttributeError):
        schedule.daily().every_blue_moon


def test_the_schedule_reports_sub_minute_tasks_and_the_chosen_cache() -> None:
    schedule = Schedule()
    schedule.command("plain").daily()

    assert schedule.has_sub_minute_events() is False
    schedule.command("often").every_ten_seconds()
    assert schedule.has_sub_minute_events() is True
    assert schedule.use_cache("redis").cache_store == "redis"
    schedule.clear()
    assert schedule.events == []


# --- running one task --------------------------------------------------------


def test_a_callback_task_runs_and_reports_its_exit_code(tmp_path: Path, no_cache: Any) -> None:
    seen: list[str] = []
    event = Event("cb", callback=lambda: seen.append("ok")).every_minute()

    assert run_event(event, base_path=tmp_path) == 0
    assert seen == ["ok"]
    assert run_event(Event("code", callback=lambda: 3), base_path=tmp_path) == 3


def test_a_command_task_goes_through_the_runner(tmp_path: Path, no_cache: Any) -> None:
    called: list[str] = []

    code = run_event(
        Event("inspire", command="inspire"),
        base_path=tmp_path,
        runner=lambda name: called.append(name) or 7,
    )

    assert (code, called) == (7, ["inspire"])
    # With no runner there is nothing to invoke, and that is not a failure.
    assert run_event(Event("inspire", command="inspire"), base_path=tmp_path) == 0


def test_a_shell_task_runs_through_the_shell(tmp_path: Path, no_cache: Any) -> None:
    schedule = Schedule()
    event = schedule.exec("echo scheduled-hello").every_minute()

    outcome = run_task(event, base_path=tmp_path)

    assert outcome.code == 0
    assert "scheduled-hello" in outcome.output


def test_a_failing_shell_task_reports_its_exit_code(tmp_path: Path, no_cache: Any) -> None:
    outcome = run_task(Event("fail", shell="exit 4"), base_path=tmp_path)

    assert outcome.code == 4


def test_a_task_that_raises_is_reported_rather_than_ending_the_tick(
    tmp_path: Path, no_cache: Any
) -> None:
    def boom() -> None:
        raise RuntimeError("task exploded")

    outcome = run_task(Event("boom", callback=boom), base_path=tmp_path)

    assert outcome.code == 1
    assert outcome.skipped is False


# --- constraints at run time -------------------------------------------------


def test_a_constraint_that_says_no_skips_the_run(tmp_path: Path, no_cache: Any) -> None:
    ran: list[int] = []
    event = Event("skipped", callback=lambda: ran.append(1)).skip(lambda: True)

    outcome = run_task(event, base_path=tmp_path)

    assert (outcome.skipped, ran) == (True, [])


def test_maintenance_mode_stops_tasks_that_did_not_ask_to_run(
    tmp_path: Path, no_cache: Any
) -> None:
    (tmp_path / "storage" / "framework").mkdir(parents=True)
    (tmp_path / "storage" / "framework" / "down").write_text("down", encoding="utf-8")
    ran: list[str] = []

    ordinary = Event("ordinary", callback=lambda: ran.append("ordinary"))
    insistent = Event(
        "insistent", callback=lambda: ran.append("insistent")
    ).even_in_maintenance_mode()

    assert run_task(ordinary, base_path=tmp_path).skipped is True
    assert run_task(insistent, base_path=tmp_path).skipped is False
    assert ran == ["insistent"]


# --- overlapping and one server ---------------------------------------------


def test_without_overlapping_prefers_a_cache_lock(tmp_path: Path, array_cache: Any) -> None:
    ran = {"n": 0}
    event = Event("demo", callback=lambda: ran.__setitem__("n", ran["n"] + 1))
    event.without_overlapping(10)

    assert run_event(event, base_path=tmp_path) == 0
    assert ran["n"] == 1

    from almasix.cache.manager import Cache

    lock = Cache.lock(f"schedule:{event.mutex_name()}", seconds=600)
    assert lock.get() is True
    assert run_task(event, base_path=tmp_path).skipped is True
    assert ran["n"] == 1
    lock.release()


def test_without_overlapping_falls_back_to_the_filesystem_mutex(
    tmp_path: Path, no_cache: Any
) -> None:
    ran = {"n": 0}
    event = Event("fs", callback=lambda: ran.__setitem__("n", ran["n"] + 1))
    event.without_overlapping()

    assert run_event(event, base_path=tmp_path) == 0
    held = Mutex(tmp_path, event.mutex_name())
    assert held.acquire() is True
    assert run_task(event, base_path=tmp_path).skipped is True
    held.release()
    assert run_event(event, base_path=tmp_path) == 0
    assert ran["n"] == 2


def test_the_overlapping_lock_expires_after_the_minutes_it_was_given(
    tmp_path: Path, array_cache: Any
) -> None:
    event = Event("expiring", command="demo:run").without_overlapping(5)
    taken: list[int] = []

    class Recorder:
        def lock(self, name: str, seconds: int | None = None, **kwargs: Any) -> Any:
            taken.append(int(seconds or 0))
            return array_cache.store().lock(name, seconds=seconds, **kwargs)

        def __getattr__(self, name: str) -> Any:
            return getattr(array_cache.store(), name)

    from almasix.console.scheduling import runner as runner_module

    original = runner_module._cache
    runner_module._cache = lambda store: Recorder()
    try:
        run_event(event, base_path=tmp_path)
    finally:
        runner_module._cache = original

    assert taken == [300]


def test_one_server_lets_only_the_first_claim_through(tmp_path: Path, array_cache: Any) -> None:
    ran: list[str] = []
    first = Event("report", command="report:generate").on_one_server()
    second = Event("report", command="report:generate").on_one_server()
    first.callback = lambda: ran.append("first")
    second.callback = lambda: ran.append("second")

    assert run_task(first, base_path=tmp_path).skipped is False
    assert run_task(second, base_path=tmp_path).skipped is True
    assert ran == ["first"]


def test_one_server_needs_a_name_it_can_share_across_servers(
    tmp_path: Path, array_cache: Any
) -> None:
    closure = Event("closure", callback=lambda: None).on_one_server()

    with pytest.raises(RuntimeError, match="needs a name"):
        run_task(closure, base_path=tmp_path)

    named = Event("closure", callback=lambda: None).name("reset-counts").on_one_server()
    assert run_task(named, base_path=tmp_path).skipped is False


def test_without_a_shared_cache_there_is_only_one_server(tmp_path: Path, no_cache: Any) -> None:
    event = Event("report", command="report:generate").on_one_server()

    assert run_task(event, base_path=tmp_path).skipped is False


def test_clear_cache_releases_the_locks_a_stuck_task_left(
    tmp_path: Path, array_cache: Any
) -> None:
    schedule = Schedule()
    event = schedule.command("stuck").every_minute().without_overlapping()
    schedule.command("free").every_minute()

    from almasix.cache.manager import Cache

    lock = Cache.lock(f"schedule:{event.mutex_name()}", seconds=600)
    assert lock.get() is True
    assert run_task(event, base_path=tmp_path).skipped is True

    assert clear_cache(schedule) == ["stuck"]
    assert run_task(event, base_path=tmp_path).skipped is False


def test_clear_cache_without_a_cache_has_nothing_to_release(no_cache: Any) -> None:
    schedule = Schedule()
    schedule.command("stuck").without_overlapping()

    assert clear_cache(schedule) == []


# --- hooks -------------------------------------------------------------------


def test_the_hooks_run_in_laravels_order(tmp_path: Path, no_cache: Any) -> None:
    seen: list[str] = []
    event = (
        Event("hooked", callback=lambda: seen.append("task"))
        .before(lambda: seen.append("before"))
        .after(lambda: seen.append("after"))
        .on_success(lambda: seen.append("success"))
        .on_failure(lambda: seen.append("failure"))
    )

    run_event(event, base_path=tmp_path)

    assert seen == ["before", "task", "after", "success"]


def test_a_failing_task_runs_the_failure_hooks(tmp_path: Path, no_cache: Any) -> None:
    seen: list[str] = []
    event = (
        Event("failing", shell="exit 2")
        .then(lambda: seen.append("then"))
        .on_success(lambda: seen.append("success"))
        .on_failure(lambda: seen.append("failure"))
    )

    assert run_event(event, base_path=tmp_path) == 2
    assert seen == ["then", "failure"]


def test_a_hook_that_asks_for_output_is_handed_it(tmp_path: Path, no_cache: Any) -> None:
    seen: list[str] = []

    def with_output(output: Any) -> None:
        seen.append(output.upper().value())

    event = Event("noisy", shell="echo from-the-task").on_success(with_output)
    run_event(event, base_path=tmp_path)

    assert seen == ["FROM-THE-TASK\n"]


def test_a_hook_with_only_optional_parameters_is_called_bare(
    tmp_path: Path, no_cache: Any
) -> None:
    seen: list[str] = []

    def optional(output: Any = None) -> None:
        seen.append("called" if output is None else "given")

    run_event(Event("cb", callback=lambda: None).after(optional), base_path=tmp_path)

    assert seen == ["called"]


def test_the_ping_family_reaches_the_http_client(tmp_path: Path, no_cache: Any) -> None:
    pinged: list[str] = []

    class FakeHttp:
        @staticmethod
        def get(url: str) -> None:
            pinged.append(url)

    import almasix.client

    original = almasix.client.Http
    almasix.client.Http = FakeHttp  # type: ignore[misc]
    try:
        event = (
            Event("pinged", shell="echo ok")
            .ping_before("https://example.test/before")
            .then_ping("https://example.test/after")
            .ping_on_success("https://example.test/success")
            .ping_on_failure("https://example.test/failure")
        )
        run_event(event, base_path=tmp_path)
    finally:
        almasix.client.Http = original  # type: ignore[misc]

    assert pinged == [
        "https://example.test/before",
        "https://example.test/after",
        "https://example.test/success",
    ]


def test_the_conditional_pings_only_register_when_the_condition_holds() -> None:
    event = (
        Event("conditional", command="demo:run")
        .ping_before_if(False, "https://example.test/no")
        .ping_before_if(True, "https://example.test/yes")
        .then_ping_if(lambda: False, "https://example.test/no")
        .then_ping_if(lambda: True, "https://example.test/yes")
        .ping_on_success_if(False, "https://example.test/no")
        .ping_on_success_if(True, "https://example.test/yes")
        .ping_on_failure_if(False, "https://example.test/no")
        .ping_on_failure_if(True, "https://example.test/yes")
    )

    assert len(event.before_callbacks) == 1
    assert len(event.after_callbacks) == 1
    assert len(event.success_callbacks) == 1
    assert len(event.failure_callbacks) == 1


def test_a_ping_that_cannot_reach_its_url_does_not_fail_the_task(
    tmp_path: Path, no_cache: Any
) -> None:
    event = Event("cb", callback=lambda: None).ping_before("http://127.0.0.1:1/nothing")

    assert run_event(event, base_path=tmp_path) == 0


# --- output ------------------------------------------------------------------


def test_output_is_written_to_the_file_it_was_sent_to(tmp_path: Path, no_cache: Any) -> None:
    path = tmp_path / "logs" / "digest.log"
    event = Event("noisy", shell="echo first").send_output_to(str(path))

    run_event(event, base_path=tmp_path)
    assert path.read_text(encoding="utf-8").strip() == "first"

    # Sending again replaces, appending adds.
    run_event(Event("noisy", shell="echo second").send_output_to(str(path)), base_path=tmp_path)
    assert path.read_text(encoding="utf-8").strip() == "second"
    run_event(Event("noisy", shell="echo third").append_output_to(str(path)), base_path=tmp_path)
    assert path.read_text(encoding="utf-8").split() == ["second", "third"]


def test_output_can_be_emailed_always_or_only_on_failure(
    tmp_path: Path, no_cache: Any
) -> None:
    sent: list[tuple[tuple[str, ...], str, int]] = []

    from almasix.console.scheduling import runner as runner_module

    original = runner_module._mail_output

    def record(event: Event, output: str, code: int) -> None:
        if not event.email_addresses or (event.email_only_on_failure and code == 0):
            return
        sent.append((tuple(event.email_addresses), output, code))

    runner_module._mail_output = record
    try:
        run_event(
            Event("ok", shell="echo fine").email_output_to("ops@example.test"),
            base_path=tmp_path,
        )
        run_event(
            Event("ok2", shell="echo fine").email_output_on_failure("ops@example.test"),
            base_path=tmp_path,
        )
        run_event(
            Event("bad", shell="exit 3").email_output_on_failure(["ops@example.test"]),
            base_path=tmp_path,
        )
    finally:
        runner_module._mail_output = original

    assert [(addresses, code) for addresses, _, code in sent] == [
        (("ops@example.test",), 0),
        (("ops@example.test",), 3),
    ]


def test_the_output_mail_states_what_happened() -> None:
    from almasix.console.scheduling.mail import ScheduledTaskOutput

    ok = ScheduledTaskOutput("report:generate", "all good", 0)
    bad = ScheduledTaskOutput("report:generate", "", 3)

    assert ok.envelope().subject == "Scheduled task output: report:generate"
    assert ok.content().text == "all good"
    assert "failed with exit code 3" in bad.envelope().subject
    assert bad.content().text == "(no output)"


def test_mailing_output_goes_through_the_mailer(tmp_path: Path, no_cache: Any) -> None:
    sent: list[Any] = []

    class FakePending:
        def send(self, mailable: Any) -> None:
            sent.append(mailable)

    import almasix.mail.mailer as mailer_module

    original = mailer_module.Mail
    mailer_module.Mail = type("Mail", (), {"to": staticmethod(lambda *a: FakePending())})
    try:
        run_event(
            Event("mailed", shell="echo hello").email_output_to("ops@example.test"),
            base_path=tmp_path,
        )
    finally:
        mailer_module.Mail = original

    assert len(sent) == 1
    assert "hello" in sent[0].content().text


def test_a_mailer_that_fails_does_not_fail_the_task(tmp_path: Path, no_cache: Any) -> None:
    import almasix.mail.mailer as mailer_module

    original = mailer_module.Mail

    class Broken:
        @staticmethod
        def to(*addresses: str) -> Any:
            raise RuntimeError("no mailer configured")

    mailer_module.Mail = Broken
    try:
        code = run_event(
            Event("mailed", shell="echo hello").email_output_to("ops@example.test"),
            base_path=tmp_path,
        )
    finally:
        mailer_module.Mail = original

    assert code == 0


# --- the tick ----------------------------------------------------------------


def test_run_due_events_runs_what_is_due_and_leaves_the_rest(
    tmp_path: Path, no_cache: Any
) -> None:
    seen: list[str] = []
    schedule = Schedule()
    schedule.call(lambda: seen.append("minutely"), description="minutely").every_minute()
    schedule.call(lambda: seen.append("daily"), description="daily").daily()

    outcomes = run_due_events(
        schedule, base_path=tmp_path, at=datetime(2026, 9, 7, 9, 30)
    )

    assert seen == ["minutely"]
    assert [outcome.event.description for outcome in outcomes] == ["minutely"]


def test_a_background_task_runs_alongside_and_is_waited_for(
    tmp_path: Path, no_cache: Any
) -> None:
    order: list[str] = []
    schedule = Schedule()

    def slow() -> None:
        import time

        time.sleep(0.05)
        order.append("background")

    schedule.call(slow, description="background").every_minute().run_in_background()
    schedule.call(lambda: order.append("foreground"), description="foreground").every_minute()

    outcomes = run_due_events(schedule, base_path=tmp_path, at=MONDAY)

    assert order == ["foreground", "background"]
    assert {outcome.event.description for outcome in outcomes} == {"foreground", "background"}


def test_the_tick_reports_each_task_to_the_callbacks_it_was_given(
    tmp_path: Path, no_cache: Any
) -> None:
    started: list[str] = []
    finished: list[str] = []
    schedule = Schedule()
    schedule.command("one").every_minute()
    schedule.call(lambda: None, description="two").every_minute().run_in_background()

    run_due_events(
        schedule,
        base_path=tmp_path,
        runner=lambda name: 0,
        at=MONDAY,
        on_start=lambda event: started.append(event.summary()),
        on_finish=lambda outcome: finished.append(outcome.event.summary()),
    )

    assert started == ["one", "two"]
    assert sorted(finished) == ["one", "two"]


def test_run_schedule_is_a_single_tick_without_sub_minute_tasks(
    tmp_path: Path, no_cache: Any
) -> None:
    seen: list[str] = []
    schedule = Schedule()
    schedule.call(lambda: seen.append("tick"), description="tick").every_minute()

    outcomes = run_schedule(
        schedule,
        base_path=tmp_path,
        now=lambda: MONDAY,
        sleep=lambda seconds: None,
    )

    assert seen == ["tick"]
    assert len(outcomes) == 1


def test_run_schedule_keeps_going_for_the_minute_when_seconds_are_scheduled(
    tmp_path: Path, no_cache: Any
) -> None:
    seen: list[int] = []
    schedule = Schedule()
    schedule.call(
        lambda: seen.append(len(seen)), description="every-thirty"
    ).every_thirty_seconds()

    moments = iter(
        [
            MONDAY.replace(second=0),
            MONDAY.replace(second=0),  # the loop's first look
            MONDAY.replace(second=30),
            MONDAY.replace(second=30),  # the same second twice runs once
            MONDAY.replace(minute=1, second=0),  # the minute is out
        ]
    )

    outcomes = run_schedule(
        schedule,
        base_path=tmp_path,
        now=lambda: next(moments),
        sleep=lambda seconds: None,
    )

    assert len(seen) == 2  # second 0 from the tick, second 30 from the loop
    assert len(outcomes) == 2


def test_an_interrupt_stops_the_sub_minute_loop(tmp_path: Path, no_cache: Any) -> None:
    seen: list[int] = []
    schedule = Schedule()
    schedule.call(lambda: seen.append(1), description="often").every_second()

    interrupt(base_path=tmp_path, at=MONDAY)
    moments = iter([MONDAY, MONDAY.replace(second=1), MONDAY.replace(second=2)])

    run_schedule(
        schedule,
        base_path=tmp_path,
        now=lambda: next(moments),
        sleep=lambda seconds: None,
    )

    assert len(seen) == 1  # the opening tick only


def test_an_interrupt_is_recorded_and_read_back(tmp_path: Path, no_cache: Any) -> None:
    minute = datetime.now().replace(second=0, microsecond=0)

    assert interrupted(minute, base_path=tmp_path) is False
    interrupt(base_path=tmp_path)
    assert interrupted(minute, base_path=tmp_path) is True
    # An interrupt is for this minute only.
    assert interrupted(minute.replace(minute=(minute.minute + 1) % 60), base_path=tmp_path) is False


def test_an_interrupt_goes_through_the_cache_when_there_is_one(
    tmp_path: Path, array_cache: Any
) -> None:
    from almasix.console.scheduling.runner import INTERRUPT_KEY

    minute = datetime.now().replace(second=0, microsecond=0)
    interrupt(base_path=tmp_path)

    assert array_cache.store().get(INTERRUPT_KEY) == minute.isoformat()
    assert interrupted(minute, base_path=tmp_path) is True
    assert not (tmp_path / "storage" / "framework" / "schedule" / "interrupt").exists()


# --- events ------------------------------------------------------------------


def test_the_lifecycle_events_are_dispatched(tmp_path: Path, no_cache: Any) -> None:
    from almasix.events.dispatcher import Dispatcher
    from almasix.events.facade import Event as Bus

    seen: list[Any] = []
    Bus.set_dispatcher(Dispatcher())
    for kind in (
        ScheduledTaskStarting,
        ScheduledTaskFinished,
        ScheduledTaskFailed,
        ScheduledTaskSkipped,
        ScheduledBackgroundTaskFinished,
    ):
        Bus.listen(kind, lambda event: seen.append(type(event).__name__))

    schedule = Schedule()
    schedule.call(lambda: None, description="fine").every_minute()
    schedule.command("failing").every_minute()
    schedule.call(lambda: None, description="turned-away").every_minute().skip(lambda: True)
    schedule.call(lambda: None, description="backgrounded").every_minute().run_in_background()

    run_due_events(schedule, base_path=tmp_path, runner=lambda name: 5, at=MONDAY)

    assert seen.count("ScheduledTaskStarting") == 3
    assert seen.count("ScheduledTaskFinished") == 3
    assert seen.count("ScheduledTaskFailed") == 1  # the command exited 5
    assert seen.count("ScheduledTaskSkipped") == 1
    assert seen.count("ScheduledBackgroundTaskFinished") == 1
    Bus.flush()


def test_a_raising_task_dispatches_the_failure_event(tmp_path: Path, no_cache: Any) -> None:
    from almasix.events.dispatcher import Dispatcher
    from almasix.events.facade import Event as Bus

    failures: list[Any] = []
    Bus.set_dispatcher(Dispatcher())
    Bus.listen(ScheduledTaskFailed, lambda event: failures.append(event))

    def boom() -> None:
        raise RuntimeError("exploded")

    run_task(Event("boom", callback=boom), base_path=tmp_path)

    assert len(failures) == 1
    assert isinstance(failures[0].exception, RuntimeError)
    Bus.flush()


def test_the_outcome_says_what_happened() -> None:
    from almasix.console.scheduling.runner import Outcome

    event = Event("demo", command="demo:run")

    assert repr(Outcome(event, 0, "")) == "<Outcome 'demo:run' exit 0>"
    assert repr(Outcome(event, 0, "", skipped=True)) == "<Outcome 'demo:run' skipped>"


# --- queued jobs -------------------------------------------------------------


def test_a_scheduled_job_is_dispatched(tmp_path: Path, no_cache: Any) -> None:
    dispatched: list[Any] = []

    class Heartbeat:
        queue: Any = False
        connection: Any = None

    from almasix.queue import helpers

    original = helpers.dispatch

    async def record(job: Any) -> None:
        dispatched.append(job)

    helpers.dispatch = record
    try:
        schedule = Schedule()
        event = schedule.job(Heartbeat(), "heartbeats", "redis").every_minute()
        assert run_event(event, base_path=tmp_path) == 0
    finally:
        helpers.dispatch = original

    assert len(dispatched) == 1
    assert (dispatched[0].queue, dispatched[0].connection) == ("heartbeats", "redis")


# --- filling in the corners --------------------------------------------------


def test_the_sub_minute_loop_reports_and_ignores_the_minutely_tasks(
    tmp_path: Path, no_cache: Any
) -> None:
    started: list[str] = []
    finished: list[str] = []
    seen: list[int] = []
    schedule = Schedule()
    schedule.call(lambda: seen.append(1), description="often").every_thirty_seconds()
    schedule.call(lambda: None, description="minutely").every_minute()
    schedule.call(lambda: None, description="daily").daily()

    moments = iter(
        [
            MONDAY.replace(second=0),
            MONDAY.replace(second=30),
            MONDAY.replace(minute=1),
        ]
    )
    run_schedule(
        schedule,
        base_path=tmp_path,
        now=lambda: next(moments),
        sleep=lambda seconds: None,
        on_start=lambda event: started.append(event.summary()),
        on_finish=lambda outcome: finished.append(outcome.event.summary()),
    )

    # The opening tick took the two minutely tasks; the loop took the repeat.
    assert started == ["often", "minutely", "often"]
    assert finished == ["often", "minutely", "often"]
    assert len(seen) == 2


def test_a_shell_task_passes_on_what_it_wrote_to_stderr(tmp_path: Path, no_cache: Any) -> None:
    outcome = run_task(Event("noisy", shell="echo oops 1>&2"), base_path=tmp_path)

    assert "oops" in outcome.output


def test_a_job_without_a_queue_or_connection_keeps_its_own(
    tmp_path: Path, no_cache: Any
) -> None:
    dispatched: list[Any] = []

    class Heartbeat:
        queue: Any = "default"
        connection: Any = "sync"

    from almasix.queue import helpers

    original = helpers.dispatch

    async def record(job: Any) -> None:
        dispatched.append(job)

    helpers.dispatch = record
    try:
        schedule = Schedule()
        run_event(schedule.job(Heartbeat()).every_minute(), base_path=tmp_path)
    finally:
        helpers.dispatch = original

    assert (dispatched[0].queue, dispatched[0].connection) == ("default", "sync")


def test_output_is_not_emailed_when_a_failure_only_task_succeeds(
    tmp_path: Path, no_cache: Any
) -> None:
    sent: list[Any] = []

    import almasix.mail.mailer as mailer_module

    original = mailer_module.Mail
    mailer_module.Mail = type(
        "Mail",
        (),
        {"to": staticmethod(lambda *a: type("P", (), {"send": lambda self, m: sent.append(m)})())},
    )
    try:
        run_event(
            Event("quiet", shell="echo fine").email_output_on_failure("ops@example.test"),
            base_path=tmp_path,
        )
        run_event(Event("silent", shell="echo fine"), base_path=tmp_path)
    finally:
        mailer_module.Mail = original

    assert sent == []


def test_installing_the_camel_aliases_twice_changes_nothing() -> None:
    from almasix.console.scheduling.event import install_camel_aliases

    before = Event.everyFiveMinutes
    install_camel_aliases(Event)

    assert Event.everyFiveMinutes is before


# --- the two ways in, besides schedule.command() -----------------------------


def test_a_closure_command_can_schedule_itself_with_arguments() -> None:
    from almasix.console.facade import Artisan
    from almasix.console.scheduling import schedule as task_schedule

    task_schedule.clear()
    try:
        event = (
            Artisan.command("emails:send {user} {--force}", lambda user: None)
            .purpose("Send emails to the given user")
            .schedule(["taylor", "--force"])
            .daily()
        )

        assert event.summary() == "emails:send taylor --force"
        assert event.expression == "0 0 * * *"
        assert task_schedule.events == [event]
    finally:
        task_schedule.clear()
        Artisan.set_kernel(None)


def test_the_application_builder_can_define_the_schedule(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from almasix.console.scheduling import schedule as task_schedule
    from almasix.framework import Application

    task_schedule.clear()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APP_BASE_PATH", raising=False)
    try:
        Application.configure(tmp_path).with_schedule(
            lambda schedule: schedule.command("inspire").hourly()
        ).create()

        assert [event.summary() for event in task_schedule.events] == ["inspire"]
        assert task_schedule.events[0].expression == "0 * * * *"
    finally:
        task_schedule.clear()


def test_an_async_callback_is_awaited(tmp_path: Path, no_cache: Any) -> None:
    seen: list[str] = []

    async def clear_recent_users() -> None:
        seen.append("cleared")

    assert run_event(Event("async", callback=clear_recent_users), base_path=tmp_path) == 0
    assert seen == ["cleared"]


def test_an_async_callback_can_report_an_exit_code(tmp_path: Path, no_cache: Any) -> None:
    async def unhappy() -> int:
        return 4

    assert run_event(Event("async", callback=unhappy), base_path=tmp_path) == 4
