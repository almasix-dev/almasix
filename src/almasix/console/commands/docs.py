"""``docs`` — open Almasix documentation in a browser.

Defaults to the hosted site at docs.almasix.com. Override with
``$ALMASIX_DOCS_URL`` for a local build. Markdown sources live in the
``almasix-docs`` repository (checked out into ``website/`` in CI).
"""

from __future__ import annotations

import os
import webbrowser

from almasix.console.command import Command

#: Where ``docs`` looks for a documentation site to open.
DOCS_URL_VARIABLE = "ALMASIX_DOCS_URL"

#: Hosted documentation site when ``ALMASIX_DOCS_URL`` is unset.
DEFAULT_DOCS_URL = "https://docs.almasix.com"

#: Markdown sources (sibling repo; CI checks it out at ``website/``).
DOCS_SOURCE_REPO = "https://github.com/almasix-dev/almasix-docs"
DOCS_SOURCE_PATH = "website/src/content/docs"


class DocsCommand(Command):
    """Laravel's ``docs`` — open the documentation in a browser.

    Laravel's also takes a ``--search`` term, which it answers from the
    published site's index. Searching is left out for now. The ``page``
    argument names a path on the site (and a file under ``almasix-docs``).

    Reading the documentation has to work in a directory that is not an
    application yet, so this boots nothing and takes its URL from the
    environment (or the default hosted site) rather than from ``config/``.
    """

    signature = "docs {page? : Documentation page, e.g. queues or articulate/casts}"
    description = "Open Almasix's documentation in a browser"
    boots_application = False

    def handle(self) -> int:
        page = str(self.argument("page") or "").strip().strip("/")
        base = os.environ.get(DOCS_URL_VARIABLE, "").strip().rstrip("/") or DEFAULT_DOCS_URL

        url = f"{base}/{page}" if page else base
        if not webbrowser.open(url):
            self.warn(f"No browser could be opened. Read it at {url}")
            self.line(f"Sources: {DOCS_SOURCE_REPO} ({DOCS_SOURCE_PATH}/)")
            return self.SUCCESS
        self.info(f"Opening {url}")
        return self.SUCCESS
