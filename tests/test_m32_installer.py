"""M32 — the installer: stub tree, stacks, databases, prompts, and the steps after.

`almasix new` used to take a name and a path. These tests hold the surface it
takes now: a stack, a database, a test suite, a git repository, dependency and
asset installs, and migrations — each with a flag, each with a default.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest
from typer.testing import CliRunner

from almasix.installer.cli import app as almasix_app
from almasix.installer.options import Answers, InstallPlan, Prompter, resolve_plan
from almasix.installer.scaffold import (
    DATABASE_NAMES,
    DEFAULT_MIGRATIONS,
    STACK_NAMES,
    ScaffoldError,
    database_env,
    find_database,
    find_stack,
    publish_scaffold_stubs,
    scaffold_app,
    sql_connection_name,
    title_case,
    validate_app_name,
)
from almasix.installer.steps import StepResult, run_steps

runner = CliRunner()


# -- the stub tree -----------------------------------------------------------


def test_every_stack_scaffolds_a_tree_with_its_own_frontend(tmp_path: Path) -> None:
    for stack in STACK_NAMES:
        root = scaffold_app(f"demo_{stack}", destination=tmp_path / stack, stack=stack)

        assert (root / "bootstrap" / "app.py").is_file()
        assert (root / "resources" / "views" / "welcome.prism.html").is_file()
        assert (root / "app" / "models" / "user.py").is_file()
        assert (root / "database" / "factories" / "user_factory.py").is_file()

        if find_stack(stack).node:
            assert (root / "package.json").is_file()
            assert (root / "vite.config.js").is_file()
            # The hot-file plugin is what makes @vite point at the dev server.
            assert (root / "vite-plugin-almasix.js").is_file()
        else:
            assert not (root / "package.json").exists()
            assert (root / "public" / "css" / "app.css").is_file()


def test_the_stack_picks_the_error_view_bundle(tmp_path: Path) -> None:
    tailwind = scaffold_app("tw", destination=tmp_path / "tw", stack="tailwind")
    plain = scaffold_app("pl", destination=tmp_path / "pl", stack="plain")
    none = scaffold_app("nn", destination=tmp_path / "nn", stack="none")

    tw_error = (tailwind / "resources" / "views" / "errors" / "404.prism.html").read_text()
    plain_error = (plain / "resources" / "views" / "errors" / "404.prism.html").read_text()
    none_error = (none / "resources" / "views" / "errors" / "404.prism.html").read_text()

    assert "@extends('layouts.minimal')" in tw_error
    assert "text-brand" in tw_error
    assert "@extends('layouts.minimal')" in plain_error
    assert "@extends('layouts.minimal')" in none_error
    assert (tailwind / "resources" / "views" / "layouts" / "minimal.prism.html").is_file()
    assert (tailwind / "resources" / "views" / "auth" / "login.prism.html").is_file()
    login = (tailwind / "resources" / "views" / "auth" / "login.prism.html").read_text()
    register = (tailwind / "resources" / "views" / "auth" / "register.prism.html").read_text()
    assert "form_action" in login and "form_action" in register
    auth = (tailwind / "app" / "http" / "controllers" / "auth_controller.py").read_text()
    assert '"form_action"' in auth
    welcome = (tailwind / "resources" / "views" / "welcome.prism.html").read_text()
    assert "Build something remarkable" in welcome
    assert "Welcome to Almasix" not in welcome


def test_readme_and_env_carry_the_chosen_database(tmp_path: Path) -> None:
    root = scaffold_app("shop", destination=tmp_path / "shop", database="pgsql")

    env = (root / ".env").read_text(encoding="utf-8")
    assert "DB_CONNECTION=pgsql" in env
    assert "DB_DATABASE=shop" in env
    assert "DB_PORT=5432" in env
    assert 'env("DB_CONNECTION", "pgsql")' in (root / "config" / "database.py").read_text()
    assert "**PostgreSQL**" in (root / "README.md").read_text(encoding="utf-8")
    # No SQLite file when nothing is going to open one.
    assert not (root / "database" / "database.sqlite").exists()


def test_sqlite_gets_its_file_created(tmp_path: Path) -> None:
    root = scaffold_app("blog", destination=tmp_path / "blog")

    assert (root / "database" / "database.sqlite").is_file()
    assert "DB_DATABASE=database/database.sqlite" in (root / ".env").read_text()


def test_mongodb_configures_documents_and_keeps_sqlite(tmp_path: Path) -> None:
    root = scaffold_app("docs_app", destination=tmp_path / "docs_app", database="mongodb")

    env = (root / ".env").read_text(encoding="utf-8")
    assert "DB_CONNECTION=sqlite" in env
    assert "DB_DATABASE=database/database.sqlite" in env
    assert "MONGODB_HOST=127.0.0.1" in env
    assert "MONGODB_PORT=27017" in env
    assert "MONGODB_DATABASE=docs_app" in env
    assert (root / "database" / "database.sqlite").is_file()
    assert 'env("DB_CONNECTION", "sqlite")' in (root / "config" / "database.py").read_text()
    assert find_database("mongodb").extra == "almasix[mongodb]"


def test_the_app_key_is_generated_not_a_placeholder(tmp_path: Path) -> None:
    first = scaffold_app("one", destination=tmp_path / "one")
    second = scaffold_app("two", destination=tmp_path / "two")

    def key(root: Path) -> str:
        line = next(
            row for row in (root / ".env").read_text().splitlines() if row.startswith("APP_KEY=")
        )
        return line.split("=", 1)[1]

    assert key(first).startswith("base64:")
    assert "change-me" not in key(first)
    assert key(first) != key(second)


def test_env_and_example_are_written_from_one_stub(tmp_path: Path) -> None:
    root = scaffold_app("twins", destination=tmp_path / "twins")

    assert (root / ".env").read_text() == (root / ".env.example").read_text()
    assert (root / ".gitignore").read_text().startswith("__pycache__/")


def test_the_default_migrations_ship_and_the_gitkeep_goes(tmp_path: Path) -> None:
    root = scaffold_app("tables", destination=tmp_path / "tables")
    directory = root / "database" / "migrations"

    for filename, _stub, class_name in DEFAULT_MIGRATIONS:
        body = (directory / filename).read_text(encoding="utf-8")
        assert f"class {class_name}(Migration)" in body
    assert not (directory / ".gitkeep").exists()

    users = (directory / DEFAULT_MIGRATIONS[0][0]).read_text()
    for table in ("users", "password_reset_tokens", "sessions"):
        assert f'Schema.create("{table}"' in users


def test_no_tests_flag_leaves_the_suite_out(tmp_path: Path) -> None:
    root = scaffold_app("bare", destination=tmp_path / "bare", tests=False)

    assert not (root / "tests").exists()
    assert (root / "pyproject.toml").is_file()


def test_scaffolding_from_published_stubs(tmp_path: Path) -> None:
    target, count = publish_scaffold_stubs(tmp_path / "team")

    assert count > 0
    assert (target / "app" / "bootstrap" / "app.py.stub").is_file()

    (target / "app" / "routes" / "web.py.stub").write_text(
        "# {{ app_display }} owns this file\n", encoding="utf-8"
    )
    root = scaffold_app("forked", destination=tmp_path / "forked", stubs=target)

    assert (root / "routes" / "web.py").read_text() == "# Forked owns this file\n"

    # Publishing twice writes nothing new unless forced.
    _, again = publish_scaffold_stubs(tmp_path / "team")
    assert again == 0
    _, forced = publish_scaffold_stubs(tmp_path / "team", force=True)
    assert forced == count


def test_publishing_scaffold_stubs_through_the_command(tmp_path: Path, monkeypatch) -> None:
    from almasix.console.kernel import ConsoleKernel

    monkeypatch.chdir(tmp_path)
    kernel = ConsoleKernel.for_cwd(tmp_path)
    kernel.discover_framework_commands()

    assert kernel.run_argv("stub:publish", ["--scaffold"]) == 0
    assert (tmp_path / "stubs" / "scaffold" / "app" / "pyproject.toml.stub").is_file()
    assert (tmp_path / "stubs" / "controller.stub").is_file()
    # Second run has nothing to add and says so rather than failing.
    assert kernel.run_argv("stub:publish", ["--scaffold"]) == 0


def test_a_stub_tree_may_hold_only_the_files_it_wants_to_change(tmp_path: Path) -> None:
    # A team that keeps a tree for one stack should not have to carry a
    # directory for the three it does not use, and a tree it wrote by hand has
    # no `.gitkeep` for the migrations to remove.
    tree = tmp_path / "minimal"
    (tree / "app").mkdir(parents=True)
    (tree / "app" / "routes").mkdir()
    (tree / "app" / "routes" / "web.py.stub").write_text("# {{ app_name }}\n", encoding="utf-8")

    root = scaffold_app("minimal", destination=tmp_path / "app", stubs=tree)

    assert (root / "routes" / "web.py").read_text() == "# minimal\n"
    assert not (root / "database" / "migrations" / ".gitkeep").exists()
    assert (root / "database" / "migrations" / "0001_01_01_000000_create_users_table.py").is_file()


def test_bad_input_is_refused_by_name(tmp_path: Path) -> None:
    with pytest.raises(ScaffoldError, match="Invalid app name"):
        validate_app_name("9bad")
    with pytest.raises(ScaffoldError, match="Unknown stack"):
        scaffold_app("x", destination=tmp_path / "x", stack="nextjs")
    with pytest.raises(ScaffoldError, match="Unknown database"):
        scaffold_app("y", destination=tmp_path / "y", database="cassandra")
    with pytest.raises(ScaffoldError, match="No scaffold stubs"):
        scaffold_app("z", destination=tmp_path / "z", stubs=tmp_path / "empty")

    scaffold_app("taken", destination=tmp_path / "taken")
    with pytest.raises(ScaffoldError, match="not empty"):
        scaffold_app("taken", destination=tmp_path / "taken")


def test_names_and_labels() -> None:
    assert title_case("my-shiny_app") == "MyShinyApp"
    assert find_database("mariadb").label == "MariaDB"
    assert "DB_DATABASE=shop" in database_env(find_database("mysql"), app_name="shop")
    assert set(DATABASE_NAMES) == {"sqlite", "pgsql", "mysql", "mariadb", "mongodb"}
    mongo = find_database("mongodb")
    assert mongo.extra == "almasix[mongodb]"
    assert sql_connection_name(mongo) == "sqlite"
    assert "MONGODB_DATABASE=shop" in database_env(mongo, app_name="shop")


# -- the questions -----------------------------------------------------------


class ScriptedPrompter(Prompter):
    """Answers the installer's questions from a script, and records them."""

    def __init__(self, selects: dict[str, str], confirms: dict[str, bool]) -> None:
        self.selects = selects
        self.confirms = confirms
        self.asked: list[str] = []

    def select(self, label: str, options: Sequence[tuple[str, str]], default: str) -> str:
        self.asked.append(label)
        return self.selects.get(label, default)

    def confirm(self, label: str, *, default: bool, hint: str = "") -> bool:
        self.asked.append(label)
        return self.confirms.get(label, default)


