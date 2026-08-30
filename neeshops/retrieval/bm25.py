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
import threading
from pathlib import Path
from typing import Optional

from neeshops.config.settings import get_settings, load_strategy
from neeshops.models.session import ConversationState
from neeshops.retrieval.base import Candidate, Retriever
from neeshops.utils.logging import log_event

_SEARCH_FIELDS = ("title", "categories", "features", "details", "store", "description")

# FTS5 column order of the index (parent_asin is UNINDEXED — its weight is
# accepted but ignored by bm25()).
_COLUMN_ORDER = ("parent_asin",) + _SEARCH_FIELDS


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

    def __init__(
        self,
        index_path: Optional[Path] = None,
        catalog_path: Optional[Path] = None,
        strategy: Optional[dict] = None,
    ) -> None:
        settings = get_settings()
        self.catalog_path = catalog_path or settings.catalog_path
        self.index_path = index_path or self.catalog_path.with_suffix(".fts.db")
        # The connection is shared across sessions/threads (e.g. a threaded
        # HTTP frontend), so serialize access and relax SQLite's per-thread
        # check — all query execution goes through `_search_locked`.
        self._conn_lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._strategy = strategy  # lazy-loaded when unset; see set_strategy
        self._popular: Optional[list[str]] = None  # empty-query fallback, built lazily

    def set_strategy(self, strategy: dict) -> None:
        """Allow the hybrid router (or an experiment) to inject the active
        strategy so config changes apply without reconstructing the index."""
        self._strategy = strategy

    def _strategy_cfg(self) -> dict:
        if self._strategy is None:
            self._strategy = load_strategy()
        return self._strategy

    def is_available(self) -> bool:
        return self.catalog_path.exists()

    def _ensure_index(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        if not self.index_path.exists():
            self._build_index()
        self._conn = sqlite3.connect(self.index_path, check_same_thread=False)
        return self._conn

    def _search_locked(self, terms: list[str], top_k: int) -> list[tuple]:
        """Run the FTS query under the connection lock (thread-safe)."""
        with self._conn_lock:
            conn = self._ensure_index()
            cur = conn.execute(
                f"SELECT parent_asin, bm25(products{self._bm25_args()}) AS rank "
                "FROM products WHERE products MATCH ? "
                "ORDER BY rank, parent_asin LIMIT ?",
                (self._match_expression(terms), top_k),
            )
            return cur.fetchall()

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
        with open(self.catalog_path, encoding="utf-8") as f:
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
            # No usable keywords (fake prompt / near-empty context) — serve a
            # stable popularity-ranked slice instead of nothing, so
            # recommendations stay non-empty and the clarification questions
            # drive convergence.
            return self._popular_fallback(top_k)
        # FTS5 MATCH with a permissive OR of terms; bm25() returns a lower
        # score for a better match, so we negate it into an ascending score.
        # Config can boost fields (title/categories) so products whose
        # title/category matches a query token outrank products that match
        # only somewhere in a long description — the user's target usually
        # shares its coarse category and title words with the conversation.
        terms = [t for t in query.split() if t]
        if not terms:
            return []
        try:
            rows = self._search_locked(terms, top_k)
        except sqlite3.OperationalError:
            # Malformed FTS query (e.g. reserved characters) — fail soft.
            return []
        return [Candidate(parent_asin=r[0], score=-r[1], source=self.name) for r in rows]

    def _popular_fallback(self, top_k: int) -> list[Candidate]:
        if not self._strategy_cfg().get("retrieval", {}).get(
            "empty_query_fallback", True
        ):
            return []
        if self._popular is None:
            self._popular = self._build_popular_list()
        rows = self._popular[:top_k] if top_k else self._popular
        total = max(1, len(rows))
        return [
            Candidate(parent_asin=asin, score=1.0 - i / total, source="popular")
            for i, asin in enumerate(rows)
        ]

    def _build_popular_list(self, limit: int = 200) -> list[str]:
        """parent_asins ordered by review count (desc), scanned once from
        the raw catalog and cached for the process lifetime."""
        import json

        entries: list[tuple[int, str]] = []
        try:
            with open(self.catalog_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    asin = str(row.get("parent_asin", ""))
                    if not asin:
                        continue
                    try:
                        popularity = int(row.get("rating_number") or 0)
                    except (TypeError, ValueError):
                        popularity = 0
                    entries.append((-popularity, asin))
        except OSError:
            return []
        entries.sort()
        return [asin for _, asin in entries[:limit]]

    def _match_expression(self, terms: list[str]) -> str:
        """OR-of-terms MATCH string (organiser starter behaviour)."""
        return " OR ".join(f'"{t}"' for t in terms)

    def _bm25_args(self) -> str:
        """Column-weight arguments for bm25() from
        `retrieval.bm25_field_weights` config (empty string = vanilla)."""
        weights = self._strategy_cfg().get("retrieval", {}).get("bm25_field_weights")
        if not weights:
            return ""
        args = ", ".join(str(float(weights.get(col, 1.0))) for col in _COLUMN_ORDER)
        return f", {args}"
