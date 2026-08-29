"""Load the catalog into an in-memory parent_asin -> row lookup, used for
filtering, ranking and personalization.

Kept separate from retrieval/bm25.py (which builds the FTS5 *search* index)
since not every caller needs the SQLite index — this is just a dict.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from neeshops.config.settings import get_settings
from neeshops.utils.logging import get_logger, log_event

_logger = get_logger("neeshops.catalog")


def load_catalog_lookup(path: Optional[Path] = None) -> dict[str, dict[str, Any]]:
    """Return {} (not an error) if the catalog isn't installed yet — the
    rest of the pipeline is written to degrade gracefully without it, so
    the agent stays importable/runnable before a teammate runs
    scripts/setup_catalog.py. See data/README.md.
    """
    catalog_path = path or get_settings().catalog_path
    if not catalog_path.exists():
        _logger.warning(
            "Catalog not found at %s — filters/personalization will no-op "
            "until it's installed. See data/README.md.",
            catalog_path,
        )
        return {}

    lookup: dict[str, dict[str, Any]] = {}
    with open(catalog_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            asin = row.get("parent_asin")
            if asin:
                lookup[asin] = row

    log_event("catalog.loaded", path=str(catalog_path), product_count=len(lookup))
    return lookup
