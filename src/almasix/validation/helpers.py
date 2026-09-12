"""``validator()`` — schema or Laravel-style rules dict."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ValidationError

from almasix.validation.form_request import FormRequest, ValidationException
from almasix.validation.messages import translate


class Validator:
    """One validation run over a payload (Laravel's ``Validator`` instance).

    ``rules`` may be a Pydantic model / FormRequest subclass **or** a
    field → rule-string / ``Rule`` list mapping.
    """

    def __init__(
        self,
        data: Mapping[str, Any],
        rules: type[BaseModel | FormRequest] | Mapping[str, Any],
        *,
        messages: Mapping[str, str] | None = None,
        attributes: Mapping[str, str] | None = None,
    ) -> None:
        self._data = dict(data)
        self._rules = rules
        self._messages = dict(messages or {})
        self._attributes = dict(attributes or {})
        self._model: BaseModel | None = None
        self._validated_data: dict[str, Any] | None = None
        self._errors: dict[str, list[str]] | None = None
        self._dsl = isinstance(rules, Mapping)
        if not self._dsl:
            # Fail fast for nonsense schema targets (same moment as before DSL).
            _schema(rules)  # type: ignore[arg-type]

    def passes(self) -> bool:
        return not self.fails()

    def fails(self) -> bool:
        self._run()
        return bool(self._errors)

    def errors(self) -> dict[str, list[str]]:
        self._run()
        return dict(self._errors or {})

    def validated(self) -> dict[str, Any]:
        self._run()
        if self._errors:
            raise ValidationException(dict(self._errors))
        if self._dsl:
            assert self._validated_data is not None
            return dict(self._validated_data)
        assert self._model is not None
        return self._model.model_dump()

    validate = validated

    def _run(self) -> None:
        if self._errors is not None:
            return
        if self._dsl:
            from almasix.validation.engine import AttributeValidator

            assert isinstance(self._rules, Mapping)
            runner = AttributeValidator(
                self._data,
                self._rules,
                messages=self._messages,
                attributes=self._attributes,
            )
            if runner.fails():
                self._errors = runner.errors()
                self._validated_data = None
            else:
                self._errors = {}
                self._validated_data = runner.validated()
            return

        schema = _schema(self._rules)  # type: ignore[arg-type]
        try:
            self._model = schema.model_validate(self._data)
        except ValidationError as exc:
            self._errors = translate(exc, messages=self._messages, attributes=self._attributes)
        else:
            self._errors = {}


def _schema(rules: type[BaseModel | FormRequest] | Any) -> type[BaseModel]:
    if isinstance(rules, type) and issubclass(rules, BaseModel):
        return rules
    if isinstance(rules, type) and issubclass(rules, FormRequest):
        return rules.__schema__
    raise TypeError("Rules must be a Pydantic model or a FormRequest subclass.")


def validator(
    data: Mapping[str, Any],
    rules: type[BaseModel | FormRequest] | Mapping[str, Any],
    *,
    messages: Mapping[str, str] | None = None,
    attributes: Mapping[str, str] | None = None,
) -> Validator:
    """Validate ``data`` against a schema or Laravel-style rules mapping."""
    return Validator(data, rules, messages=messages, attributes=attributes)


__all__ = ["Validator", "validator"]
