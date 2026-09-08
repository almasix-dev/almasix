"""The application answers, end to end (M28)."""

from __future__ import annotations

from almasix.testing import TestCase, fake


class ExampleTest(TestCase):
    """A feature test drives real routes through the real middleware."""

    async def test_the_home_page_answers(self) -> None:
        response = await self.get("/")

        response.assert_ok().assert_see("Almasix")

    async def test_the_health_endpoint_reports_ok(self) -> None:
        response = await self.get_json("/api/health")

        response.assert_ok().assert_json({"status": "ok"})

    async def test_the_board_renders_the_milestones(self) -> None:
        response = await self.get("/progress")

        response.assert_ok().assert_view_is("progress").assert_view_has("milestones")

    async def test_the_board_api_counts_what_is_done(self) -> None:
        response = await self.get_json("/api/progress")

        response.assert_ok().assert_json_structure(["completed", "total", "milestones"])
        response.assert_json_path("total", lambda total: total > 0)

    async def test_a_page_that_is_not_there_is_a_404(self) -> None:
        (await self.get("/nowhere")).assert_not_found()

    async def test_a_queued_job_is_recorded_rather_than_run(self) -> None:
        from app.console.commands.progress_demo import ProgressDigestJob

        from almasix.queue import dispatch

        queue = fake("queue")
        await dispatch(ProgressDigestJob("from a test"))

        queue.assert_pushed(ProgressDigestJob)
