"""Authorization gate — abilities, policies, before/after hooks."""

from __future__ import annotations

import inspect
import types
from collections.abc import Callable, Sequence
from typing import Any, Union

from almasix.auth.access.response import AuthorizationResponse
from almasix.orm.inflector import snake

AbilityCallback = Callable[..., Any]
GuessCallback = Callable[[type], str | type | Sequence[str | type] | None]

RESOURCE_ABILITIES: dict[str, str] = {
    "viewAny": "view_any",
    "view_any": "view_any",
    "view": "view",
    "create": "create",
    "update": "update",
    "delete": "delete",
    "restore": "restore",
    "forceDelete": "force_delete",
    "force_delete": "force_delete",
}

CONTROLLER_RESOURCE_ABILITIES: dict[str, str] = {
    "index": "view_any",
    "show": "view",
    "create": "create",
    "store": "create",
    "edit": "update",
    "update": "update",
    "destroy": "delete",
}


class Gate:
    """Evaluate abilities against the current (or a given) user."""

    def __init__(
        self,
        *,
        user_resolver: Callable[[], Any] | None = None,
        container: Any | None = None,
        user: Any = None,
        explicit_user: bool = False,
    ) -> None:
        self._user_resolver = user_resolver
        self._container = container
        self._user = user
        self._explicit_user = explicit_user
        self._abilities: dict[str, AbilityCallback] = {}
        self._policies: dict[type, type] = {}
        self._before: list[AbilityCallback] = []
        self._after: list[AbilityCallback] = []
        self._guess_callbacks: list[GuessCallback] = []
        self._default_deny: Callable[[], AuthorizationResponse] | None = None
        self._policy_cache: dict[type, Any] = {}

    def define(self, ability: str, callback: AbilityCallback | str | Sequence[Any]) -> Gate:
        self._abilities[str(ability)] = callback  # type: ignore[assignment]
        return self

    def policy(self, model: type, policy: type) -> Gate:
        self._policies[model] = policy
        self._policy_cache.pop(model, None)
        return self

    def register_policies(self, policies: dict[type, type]) -> Gate:
        for model, policy in policies.items():
            self.policy(model, policy)
        return self

    def resource(
        self,
        name: str,
        policy: type,
        abilities: dict[str, str] | None = None,
    ) -> Gate:
        mapping = dict(RESOURCE_ABILITIES)
        if abilities:
            mapping.update(abilities)
        for ability, method in mapping.items():
            self.define(f"{name}.{ability}", [policy, method])
        return self

    def before(self, callback: AbilityCallback) -> Gate:
        self._before.append(callback)
        return self

    def after(self, callback: AbilityCallback) -> Gate:
        self._after.append(callback)
        return self

    def guess_policy_names_using(self, callback: GuessCallback) -> Gate:
        self._guess_callbacks.append(callback)
        return self

    def default_deny_response(
        self,
        callback: Callable[[], AuthorizationResponse] | AuthorizationResponse,
    ) -> Gate:
        if callable(callback) and not isinstance(callback, AuthorizationResponse):
            self._default_deny = callback
        else:
            response = callback

            def _fixed() -> AuthorizationResponse:
                return response  # type: ignore[return-value]

            self._default_deny = _fixed
        return self

    def has(self, ability: str) -> bool:
        return str(ability) in self._abilities

    def abilities(self) -> dict[str, AbilityCallback]:
        return dict(self._abilities)

    def policies(self) -> dict[type, type]:
        return dict(self._policies)

    def flush(self) -> None:
        self._abilities.clear()
        self._policies.clear()
        self._before.clear()
        self._after.clear()
        self._guess_callbacks.clear()
        self._policy_cache.clear()
        self._default_deny = None

    def for_user(self, user: Any) -> Gate:
        clone = Gate(
            user_resolver=lambda: user,
            container=self._container,
            user=user,
            explicit_user=True,
        )
        clone._abilities = self._abilities
        clone._policies = self._policies
        clone._before = self._before
        clone._after = self._after
        clone._guess_callbacks = self._guess_callbacks
        clone._default_deny = self._default_deny
        clone._policy_cache = self._policy_cache
        return clone

    def allows(self, ability: str, arguments: Any = None) -> bool:
        return self.inspect(ability, arguments).allowed()

    def denies(self, ability: str, arguments: Any = None) -> bool:
        return not self.allows(ability, arguments)

    def check(self, abilities: str | Sequence[str], arguments: Any = None) -> bool:
        names = [abilities] if isinstance(abilities, str) else list(abilities)
        return all(self.allows(name, arguments) for name in names)

    def any(self, abilities: Sequence[str], arguments: Any = None) -> bool:
        return any(self.allows(name, arguments) for name in abilities)

    def none(self, abilities: Sequence[str], arguments: Any = None) -> bool:
        return not self.any(abilities, arguments)

    def authorize(self, ability: str, arguments: Any = None) -> AuthorizationResponse:
        return self.inspect(ability, arguments).authorize()

    def inspect(self, ability: str, arguments: Any = None) -> AuthorizationResponse:
        args = _normalize_arguments(arguments)
        user = self._resolve_user()
        result = self._raw(user, str(ability), args)
        result = self._run_after(user, str(ability), result, args)
        return self._to_response(result)

    def get_policy_for(self, model: Any) -> Any | None:
        model_class = model if inspect.isclass(model) else type(model)
        if not isinstance(model_class, type):
            return None
        policy_class = self._policies.get(model_class)
        if policy_class is None:
            attr = getattr(model_class, "policy", None)
            if isinstance(attr, type):
                policy_class = attr
        if policy_class is None:
            policy_class = self._guess_policy_class(model_class)
        if policy_class is None:
            return None
        return self._policy_instance(policy_class)

    def _resolve_user(self) -> Any:
        if self._explicit_user:
            return self._user
        if self._user_resolver is not None:
            return self._user_resolver()
        try:
            from almasix.auth.guard import get_auth

            manager = get_auth()
        except Exception:
            return None
        if manager is None:
            return None
        return manager.user()

    def _raw(self, user: Any, ability: str, arguments: list[Any]) -> Any:
        before = self._run_before(user, ability, arguments)
        if before is not None:
            return before
        if ability in self._abilities:
            callback = self._abilities[ability]
            if not _can_be_called_with_user(callback, user):
                return False
            return _invoke(callback, user, arguments, container=self._container)
        if arguments:
            policy = self.get_policy_for(arguments[0])
            if policy is not None:
                return self._call_policy(policy, user, ability, arguments)
        return None

    def _run_before(self, user: Any, ability: str, arguments: list[Any]) -> Any:
        for callback in self._before:
            if not _can_be_called_with_user(callback, user):
                continue
            value = _invoke(callback, user, [ability, *arguments], container=self._container)
            if value is not None:
                return value
        return None

    def _run_after(self, user: Any, ability: str, result: Any, arguments: list[Any]) -> Any:
        current = result
        for callback in self._after:
            if not _can_be_called_with_user(callback, user):
                continue
            value = _call_after(callback, user, ability, current, arguments)
            if value is not None:
                current = value
        return current

    def _call_policy(self, policy: Any, user: Any, ability: str, arguments: list[Any]) -> Any:
        before = getattr(policy, "before", None)
        if callable(before):
            if _can_be_called_with_user(before, user):
                value = _invoke(before, user, [ability], container=self._container)
                if value is not None:
                    return value
        method_name = _policy_method_name(policy, ability)
        if method_name is None:
            return None
        method = getattr(policy, method_name)
        if not _can_be_called_with_user(method, user):
            return False
        model = arguments[0]
        rest = arguments[1:]
        if inspect.isclass(model):
            return _invoke(method, user, rest, container=self._container)
        return _invoke(method, user, [model, *rest], container=self._container)

    def _guess_policy_class(self, model_class: type) -> type | None:
        if self._guess_callbacks:
            for callback in self._guess_callbacks:
                guessed = callback(model_class)
                for candidate in _wrap_guess(guessed):
                    resolved = _maybe_import(candidate) if isinstance(candidate, str) else candidate
                    if isinstance(resolved, type):
                        return resolved
            return None
        for path in _default_policy_paths(model_class):
            resolved = _maybe_import(path)
            if isinstance(resolved, type):
                return resolved
        return None

    def _policy_instance(self, policy_class: type) -> Any:
        cached = self._policy_cache.get(policy_class)
        if cached is not None:
            return cached
        instance: Any = None
        if self._container is not None and hasattr(self._container, "make"):
            try:
                instance = self._container.make(policy_class)
            except Exception:
                instance = None
        if instance is None:
            instance = policy_class()
        self._policy_cache[policy_class] = instance
        return instance

    def _to_response(self, result: Any) -> AuthorizationResponse:
        if isinstance(result, AuthorizationResponse):
            return result
        if result is True:
            return AuthorizationResponse.allow()
        if result is False:
            return self._deny_response()
        if result is None:
            return self._deny_response()
        return AuthorizationResponse.allow() if result else self._deny_response()

    def _deny_response(self) -> AuthorizationResponse:
        if self._default_deny is not None:
            value = self._default_deny()
            if isinstance(value, AuthorizationResponse):
                return value
        return AuthorizationResponse.deny()


