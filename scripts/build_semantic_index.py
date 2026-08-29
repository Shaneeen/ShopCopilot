#!/usr/bin/env python3
"""Build the semantic (hashed TF-IDF) index from the catalog.

    python scripts/build_semantic_index.py [--catalog data/catalog.jsonl] [--dim 1024] [--force]

Writes `data/semantic.index.npy` + `data/semantic.meta.json` (both
gitignored). Refuses to overwrite an existing index unless `--force` is
given — a rebuild is deterministic, so the only reason to force is a catalog
change. Safe to re-run against the same catalog.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from neeshops.config.settings import get_settings
from neeshops.retrieval.semantic import DEFAULT_DIM, build_index


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog", type=Path, default=settings.catalog_path)
    parser.add_argument("--dim", type=int, default=DEFAULT_DIM)
    parser.add_argument("--force", action="store_true", help="overwrite an existing index")
    args = parser.parse_args()

    if not settings.enable_semantic_retrieval:
        print(
            "Note: NEESHOPS_ENABLE_SEMANTIC_RETRIEVAL is not set to true — the "
            "index will be built, but SemanticRetriever stays off until you "
            "export NEESHOPS_ENABLE_SEMANTIC_RETRIEVAL=true."
        )

    index_path = args.catalog.parent / "semantic.index.npy"
    meta_path = args.catalog.parent / "semantic.meta.json"
    if index_path.exists() and not args.force:
        print(f"Index already exists at {index_path} — pass --force to rebuild.")
        return 1

    try:
        stats = build_index(args.catalog, index_path, meta_path, dim=args.dim)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"Failed to build semantic index: {exc}")
        return 1

    size_mb = index_path.stat().st_size / (1024 * 1024)
    print(
        f"Built semantic index: {stats['rows']} products, dim={stats['dim']}, "
        f"{size_mb:.1f} MB\n  {index_path}\n  {meta_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