def test_the_real_prompter_asks_through_the_console_prompts(monkeypatch) -> None:
    from almasix.console import prompts

    monkeypatch.setattr(prompts, "select", lambda label, options, default: min(options))
    monkeypatch.setattr(prompts, "confirm", lambda label, default, hint="": not default)

    prompter = Prompter()

    assert prompter.select("Stack?", [("tailwind", "Tailwind"), ("none", "None")], "tailwind") == (
        "none"
    )
    assert prompter.confirm("Git?", default=False, hint="git init") is True


def test_no_interaction_takes_the_documented_defaults(tmp_path: Path) -> None:
    prompter = ScriptedPrompter({}, {})
    plan = resolve_plan(
        "demo",
        tmp_path / "demo",
        Answers(),
        interactive=False,
        prompter=prompter,
        node_available=lambda: True,
    )

    assert prompter.asked == []
    assert plan.kit == "none"
    assert (plan.stack, plan.database) == ("tailwind", "sqlite")
    assert plan.tests is True
    assert (plan.git, plan.install, plan.migrate) == (False, False, False)
    assert plan.npm is True
    assert plan.asked == []


def test_a_flag_is_never_asked_about(tmp_path: Path) -> None:
    prompter = ScriptedPrompter({}, {})
    plan = resolve_plan(
        "demo",
        tmp_path / "demo",
        Answers(
            kit="none",
            stack="bootstrap",
            database="mysql",
            tests=False,
            git=True,
            install=False,
            npm=True,
            migrate=True,
        ),
        prompter=prompter,
        node_available=lambda: True,
    )

    assert prompter.asked == []
    assert (plan.stack, plan.database) == ("bootstrap", "mysql")
    assert plan.tests is False
    assert plan.git is True
    assert plan.npm is True
    # --migrate stands even without --install; the flag was explicit.
    assert plan.migrate is True


