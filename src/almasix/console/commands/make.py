"""The ``make:*`` generators.

Generators write files into a project; none of them needs a booted
application, so they keep working in a directory that ``almasix new`` has not
touched yet.
"""

from __future__ import annotations

from pathlib import Path

from almasix.console.command import Command
from almasix.orm.inflector import snake, studly, table_name
from almasix.orm.migration import MigrationError, make_migration
from almasix.smith.make import MakeError, make, make_component, make_view, view_name
from almasix.support.str import Str


class Generator(Command):
    """Shared body for the blueprint-driven generators."""

    boots_application = False

    #: Key into ``almasix.smith.make.BLUEPRINTS``.
    kind: str = ""

    def handle(self) -> int:
        try:
            path = self.write()
        except MakeError as exc:
            self.error(str(exc))
            return self.FAILURE
        self.success(f"{self.kind.capitalize()} created: {path.relative_to(self.root())}")
        return self.SUCCESS

    def write(self) -> Path:
        return make(
            self.kind,
            self.argument("name"),
            base_path=self.root(),
            force=bool(self.option("force")),
            stub=self.stub(),
            replacements=self.replacements(),
        )

    def stub(self) -> str | None:
        """Which template this run writes from; ``None`` takes the blueprint's."""
        return None

    def replacements(self) -> dict[str, str]:
        """Placeholder values beyond ``class`` and ``command``."""
        return {}

    def class_name(self) -> str:
        """The trailing segment of the name argument, without its namespace."""
        return str(self.argument("name") or "").replace("\\", "/").split("/")[-1]

    def root(self) -> Path:
        """Where the file lands: the working directory, as ``smith`` was run."""
        return Path.cwd()

    def write_factory(self) -> int:
        """The factory `--factory` asks for, bound to the class just written."""
        model = self.class_name()
        try:
            path = make(
                "factory",
                f"{model}Factory",
                base_path=self.root(),
                force=bool(self.option("force")),
                stub="factory.stub",
                replacements={
                    "model": model,
                    "modelVariable": snake(model),
                    "namespacedModel": f"app.models.{snake(model)}",
                },
            )
        except MakeError as exc:
            self.error(str(exc))
            return self.FAILURE
        self.success(f"Factory created: {path.relative_to(self.root())}")
        return self.SUCCESS


class MakeControllerCommand(Generator):
    signature = (
        "make:controller {name : Class name, e.g. PostController or Admin/PostController} "
        "{--force : Overwrite an existing file}"
    )
    description = "Create a controller in app/http/controllers"
    kind = "controller"


class MakeMiddlewareCommand(Generator):
    signature = (
        "make:middleware {name : Class name, e.g. EnsureTokenIsValid} "
        "{--force : Overwrite an existing file}"
    )
    description = "Create a middleware in app/http/middleware"
    kind = "middleware"


class MakeProviderCommand(Generator):
    signature = (
        "make:provider {name : Class name, e.g. RouteServiceProvider} "
        "{--force : Overwrite an existing file}"
    )
    description = "Create a service provider in app/providers"
    kind = "provider"


class MakeRequestCommand(Generator):
    signature = (
        "make:request {name : Class name, e.g. StorePostRequest} "
        "{--force : Overwrite an existing file}"
    )
    description = "Create a FormRequest in app/http/requests"
    kind = "request"


class MakeSeederCommand(Generator):
    signature = (
        "make:seeder {name : Class name, e.g. UserSeeder} {--force : Overwrite an existing file}"
    )
    description = "Create a seeder in database/seeders"
    kind = "seeder"


class MakeFactoryCommand(Generator):
    signature = (
        "make:factory {name : Class name, e.g. PostFactory} "
        "{--model= : The model the factory builds, e.g. Post} "
        "{--force : Overwrite an existing file}"
    )
    description = "Create a model factory in database/factories"
    kind = "factory"

    def stub(self) -> str:
        return "factory.stub" if self.option("model") else "factory.plain.stub"

    def replacements(self) -> dict[str, str]:
        model = studly(str(self.option("model") or ""))
        if not model:
            return {}
        return {
            "model": model,
            "modelVariable": snake(model),
            "namespacedModel": f"app.models.{snake(model)}",
        }


class MakeCommandCommand(Generator):
    signature = (
        "make:command {name : Class name, e.g. SendEmails} {--force : Overwrite an existing file}"
    )
    description = "Create a console command in app/console/commands"
    kind = "command"


