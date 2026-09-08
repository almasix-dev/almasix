"""``validator()`` — validate a payload outside the request lifecycle."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ValidationError

from almasix.validation.form_request import FormRequest, ValidationException
from almasix.validation.messages import translate


class Validator:
    """One validation run over a payload (Laravel's ``Validator`` instance).

    **Named deviation:** rules are a Pydantic model or a
    :class:`~almasix.validation.FormRequest` subclass rather than Laravel's
    array of rule strings, because that is how Almasix declares validation
    everywhere else.
    """

    def __init__(
        self,
        data: Mapping[str, Any],
        rules: type[BaseModel | FormRequest],
        *,
        messages: Mapping[str, str] | None = None,
        attributes: Mapping[str, str] | None = None,
    ) -> None:
        self._data = dict(data)
        self._schema = _schema(rules)
        self._messages = dict(messages or {})
        self._attributes = dict(attributes or {})
        self._model: BaseModel | None = None
        self._errors: dict[str, list[str]] | None = None

    def passes(self) -> bool:
        """Run validation, returning whether the payload is valid."""
        return not self.fails()

    def fails(self) -> bool:
        """Run validation, returning whether the payload is invalid."""
        self._run()
        return bool(self._errors)

    def errors(self) -> dict[str, list[str]]:
        """Return field → messages, empty when the payload is valid."""
        self._run()
        return dict(self._errors or {})

    def validated(self) -> dict[str, Any]:
        """Return the validated payload, raising ``ValidationException`` if invalid."""
        self._run()
        if self._errors:
            raise ValidationException(dict(self._errors))
        assert self._model is not None
        return self._model.model_dump()

    # Laravel spells the raising form ``validate()``.
    validate = validated

    def _run(self) -> None:
        if self._model is not None or self._errors is not None:
            return
        try:
            self._model = self._schema.model_validate(self._data)
        except ValidationError as exc:
            self._errors = translate(exc, messages=self._messages, attributes=self._attributes)
        else:
            self._errors = {}


def _schema(rules: type[BaseModel | FormRequest]) -> type[BaseModel]:
    if isinstance(rules, type) and issubclass(rules, BaseModel):
        return rules
    if isinstance(rules, type) and issubclass(rules, FormRequest):
        return rules.__schema__
    raise TypeError("Rules must be a Pydantic model or a FormRequest subclass.")


def validator(
    data: Mapping[str, Any],
    rules: type[BaseModel | FormRequest],
    *,
    messages: Mapping[str, str] | None = None,
    attributes: Mapping[str, str] | None = None,
) -> Validator:
    """Validate ``data`` against ``rules`` (Laravel ``validator``)."""
    return Validator(data, rules, messages=messages, attributes=attributes)


__all__ = ["Validator", "validator"]
