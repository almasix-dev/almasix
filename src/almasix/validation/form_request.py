"""Form Request-style validation — Laravel's FormRequest on Pydantic v2."""

from __future__ import annotations

from typing import Any, ClassVar, get_type_hints

from pydantic import BaseModel, ValidationError, create_model
from pydantic_core import PydanticUndefined

from almasix.http.exceptions import ForbiddenHttpException, UnprocessableEntityHttpException
from almasix.http.request import Request
from almasix.validation.messages import translate


class ValidationException(UnprocessableEntityHttpException):
    """422 with the locked `{message, status, errors}` envelope."""

    def __init__(
        self,
        errors: dict[str, list[str]],
        message: str = "The given data was invalid.",
    ) -> None:
        super().__init__(message, errors=errors)


def _validators_for(cls: type[FormRequest]) -> dict[str, Any]:
    """Collect `@field_validator` / `@model_validator` members from the class."""
    validators: dict[str, Any] = {}
    for klass in reversed(cls.__mro__):
        for name, value in vars(klass).items():
            if hasattr(value, "decorator_info"):
                validators[name] = value
    return validators


def _schema_for(cls: type[FormRequest]) -> type[BaseModel]:
    """Build a Pydantic model from the class's field annotations."""
    hints = get_type_hints(cls, include_extras=True)
    fields: dict[str, Any] = {}
    for name, annotation in hints.items():
        if name.startswith("_"):
            continue
        if getattr(annotation, "__origin__", None) is ClassVar:
            continue
        default = getattr(cls, name, PydanticUndefined)
        if callable(default) and not isinstance(default, type):
            continue
        fields[name] = (annotation, default)
    return create_model(
        f"{cls.__name__}Schema",
        __validators__=_validators_for(cls),
        **fields,
    )


class FormRequest:
    """Validates incoming input before the controller action runs.

    Declare fields as annotations; the kernel builds one per request, runs
    `authorize()` then validation, and injects it into the action::

        class StorePostRequest(FormRequest):
            title: str = Field(min_length=3)
            published: bool = False

        async def store(self, request: StorePostRequest) -> dict:
            return {"title": request.data.title}

    Anything not defined here proxies to the underlying `Request`, so the full
    M2 input bag (`input()`, `header()`, `file()`, …) stays available.
    """

    __schema__: ClassVar[type[BaseModel]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.__schema__ = _schema_for(cls)

    def __init__(self, request: Request) -> None:
        self._request = request
        self._model: BaseModel | None = None
        self._validated: dict[str, Any] = {}

    # ------------------------------------------------------------------ hooks

    def authorize(self) -> bool:
        """Return False to reject the request with 403."""
        return True

    def prepare_for_validation(self) -> None:
        """Normalize input before validation (use `merge()` / `replace()`)."""

    def passed_validation(self) -> None:
        """Runs after validation succeeds."""

    def messages(self) -> dict[str, str]:
        """Override messages by `field.rule` or `field`."""
        return {}

    def attributes(self) -> dict[str, str]:
        """Human-readable field names used in messages."""
        return {}

    def validation_data(self) -> dict[str, Any]:
        """Query merged with body (body wins) — route params excluded."""
        return self._request.all()

    # ------------------------------------------------------------------ state

    @property
    def request(self) -> Request:
        return self._request

    @property
    def data(self) -> BaseModel:
        """Validated input as the typed model."""
        if self._model is None:
            raise RuntimeError("FormRequest has not been validated yet.")
        return self._model

    def validated(self, *keys: str) -> dict[str, Any]:
        """Validated input as a dict, optionally narrowed to `keys`."""
        if not keys:
            return dict(self._validated)
        return {key: self._validated[key] for key in keys if key in self._validated}

    # ------------------------------------------------------------- validation

    @classmethod
    def validate_request(cls, request: Request) -> FormRequest:
        instance = cls(request)
        instance.validate()
        return instance

    def validate(self) -> None:
        self.prepare_for_validation()
        allowed = self.authorize()
        from almasix.auth.access.exceptions import AuthorizationException
        from almasix.auth.access.response import AuthorizationResponse

        if isinstance(allowed, AuthorizationResponse):
            allowed.authorize()
        elif allowed is False:
            raise ForbiddenHttpException("This action is unauthorized.")
        elif isinstance(allowed, AuthorizationException):
            raise allowed

        try:
            model = self.__schema__.model_validate(self.validation_data())
        except ValidationError as exc:
            raise ValidationException(
                translate(exc, messages=self.messages(), attributes=self.attributes())
            ) from exc

        self._model = model
        self._validated = model.model_dump()
        self.passed_validation()

    def __getattr__(self, item: str) -> Any:
        try:
            request = object.__getattribute__(self, "_request")
        except AttributeError:
            raise AttributeError(item) from None
        return getattr(request, item)
