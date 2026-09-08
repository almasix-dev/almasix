"""``docs`` — where Almasix's documentation is.

Almasix's documentation site is not published yet; M39 publishes it. This
command therefore has no URL to open by default and does not invent one. It
opens ``$ALMASIX_DOCS_URL`` when that names a site you can reach — your own
build of ``website/``, or the hosted one once it exists — and otherwise says
where the Markdown sources live instead of pretending a link works.
"""

from __future__ import annotations

import os
import webbrowser

from almasix.console.command import Command

#: Where ``docs`` looks for a documentation site to open.
DOCS_URL_VARIABLE = "ALMASIX_DOCS_URL"

#: The documentation sources in the Almasix repository. They ship with no wheel,
#: so this is a place to look, not a path to open.
DOCS_SOURCE_PATH = "website/src/content/docs"


class DocsCommand(Command):
    """Laravel's ``docs`` — open the documentation in a browser.

    Laravel's also takes a ``--search`` term, which it answers from the
    published site's index. There is no published site and so no index, so
    searching is left out until M39 gives it something to search. The ``page``
    argument stays, because it names a file that exists in the repository
    today and a path that will exist on the site tomorrow.

    Reading the documentation has to work in a directory that is not an
    application yet, so this boots nothing and takes its URL from the
    environment rather than from ``config/``.
    """

    signature = "docs {page? : Documentation page, e.g. queues or articulate/casts}"
    description = "Open Almasix's documentation in a browser"
    boots_application = False

    def handle(self) -> int:
        page = str(self.argument("page") or "").strip().strip("/")
        base = os.environ.get(DOCS_URL_VARIABLE, "").strip().rstrip("/")
        if not base:
            self.report_unpublished(page)
            return self.SUCCESS

        url = f"{base}/{page}" if page else base
        if not webbrowser.open(url):
            self.warn(f"No browser could be opened. Read it at {url}")
            return self.SUCCESS
        self.info(f"Opening {url}")
        return self.SUCCESS

    def report_unpublished(self, page: str) -> None:
        """Say where the documentation is, there being nowhere to send a browser."""
        source = f"{DOCS_SOURCE_PATH}/{page}.md" if page else f"{DOCS_SOURCE_PATH}/"
        self.warn("Almasix's documentation site is not published yet.")
        self.line(f"Read it in the Almasix repository, under {source}")
        self.line(f"Set {DOCS_URL_VARIABLE} to a documentation site to open it here instead.")
