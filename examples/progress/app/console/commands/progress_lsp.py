"""Demo Almasix language server index against this app (M46)."""

from __future__ import annotations

from almasix.console.command import Command
from almasix.lsp import build_index
from almasix.lsp.features import completions, definition


class ProgressLspCommand(Command):
    signature = "progress:lsp"
    description = "Demo almasix-lsp application index (M46)"

    def handle(self) -> int:
        self.info("Language server — build_index")
        index = build_index(self.app.base_path)
        if index.error:
            self.error(index.error)
            return self.FAILURE
        self.line(f"  views  -> {len(index.views)}")
        self.line(f"  routes -> {len(index.routes)}")
        self.line(f"  config -> {len(index.config_keys)}")
        self.line(f"  models -> {len(index.models)}")
        self.line(f"  middleware -> {len(index.middleware_aliases)}")
        self.line(f"  translations -> {len(index.translation_keys)}")
        data_keys = sum(len(keys) for keys in index.view_data.values())
        self.line(f"  view-vars -> {data_keys} data keys / {len(index.view_helpers)} helpers")
        self.line(f"  vite    -> {len(index.vite_entries)} entries")

        # Prove template variable intelligence against welcome's app_name.
        template = self.app.base_path / "resources" / "views" / "welcome.prism.html"
        source = '<h1>{{ app_name }}</h1>\n{{ route("x") }}'
        char = source.index("app_name") + 1
        items = completions(
            index,
            source,
            0,
            char,
            language="prism-html",
            uri_path=template if template.is_file() else None,
        )
        loc = definition(
            index,
            source,
            0,
            char,
            language="prism-html",
            uri_path=template if template.is_file() else None,
        )
        if not any(i.label == "app_name" for i in items):
            self.error("template var completion for app_name failed")
            return self.FAILURE
        if loc is None or loc.path.name != "welcome_controller.py":
            self.error("template var definition for app_name failed")
            return self.FAILURE
        self.line(
            f"  {{{{ app_name }}}} -> {loc.path.name}:{loc.start_line + 1} (complete + definition)"
        )
        # Helper name → url.py
        url_source = "{{ url }}"
        url_loc = definition(
            index,
            url_source,
            0,
            url_source.index("url") + 1,
            language="prism-html",
            uri_path=template if template.is_file() else None,
        )
        if url_loc is None or url_loc.path.name != "url.py":
            self.error("helper definition for url() failed")
            return self.FAILURE
        self.line("  {{ url }} -> " + f"{url_loc.path.name}:{url_loc.start_line + 1}")

        if not self._show_route_argument_completion(index, template):
            return self.FAILURE
        if not self._show_invoked_completion(index, template):
            return self.FAILURE
        if not self._show_directive_snippet(index):
            return self.FAILURE
        if not self._show_format():
            return self.FAILURE
        if not self._show_env_completion(index):
            return self.FAILURE
        if not self._show_schema_completion(index):
            return self.FAILURE

        self.line("  run: almasix-lsp  |  python -m almasix.lsp  |  smith lsp:serve")
        self.info("lsp ok")
        return self.SUCCESS

    def _show_route_argument_completion(self, index, template) -> bool:
        """``route('')`` offers names before a single character is typed."""
        source = "<a href=\"{{ route('') }}\">go</a>"
        char = source.index("('") + 2
        items = completions(
            index,
            source,
            0,
            char,
            language="prism-html",
            uri_path=template if template.is_file() else None,
        )
        if not items:
            self.error("route('') completion returned nothing")
            return False
        self.line(f"  route('') -> {len(items)} route names, e.g. {items[0].label}")
        return True

    def _show_invoked_completion(self, index, template) -> bool:
        """Ctrl+Space in plain markup still offers directives and globals."""
        source = '<div class="card">\n  \n</div>\n'
        items = completions(
            index,
            source,
            1,
            2,
            language="prism-html",
            uri_path=template if template.is_file() else None,
        )
        labels = {item.label for item in items}
        directives = sum(1 for label in labels if label.startswith("@"))
        if "@if" not in labels or not directives:
            self.error("invoked completion in plain markup returned no directives")
            return False
        self.line(
            f"  ctrl+space -> {len(items)} items ({directives} directives + globals)"
        )
        return True

    def _show_directive_snippet(self, index) -> bool:
        """``@if`` completes as a snippet that keeps ``@`` and closes with ``@endif``."""
        source = "@if"
        items = completions(index, source, 0, 3, language="prism-html")
        match = next((item for item in items if item.label == "@if"), None)
        if match is None or not (match.insert_text or "").startswith("@if"):
            self.error("@if directive snippet missing or stripped the @")
            return False
        if "@endif" not in (match.insert_text or ""):
            self.error("@if snippet did not include @endif")
            return False
        indented = "    @if"
        indented_items = completions(index, indented, 0, 7, language="prism-html")
        indented_match = next((item for item in indented_items if item.label == "@if"), None)
        expected = "@if($1)\n        $0\n    @endif"
        if indented_match is None or indented_match.insert_text != expected:
            self.error("@if snippet did not bake line indent for @endif alignment")
            return False
        self.line("  @if -> snippet keeps @, closes with @endif, aligns under indent")
        return True

    def _show_format(self) -> bool:
        """LSP formatting uses the same format_prism as smith prism:format."""
        from almasix.lsp.features import format_document

        messy = "@if(True)\nx\n@endif\n"
        out = format_document(messy, language="prism-html")
        if out is None or "@if(True)" not in out or "    x" not in out:
            self.error("format_document did not indent Prism body")
            return False
        if format_document("print(1)\n", language="python") is not None:
            self.error("format_document should skip non-Prism files")
            return False
        self.line("  textDocument/formatting -> format_prism (Ctrl+Alt+L / format-on-save)")
        return True

    def _show_env_completion(self, index) -> bool:
        """``env("APP_")`` completes keys declared in ``.env`` / read by config."""
        source = 'name = env("APP_")'
        items = completions(index, source, 0, source.index("APP_") + 4, language="python")
        if not any(item.label == "APP_NAME" for item in items):
            self.error("env() completion for APP_NAME failed")
            return False
        # Interpolation inside a dotenv file must offer the same keys.
        dotenv = "APP_TITLE=${APP_}\n"
        char = dotenv.index("${APP_") + len("${APP_")
        dotenv_items = completions(
            index,
            dotenv,
            0,
            char,
            language="dotenv",
        )
        if not any(item.label == "APP_NAME" for item in dotenv_items):
            self.error("${APP_} completion inside .env failed")
            return False
        self.line(
            f"  env('APP_') -> {len(items)} keys; "
            f"${{APP_}} -> {len(dotenv_items)} keys (e.g. APP_NAME)"
        )
        return True

    def _show_schema_completion(self, index) -> bool:
        """Tables / columns in string args, plus ``user.name`` model attributes."""
        tables = completions(
            index,
            'q = DB.table("")',
            0,
            len('q = DB.table("'),
            language="python",
        )
        users = next((item for item in tables if item.label == "users"), None)
        if users is None:
            self.error("DB.table() completion for users failed")
            return False
        # Insert must replace only the inside of the quotes (never eat the opener).
        if users.insert_text != "users" or users.start_character != len('q = DB.table("'):
            self.error("table completion text edit would corrupt surrounding quotes")
            return False
        columns = completions(
            index,
            'rows = DB.table("posts").where("")',
            0,
            len('rows = DB.table("posts").where("'),
            language="python",
        )
        if not any(item.label == "slug" for item in columns):
            self.error("column completion for posts.slug failed")
            return False
        attrs = completions(
            index,
            "user = await User.find(1)\nprint(user.)\n",
            1,
            len("print(user."),
            language="python",
        )
        labels = {item.label for item in attrs}
        if "email" not in labels or "name" not in labels:
            self.error("user. attribute completion missing email/name")
            return False
        self.line(
            f"  DB.table('') -> {len(tables)} tables (quote-safe); "
            f"posts.where('') -> {len(columns)} columns; "
            f"user. -> {len(attrs)} attrs (e.g. email)"
        )
        return True
