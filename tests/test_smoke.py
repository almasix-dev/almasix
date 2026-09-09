import tomllib
from pathlib import Path

from almasix import __version__
from almasix.framework import Application, Container


def test_version() -> None:
    assert __version__ == "0.4.0"


def test_version_matches_the_packaged_metadata() -> None:
    """The release tag is checked against pyproject, not against ``__version__``.

    Without this the two can drift and a stale ``__version__`` ships unnoticed.
    """
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    assert tomllib.loads(pyproject.read_text())["project"]["version"] == __version__


def test_container_bind_and_resolve() -> None:
    container = Container()
    container.bind(str, lambda c: "almasix")
    assert container.resolve(str) == "almasix"


def test_container_singleton() -> None:
    container = Container()
    counter = {"n": 0}

    def factory(_c: Container) -> dict:
        counter["n"] += 1
        return counter

    container.singleton("counter", factory)
    assert container.resolve("counter") is container.resolve("counter")
    assert counter["n"] == 1


def test_application_boot_stub() -> None:
    app = Application(base_path=".")
    assert app.is_booted is False
    app.boot()
    assert app.is_booted is True