class MakeModelCommand(Generator):
    signature = (
        "make:model {name : Class name, e.g. Post or Admin/Post} "
        "{--m|migration : Also create a migration} "
        "{--f|factory : Also create a factory} "
        "{--force : Overwrite an existing file}"
    )
    description = "Create a model in app/models"
    kind = "model"

    def handle(self) -> int:
        code = super().handle()
        if code == self.SUCCESS and self.option("factory"):
            code = self.write_factory()
        if code != self.SUCCESS or not self.option("migration"):
            return code
        root = self.root()
        class_name = self.class_name()
        path = make_migration(
            f"create_{table_name(class_name)}_table",
            root / "database" / "migrations",
            table=table_name(class_name),
            create=True,
            base_path=root,
        )
        self.success(f"Migration created: {path.relative_to(root)}")
        return self.SUCCESS


class MakeDocumentCommand(Generator):
    """A document model — a collection instead of a table, no migration."""

    signature = (
        "make:document {name : Class name, e.g. Article or Blog/Article} "
        "{--f|factory : Also create a factory} "
        "{--e|embed : An embedded document rather than a collection-backed one} "
        "{--force : Overwrite an existing file}"
    )
    description = "Create a document model in app/models"
    kind = "document"

    def stub(self) -> str:
        return "embed.stub" if self.option("embed") else "document.stub"

    def handle(self) -> int:
        code = super().handle()
        if code != self.SUCCESS or not self.option("factory"):
            return code
        return self.write_factory()


class MakeResourceCommand(Generator):
    signature = (
        "make:resource {name : Class name, e.g. UserResource or Api/UserResource} "
        "{--collection : A resource collection rather than a single resource} "
        "{--force : Overwrite an existing file}"
    )
    description = "Create an API resource in app/http/resources"
    kind = "resource"

    def stub(self) -> str:
        collection = bool(self.option("collection")) or self.class_name().endswith("Collection")
        return "resource.collection.stub" if collection else "resource.stub"


class MakeJobCommand(Generator):
    signature = (
        "make:job {name : Class name, e.g. SendDigest or Mail/SendDigest} "
        "{--sync : A job that runs in-process instead of on the queue} "
        "{--force : Overwrite an existing file}"
    )
    description = "Create a queue job in app/jobs"
    kind = "job"

    def stub(self) -> str:
        return "job.stub" if self.option("sync") else "job.queued.stub"


class MarkdownGenerator(Generator):
    """Shared body for the generators whose ``--markdown`` writes a view too."""

    def handle(self) -> int:
        code = super().handle()
        markdown = str(self.option("markdown") or "")
        if code != self.SUCCESS or not markdown:
            return code
        return self.write_markdown_view(markdown)

    def replacements(self) -> dict[str, str]:
        markdown = str(self.option("markdown") or "")
        return {
            "subject": Str.headline(self.class_name()),
            "view": view_name(markdown) if markdown else "",
        }

    def write_markdown_view(self, markdown: str) -> int:
        """Write the Markdown view the generated class renders."""
        try:
            path = make_view(
                markdown,
                base_path=self.root(),
                force=bool(self.option("force")),
                stub="markdown.stub",
                replacements={"subject": Str.headline(self.class_name())},
            )
        except MakeError as exc:
            self.error(str(exc))
            return self.FAILURE
        self.success(f"View created: {path.relative_to(self.root())}")
        return self.SUCCESS


class MakeMailCommand(MarkdownGenerator):
    signature = (
        "make:mail {name : Class name, e.g. OrderShipped} "
        "{--markdown= : Also create a Markdown view, e.g. mail.order-shipped} "
        "{--force : Overwrite an existing file}"
    )
    description = "Create a mailable in app/mail"
    kind = "mail"

    def stub(self) -> str:
        return "markdown-mail.stub" if self.option("markdown") else "mail.stub"


class MakeNotificationCommand(MarkdownGenerator):
    signature = (
        "make:notification {name : Class name, e.g. InvoicePaid} "
        "{--markdown= : Also create a Markdown view, e.g. mail.invoice-paid} "
        "{--force : Overwrite an existing file}"
    )
    description = "Create a notification in app/notifications"
    kind = "notification"

    def stub(self) -> str:
        return "markdown-notification.stub" if self.option("markdown") else "notification.stub"


class MakeRuleCommand(Generator):
    signature = (
        "make:rule {name : Class name, e.g. Uppercase} "
        "{--implicit : Run the rule on empty values too} "
        "{--force : Overwrite an existing file}"
    )
    description = "Create a validation rule in app/rules"
    kind = "rule"

    def stub(self) -> str:
        return "rule.implicit.stub" if self.option("implicit") else "rule.stub"


class MakeCastCommand(Generator):
    signature = (
        "make:cast {name : Class name, e.g. AsMoney} "
        "{--inbound : A write-only cast, untouched on read} "
        "{--force : Overwrite an existing file}"
    )
    description = "Create an attribute cast in app/casts"
    kind = "cast"

    def stub(self) -> str:
        return "cast.inbound.stub" if self.option("inbound") else "cast.stub"


