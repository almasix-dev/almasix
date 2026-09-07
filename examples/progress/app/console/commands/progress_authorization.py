"""Demo Gate / Policy (M19)."""

from __future__ import annotations

from typing import Any

from avalon.auth import AuthorizationException, Gate, Policy
from avalon.console.command import Command


class _User:
    def __init__(self, user_id: int, *, admin: bool = False) -> None:
        self.id = user_id
        self.admin = admin

    def get_auth_identifier(self) -> int:
        return self.id


class _Post:
    def __init__(self, user_id: int) -> None:
        self.user_id = user_id


class _PostPolicy(Policy):
    def before(self, user: Any, ability: str) -> bool | None:
        if getattr(user, "admin", False):
            return True
        return None

    def update(self, user: Any, post: _Post) -> bool:
        return user.id == post.user_id


class ProgressAuthorizationCommand(Command):
    signature = "progress:authorization"
    description = "Demo Gate.define / Policy / authorize (M19)"

    def handle(self) -> int:
        Gate.flush()
        Gate.define("view-dashboard", lambda user: user is not None)
        Gate.define("guest-ping", lambda user=None: True)
        Gate.policy(_Post, _PostPolicy)

        author = _User(1)
        stranger = _User(9)
        admin = _User(2, admin=True)
        post = _Post(1)

        assert Gate.for_user(author).allows("update", post)
        assert Gate.for_user(stranger).denies("update", post)
        assert Gate.for_user(admin).allows("update", post)
        assert Gate.for_user(author).allows("view-dashboard")
        assert Gate.for_user(None).allows("guest-ping")
        assert Gate.for_user(None).denies("view-dashboard")

        Gate.for_user(author).authorize("update", post)
        try:
            Gate.for_user(stranger).authorize("update", post)
            raise AssertionError("stranger should be denied")
        except AuthorizationException:
            self.info("stranger denied as expected")

        self.success("authorization demo ok")
        return 0
