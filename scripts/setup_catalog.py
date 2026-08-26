#!/usr/bin/env python3
"""Build the local BM25 (SQLite FTS5) search index from data/catalog.jsonl.

    python scripts/setup_catalog.py

Safe to re-run — deletes and rebuilds the index. Does not touch
data/catalog.jsonl itself.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from neeshops.config.settings import get_settings
from neeshops.retrieval.bm25 import BM25Retriever


def main() -> int:
    settings = get_settings()
    if not settings.catalog_path.exists():
        print(
            f"Catalog not found at {settings.catalog_path}.\n"
            "See data/README.md for how to install it before running this script."
        )
        return 1

    if settings.catalog_path.with_suffix(".fts.db").exists():
        settings.catalog_path.with_suffix(".fts.db").unlink()
        print("Removed stale index.")

    retriever = BM25Retriever()
    retriever._build_index()  # noqa: SLF001 — this script's whole job is to build it
    print(f"Built BM25 index at {retriever.index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
