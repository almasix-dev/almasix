"""Demo Prism language support — formatter + grammar assets (M45)."""

from __future__ import annotations

from almasix.console.command import Command
from almasix.prism.formatter import format_prism

_SAMPLE = """
<div>
@if(user)
<ul>
@foreach(items as item)
<li>{{ item }}</li>
@endforeach
</ul>
@else
<p>empty</p>
@endif
@python
x = 1
  y = 2
@endpython
</div>
""".strip()


class ProgressPrismLangCommand(Command):
    signature = "progress:prism-lang"
    description = "Demo Prism formatter and language assets (M45)"

    def handle(self) -> int:
        self.info("Prism language — format_prism")
        once = format_prism(_SAMPLE)
        twice = format_prism(once)
        assert once == twice, "formatter must be idempotent"
        assert "@python" in once and "  y = 2" in once
        self.line("  idempotent -> yes")
        self.line("  @python body preserved -> yes")
        self.line("  smith prism:format --check available")
        self.info("prism lang ok")
        return self.SUCCESS
