"""Register auth / session services and view shares."""

from __future__ import annotations

from avalon.providers.provider import ServiceProvider


class AuthServiceProvider(ServiceProvider):
    """Binds auth helpers and shares CSRF / auth state with Caliburn."""

    def register(self) -> None:
        from avalon.auth.access.facade import Gate
        from avalon.auth.access.gate import Gate as AccessGate
        from avalon.auth.guard import AuthManager

        self.app.container.singleton(AuthManager, lambda _c: AuthManager())

        app = self.app

        def gate_factory(_container):
            def user_resolver():
                from avalon.auth.guard import get_auth

                manager = get_auth()
                return None if manager is None else manager.user()

            instance = AccessGate(container=app.container, user_resolver=user_resolver)
            Gate.set_gate(instance)
            return instance

        app.container.singleton(AccessGate, gate_factory)
        app.container.alias(AccessGate, "gate")

    def boot(self) -> None:
        from avalon.auth.access.facade import Gate
        from avalon.auth.access.gate import Gate as AccessGate

        if self.app.container.bound(AccessGate):
            Gate.set_gate(self.app.make(AccessGate))

        try:
            from avalon.caliburn.helpers import get_engine
            from avalon.session.csrf import csrf_token

            engine = get_engine()
        except Exception:
            return

        def share(context: dict) -> None:
            from avalon import __version__
            from avalon.auth.guard import get_auth
            from avalon.session.store import get_session

            context.setdefault("version", __version__)
            if "csrf_token" not in context:
                context["csrf_token"] = csrf_token()
            manager = get_auth()
            if manager is not None and "auth_user" not in context:
                context["auth_user"] = manager.user()
                context["__authenticated"] = manager.check()
            session = get_session()
            if session is not None:
                for key in ("error", "errors", "status"):
                    if key not in context:
                        context[key] = session.get(key)
            context.setdefault("status", None)
            context.setdefault("error", None)
            context.setdefault("errors", {})
            context.setdefault("auth_user", None)
            context.setdefault("__authenticated", False)

        engine.composer("*", share)
