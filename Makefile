.PHONY: help smoke regression test test-cov test-cov-prism lint docs docs-build

PYTHON ?= .venv/bin/python
PYTEST ?= $(PYTHON) -m pytest

help:
	@echo "make smoke              - milestone smoke gate (no coverage)"
	@echo "make regression         - smoke + contract regression tests (no coverage)"
	@echo "make test               - full unit + smoke suite (no coverage)"
	@echo "make test-cov           - full suite with coverage fail-under 98% (aim 100%)"
	@echo "make test-cov-prism  - M6 Prism package coverage fail-under 100%"
	@echo "make lint               - ruff check"
	@echo "make docs               - Starlight docs site (dev server)"
	@echo "make docs-build         - build Starlight docs site"

smoke:
	$(PYTEST) -q tests/smoke -m smoke

regression:
	$(PYTEST) -q -m regression

test:
	$(PYTEST) -q

test-cov:
	$(PYTEST) -q --cov=almasix --cov-report=term-missing --cov-report=xml

test-cov-prism:
	$(PYTEST) -q tests/test_m6_*.py tests/smoke/test_m6_smoke.py --cov=almasix.prism --cov-report=term-missing --cov-fail-under=100

lint:
	$(PYTHON) -m ruff check src tests

docs:
	cd website && (npx astro dev stop >/dev/null 2>&1 || true) && npm run dev

docs-build:
	cd website && npm run build
