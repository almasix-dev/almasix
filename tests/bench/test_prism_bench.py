"""Prism render benchmarks (MVP fixtures).

Run: ``pytest -q tests/bench/test_prism_bench.py -q``
Not a CI gate — tracks regressions locally / in planned M6 harness.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from almasix.prism.engine import Engine

pytestmark = pytest.mark.skipif(
    False,
    reason="bench always available; mark for selective runs",
)


@pytest.fixture()
def engine(tmp_path: Path) -> Engine:
    views = tmp_path / "views"
    (views / "layouts").mkdir(parents=True)
    (views / "layouts" / "app.prism.html").write_text(
        "<html><body>@yield('content')</body></html>",
        encoding="utf-8",
    )
    (views / "echo.prism.html").write_text("<p>{{ name }}</p>", encoding="utf-8")
    (views / "layout_child.prism.html").write_text(
        "@extends('layouts.app')\n@section('content')\n{{ name }}\n@endsection\n",
        encoding="utf-8",
    )
    return Engine(paths=[views])


def _time(fn, n: int = 2000) -> float:
    start = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - start) / n


def test_bench_echo(engine: Engine) -> None:
    # Warm cache
    engine.render("echo", {"name": "x"})
    secs = _time(lambda: engine.render("echo", {"name": "x"}))
    # Featherweight sanity: under 200µs/render on typical CI hardware
    assert secs < 0.0005, f"echo render too slow: {secs * 1e6:.1f}µs"


def test_bench_layout(engine: Engine) -> None:
    engine.render("layout_child", {"name": "x"})
    secs = _time(lambda: engine.render("layout_child", {"name": "x"}))
    assert secs < 0.001, f"layout render too slow: {secs * 1e6:.1f}µs"
