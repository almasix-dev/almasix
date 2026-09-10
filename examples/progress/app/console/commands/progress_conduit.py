"""Demo almasix.conduit reactive components (M54)."""

from __future__ import annotations

from almasix.conduit import Conduit, conduit
from almasix.conduit.parity import PARITY, parity_summary
from almasix.console.command import Command
from almasix.prism.helpers import render


class ProgressConduitCommand(Command):
    signature = "progress:conduit"
    description = "Demo almasix.conduit components, wire protocol, and LW4 parity (M54)"

    def handle(self) -> int:
        from app.conduit.counter import Counter, NestedShell

        Conduit.register("counter", Counter)
        Conduit.register("nested-shell", NestedShell)

        html = conduit("counter")
        self.info(f"embed counter → {len(html)} bytes")
        assert "wire:id=" in html and "wire:initial-data=" in html
        assert "data-conduit" in html or "Progress Conduit" in html or "conduit-counter" in html

        from almasix.conduit.mechanism import checksum, hydrate_from_snapshot, render_html, snapshot

        component = Conduit.component("counter")
        component.conduit_id = "test-id"
        component.mount()
        snap = snapshot(component)
        assert snap["serverMemo"]["checksum"] == checksum(
            {
                "data": snap["serverMemo"]["data"],
                "name": "counter",
                "id": "test-id",
            }
        )

        hydrated = hydrate_from_snapshot("counter", snap["serverMemo"], snap["fingerprint"])
        hydrated.call("increment")
        assert hydrated.count == 1
        body = render_html(hydrated)
        assert "1" in body

        nested_html = conduit("nested-shell")
        assert "wire:id=" in nested_html
        self.info(f"nested shell → {len(nested_html)} bytes")

        summary = parity_summary()
        self.info(
            f"LW4 parity → {summary['complete']} complete, "
            f"{summary['partial']} partial, {summary['planned']} planned "
            f"({len(PARITY)} rows)"
        )
        assert summary["complete"] == len(PARITY)
        assert summary["partial"] == 0 and summary["planned"] == 0

        from almasix.conduit.signing import public_signed_update_url, verify_update_request_url
        from almasix.routing.signing import has_valid_signature

        signed = public_signed_update_url()
        assert "signature=" in signed
        internal = "/conduit/update?" + signed.split("?", 1)[1] if "?" in signed else signed
        assert has_valid_signature(internal, absolute=False)
        self.info("signed update URL ok")

        uris = {route.uri for route in self.app.router.routes}
        assert "/conduit/update" in uris, "Conduit provider should register POST /conduit/update"
        assert "/conduit/conduit.js" in uris
        self.info("routes /conduit/update + /conduit/conduit.js ok")

        page = render(
            "conduit.demo",
            {"counter_html": html, "csrf_token": "demo-token"},
        )
        assert "almasix.conduit" in page
        self.info("conduit.demo page renders")

        self.success("conduit ok")
        return 0
