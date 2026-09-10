"""Web routes — browser facing, stateful, HTML responses."""

from app.http.controllers.auth_controller import AuthController
from app.http.controllers.progress_controller import ProgressController
from app.http.controllers.showcase_controller import ShowcaseController
from app.http.controllers.verification_controller import VerificationController
from app.http.controllers.welcome_controller import WelcomeController

from almasix.routing import Route

with Route.group(middleware=["web"]):
    Route.get("/", [WelcomeController, "index"])
    Route.get("/progress", [ProgressController, "index"])
    Route.get("/conduit", [ProgressController, "conduit_demo"])
    Route.get("/flux", [ProgressController, "conduit_demo"])  # rename alias
    Route.get("/inertia", [ProgressController, "inertia_demo"])
    Route.get("/showcase", [ShowcaseController, "index"])
    Route.get("/boom", [WelcomeController, "boom"])
    Route.get("/dd", [WelcomeController, "dump_demo"])
    Route.get("/login", [AuthController, "show_login"], middleware=["guest"])
    Route.post("/login", [AuthController, "login"], middleware=["guest"])
    Route.post("/logout", [AuthController, "logout"], middleware=["auth"])
    Route.get("/logout", [AuthController, "logout"], middleware=["auth"])
    Route.get("/confirm-password", [AuthController, "show_confirm"], middleware=["auth"])
    Route.post("/confirm-password", [AuthController, "confirm"], middleware=["auth"])
    Route.get("/email/verify", [VerificationController, "notice"], middleware=["auth"])
    Route.get("/email/verify/{id}/{hash}", [VerificationController, "verify"])
    Route.post(
        "/email/verification-notification",
        [VerificationController, "resend"],
        middleware=["auth"],
    )
    Route.get(
        "/settings",
        [WelcomeController, "settings"],
        middleware=["auth", "password.confirm", "verified"],
    )
