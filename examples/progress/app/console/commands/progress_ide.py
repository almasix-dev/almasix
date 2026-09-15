"""Demo editor integrations — ide:install + ide:stubs + ide:index (M47)."""

from __future__ import annotations

from almasix.console.command import Command
from almasix.ide.index import build_ide_index
from almasix.ide.install import install_editor_config
from almasix.ide.stubs import generate_stubs

_VSCODE_REPO = "https://github.com/almasix-dev/almasix-vscode"
_IDEA_REPO = "https://github.com/almasix-dev/almasix-idea"
_VS_MARKETPLACE = "https://marketplace.visualstudio.com/items?itemName=almasix.almasix"


class ProgressIdeCommand(Command):
    signature = "progress:ide"
    description = "Demo editor install config, stubs, and ide:index (M47)"

    def handle(self) -> int:
        self.info("Editor integrations — ide:install + ide:stubs + ide:index")
        root = self.app.base_path

        install = install_editor_config(root, force=True)
        if not install.ok:
            self.error(install.error or "ide:install failed")
            return self.FAILURE
        for path in install.written:
            try:
                rel = path.relative_to(root)
            except ValueError:
                rel = path
            self.line(f"  install -> {rel}")

        stubs = generate_stubs(root)
        if not stubs.ok:
            self.error(stubs.error or "ide:stubs failed")
            return self.FAILURE
        self.line(f"  stubs   -> {stubs.output_dir.relative_to(root)}")
        self.line(f"  models  -> {len(stubs.model_files)}")
        if stubs.routes_file is not None:
            self.line(f"  routes  -> {stubs.routes_file.relative_to(root)}")

        payload = build_ide_index(root)
        if not payload.get("ok"):
            self.error(payload.get("error") or "ide:index failed")
            return self.FAILURE
        self.line(
            f"  index   -> views={len(payload['views'])} "
            f"routes={len(payload['routes'])} "
            f"config_keys={len(payload['config_keys'])} "
            f"config_locations={len(payload.get('config_locations') or {})} "
            f"env_options={len(payload.get('env_options') or {})} "
            f"rules={len(payload['validation_rules'])} "
            f"cmds={len(payload['smith_commands'])}"
        )
        self.line("  jetbrains -> native Almasix Idea (ide:index; Ctrl-click keys/vars)")

        self.line(f"  almasix-vscode -> {_VSCODE_REPO}")
        self.line(f"  almasix-idea   -> {_IDEA_REPO}")
        self.line(f"  vscode  -> {_VS_MARKETPLACE}")
        self.line("  jetbrains -> Marketplace com.almasix.ide")
        self.line("  docs    -> Editor setup (Starlight) + VS Code ↔ PyCharm parity matrix")
        self.info("ide ok")
        return self.SUCCESS