class MakeExceptionCommand(Generator):
    signature = (
        "make:exception {name : Class name, e.g. PaymentDeclined} "
        "{--render : Add a render() that returns its own response} "
        "{--report : Add a report() that handles its own logging} "
        "{--force : Overwrite an existing file}"
    )
    description = "Create an exception in app/exceptions"
    kind = "exception"

    def stub(self) -> str:
        renders, reports = bool(self.option("render")), bool(self.option("report"))
        if renders and reports:
            return "exception-render-report.stub"
        if renders:
            return "exception-render.stub"
        if reports:
            return "exception-report.stub"
        return "exception.stub"


class MakeEnumCommand(Generator):
    signature = (
        "make:enum {name : Class name, e.g. OrderStatus} "
        "{--string : Back the cases with strings} "
        "{--int : Back the cases with integers} "
        "{--force : Overwrite an existing file}"
    )
    description = "Create an enum in app/enums"
    kind = "enum"

    def handle(self) -> int:
        if self.option("string") and self.option("int"):
            self.error("An enum is backed by --string or --int, not both.")
            return self.FAILURE
        return super().handle()

    def stub(self) -> str | None:
        return "enum.backed.stub" if self.backed() else None

    def replacements(self) -> dict[str, str]:
        if not self.backed():
            return {}
        if self.option("int"):
            return {"base": "int", "case": "1"}
        return {"base": "str", "case": '"example"'}

    def backed(self) -> bool:
        return bool(self.option("string") or self.option("int"))


class MakeInterfaceCommand(Generator):
    signature = (
        "make:interface {name : Class name, e.g. PaymentGateway} "
        "{--force : Overwrite an existing file}"
    )
    description = "Create a Protocol in app/contracts"
    kind = "interface"


class MakeObserverCommand(Generator):
    signature = (
        "make:observer {name : Class name, e.g. PostObserver} "
        "{--model= : The model the observer watches, e.g. Post} "
        "{--force : Overwrite an existing file}"
    )
    description = "Create a model observer in app/observers"
    kind = "observer"

    def stub(self) -> str:
        return "observer.stub" if self.option("model") else "observer.plain.stub"

    def replacements(self) -> dict[str, str]:
        model = studly(str(self.option("model") or ""))
        if not model:
            return {}
        return {
            "model": model,
            "modelVariable": snake(model),
            "namespacedModel": f"app.models.{snake(model)}",
        }


class MakeClassCommand(Generator):
    signature = (
        "make:class {name : Class name, e.g. Ledger or Services/Ledger} "
        "{--invokable : Give the class a __call__} "
        "{--force : Overwrite an existing file}"
    )
    description = "Create a class in app, under the path its name gives"
    kind = "class"

    def stub(self) -> str:
        return "class.invokable.stub" if self.option("invokable") else "class.stub"


class MakeViewCommand(Command):
    signature = (
        "make:view {name : View name, e.g. posts.index or posts/index} "
        "{--force : Overwrite an existing file}"
    )
    description = "Create a Prism view in resources/views"
    boots_application = False

    def handle(self) -> int:
        root = Path.cwd()
        try:
            path = make_view(
                str(self.argument("name") or ""),
                base_path=root,
                force=bool(self.option("force")),
            )
        except MakeError as exc:
            self.error(str(exc))
            return self.FAILURE
        self.success(f"View created: {path.relative_to(root)}")
        return self.SUCCESS


class MakeMigrationCommand(Command):
    signature = (
        "make:migration {name : Slug, e.g. create_posts_table or add_slug_to_posts_table} "
        "{--table= : Table to alter (overrides name inference)} "
        "{--create= : Table to create (overrides name inference)}"
    )
    description = "Create a migration in database/migrations"
    boots_application = False

    def handle(self) -> int:
        """Names like ``create_users_table`` pick their own stub (Laravel TableGuesser)."""
        root = Path.cwd()
        create = self.option("create")
        try:
            path = make_migration(
                self.argument("name"),
                root / "database" / "migrations",
                table=create or self.option("table"),
                create=create is not None,
                base_path=root,
            )
        except MigrationError as exc:
            self.error(str(exc))
            return self.FAILURE
        self.success(f"Migration created: {path.relative_to(root)}")
        return self.SUCCESS


class MakeComponentCommand(Command):
    signature = (
        "make:component {name : Component name, e.g. alert or forms/input} "
        "{--force : Overwrite an existing file} "
        "{--class : Also create app/view/components/… class}"
    )
    description = "Create an anonymous Prism component in resources/views/components"
    boots_application = False

    def handle(self) -> int:
        root = Path.cwd()
        class_based = bool(self.option("class"))
        try:
            path = make_component(
                self.argument("name"),
                base_path=root,
                force=bool(self.option("force")),
                class_based=class_based,
            )
        except MakeError as exc:
            self.error(str(exc))
            return self.FAILURE
        self.success(f"Component created: {path.relative_to(root)}")
        if class_based:
            self.success("Class created under app/view/components/")
        return self.SUCCESS
