"""M19 Authorization — gates, policies, Prism, make:policy, middleware."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest
from typer.testing import CliRunner

from almasix.auth import (
    AccessGate,
    AuthenticatableMixin,
    AuthorizationException,
    AuthorizationResponse,
    Authorize,
    Gate,
    HandlesAuthorization,
    Policy,
    authorize,
    gate,
)
from almasix.auth.access.helpers import gate_allows, gate_any
from almasix.auth.provider import AuthServiceProvider
from almasix.framework.application import Application
from almasix.http import Controller, ForbiddenHttpException
from almasix.http.request import Request
from almasix.prism.compiler import compile_template
from almasix.routing.router import RouteDefinition
from almasix.smith.cli import app as smith_app
from almasix.validation.form_request import FormRequest


class User(AuthenticatableMixin):
    def __init__(self, user_id: int, *, admin: bool = False) -> None:
        self.id = user_id
        self.admin = admin

    def get_auth_identifier(self) -> int:
        return self.id


class Post:
    def __init__(self, user_id: int, published: bool = True) -> None:
        self.user_id = user_id
        self.published = published


class PostPolicy(Policy):
    def before(self, user: Any, ability: str) -> bool | None:
        if user is not None and getattr(user, "admin", False):
            return True
        return None

    def view_any(self, user: Any) -> bool:
        return user is not None

    def view(self, user: Any, post: Post) -> bool:
        return True

    def create(self, user: Any) -> bool:
        return user is not None

    def update(self, user: Any, post: Post) -> bool:
        return user.id == post.user_id

    def delete(self, user: Any, post: Post) -> Any:
        if user.id == post.user_id:
            return True
        return self.deny("You do not own this post.")

    def force_delete(self, user: Any, post: Post) -> Any:
        return self.deny_as_not_found()


class GuestPolicy(Policy):
    def view(self, user: Any | None, post: Post) -> bool:
        return True


class HandleAbility:
    def handle(self, user: Any, *args: Any) -> bool:
        return user is not None


@pytest.fixture(autouse=True)
def _reset_gate() -> None:
    Gate.set_gate(None)
    yield
    Gate.set_gate(None)


def test_define_allows_denies_inspect_authorize() -> None:
    Gate.define("ping", lambda user: True)
    user = User(1)
    assert Gate.for_user(user).allows("ping")
    assert Gate.for_user(user).denies("missing")
    assert Gate.has("ping")
    assert "ping" in Gate.abilities()
    Gate.for_user(user).authorize("ping")
    with pytest.raises(AuthorizationException) as exc:
        Gate.for_user(user).authorize("missing")
    assert exc.value.status_code == 403
    response = Gate.for_user(user).inspect("ping")
    assert response.allowed()
    assert bool(response)


def test_guest_required_user_denied_optional_allowed() -> None:
    Gate.define("needs-user", lambda user: True)
    Gate.define("guest-ok", lambda user=None: True)

    assert Gate.for_user(None).denies("needs-user")
    assert Gate.for_user(None).allows("guest-ok")
    assert Gate.for_user(User(1)).allows("needs-user")


def test_check_any_none() -> None:
    Gate.define("a", lambda user: True)
    Gate.define("b", lambda user: False)
    user = User(1)
    g = Gate.for_user(user)
    assert g.check("a")
    assert not g.check(["a", "b"])
    assert g.any(["a", "b"])
    assert g.none(["b", "missing"])
    assert not g.none(["a", "b"])


def test_arguments_and_helpers() -> None:
    Gate.define("sum", lambda user, a, b: a + b == 3)
    user = User(1)
    assert Gate.for_user(user).allows("sum", [1, 2])
    assert not Gate.for_user(user).allows("sum", [1, 1])
    Gate.set_gate(Gate.get_gate())
    assert gate() is Gate.get_gate()
    Gate.define("ok", lambda user: True)
    assert gate_allows("ok") is False  # no user
    assert gate_allows("ok", None) is False
    Gate.define("guest", lambda user=None: True)
    assert gate_allows("guest")
    assert gate_any(["guest", "ok"])
    assert gate_any(["guest"], User(1))
    authorize("guest")


def test_before_after_and_default_deny() -> None:
    hits: list[str] = []
    Gate.define("edit", lambda user: False)
    Gate.before(lambda user, ability: True if getattr(user, "admin", False) else None)
    Gate.after(lambda user, ability, result, arguments: hits.append(ability) or result)
    admin = User(1, admin=True)
    regular = User(2)
    assert Gate.for_user(admin).allows("edit")
    assert Gate.for_user(regular).denies("edit")
    assert "edit" in hits

    Gate.flush()
    Gate.default_deny_response(AuthorizationResponse.deny("nope", code="x"))
    denied = Gate.for_user(User(1)).inspect("missing")
    assert denied.message() == "nope"
    assert denied.code() == "x"

    Gate.flush()
    Gate.default_deny_response(lambda: AuthorizationResponse.deny("callable"))
    assert Gate.for_user(User(1)).inspect("x").message() == "callable"


def test_after_short_arity() -> None:
    Gate.define("z", lambda user: False)
    Gate.after(lambda user, ability: True)
    assert Gate.for_user(User(1)).allows("z")


def test_policy_instance_and_class_abilities() -> None:
    Gate.policy(Post, PostPolicy)
    author = User(1)
    stranger = User(9)
    admin = User(2, admin=True)
    post = Post(1)
    assert Gate.for_user(author).allows("update", post)
    assert Gate.for_user(stranger).denies("update", post)
    assert Gate.for_user(admin).allows("update", post)
    assert Gate.for_user(author).allows("create", Post)
    assert Gate.for_user(None).denies("create", Post)
    assert Gate.for_user(author).allows("view_any", Post)
    response = Gate.for_user(stranger).inspect("delete", post)
    assert response.denied()
    assert "own" in (response.message() or "")
    with pytest.raises(AuthorizationException) as exc:
        Gate.for_user(stranger).authorize("force_delete", post)
    assert exc.value.status_code == 404
    assert Post in Gate.policies()


def test_policy_attribute_and_guess(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Tagged:
        policy = PostPolicy

    assert Gate.get_policy_for(Tagged()) is not None

    class Mystery:
        pass

    assert Gate.get_policy_for(Mystery()) is None
    assert Gate.get_policy_for(1) is None

    Gate.guess_policy_names_using(lambda model: PostPolicy if model is Post else None)
    assert isinstance(Gate.get_policy_for(Post), PostPolicy)

    Gate.flush()
    Gate.guess_policy_names_using(lambda model: [f"no.such.{model.__name__}Policy"])
    assert Gate.get_policy_for(Post) is None


def test_guest_policy_optional_user() -> None:
    Gate.policy(Post, GuestPolicy)
    post = Post(1)
    assert Gate.for_user(None).allows("view", post)


def test_resource_gates() -> None:
    Gate.resource("posts", PostPolicy)
    post = Post(1)
    user = User(1)
    assert Gate.has("posts.update")
    assert Gate.for_user(user).allows("posts.update", post)
    assert Gate.for_user(User(9)).denies("posts.update", post)


def test_string_and_class_callbacks() -> None:
    Gate.define("handled", HandleAbility)
    assert Gate.for_user(User(1)).allows("handled")
    path = f"{HandleAbility.__module__}.{HandleAbility.__qualname__}"
    Gate.define("via-path", path)
    assert Gate.for_user(User(1)).allows("via-path")
    Gate.define("via-at", f"{path}@handle")
    assert Gate.for_user(User(1)).allows("via-at")
    Gate.define("via-tuple", [HandleAbility, "handle"])
    assert Gate.for_user(User(1)).allows("via-tuple")
    with pytest.raises(TypeError):
        Gate.define("bad", "not.a.real.Callback")
        Gate.for_user(User(1)).allows("bad")
    with pytest.raises(TypeError):
        Gate.get_gate()._invoke_missing = None  # type: ignore[attr-defined]
        from almasix.auth.access.gate import _resolve_callback

        _resolve_callback(object(), container=None)


def test_helpers_gate_resolution_and_payload_shapes() -> None:
    from almasix.auth.access.helpers import gate as resolve_gate
    from almasix.auth.access.helpers import gate_allows as allows
    from almasix.auth.access.helpers import gate_any as any_

    Gate.flush()
    Gate.set_gate(None)
    resolved = resolve_gate()
    assert isinstance(resolved, AccessGate)
    Gate.define("one", lambda user, value=None: value == 1)
    Gate.set_gate(Gate.get_gate().for_user(User(1)))
    assert allows("one", 1)
    assert allows("one", 1, 2)
    assert any_(["one"], 1)
    assert any_(["one"], 1, 2)


def test_guest_policy_guess_and_deny_fallbacks() -> None:
    Gate.flush()

    class NeedsUser:
        pass

    Gate.guess_policy_names_using(lambda model: None)
    assert Gate.get_policy_for(NeedsUser()) is None
    Gate.default_deny_response(lambda: AuthorizationResponse.deny("fallback"))
    assert Gate.for_user(None).inspect("missing").message() == "fallback"
    Gate.default_deny_response(AuthorizationResponse.deny("fixed"))
    assert Gate.for_user(None).inspect("still-missing").message() == "fixed"
    Gate.flush()


def test_policy_class_and_method_name_resolution() -> None:
    class CamelPolicy(Policy):
        def deletePost(self, user: Any, post: Post) -> bool:
            return True

        def name(self, user: Any, post: Post) -> bool:
            return True

    Gate.policy(Post, CamelPolicy)
    assert Gate.for_user(User(1)).allows("deletePost", Post(1))
    assert Gate.for_user(User(1)).allows("delete_post", Post(1))
    assert Gate.for_user(User(1)).allows("name", Post(1))


def test_authorizable_mixin() -> None:
    Gate.define("ping", lambda user: True)
    user = User(1)
    assert user.can("ping")
    assert not user.cannot("ping")
    assert user.cant("missing")
    assert user.can_any(["ping", "missing"])


def test_controller_authorize() -> None:
    Gate.define("go", lambda user: True)
    Gate.define("no", lambda user: False)
    ctrl = Controller()
    Gate.for_user(User(1))
    # no current user — go requires user
    with pytest.raises(AuthorizationException):
        ctrl.authorize("go")
    ctrl.authorize_for_user(User(1), "go")
    with pytest.raises(AuthorizationException):
        ctrl.authorize_for_user(User(1), "no")
    assert "update" in ctrl.resource_ability_map()


def test_form_request_bool_and_response() -> None:
    class DenyReq(FormRequest):
        def authorize(self) -> bool:
            return False

    class AllowReq(FormRequest):
        def authorize(self) -> bool:
            return True

    class ResponseReq(FormRequest):
        def authorize(self) -> AuthorizationResponse:
            return AuthorizationResponse.deny("nope")

    request = Request.__new__(Request)
    request._data = {}
    # FormRequest.validate uses validation_data -> request.all(); stub minimally
    for cls, exc_type in (
        (DenyReq, ForbiddenHttpException),
        (ResponseReq, AuthorizationException),
    ):
        inst = cls.__new__(cls)
        inst._request = request
        inst._model = None
        inst._validated = {}
        inst.prepare_for_validation = lambda: None  # type: ignore[method-assign]
        with pytest.raises(exc_type):
            # authorize only path
            allowed = inst.authorize()
            if isinstance(allowed, AuthorizationResponse):
                allowed.authorize()
            elif allowed is False:
                raise ForbiddenHttpException("This action is unauthorized.")


def test_form_request_validate_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    class Ok(FormRequest):
        name: str = "x"

        def authorize(self) -> bool:
            return True

    class FakeRequest:
        def all(self) -> dict:
            return {"name": "ok"}

    inst = Ok(FakeRequest())  # type: ignore[arg-type]
    inst.validate()
    assert inst.validated()["name"] == "ok"

    class Nope(FormRequest):
        name: str = "x"

        def authorize(self) -> bool:
            return False

    with pytest.raises(ForbiddenHttpException):
        Nope(FakeRequest()).validate()  # type: ignore[arg-type]

    class Resp(FormRequest):
        name: str = "x"

        def authorize(self) -> AuthorizationResponse:
            return AuthorizationResponse.allow()

    Resp(FakeRequest()).validate()  # type: ignore[arg-type]


def test_authorization_response_helpers() -> None:
    allow = AuthorizationResponse.allow("ok", 1)
    assert allow.allowed() and not allow.denied()
    assert allow.message() == "ok" and allow.code() == 1
    allow.authorize()
    deny = AuthorizationResponse.deny_with_status(418, "teapot")
    assert deny.status() == 418
    not_found = AuthorizationResponse.deny_as_not_found()
    with pytest.raises(AuthorizationException) as exc:
        not_found.authorize()
    assert exc.value.status_code == 404
    handles = HandlesAuthorization()
    assert handles.allow().allowed()
    assert handles.deny().denied()
    assert handles.deny_with_status(401).status() == 401
    assert handles.deny_as_not_found().status() == 404


def test_prism_can_cannot_canany() -> None:
    Gate.define("edit", lambda user, post: user.id == post.user_id)
    Gate.define("other", lambda user, post: False)
    user = User(1)
    post = Post(1)
    other = Post(2)
    ctx = {"user": user, "post": post, "other": other}
    Gate.set_gate(Gate.get_gate().for_user(user))

    can = compile_template("@can('edit', post)yes@else\nno@endcan")
    assert "yes" in can(ctx, None)
    cannot = compile_template("@cannot('edit', other)hidden@endcannot")
    assert "hidden" in cannot({**ctx, "other": other}, None)
    canany = compile_template("@canany(['edit', 'other'], post)any@endcanany")
    assert "any" in canany(ctx, None)
    cannotany = compile_template("@cannotany(['other'], post)none@endcannotany")
    assert "none" in cannotany(ctx, None)


def test_route_can_appends_middleware() -> None:
    route = RouteDefinition(methods=("GET",), uri="/x", action=lambda: None)
    route.can("update", "post")
    assert "can:update,post" in route.middleware
    route.can("view-dashboard")
    assert "can:view-dashboard" in route.middleware
    route.can("create", Post)
    assert any(item.startswith("can:create,") for item in route.middleware)


@pytest.mark.asyncio
async def test_authorize_middleware(monkeypatch: pytest.MonkeyPatch) -> None:
    Gate.define("view-dashboard", lambda user=None: True)
    seen = []

    async def nxt(request):
        seen.append("ok")
        return "done"

    mw = Authorize("view-dashboard")
    result = await mw.handle(type("R", (), {"path_params": {}})(), nxt)
    assert result == "done" and seen == ["ok"]

    Gate.flush()
    Gate.define("update", lambda user=None, post=None: post == "1")
    mw = Authorize("update,post")
    request = type("R", (), {"path_params": {"post": "1"}})()
    await mw.handle(request, nxt)

    mw = Authorize("create,almasix.auth.Policy")
    Gate.define("create", lambda user=None, cls=None: cls is Policy)
    await mw.handle(type("R", (), {"path_params": {}})(), nxt)

    empty = Authorize("")
    await empty.handle(type("R", (), {"path_params": {}})(), nxt)

    with pytest.raises(AuthorizationException):
        await Authorize("missing,nope.token").handle(
            type("R", (), {"path_params": {}})(), nxt
        )


def test_provider_binds_gate(tmp_path: Path) -> None:
    app = Application.configure(tmp_path).create()
    AuthServiceProvider(app).register()
    AuthServiceProvider(app).boot()
    assert isinstance(Gate.get_gate(), AccessGate)
    Gate.define("boot", lambda user=None: True)
    assert Gate.allows("boot")


def test_make_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app").mkdir()
    runner = CliRunner()
    from almasix.console.kernel import ConsoleKernel

    ConsoleKernel.from_cwd(tmp_path).register_on_typer(smith_app)
    result = runner.invoke(smith_app, ["make:policy", "PostPolicy", "--model=Post", "--resource"])
    assert result.exit_code == 0, result.stdout + result.stderr
    path = tmp_path / "app" / "policies" / "post_policy.py"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "class PostPolicy" in text
    assert "def update" in text
    dup = runner.invoke(smith_app, ["make:policy", "PostPolicy"])
    assert dup.exit_code == 1
    forced = runner.invoke(smith_app, ["make:policy", "PostPolicy", "--force"])
    assert forced.exit_code == 0
    empty = runner.invoke(smith_app, ["make:policy", "Comment"])
    assert empty.exit_code == 0
    assert (tmp_path / "app" / "policies" / "comment_policy.py").is_file()
    nameless = runner.invoke(smith_app, ["make:policy", ""])
    assert nameless.exit_code == 1
    resource_only = runner.invoke(smith_app, ["make:policy", "Widget", "--resource"])
    assert resource_only.exit_code == 0
    widget = (tmp_path / "app" / "policies" / "widget_policy.py").read_text(encoding="utf-8")
    assert "def view_any" in widget
    assert ": model" not in widget


def test_kernel_resource_authorization() -> None:
    from almasix.http.kernel import HttpKernel
    from almasix.routing.router import Router

    class PostController(Controller):
        authorizes_resource = Post

        def show(self, post: Post) -> dict:
            return {"id": post.user_id}

        def index(self) -> dict:
            return {"ok": True}

        def unknown(self) -> dict:
            return {}

    Gate.policy(Post, PostPolicy)
    kernel = HttpKernel(Application(Path(".")), Router())

    class FakeRequest:
        path_params: ClassVar[dict] = {}

    ctrl = PostController()
    with pytest.raises(AuthorizationException):
        kernel._authorize_controller_resource(ctrl.index, FakeRequest(), {})
    kernel._authorize_controller_resource(ctrl.unknown, FakeRequest(), {})
    post = Post(1)
    with pytest.raises(AuthorizationException):
        kernel._authorize_controller_resource(ctrl.show, FakeRequest(), {"post": post})
    Gate.for_user(User(1))
    # still uses current gate user (none) unless we set resolver
    Gate.set_gate(Gate.get_gate().for_user(User(1)))
    kernel._authorize_controller_resource(ctrl.show, FakeRequest(), {"post": post})
    kernel._authorize_controller_resource(ctrl.index, FakeRequest(), {})


def test_kernel_resource_authorization_parameter_and_fallbacks() -> None:
    from almasix.http.kernel import HttpKernel
    from almasix.routing.router import Router

    class PostController(Controller):
        authorizes_resource = (Post, "item")

        def show(self, item: Post) -> dict:
            return {"id": item.user_id}

    Gate.policy(Post, PostPolicy)
    kernel = HttpKernel(Application(Path(".")), Router())

    class FakeRequest:
        path_params: ClassVar[dict] = {}

    ctrl = PostController()
    post = Post(1)
    Gate.set_gate(Gate.get_gate().for_user(User(1)))
    kernel._authorize_controller_resource(ctrl.show, FakeRequest(), {"item": post})
    with pytest.raises(TypeError):
        kernel._authorize_controller_resource(ctrl.show, FakeRequest(), {})

    class NoopController(Controller):
        authorizes_resource = Post

        def ping(self) -> dict:
            return {}

    kernel._authorize_controller_resource(NoopController().ping, FakeRequest(), {})


def test_access_gate_container_policy_make(tmp_path: Path) -> None:
    app = Application.configure(tmp_path).create()
    g = AccessGate(container=app.container)
    g.policy(Post, PostPolicy)
    assert isinstance(g.get_policy_for(Post), PostPolicy)
    g.define("truthy", lambda user: "yes")
    assert g.for_user(User(1)).allows("truthy")
    g.define("empty-fn", lambda: True)
    assert g.for_user(User(1)).allows("empty-fn")


def test_gate_internal_branches_for_parity(monkeypatch: pytest.MonkeyPatch) -> None:
    import inspect
    from typing import Optional, Union
    from unittest.mock import Mock

    from almasix.auth.access.exceptions import AuthorizationException
    from almasix.auth.access.gate import (
        _call_after,
        _can_be_called_with_user,
        _default_policy_paths,
        _invoke,
        _make,
        _maybe_import,
        _parameter_allows_none,
        _policy_method_name,
        _resolve_callback,
        _user_parameter,
        _wrap_guess,
    )
    from almasix.auth.access.helpers import resolve_gate
    from almasix.auth.access.middleware import _import_string

    def first_param(fn: Any) -> inspect.Parameter:
        return next(iter(inspect.signature(fn).parameters.values()))

    Gate.flush()
    Gate.register_policies({Post: PostPolicy})
    Gate.resource("posts", PostPolicy, abilities={"publish": "update", "viewAny": "view_any"})
    user = User(1)
    assert Gate.has("posts.publish") and Gate.has("posts.view_any")
    assert Gate.for_user(user).allows("posts.update", Post(1))
    Gate.set_gate(Gate.get_gate().for_user(user))
    assert Gate.denies("posts.update", Post(9))
    assert Gate.check(["posts.view", "posts.update"], Post(1))
    assert Gate.any(["posts.delete", "posts.update"], Post(1))
    assert Gate.none(["missing-ability"])
    assert Gate.inspect("posts.update", Post(1)).allowed()

    class Nested:
        __module__ = "app.models.blog.post"

    paths = _default_policy_paths(Nested)
    assert any(".policies." in p for p in paths)
    assert _maybe_import("almasix.auth.Policy") is Policy
    assert _maybe_import("Policy") is None
    assert _maybe_import("no.such.module.Thing") is None
    assert _import_string("almasix.auth.Policy") is Policy
    assert _import_string("Policy") is None
    assert _import_string("no.such.module.Thing") is None

    class BrokenContainer:
        def make(self, cls: type) -> Any:
            raise RuntimeError("nope")

    broken = AccessGate(container=BrokenContainer())
    broken.policy(Post, PostPolicy)
    assert isinstance(broken.get_policy_for(Post), PostPolicy)
    assert isinstance(_make(PostPolicy, BrokenContainer()), PostPolicy)

    class OptionalBefore(Policy):
        def before(self, user: Any = None, ability: str | None = None) -> None:
            return None

        def mystery(self, user: Any, post: Post) -> bool:
            return True

    Gate.flush()
    Gate.policy(Post, OptionalBefore)
    Gate.before(lambda user, ability: None)
    Gate.before(lambda user=None, ability=None: None)
    Gate.after(lambda user, ability, result, arguments: None)
    Gate.after(lambda user=None, ability=None, result=None, arguments=None: result)
    assert Gate.for_user(User(1)).allows("mystery", Post(1))
    assert Gate.for_user(User(1)).denies("absent", Post(1))
    assert Gate.for_user(None).denies("mystery", Post(1))

    class NoMethodPolicy(Policy):
        pass

    Gate.flush()
    Gate.policy(Post, NoMethodPolicy)
    assert Gate.for_user(User(1)).denies("update", Post(1))

    class GuessModel:
        __module__ = "app.models.widget"

    Gate.flush()
    assert Gate.get_policy_for(GuessModel) is None
    Gate.guess_policy_names_using(lambda model: [None, "no.such.Policy", PostPolicy])
    assert isinstance(Gate.get_policy_for(Post), PostPolicy)

    Gate.flush()
    Gate.default_deny_response(lambda: "not-a-response")  # type: ignore[arg-type]
    assert Gate.for_user(User(1)).inspect("missing").denied()

    class CamelPolicy(Policy):
        def restoreThing(self, user: Any, post: Post) -> bool:
            return True

    Gate.flush()
    Gate.policy(Post, CamelPolicy)
    assert Gate.for_user(User(1)).allows("restore_thing", Post(1))
    assert _policy_method_name(CamelPolicy(), "nope") is None

    assert _user_parameter(lambda: True) is None
    assert _user_parameter("string") is None
    assert _user_parameter(["only-one"]) is None
    assert _user_parameter([HandleAbility, "handle"]) is not None
    assert _user_parameter(object()) is None
    assert _can_be_called_with_user(lambda: True, None)
    assert _can_be_called_with_user(lambda *args: True, None)
    assert _can_be_called_with_user(HandleAbility, None) is False
    class NoHandle:
        pass

    assert _can_be_called_with_user(NoHandle, None)
    path = f"{HandleAbility.__module__}.{HandleAbility.__qualname__}"
    assert _can_be_called_with_user(path, None) is False
    assert _can_be_called_with_user([HandleAbility, "handle"], None) is False
    assert _can_be_called_with_user([HandleAbility, "missing"], None) is False

    def annotated_optional(user: User | None) -> bool:
        return True

    def annotated_union(user: User | None) -> bool:
        return True

    def required(user: User) -> bool:
        return True

    def unannotated(user) -> bool:
        return True

    assert _parameter_allows_none(first_param(annotated_optional))
    assert _parameter_allows_none(first_param(annotated_union))
    assert not _parameter_allows_none(first_param(required))
    assert not _parameter_allows_none(first_param(unannotated))
    assert _parameter_allows_none(first_param(lambda user="x": True))
    assert _parameter_allows_none(
        inspect.Parameter(
            "user",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation="typing.Optional[User]",
        )
    )
    assert _parameter_allows_none(
        inspect.Parameter(
            "user",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation="Optional[User]",
        )
    )
    empty = inspect.Parameter("user", inspect.Parameter.POSITIONAL_OR_KEYWORD)
    assert not _parameter_allows_none(empty)
    assert _parameter_allows_none(
        inspect.Parameter("user", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=User | None)
    )
    assert _parameter_allows_none(
        inspect.Parameter("user", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Union[User, None])  # noqa: UP007
    )
    assert _parameter_allows_none(
        inspect.Parameter("user", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Optional[User])  # noqa: UP045
    )
    assert not _parameter_allows_none(
        inspect.Parameter("user", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=User)
    )

    with pytest.raises(TypeError):
        _resolve_callback("no.such.Class@handle", container=None)
    with pytest.raises(TypeError):
        _resolve_callback(f"{path}@missing", container=None)
    with pytest.raises(TypeError):
        _resolve_callback(["no.such.Class", "handle"], container=None)
    with pytest.raises(TypeError):
        _resolve_callback([HandleAbility, "missing"], container=None)
    assert callable(_resolve_callback(["almasix.auth.access.policies.Policy", "allow"], container=None))
    assert callable(_resolve_callback(f"{path}@handle", container=None))

    class OkContainer:
        def make(self, cls: type) -> Any:
            return cls()

    assert isinstance(_make(PostPolicy, OkContainer()), PostPolicy)
    assert _invoke(Mock(return_value=True), User(1), [], container=None) is True
    assert _call_after(Mock(return_value=None), User(1), "x", False, []) is None
    assert _call_after(lambda *a: a[2], User(1), "x", False, []) is False
    assert _invoke(lambda user, *a: True, User(1), ["x"], container=None) is True

    Gate.flush()
    Gate.define("guest-star", lambda *args: True)
    assert Gate.for_user(None).allows("guest-star")
    Gate.set_gate(None)
    first = resolve_gate()
    assert resolve_gate() is first

    Gate.define("ok", lambda user=None: True)
    Gate.define("no", lambda user=None: False)
    ctrl = Controller()
    assert ctrl.can("ok")
    assert ctrl.cannot("no")
    ctrl.authorize_when(False, "no")
    ctrl.authorize_when(True, "ok")
    ctrl.authorize_unless(True, "no")
    with pytest.raises(AuthorizationException):
        ctrl.authorize_unless(False, "no")
    assert user.canany(["ok", "no"])

    import sys

    gmod = sys.modules[AccessGate.__module__]
    monkeypatch.setattr(gmod, "_default_policy_paths", lambda cls: ["almasix.auth.access.policies.Policy"])
    Gate.flush()
    assert isinstance(Gate.get_policy_for(Post), Policy)
    monkeypatch.setattr(inspect, "isclass", lambda _m: True)
    assert Gate.get_policy_for("not-a-type") is None
    _policy_method_name(CamelPolicy(), "")

    real_signature = inspect.signature

    def boom_signature(obj: Any, *args: Any, **kwargs: Any) -> Any:
        if getattr(obj, "__name__", "") == "no_signature_fn":
            raise ValueError("no signature")
        return real_signature(obj, *args, **kwargs)

    def no_signature_fn(*args: Any) -> bool:
        return True

    monkeypatch.setattr(inspect, "signature", boom_signature)
    assert _invoke(no_signature_fn, User(1), [], container=None) is True
    assert _call_after(no_signature_fn, User(1), "x", False, []) is True

    exc = AuthorizationException("x", response=AuthorizationResponse.deny_with_status(418, "teapot"))
    assert exc.status_code == 418

    Gate.flush()
    Gate.set_gate(AccessGate())
    Gate.define("ok", lambda user=None: True)
    assert Gate.denies("no")
    assert Gate.check("ok")
    assert Gate.none(["no"])
    assert not Gate.inspect("no").allowed()

    import almasix.auth.guard as ag

    class FakeManager:
        def user(self) -> User:
            return User(3)

    old = ag.get_auth
    ag.get_auth = lambda: FakeManager()  # type: ignore[method-assign]
    try:
        assert AccessGate()._resolve_user().id == 3
        ag.get_auth = lambda: None  # type: ignore[method-assign]
        assert AccessGate()._resolve_user() is None

        def boom() -> Any:
            raise RuntimeError("auth down")

        ag.get_auth = boom  # type: ignore[method-assign]
        assert AccessGate()._resolve_user() is None
    finally:
        ag.get_auth = old  # type: ignore[method-assign]

    assert _wrap_guess(None) == []
    assert _wrap_guess("x") == ["x"]
    assert _wrap_guess(("a", "b")) == ["a", "b"]


@pytest.mark.asyncio
async def test_authorize_middleware_multi_arguments() -> None:
    Gate.define("update", lambda user=None, *args: True)
    Gate.define("create", lambda user=None, *args: True)

    async def nxt(request: Any) -> str:
        return "ok"

    mw = Authorize("update,post,extra")
    result = await mw.handle(type("R", (), {"path_params": {"post": "1"}})(), nxt)
    assert result == "ok"
    await Authorize("create,no.such.Token").handle(type("R", (), {"path_params": {}})(), nxt)