def _normalize_arguments(arguments: Any) -> list[Any]:
    if arguments is None:
        return []
    if isinstance(arguments, (list, tuple)):
        return list(arguments)
    return [arguments]


def _wrap_guess(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _default_policy_paths(model_class: type) -> list[str]:
    name = model_class.__name__
    module = getattr(model_class, "__module__", "") or ""
    snake_name = snake(name)
    paths = [f"app.policies.{snake_name}_policy.{name}Policy"]
    if ".models." in module:
        suffix = module.split(".models.", 1)[1]
        parts = suffix.split(".")
        parts[-1] = f"{snake(parts[-1])}_policy"
        paths.append(f"app.policies.{'.'.join(parts)}.{name}Policy")
        replaced = module.replace(".models.", ".policies.", 1)
        paths.append(f"{replaced}.{name}Policy")
    return paths


def _maybe_import(path: str) -> Any | None:
    module_path, _, attr = path.rpartition(".")
    if not module_path:
        return None
    try:
        import importlib

        module = importlib.import_module(module_path)
        return getattr(module, attr, None)
    except Exception:
        return None


def _policy_method_name(policy: Any, ability: str) -> str | None:
    candidates = [ability, snake(ability)]
    camel = ability.replace("_", " ").title().replace(" ", "")
    if camel:
        candidates.append(camel[:1].lower() + camel[1:])
    for name in candidates:
        if callable(getattr(policy, name, None)):
            return name
    return None


def _parameter_allows_none(parameter: inspect.Parameter) -> bool:
    if parameter.default is not inspect.Parameter.empty:
        return True
    annotation = parameter.annotation
    if annotation is inspect.Parameter.empty:
        return False
    if isinstance(annotation, str):
        stripped = annotation.replace(" ", "")
        return (
            "None" in stripped.split("|")
            or stripped.startswith("Optional[")
            or stripped.startswith("typing.Optional[")
        )
    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())
    if origin is Union or str(origin).endswith("Union"):
        return type(None) in args
    if isinstance(annotation, types.UnionType):
        return type(None) in annotation.__args__
    return False


