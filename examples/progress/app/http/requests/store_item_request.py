"""Validation for POST /api/items — the M3 FormRequest surface."""

from __future__ import annotations

from almasix.validation import Field, FormRequest


class StoreItemRequest(FormRequest):
    name: str = Field(min_length=2, max_length=40)
    count: int = Field(default=1, ge=1, le=99)
    flag: bool = False
    tags: list[str] = []
    note: str | None = None

    def authorize(self) -> bool:
        # `header()` proxies to the underlying Request.
        return self.header("x-demo-forbid") is None

    def attributes(self) -> dict[str, str]:
        return {"count": "item count"}

    def messages(self) -> dict[str, str]:
        return {"tags.array": "The tags must be a list of strings."}
