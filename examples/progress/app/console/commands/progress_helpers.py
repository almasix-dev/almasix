"""Demo Support helpers + Str in the living example (M14, M50)."""

from __future__ import annotations

from almasix.console.command import Command
from almasix.framework import app
from almasix.log import Log
from almasix.support import Arr, Number, Str, blank, data_get, str_


class ProgressHelpersCommand(Command):
    signature = "progress:helpers"
    description = "Demo Arr / Str / Number helpers and the global helpers (M14, M50)"

    def handle(self) -> int:
        payload = {"user": {"name": "Ada", "roles": ["admin", "editor"]}}
        self.info(f"data path → {Arr.get(payload, 'user.name')}")
        self.info(f"slug → {Str.slug('Hello Almasix Framework')}")
        self.info(f"fluent → {str_('foo_bar').camel()}")
        self.info(f"ordinal → {Number.ordinal(3)}")
        self.info(f"blank('') → {blank('')}")
        self.line(Str.of("m14").upper().prepend("SHIPPED ").to_string())

        self.new_line()
        self.comment("M50 — the fluent surface, the gaps, and the global helpers")

        # Stringable delegates every Str method and never alters its subject.
        subject = str_("  almasix framework  ")
        self.info(f"chained → {subject.trim().headline().append('!')}")
        self.info(f"unchanged → {subject!r}")
        self.info(f"initials → {Str.initials('Ada Lovelace')}")

        # A wildcard fans out over every entry at that level.
        orders = {"orders": [{"total": 30}, {"total": 12}]}
        self.info(f"wildcard → {data_get(orders, 'orders.*.total')}")

        # Arr and Number reach what Laravel documents.
        approved, pending = Arr.partition([1, 2, 3, 4], lambda value: value % 2 == 0)
        self.info(f"partition → {approved} / {pending}")
        self.info(f"sole → {Arr.sole([7], lambda value: value > 1)}")
        self.info(f"spelled ordinal → {Number.spell_ordinal(3)}")

        # The global helpers wrap what the container already holds.
        self.info(f"app() → {app().base_path.name}")
        Log.info("progress:helpers ran", extra={"milestone": "M50"})
        Log.debug("helpers detail")
        Log.success("helpers logged")

        self.success("helpers demo ok")
        return 0