def test_the_prompts_decide_what_the_flags_did_not(tmp_path: Path) -> None:
    prompter = ScriptedPrompter(
        {
            "Which starter kit?": "none",
            "Which frontend stack?": "plain",
            "Which database will this application use?": "pgsql",
        },
        {
            "Scaffold a pytest suite (tests/)?": True,
            "Initialize a git repository?": True,
            "Create a .venv and install Python dependencies?": True,
            "Run npm install and npm run build?": True,
            "Run the default migrations?": True,
        },
    )
    plan = resolve_plan(
        "demo",
        tmp_path / "demo",
        Answers(),
        prompter=prompter,
        node_available=lambda: True,
    )

    assert plan.kit == "none"
    assert plan.stack == "plain"
    assert plan.database == "pgsql"
    assert plan.git is True
    assert plan.install is True
    assert plan.npm is True
    assert plan.migrate is True
    assert plan.asked == ["kit", "stack", "database", "tests", "git", "install", "npm", "migrate"]


def test_npm_is_not_asked_about_without_node_or_without_a_stack(tmp_path: Path) -> None:
    prompter = ScriptedPrompter({}, {"Run npm install and npm run build?": True})

    no_node = resolve_plan(
        "demo",
        tmp_path / "demo",
        Answers(stack="tailwind", npm=True),
        prompter=prompter,
        node_available=lambda: False,
    )
    assert no_node.npm is False

    no_stack = resolve_plan(
        "demo",
        tmp_path / "demo",
        Answers(stack="none"),
        prompter=prompter,
        node_available=lambda: True,
    )
    assert no_stack.npm is False
    assert "npm" not in no_stack.asked