def _user_parameter(callback: Any) -> inspect.Parameter | None:
    fn = callback
    if isinstance(callback, str):
        return None
    if isinstance(callback, (list, tuple)):
        if len(callback) != 2:
            return None
        target, method = callback
        fn = getattr(target, method, None)
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return None
    params = [
        p
        for p in signature.parameters.values()
        if p.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        )
        and p.name != "self"
    ]
    if not params:
        return None
    return params[0]


def _can_be_called_with_user(callback: Any, user: Any) -> bool:
    if user is not None:
        return True
    if isinstance(callback, type):
        handle = getattr(callback, "handle", None)
        if callable(handle):
            return _can_be_called_with_user(handle, user)
    if isinstance(callback, str):
        resolved = _resolve_callback(callback, container=None)
        return _can_be_called_with_user(resolved, user)
    if isinstance(callback, (list, tuple)) and len(callback) == 2:
        target, method = callback
        attr = getattr(target, str(method), None)
        if attr is None:
            return False
        return _can_be_called_with_user(attr, user)
    param = _user_parameter(callback)
    if param is None:
        return True
    if param.kind == inspect.Parameter.VAR_POSITIONAL:
        return True
    return _parameter_allows_none(param)


def _resolve_callback(callback: Any, *, container: Any | None) -> Any:
    if callable(callback) and not isinstance(callback, type):
        return callback
    if isinstance(callback, type):
        instance = _make(callback, container)
        handle = getattr(instance, "handle", None)
        return handle if callable(handle) else instance
    if isinstance(callback, str):
        if "@" in callback:
            path, _, method = callback.partition("@")
            cls = _maybe_import(path)
            if cls is None:
                raise TypeError(f"Unable to resolve gate callback {callback!r}")
            instance = _make(cls, container) if inspect.isclass(cls) else cls
            attr = getattr(instance, method, None)
            if not callable(attr):
                raise TypeError(f"Unable to resolve gate callback {callback!r}")
            return attr
        cls = _maybe_import(callback)
        if cls is None:
            raise TypeError(f"Unable to resolve gate callback {callback!r}")
        return _resolve_callback(cls, container=container)
    if isinstance(callback, (list, tuple)) and len(callback) == 2:
        target, method = callback
        if isinstance(target, str):
            target = _maybe_import(target)
        if target is None:
            raise TypeError(f"Unable to resolve gate callback {callback!r}")
        instance = _make(target, container) if inspect.isclass(target) else target
        attr = getattr(instance, str(method), None)
        if not callable(attr):
            raise TypeError(f"Unable to resolve gate method {method!r}")
        return attr
    raise TypeError(f"Unsupported gate callback: {callback!r}")


def _make(cls: type, container: Any | None) -> Any:
    if container is not None and hasattr(container, "make"):
        try:
            return container.make(cls)
        except Exception:
            pass
    return cls()


def _invoke(callback: Any, user: Any, arguments: Sequence[Any], *, container: Any | None) -> Any:
    fn = _resolve_callback(callback, container=container)
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return fn(user, *arguments)
    params = [
        p
        for p in signature.parameters.values()
        if p.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
        and p.name != "self"
    ]
    has_varargs = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in signature.parameters.values())
    args: list[Any] = [user, *list(arguments)]
    if not has_varargs:
        args = args[: len(params)] if params else []
    return fn(*args)


def _call_after(
    callback: AbilityCallback,
    user: Any,
    ability: str,
    result: Any,
    arguments: list[Any],
) -> Any:
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return callback(user, ability, result, arguments)
    params = [
        p
        for p in signature.parameters.values()
        if p.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
        and p.name != "self"
    ]
    has_varargs = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in signature.parameters.values())
    args: list[Any] = [user, ability, result, arguments]
    if not has_varargs:
        args = args[: len(params)] if params else []
    return callback(*args)
