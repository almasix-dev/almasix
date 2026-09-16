"""The application answers, end to end."""

from __future__ import annotations

from almasix.testing import TestCase


class ExampleTest(TestCase):
    """A feature test drives real routes through the real middleware."""

    async def test_the_home_page_answers(self) -> None:
        response = await self.get("/")

        response.assert_ok()

    async def test_the_health_endpoint_reports_ok(self) -> None:
        response = await self.get_json("/api/health")

        response.assert_ok().assert_json({"status": "ok"})
