"""UpdateAuthorRequest."""

from __future__ import annotations

from almasix.validation import Field, FormRequest


class UpdateAuthorRequest(FormRequest):
    """UpdateAuthorRequest."""

    name: str = Field(min_length=1)

    def authorize(self) -> bool:
        return True

    def messages(self) -> dict[str, str]:
        return {}
