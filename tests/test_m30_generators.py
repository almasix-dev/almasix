"""M30 — the ``make:*`` generators Laravel has, and what a generated file gives you.

A generator earns its place by writing something the framework can already
run, so these tests do not stop at "a file appeared": they import what was
generated and hand it to the subsystem it names.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Annotated, Any

import pytest
from pydantic import AfterValidator, BaseModel, ValidationError

from almasix.console.kernel import ConsoleKernel
from almasix.console.stub import publish
from almasix.mail.markdown import render_content
from almasix.orm.casts import CastsAttributes, CastsInboundAttributes, resolve_cast
from almasix.orm.model import EVENTS
from almasix.prism.engine import Engine
from almasix.prism.helpers import get_engine, set_engine
from almasix.queue import Job, ShouldQueue

#: Command, argv, and the file it must write — the whole shipped surface.
GENERATORS: list[tuple[str, list[str], str]] = [
    ("make:job", ["SendDigest"], "app/jobs/send_digest.py"),
    ("make:mail", ["OrderShipped"], "app/mail/order_shipped.py"),
    ("make:notification", ["InvoicePaid"], "app/notifications/invoice_paid.py"),
    ("make:rule", ["Uppercase"], "app/rules/uppercase.py"),
    ("make:cast", ["AsMoney"], "app/casts/as_money.py"),
    ("make:exception", ["PaymentDeclined"], "app/exceptions/payment_declined.py"),
    ("make:class", ["Ledger"], "app/ledger.py"),
    ("make:enum", ["OrderStatus"], "app/enums/order_status.py"),
    ("make:interface", ["PaymentGateway"], "app/contracts/payment_gateway.py"),
    ("make:observer", ["PostObserver"], "app/observers/post_observer.py"),
]


@pytest.fixture()
def kernel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ConsoleKernel:
    monkeypatch.chdir(tmp_path)
    built = ConsoleKernel.for_cwd(tmp_path)
    built.discover_framework_commands()
    return built


def load(path: Path) -> ModuleType:
    """Import a generated file under its own name, off any package path."""
    spec = importlib.util.spec_from_file_location(f"generated_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- the whole surface ----------------------------------------------------


@pytest.mark.parametrize(("command", "argv", "relative"), GENERATORS)
def test_each_generator_writes_the_file_its_description_promises(
    kernel: ConsoleKernel, tmp_path: Path, command: str, argv: list[str], relative: str
) -> None:
    assert kernel.run_argv(command, argv) == 0

    path = tmp_path / relative
    assert path.is_file()
    compile(source(path), str(path), "exec")


@pytest.mark.parametrize(("command", "argv", "relative"), GENERATORS)
def test_each_generator_leaves_an_importable_package_behind(
    kernel: ConsoleKernel, tmp_path: Path, command: str, argv: list[str], relative: str
) -> None:
    assert kernel.run_argv(command, argv) == 0

    assert (tmp_path / Path(relative).parent / "__init__.py").is_file()


@pytest.mark.parametrize(("command", "argv", "relative"), GENERATORS)
def test_no_generator_overwrites_a_file_it_was_not_asked_to(
    kernel: ConsoleKernel,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    command: str,
    argv: list[str],
    relative: str,
) -> None:
    assert kernel.run_argv(command, argv) == 0
    (tmp_path / relative).write_text("# hand-edited\n", encoding="utf-8")

    assert kernel.run_argv(command, argv) == 1
    assert "already exists" in capsys.readouterr().err
    assert source(tmp_path / relative) == "# hand-edited\n"

    assert kernel.run_argv(command, [*argv, "--force"]) == 0
    assert source(tmp_path / relative) != "# hand-edited\n"


def test_the_new_generators_describe_themselves_like_the_old_ones(
    kernel: ConsoleKernel,
) -> None:
    directories = {relative: str(Path(relative).parent) for _, _, relative in GENERATORS}
    for command, _, relative in GENERATORS:
        description = kernel.commands[command].description
        assert description.startswith("Create a")
        assert directories[relative] in description
    assert kernel.commands["make:view"].description == (
        "Create a Prism view in resources/views"
    )


def test_no_generator_wants_an_application_to_exist_first(kernel: ConsoleKernel) -> None:
    """A generator has to work in a directory ``almasix new`` has not touched."""
    for command, _, _ in [*GENERATORS, ("make:view", [], "")]:
        assert kernel.commands[command].boots_application is False


def test_a_nested_name_becomes_a_package_path(kernel: ConsoleKernel, tmp_path: Path) -> None:
    assert kernel.run_argv("make:job", ["Admin/PruneAccounts"]) == 0

    path = tmp_path / "app" / "jobs" / "admin" / "prune_accounts.py"
    assert path.is_file()
    assert (tmp_path / "app" / "jobs" / "admin" / "__init__.py").is_file()
    assert "class PruneAccounts(" in source(path)


def test_a_published_stub_wins_over_the_frameworks(
    kernel: ConsoleKernel, tmp_path: Path
) -> None:
    publish(tmp_path)
    (tmp_path / "stubs" / "job.queued.stub").write_text(
        '"""{{ class }} — house style."""\n', encoding="utf-8"
    )

    assert kernel.run_argv("make:job", ["SendDigest"]) == 0

    path = tmp_path / "app" / "jobs" / "send_digest.py"
    assert source(path) == '"""SendDigest — house style."""\n'


# --- jobs -----------------------------------------------------------------


def test_a_generated_job_is_a_queued_job(kernel: ConsoleKernel, tmp_path: Path) -> None:
    assert kernel.run_argv("make:job", ["SendDigest"]) == 0

    job = load(tmp_path / "app" / "jobs" / "send_digest.py").SendDigest()
    assert isinstance(job, Job)
    assert isinstance(job, ShouldQueue)
    assert job.should_queue() is True


def test_the_sync_option_makes_a_job_that_stays_in_process(
    kernel: ConsoleKernel, tmp_path: Path
) -> None:
    assert kernel.run_argv("make:job", ["WarmCache", "--sync"]) == 0

    job = load(tmp_path / "app" / "jobs" / "warm_cache.py").WarmCache()
    assert isinstance(job, Job)
    assert not isinstance(job, ShouldQueue)
    assert job.should_queue() is False


async def test_a_generated_job_runs(kernel: ConsoleKernel, tmp_path: Path) -> None:
    from almasix.queue.job import call_handle

    assert kernel.run_argv("make:job", ["SendDigest"]) == 0
    job = load(tmp_path / "app" / "jobs" / "send_digest.py").SendDigest()

    assert await call_handle(job) is None


# --- mail -----------------------------------------------------------------


def test_a_generated_mailable_carries_a_subject_read_off_its_name(
    kernel: ConsoleKernel, tmp_path: Path
) -> None:
    assert kernel.run_argv("make:mail", ["OrderShipped"]) == 0

    mailable = load(tmp_path / "app" / "mail" / "order_shipped.py").OrderShipped()
    assert mailable.envelope().subject == "Order Shipped"
    assert mailable.attachments() == []


def test_the_markdown_option_writes_the_view_the_mailable_names(
    kernel: ConsoleKernel, tmp_path: Path
) -> None:
    assert kernel.run_argv("make:mail", ["InvoicePaid", "--markdown", "mail.invoice-paid"]) == 0

    mailable = load(tmp_path / "app" / "mail" / "invoice_paid.py").InvoicePaid()
    assert mailable.content().markdown == "mail.invoice_paid"
    assert (tmp_path / "resources" / "views" / "mail" / "invoice_paid.prism.html").is_file()


def test_the_generated_markdown_mail_renders_through_prism(
    kernel: ConsoleKernel, tmp_path: Path, engine_restored: None
) -> None:
    assert kernel.run_argv("make:mail", ["InvoicePaid", "--markdown", "mail.invoice-paid"]) == 0
    set_engine(Engine(paths=[tmp_path / "resources" / "views"]))

    mailable = load(tmp_path / "app" / "mail" / "invoice_paid.py").InvoicePaid()
    body, text = render_content(mailable.content())

    assert body is not None and "<h1>Invoice Paid</h1>" in body
    assert text is not None and "Invoice Paid" in text


# --- notifications --------------------------------------------------------


def test_a_generated_notification_goes_out_on_mail(
    kernel: ConsoleKernel, tmp_path: Path
) -> None:
    assert kernel.run_argv("make:notification", ["InvoicePaid"]) == 0

    notification = load(tmp_path / "app" / "notifications" / "invoice_paid.py").InvoicePaid()
    assert notification.via(object()) == ["mail"]
    assert notification.to_mail(object()) == {"subject": "Invoice Paid", "text": ""}
    assert notification.to_database(object()) == {}


def test_a_markdown_view_that_exists_is_reported_not_clobbered(
    kernel: ConsoleKernel, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    view = tmp_path / "resources" / "views" / "mail" / "invoice_paid.prism.html"
    view.parent.mkdir(parents=True)
    view.write_text("# mine\n", encoding="utf-8")

    assert kernel.run_argv("make:mail", ["InvoicePaid", "--markdown", "mail.invoice-paid"]) == 1

    assert "already exists" in capsys.readouterr().err
    assert source(view) == "# mine\n"


def test_a_markdown_notification_hands_the_mail_channel_a_mailable(
    kernel: ConsoleKernel, tmp_path: Path
) -> None:
    from almasix.mail import Mailable

    argv = ["ShipmentDelayed", "--markdown", "mail.shipment-delayed"]
    assert kernel.run_argv("make:notification", argv) == 0

    module = load(tmp_path / "app" / "notifications" / "shipment_delayed.py")
    message = module.ShipmentDelayed().to_mail(object())
    assert isinstance(message, Mailable)
    assert message.content().markdown == "mail.shipment_delayed"
    assert (tmp_path / "resources" / "views" / "mail" / "shipment_delayed.prism.html").is_file()


# --- validation rules -----------------------------------------------------


def test_a_generated_rule_validates_a_field(kernel: ConsoleKernel, tmp_path: Path) -> None:
    assert kernel.run_argv("make:rule", ["Uppercase"]) == 0
    rule_class = load(tmp_path / "app" / "rules" / "uppercase.py").Uppercase

    class Shouty(rule_class):  # type: ignore[misc, valid-type]
        def __call__(self, value: Any) -> Any:
            value = super().__call__(value)
            if value and value != value.upper():
                raise ValueError(self.message)
            return value

    class Payload(BaseModel):
        title: Annotated[str, AfterValidator(Shouty())]

    assert Payload(title="ADA").title == "ADA"
    with pytest.raises(ValidationError) as excinfo:
        Payload(title="ada")
    assert "The given value is invalid." in str(excinfo.value)


def test_a_plain_rule_leaves_empty_input_to_required(
    kernel: ConsoleKernel, tmp_path: Path
) -> None:
    assert kernel.run_argv("make:rule", ["Uppercase"]) == 0

    body = source(tmp_path / "app" / "rules" / "uppercase.py")
    assert "``required``'s business" in body
    assert load(tmp_path / "app" / "rules" / "uppercase.py").Uppercase()("") == ""


def test_an_implicit_rule_inspects_the_empty_values_too(
    kernel: ConsoleKernel, tmp_path: Path
) -> None:
    assert kernel.run_argv("make:rule", ["NotBlank", "--implicit"]) == 0

    body = source(tmp_path / "app" / "rules" / "not_blank.py")
    assert "``required``" not in body.split("Unlike")[0]
    assert "validate_default=True" in body
    assert load(tmp_path / "app" / "rules" / "not_blank.py").NotBlank()(None) is None


# --- casts ----------------------------------------------------------------


def test_a_generated_cast_is_the_cast_contract(kernel: ConsoleKernel, tmp_path: Path) -> None:
    assert kernel.run_argv("make:cast", ["AsMoney"]) == 0
    cast_class = load(tmp_path / "app" / "casts" / "as_money.py").AsMoney

    resolved = resolve_cast(cast_class)
    assert isinstance(resolved, CastsAttributes)
    assert resolved.get(None, "price", 10, {}) == 10
    assert resolved.set(None, "price", 10, {}) == 10


def test_an_inbound_cast_passes_reads_through(kernel: ConsoleKernel, tmp_path: Path) -> None:
    assert kernel.run_argv("make:cast", ["AsSlug", "--inbound"]) == 0
    cast_class = load(tmp_path / "app" / "casts" / "as_slug.py").AsSlug

    resolved = resolve_cast(cast_class)
    assert isinstance(resolved, CastsInboundAttributes)
    assert resolved.get(None, "slug", "a-b", {}) == "a-b"


# --- exceptions -----------------------------------------------------------


def test_a_generated_exception_is_raisable(kernel: ConsoleKernel, tmp_path: Path) -> None:
    assert kernel.run_argv("make:exception", ["PaymentDeclined"]) == 0
    exception_class = load(tmp_path / "app" / "exceptions" / "payment_declined.py").PaymentDeclined

    with pytest.raises(exception_class):
        raise exception_class("card refused")


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ([], ()),
        (["--report"], ("report",)),
        (["--render"], ("render",)),
        (["--render", "--report"], ("render", "report")),
    ],
)
def test_an_exception_only_grows_the_hooks_it_was_asked_for(
    kernel: ConsoleKernel, tmp_path: Path, options: list[str], expected: tuple[str, ...]
) -> None:
    assert kernel.run_argv("make:exception", ["OutOfStock", *options, "--force"]) == 0
    exception_class = load(tmp_path / "app" / "exceptions" / "out_of_stock.py").OutOfStock

    hooks = tuple(name for name in ("render", "report") if hasattr(exception_class, name))
    assert hooks == expected


def test_the_hooks_a_generated_exception_declares_are_the_ones_m8_looks_for(
    kernel: ConsoleKernel, tmp_path: Path
) -> None:
    """``--render`` and ``--report`` are only worth offering because the Handler asks."""
    from almasix.exceptions import Handler

    assert 'getattr(exc, "report", None)' in inspect.getsource(Handler.report)
    assert 'getattr(exc, "render", None)' in inspect.getsource(Handler.render)

    assert kernel.run_argv("make:exception", ["OutOfStock", "--render", "--report"]) == 0
    exception = load(tmp_path / "app" / "exceptions" / "out_of_stock.py").OutOfStock("gone")

    # Both hooks decline, which is what the Handler reads as "carry on".
    assert exception.report() is None
    assert exception.render(None) is None


# --- enums, interfaces, plain classes -------------------------------------


def test_a_generated_enum_has_a_case(kernel: ConsoleKernel, tmp_path: Path) -> None:
    assert kernel.run_argv("make:enum", ["OrderStatus"]) == 0

    enum_class = load(tmp_path / "app" / "enums" / "order_status.py").OrderStatus
    assert [member.name for member in enum_class] == ["EXAMPLE"]


@pytest.mark.parametrize(
    ("option", "expected"),
    [("--string", "example"), ("--int", 1)],
)
def test_a_backed_enum_casts_a_stored_value(
    kernel: ConsoleKernel, tmp_path: Path, option: str, expected: object
) -> None:
    from almasix.orm.casts import cast_value

    assert kernel.run_argv("make:enum", ["Level", option, "--force"]) == 0

    enum_class = load(tmp_path / "app" / "enums" / "level.py").Level
    assert enum_class.EXAMPLE.value == expected
    assert cast_value(expected, enum_class) is enum_class.EXAMPLE


def test_an_enum_is_backed_one_way_or_the_other(
    kernel: ConsoleKernel, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("make:enum", ["Level", "--string", "--int"]) == 1

    assert "not both" in capsys.readouterr().err
    assert not (tmp_path / "app" / "enums" / "level.py").exists()


def test_a_generated_interface_is_a_protocol(kernel: ConsoleKernel, tmp_path: Path) -> None:
    assert kernel.run_argv("make:interface", ["PaymentGateway"]) == 0

    protocol = load(tmp_path / "app" / "contracts" / "payment_gateway.py").PaymentGateway
    assert getattr(protocol, "_is_protocol", False)
    assert isinstance(object(), protocol)  # runtime_checkable, and empty so far


def test_a_class_lands_under_the_path_its_name_gives(
    kernel: ConsoleKernel, tmp_path: Path
) -> None:
    assert kernel.run_argv("make:class", ["Services/Ledger"]) == 0

    path = tmp_path / "app" / "services" / "ledger.py"
    assert path.is_file()
    assert (tmp_path / "app" / "services" / "__init__.py").is_file()
    assert isinstance(load(path).Ledger(), object)


def test_an_invokable_class_is_callable(kernel: ConsoleKernel, tmp_path: Path) -> None:
    assert kernel.run_argv("make:class", ["ChargeCard", "--invokable"]) == 0

    action = load(tmp_path / "app" / "charge_card.py").ChargeCard()
    assert action() is None


# --- observers ------------------------------------------------------------


def test_a_generated_observer_only_names_real_model_events(
    kernel: ConsoleKernel, tmp_path: Path
) -> None:
    assert kernel.run_argv("make:observer", ["PostObserver"]) == 0
    observer = load(tmp_path / "app" / "observers" / "post_observer.py").PostObserver

    hooks = [name for name in vars(observer) if not name.startswith("_")]
    assert hooks == ["created", "updated", "deleted", "restored"]
    assert set(hooks) <= set(EVENTS)


def test_a_generated_observer_registers_on_a_model(
    kernel: ConsoleKernel, tmp_path: Path
) -> None:
    from almasix.orm import Model

    assert kernel.run_argv("make:observer", ["PostObserver"]) == 0
    observer = load(tmp_path / "app" / "observers" / "post_observer.py").PostObserver

    class Post(Model):
        table = "posts"

    Post.observe(observer)

    listening = {event for event, listeners in Post._events.items() if listeners}
    assert listening == {"created", "updated", "deleted", "restored"}


def test_the_model_option_types_the_observers_arguments(
    kernel: ConsoleKernel, tmp_path: Path
) -> None:
    assert kernel.run_argv("make:observer", ["UserObserver", "--model", "User"]) == 0

    body = source(tmp_path / "app" / "observers" / "user_observer.py")
    assert "from app.models.user import User" in body
    assert "async def created(self, user: User) -> None:" in body
    # The import is behind TYPE_CHECKING, so the observer loads before the model does.
    assert load(tmp_path / "app" / "observers" / "user_observer.py").UserObserver is not None


# --- views ----------------------------------------------------------------


def test_make_view_writes_a_prism_template(kernel: ConsoleKernel, tmp_path: Path) -> None:
    assert kernel.run_argv("make:view", ["posts.index"]) == 0

    path = tmp_path / "resources" / "views" / "posts" / "index.prism.html"
    assert path.is_file()
    assert source(path).startswith("{{-- posts.index --}}")


def test_a_view_name_reads_the_same_with_dots_or_slashes(
    kernel: ConsoleKernel, tmp_path: Path
) -> None:
    assert kernel.run_argv("make:view", ["Admin/Posts/Index"]) == 0

    assert (tmp_path / "resources" / "views" / "admin" / "posts" / "index.prism.html").is_file()


def test_a_view_is_not_overwritten_without_force(
    kernel: ConsoleKernel, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("make:view", ["welcome"]) == 0
    path = tmp_path / "resources" / "views" / "welcome.prism.html"
    path.write_text("<p>mine</p>\n", encoding="utf-8")

    assert kernel.run_argv("make:view", ["welcome"]) == 1
    assert "already exists" in capsys.readouterr().err
    assert source(path) == "<p>mine</p>\n"
    assert kernel.run_argv("make:view", ["welcome", "--force"]) == 0
    assert source(path) != "<p>mine</p>\n"


def test_a_view_name_has_to_be_a_name(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("make:view", ["posts.@index"]) == 1

    assert "Invalid name segment" in capsys.readouterr().err


def test_a_view_needs_a_name(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("make:view", ["..."]) == 1

    assert "A view name is required." in capsys.readouterr().err


def test_a_view_name_cannot_climb_out_of_the_views_directory(
    kernel: ConsoleKernel, tmp_path: Path
) -> None:
    """``..`` is punctuation between segments, never a segment of its own."""
    assert kernel.run_argv("make:view", ["posts/../secrets"]) == 0

    assert (tmp_path / "resources" / "views" / "posts" / "secrets.prism.html").is_file()


def test_the_generated_view_compiles_as_a_template(
    kernel: ConsoleKernel, tmp_path: Path, engine_restored: None
) -> None:
    assert kernel.run_argv("make:view", ["posts.index"]) == 0
    set_engine(Engine(paths=[tmp_path / "resources" / "views"]))

    assert get_engine().render("posts.index", {}).strip() == "<div>\n  \n</div>"


# --- the whole set, in a real application ---------------------------------


def test_every_generated_file_imports_inside_a_scaffolded_app(app_root: Path) -> None:
    """The proof that matters: ``smith make:*`` output an application can import."""
    built = ConsoleKernel.for_cwd(app_root)
    built.discover_framework_commands()
    scaffolded = set((app_root / "app").rglob("*.py"))

    for command, argv, _ in GENERATORS:
        assert built.run_argv(command, argv) == 0
    for command, argv in (
        ("make:job", ["WarmCache", "--sync"]),
        ("make:mail", ["Welcome", "--markdown", "mail.welcome"]),
        ("make:notification", ["Shipped", "--markdown", "mail.shipped"]),
        ("make:rule", ["NotBlank", "--implicit"]),
        ("make:cast", ["AsSlug", "--inbound"]),
        ("make:exception", ["OutOfStock", "--render", "--report"]),
        ("make:enum", ["Suit", "--string"]),
        ("make:class", ["ChargeCard", "--invokable"]),
        ("make:observer", ["UserObserver", "--model", "User"]),
        ("make:view", ["posts.index"]),
    ):
        assert built.run_argv(command, argv) == 0

    generated = sorted(
        path.relative_to(app_root).with_suffix("").as_posix().replace("/", ".")
        for path in set((app_root / "app").rglob("*.py")) - scaffolded
        if path.name != "__init__.py"
    )
    assert len(generated) == len(GENERATORS) + 9  # every generator, plus the option variants
    for module in generated:
        importlib.import_module(module)


@pytest.fixture()
def engine_restored() -> Iterator[None]:
    """Put back whatever engine the process had, so a render test stays local."""
    try:
        previous: Engine | None = get_engine()
    except RuntimeError:
        previous = None
    yield
    set_engine(previous)
