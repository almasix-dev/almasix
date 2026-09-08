"""Search — Laravel Scout parity for Articulate models.

Mix `Searchable` into a model and it keeps a search index in step with the
database on its own::

    class Post(Searchable, Model):
        def to_searchable_array(self) -> dict[str, Any]:
            return {"id": self.id, "title": self.title, "body": self.body}

    found = await Post.search("almasix").where("published", True).get()

Which engine answers is `config/scout.py`'s business: `database` searches the
table you already have, `collection` filters rows in Python, `meilisearch`
talks to a real index, `null` finds nothing, and `Scout.extend()` takes your
own.
"""

from __future__ import annotations

from almasix.scout import macros
from almasix.scout.builder import SOFT_DELETED, SearchBuilder
from almasix.scout.engines import (
    CollectionEngine,
    DatabaseEngine,
    Engine,
    MeilisearchEngine,
    NullEngine,
)
from almasix.scout.exceptions import (
    ScoutException,
    SearchException,
    UnsupportedEngineException,
)
from almasix.scout.facade import Scout
from almasix.scout.helpers import (
    default_scout_config,
    get_engine_manager,
    set_engine_manager,
)
from almasix.scout.jobs import MakeSearchable, RemoveFromSearch
from almasix.scout.manager import BUILT_IN, EngineManager
from almasix.scout.pending import flush_search
from almasix.scout.provider import ScoutServiceProvider
from almasix.scout.searchable import Searchable, make_searchable, remove_from_search
from almasix.scout.testing import FakeEngine, RecordedIndexWrite

macros.install()

__all__ = [
    "BUILT_IN",
    "SOFT_DELETED",
    "CollectionEngine",
    "DatabaseEngine",
    "Engine",
    "EngineManager",
    "FakeEngine",
    "MakeSearchable",
    "MeilisearchEngine",
    "NullEngine",
    "RecordedIndexWrite",
    "RemoveFromSearch",
    "Scout",
    "ScoutException",
    "ScoutServiceProvider",
    "SearchBuilder",
    "SearchException",
    "Searchable",
    "UnsupportedEngineException",
    "default_scout_config",
    "flush_search",
    "get_engine_manager",
    "make_searchable",
    "remove_from_search",
    "set_engine_manager",
]