def test_migrating_is_only_offered_once_dependencies_are_installed(tmp_path: Path) -> None:
    prompter = ScriptedPrompter({}, {"Create a .venv and install Python dependencies?": False})
    plan = resolve_plan(
        "demo",
        tmp_path / "demo",
        Answers(stack="none"),
        prompter=prompter,
        node_available=lambda: True,
    )

    assert plan.install is False
    assert plan.migrate is False
    assert "migrate" not in plan.asked


def test_node_detection_reads_the_path(monkeypatch) -> None:
    from almasix.installer import options

    monkeypatch.setattr(options.shutil if hasattr(options, "shutil") else options, "__name__", "x")
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/npm")
    assert options._node_available() is True
    monkeypatch.setattr("shutil.which", lambda _name: None)
    assert options._node_available() is False


# -- the steps after ---------------------------------------------------------


def _plan(tmp_path: Path, **kwargs: object) -> InstallPlan:
    return InstallPlan(name="demo", destination=tmp_path / "demo", **kwargs)  # type: ignore[arg-type]


def test_nothing_runs_when_nothing_was_asked_for(tmp_path: Path) -> None:
    results = run_steps(_plan(tmp_path, npm=False), tmp_path)

    assert [result.name for result in results] == [
        "git",
        "venv",
        "install",
        "storage-link",
        "npm",
        "migrate",
    ]
    assert all(not result.ran for result in results)


def test_git_init_commits_the_tree(tmp_path: Path) -> None:
    root = scaffold_app("gitty", destination=tmp_path / "gitty")
    plan = _plan(tmp_path, git=True, branch="trunk")

    result = run_steps(plan, root)[0]

    if result.ok:
        assert (root / ".git").is_dir()
        head = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert head.stdout.strip() == "trunk"
        # A second run sees a repository and leaves it alone.
        assert run_steps(plan, root)[0].ran is False
    else:  # pragma: no cover - a machine without git or an identity
        assert result.detail


