"""BM25 keyword retrieval over the product catalog, backed by SQLite FTS5
(ranked with SQLite's built-in `bm25()` function) — stdlib only, no extra
dependency required for the competition baseline.

Indexed fields and tokenizer intentionally mirror the organiser's weak
starter (`starter/agent.py` as originally shipped, before the NeeShops
adapter replaced it — see git history) so Hit Rate/MRR stay comparable to
the published baseline (0.125 / 0.068034): `title`, `categories`,
`features`, `details`, `store`, `description`, `unicode61
remove_diacritics 2` tokenizer. Diverge from this deliberately, not
accidentally.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from neeshops.config.settings import get_settings
from neeshops.models.session import ConversationState
from neeshops.retrieval.base import Candidate, Retriever
from neeshops.utils.logging import log_event

_SEARCH_FIELDS = ("title", "categories", "features", "details", "store", "description")


def _flatten(value: object) -> str:
    """Match the organiser catalog's mixed str/list/dict field shapes into
    plain text for indexing — same approach as the official starter's
    `_text()` helper."""
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(f"{key} {item}" for key, item in value.items())
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


class BM25Retriever(Retriever):
    name = "bm25"

    def __init__(self, index_path: Optional[Path] = None, catalog_path: Optional[Path] = None) -> None:
        settings = get_settings()
        self.catalog_path = catalog_path or settings.catalog_path
        self.index_path = index_path or self.catalog_path.with_suffix(".fts.db")
        self._conn: Optional[sqlite3.Connection] = None

    def is_available(self) -> bool:
        return self.catalog_path.exists()

    def _ensure_index(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        if not self.index_path.exists():
            self._build_index()
        self._conn = sqlite3.connect(self.index_path)
        return self._conn

    def _build_index(self) -> None:
        """Build the FTS5 index from data/catalog.jsonl. Run once, cached to
        disk (`<catalog>.fts.db`, gitignored) — see scripts/setup_catalog.py
        to build it explicitly ahead of time.
        """
        import json

        if not self.catalog_path.exists():
            raise FileNotFoundError(
                f"Catalog not found at {self.catalog_path}. See data/README.md "
                "for how to install the organiser's catalog."
            )

        conn = sqlite3.connect(self.index_path)
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS products USING fts5("
            "parent_asin UNINDEXED, title, categories, features, details, store, description, "
            "tokenize='unicode61 remove_diacritics 2')"
        )
        with open(self.catalog_path) as f:
            rows = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                rows.append(
                    (
                        str(row.get("parent_asin", "")),
                        *(_flatten(row.get(field)) for field in _SEARCH_FIELDS),
                    )
                )
                if len(rows) >= 1000:
                    conn.executemany(
                        "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", rows
                    )
                    rows.clear()
        if rows:
            conn.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
        conn.close()
        log_event("bm25.index_built", path=str(self.index_path))

    def search(self, query: str, state: ConversationState, top_k: int) -> list[Candidate]:
        if not query.strip():
            return []
        conn = self._ensure_index()
        # FTS5 MATCH with a permissive OR of terms; bm25() returns a lower
        # score for a better match, so we negate it into an ascending score.
        terms = " OR ".join(f'"{t}"' for t in query.split() if t)
        if not terms:
            return []
        try:
            cur = conn.execute(
                "SELECT parent_asin, bm25(products) AS rank FROM products "
                "WHERE products MATCH ? ORDER BY rank LIMIT ?",
                (terms, top_k),
            )
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            # Malformed FTS query (e.g. reserved characters) — fail soft.
            return []
        return [Candidate(parent_asin=r[0], score=-r[1], source=self.name) for r in rows]
