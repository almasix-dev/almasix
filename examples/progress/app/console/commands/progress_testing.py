"""Demo the testing toolkit — client, assertions, fakes, time travel (M28)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from almasix.console.command import Command
from almasix.mail import Mail
from almasix.queue import dispatch
from almasix.support.helpers import now
from almasix.testing import (
    TestClient,
    artisan,
    assert_database_has,
    boot_application,
    database_transactions,
    fake,
    fakeable,
    frozen_time,
    restore_fakes,
)
from app.console.commands.progress_demo import ProgressDigestJob, WelcomeMail
from app.models.user import User
from app.support.demo_db import ensure_demo_database


class ProgressTestingCommand(Command):
    signature = "progress:testing"
    description = "Demo the testing toolkit — HTTP, console, database, fakes (M28)"

    def handle(self) -> int:
        return asyncio.run(self.demonstrate())

    async def demonstrate(self) -> int:
        await ensure_demo_database()
        client = TestClient(boot_application(self.app.base_path))

        # The request goes through the real router, middleware and views.
        page = await client.get("/progress")
        page.assert_ok().assert_see("Milestones").assert_view_is("progress")
        self.info("http -> GET /progress rendered the [progress] view")

        health = await client.get_json("/api/health")
        health.assert_ok().assert_json({"status": "ok"}).assert_json_path("status", "ok")
        self.info("json -> /api/health answered {'status': 'ok'}")

        missing = await client.get("/nowhere")
        missing.assert_not_found()
        self.info(f"status -> a route that does not exist answered {missing.status}")

        # A session and a signed-in user, without going through the login form.
        ada = await User.query().order_by("id").first()
        signed_in = await client.acting_as(ada).with_session({"tour": "m28"}).get("/progress")
        signed_in.assert_ok().assert_session_has("tour", "m28")
        self.info(f"acting_as -> signed in as {ada.email} for one request")

        # Console commands run for real; only the terminal is a fake.
        listed = artisan("progress:hello", {"name": "Toolkit"}).assert_successful()
        listed.assert_output_contains("Hello, Toolkit")
        self.info("console -> progress:hello greeted the test and exited 0")

        # Writes inside a transaction never outlive the block.
        async with database_transactions():
            await User.create({"email": "temporary@example.com", "name": "Temporary"})
            await assert_database_has("users", {"email": "temporary@example.com"})
        after = await User.query().where("email", "temporary@example.com").count()
        self.info(f"database -> the transaction rolled back, {after} row(s) left behind")

        # Every façade fakes the same way, through one door.
        self.info(f"fakes -> {', '.join(fakeable())}")
        queue, mail = fake("queue"), fake("mail")
        await dispatch(ProgressDigestJob("from the test"))
        Mail.to(ada.email).send(WelcomeMail(ada.name))
        queue.assert_pushed(ProgressDigestJob)
        mail.assert_queued(WelcomeMail)
        self.info(
            f"fake -> queue held {len(queue.recorded())} job(s), "
            f"mail caught {len(mail.queued())} message(s), and neither went anywhere"
        )
        restore_fakes()

        with frozen_time(datetime(2030, 1, 1, tzinfo=UTC)):
            self.info(f"travel -> the clock reads {now():%Y-%m-%d} inside the block")
        self.info(f"travel -> and {now():%Y-%m-%d} outside it")

        self.success("testing demo ok")
        return 0
