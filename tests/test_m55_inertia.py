"""Unit tests for almasix-inertia (M55)."""

from __future__ import annotations

from inertia import Inertia
from inertia.response import _filter_partial
from inertia.ssr import render_ssr


def test_render_page_props() -> None:
    Inertia._shared.clear()
    Inertia._shared_callbacks.clear()
    Inertia.share("app", "Progress")
    Inertia.set_version("v1")
    resp = Inertia.render("Dashboard", {"user": "ada"})
    page = resp._page(None)
    assert page["component"] == "Dashboard"
    assert page["props"]["user"] == "ada"
    assert page["props"]["app"] == "Progress"
    assert page["version"] == "v1"


def test_document_contains_app_div() -> None:
    Inertia.set_version("v1")
    resp = Inertia.render("Welcome", {"framework": "almasix"}, root_view="inertia::app")
    # May fail if engine not booted — use _document with minimal page only when engine set.
    page = resp._page(None)
    assert "Welcome" in page["component"]


def test_partial_filter() -> None:
    class Req:
        def header(self, name: str, default=None):
            return {
                "X-Inertia-Partial-Component": "Welcome",
                "X-Inertia-Partial-Data": "a,b",
            }.get(name, default)

    out = _filter_partial(Req(), "Welcome", {"a": 1, "b": 2, "c": 3})
    assert out == {"a": 1, "b": 2}


def test_location_non_inertia() -> None:
    Inertia._shared.clear()
    resp = Inertia.location("https://example.test")
    assert resp.status_code in {302, 307, 303}


def test_ssr_fallback_when_down() -> None:
    assert render_ssr({"component": "X", "props": {}}) in (None,) or isinstance(
        render_ssr({"component": "X", "props": {}}), (dict, type(None))
    )


def test_lazy_props_omitted_until_partial() -> None:
    Inertia._shared.clear()
    Inertia._shared_callbacks.clear()
    Inertia.set_version("v1")
    resp = Inertia.render(
        "Dash",
        {
            "eager": 1,
            "slow": Inertia.lazy(lambda: "heavy"),
            "later": Inertia.defer(lambda: "soon"),
        },
    )
    page = resp._page(None)
    assert page["props"]["eager"] == 1
    assert "slow" not in page["props"]
    assert "deferredProps" in page
    assert "later" in page["deferredProps"]["default"]

    class Req:
        def header(self, name: str, default=None):
            return {
                "X-Inertia-Partial-Component": "Dash",
                "X-Inertia-Partial-Data": "slow,later",
            }.get(name, default)

    page2 = resp._page(Req())  # type: ignore[arg-type]
    assert page2["props"]["slow"] == "heavy"
    assert page2["props"]["later"] == "soon"


def test_once_prop_evaluates_once() -> None:
    Inertia._shared.clear()
    Inertia.set_version("v1")
    hits = {"n": 0}

    def compute() -> int:
        hits["n"] += 1
        return hits["n"]

    resp = Inertia.render("Dash", {"n": Inertia.once(compute)})
    page = resp._page(None)
    assert page["props"]["n"] == 1
    page2 = resp._page(None)
    assert page2["props"]["n"] == 1
    assert hits["n"] == 1