def test_a_step_that_fails_is_reported_not_raised(tmp_path: Path, monkeypatch) -> None:
    from almasix.installer import steps

    monkeypatch.setattr(steps.shutil, "which", lambda _name: None)

    plan = _plan(tmp_path, git=True, install=True, npm=True, installer="uv")
    results = {result.name: result for result in run_steps(plan, tmp_path)}

    assert results["git"].failed and "git is not installed" in results["git"].detail
    assert results["venv"].failed and "uv is not installed" in results["venv"].detail
    assert results["install"].failed
    assert results["npm"].failed and "npm is not installed" in results["npm"].detail


def test_the_installer_prefers_uv_and_falls_back_to_pip(tmp_path: Path, monkeypatch) -> None:
    from almasix.installer import steps

    root = tmp_path / "app"
    root.mkdir()
    # Pretend the venv already exists so install command resolution can run.
    python = steps.venv_python(root)
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("", encoding="utf-8")

    monkeypatch.setattr(steps.shutil, "which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    monkeypatch.setattr(steps, "kit_install_packages", lambda _plan: [])
    command = steps._python_install_command(_plan(tmp_path, install=True), root)
    assert command is not None and command[:2] == ("uv", "pip")
    assert "--python" in command and "-e" in command and "." in command

    monkeypatch.setattr(steps.shutil, "which", lambda _name: None)
    command = steps._python_install_command(_plan(tmp_path, install=True), root)
    assert command is not None and command[1:4] == ("-m", "pip", "install")
    assert "-e" in command and "." in command
    assert steps._python_install_command(_plan(tmp_path, installer="poetry"), root) is None


def test_spa_kit_install_path_wires_monorepo_framework(tmp_path: Path, monkeypatch) -> None:
    from almasix.installer import steps

    root = tmp_path / "app"
    root.mkdir()
    python = steps.venv_python(root)
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("", encoding="utf-8")

    fw = tmp_path / "framework"
    (fw / "src" / "almasix").mkdir(parents=True)
    (fw / "pyproject.toml").write_text('[project]\nname = "almasix"\n', encoding="utf-8")

    monkeypatch.setattr(steps, "framework_source_root", lambda: fw)
    monkeypatch.setattr(steps.shutil, "which", lambda _name: None)
    command = steps._python_install_command(_plan(tmp_path, install=True, kit="vue"), root)
    assert command is not None
    assert "-e" in command and str(fw) in command
    assert "packages" not in " ".join(command)
    assert command[-2:] == ("-e", ".")


def test_run_streams_subprocess_output_instead_of_capturing(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from almasix.installer import steps

    calls: list[dict] = []

    def fake_subprocess_run(*args, **kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess(args[0], 0, stdout=None, stderr=None)

    monkeypatch.setattr(steps.subprocess, "run", fake_subprocess_run)
    completed = steps._run(("echo", "hello"), tmp_path)

    assert completed.returncode == 0
    assert calls and calls[0].get("capture_output") is False
    assert "$ echo hello" in capsys.readouterr().out

    from almasix.installer import steps

    ran: list[list[str]] = []

    def fake_run(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        ran.append(list(command))
        # Simulate `python -m venv` / `uv venv` leaving an interpreter behind.
        if "venv" in command or (len(command) >= 3 and command[-3:-1] == ["-m", "venv"]):
            python = steps.venv_python(cwd)
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_text("", encoding="utf-8")
        failing = list(command)[:2] == ["npm", "run"]
        return subprocess.CompletedProcess(
            list(command),
            1 if failing else 0,
            stdout="",
            stderr="  \nnpm ERR! build failed\n" if failing else "",
        )

    monkeypatch.setattr(steps, "_run", fake_run)
    monkeypatch.setattr(steps.shutil, "which", lambda _name: "/usr/bin/npm")

    plan = _plan(tmp_path, npm=True, install=True, migrate=True)
    results = {result.name: result for result in run_steps(plan, tmp_path)}

    assert results["venv"].ok
    assert results["install"].ok
    assert results["npm"].failed
    assert results["npm"].detail == "npm ERR! build failed"
    assert results["migrate"].ok
    assert ["npm", "install"] in ran
    assert any(command[-3:] == ["smith", "migrate", "--force"] for command in ran)


def test_a_frontend_that_builds_reports_both_commands(tmp_path: Path, monkeypatch) -> None:
    from almasix.installer import steps

    monkeypatch.setattr(
        steps,
        "_run",
        lambda command, cwd: subprocess.CompletedProcess(list(command), 0, "", ""),
    )
    monkeypatch.setattr(steps.shutil, "which", lambda _name: "/usr/bin/npm")

    result = steps.install_node(_plan(tmp_path, npm=True), tmp_path)

    assert result.ok
    assert result.detail == "npm install && npm run build"


def test_a_migration_failure_names_itself(tmp_path: Path, monkeypatch) -> None:
    from almasix.installer import steps

    def fake_run(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if "venv" in command or (len(command) >= 3 and command[-3:-1] == ["-m", "venv"]):
            python = steps.venv_python(cwd)
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_text("", encoding="utf-8")
            return subprocess.CompletedProcess(list(command), 0, "", "")
        return subprocess.CompletedProcess(list(command), 1, "", "")

    monkeypatch.setattr(steps, "_run", fake_run)

    plan = _plan(tmp_path, migrate=True, git=True, install=True)
    monkeypatch.setattr(steps.shutil, "which", lambda _name: "/usr/bin/git")
    results = {result.name: result for result in run_steps(plan, tmp_path)}

    assert "failed" in results["git"].detail
    assert results["venv"].ok
    assert "dependency install failed" in results["install"].detail
    assert "smith migrate failed" in results["migrate"].detail


def test_step_result_reads_as_a_sentence() -> None:
    assert StepResult("npm", ran=True).failed is False
    assert StepResult("npm", ran=True, ok=False).failed is True
    assert StepResult("npm", ran=False, ok=False).failed is False


def test_create_venv_and_editable_install_use_the_app_venv(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from almasix.installer import steps

    root = tmp_path / "fresh"
    root.mkdir()
    ran: list[list[str]] = []

    def fake_run(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        ran.append(list(command))
        if "venv" in command or (len(command) >= 3 and command[-3:-1] == ["-m", "venv"]):
            python = steps.venv_python(cwd)
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(list(command), 0, "", "")

    monkeypatch.setattr(steps, "_run", fake_run)
    monkeypatch.setattr(steps.shutil, "which", lambda _name: None)

    plan = _plan(tmp_path, install=True, migrate=True, database="pgsql")
    results = {result.name: result for result in run_steps(plan, root)}

    assert results["venv"].ok
    assert results["install"].ok
    assert any("-m" in cmd and "venv" in cmd for cmd in ran)
    install_cmd = next(cmd for cmd in ran if "pip" in cmd and "-e" in cmd)
    assert str(steps.venv_python(root)) in install_cmd
    assert "almasix[pgsql]" in install_cmd
    migrate_cmd = next(cmd for cmd in ran if "migrate" in cmd)
    assert migrate_cmd[0] == str(steps.venv_python(root))


def test_scaffolded_apps_include_the_users_migration(tmp_path: Path) -> None:
    root = scaffold_app("auth_tables", destination=tmp_path / "auth_tables")
    users = root / "database" / "migrations" / "0001_01_01_000000_create_users_table.py"
    body = users.read_text(encoding="utf-8")
    assert 'Schema.create("users"' in body
    assert 'Schema.create("password_reset_tokens"' in body
    assert 'Schema.create("sessions"' in body


# -- the command line --------------------------------------------------------


def test_new_reports_the_stack_the_database_and_what_is_left_to_do(tmp_path: Path) -> None:
    result = runner.invoke(
        almasix_app,
        ["new", "cli_demo", "--path", str(tmp_path), "--no-interaction", "--stack", "bootstrap"],
    )

    assert result.exit_code == 0, result.stdout
    assert "Created Almasix application" in result.stdout
    assert "Bootstrap" in result.stdout
    assert "SQLite" in result.stdout
    assert "cd cli_demo" in result.stdout
    assert "python smith migrate" in result.stdout
    assert "npm install && npm run build" in result.stdout


def test_new_with_no_frontend_says_nothing_about_npm(tmp_path: Path) -> None:
    result = runner.invoke(
        almasix_app,
        ["new", "quiet", "--path", str(tmp_path), "-n", "--stack", "none", "--no-tests"],
    )

    assert result.exit_code == 0, result.stdout
    assert "npm" not in result.stdout
    assert not (tmp_path / "quiet" / "tests").exists()


def test_new_names_a_non_sqlite_extra_in_the_next_steps(tmp_path: Path) -> None:
    result = runner.invoke(
        almasix_app,
        ["new", "pg_demo", "--path", str(tmp_path), "-n", "--database", "pgsql"],
    )

    assert result.exit_code == 0, result.stdout
    assert "almasix[pgsql]" in result.stdout


def test_new_exits_non_zero_when_a_step_failed(tmp_path: Path, monkeypatch) -> None:
    from almasix.installer import steps

    monkeypatch.setattr(steps.shutil, "which", lambda _name: None)
    result = runner.invoke(
        almasix_app,
        ["new", "broken", "--path", str(tmp_path), "-n", "--git"],
    )

    assert result.exit_code == 1
    assert "git is not installed" in result.stderr


def test_new_refuses_an_unknown_stack(tmp_path: Path) -> None:
    result = runner.invoke(
        almasix_app,
        ["new", "nope", "--path", str(tmp_path), "-n", "--stack", "svelte"],
    )

    assert result.exit_code == 1
    assert "Unknown stack" in result.stderr


def test_new_lists_only_the_steps_still_owed(tmp_path: Path, monkeypatch) -> None:
    from almasix.installer import cli as installer_cli

    monkeypatch.setattr(
        installer_cli,
        "run_steps",
        lambda plan, root: [
            StepResult("install", ran=True, detail="uv pip install -e ."),
            StepResult("npm", ran=True, detail="npm install && npm run build"),
            StepResult("migrate", ran=True, detail="smith migrate --force"),
        ],
    )

    result = runner.invoke(
        almasix_app,
        ["new", "done", "--path", str(tmp_path), "-n", "--install", "--npm", "--migrate"],
    )

    assert result.exit_code == 0
    assert "install   uv pip install -e ." in result.stdout
    for owed in ("pip install -e .", "python smith migrate", "npm install"):
        assert owed not in result.stdout.split("Next steps")[-1], owed
    assert "python smith serve" in result.stdout


def test_without_a_terminal_new_takes_the_non_interactive_defaults(
    tmp_path: Path, monkeypatch
) -> None:
    # A prompt's displayed default is not the documented one: `--install` shows
    # Yes for someone at a keyboard, and No for a script. A pipeline that ran
    # `almasix new` and got a pip install it never asked for is the bug.
    from almasix.installer import cli as installer_cli

    seen: list[InstallPlan] = []

    def spy(plan: InstallPlan, root: Path) -> list[StepResult]:
        seen.append(plan)
        return []

    monkeypatch.setattr(installer_cli, "run_steps", spy)
    monkeypatch.setattr("almasix.console.prompts.types.sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("almasix.installer.options._node_available", lambda: True)
    result = runner.invoke(almasix_app, ["new", "quiet", "--path", str(tmp_path)])

    assert result.exit_code == 0, result.stdout
    plan = seen[0]
    assert (plan.install, plan.migrate, plan.git) == (False, False, False)
    assert plan.npm is True
    assert plan.asked == []


def test_version_prints_the_framework_version() -> None:
    from almasix import __version__

    result = runner.invoke(almasix_app, ["version"])

    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_stacks_lists_what_new_accepts() -> None:
    result = runner.invoke(almasix_app, ["stacks"])

    assert result.exit_code == 0
    for name in STACK_NAMES:
        assert name in result.stdout
    assert "almasix[pgsql]" in result.stdout
