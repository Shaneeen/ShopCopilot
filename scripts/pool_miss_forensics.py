#!/usr/bin/env python3
"""Pool-miss forensics (P4): why did the target miss the 200-pool?

For sampled targets, builds the constraint values exactly the way the
evaluator protocol discloses them (coarse category + intent-card hard/soft
constraints) and computes:

    set(final constraint tokens) − doc_tokens[target]

across the whole sample. Recurring offenders are either PARAPHRASES (the
user's token isn't the target's token → add to retrieval/synonyms.py) or
EXTRACTION BUGS (fix conversation/constraints.py). The Boolean guarantee
holds per-session, so every listed token is a real recall hole.

    python scripts/pool_miss_forensics.py --cases 200 --seed 7
    python scripts/pool_miss_forensics.py --emit-synonyms
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from collections import Counter
from pathlib import Path

os.environ.setdefault("NEESHOPS_LOG_LEVEL", "ERROR")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluator.local_evaluator import coarse_category, intent_card  # noqa: E402
from neeshops.retrieval.token_index import TokenIndex, index_tokenize, loads_jsonl  # noqa: E402


def stated_tokens(row: dict) -> set[str]:
    """Tokens the pipeline would actually put in constraint slots — card
    values after the extractor's own classification (a 'color: grey' value
    stores 'grey', the prefix is stripped by _classify_requirement)."""
    card = intent_card(row)
    categories = [str(c) for c in row.get("categories") or []]
    values = [coarse_category(categories)]
    values.extend(str(v) for v in card["hard_constraints"])
    values.extend(str(v) for v in card["soft_preferences"])
    tokens: set[str] = set()
    for value in values:
        lowered = value.lower()
        if lowered.startswith("color:"):
            lowered = lowered.split(":", 1)[1]
            value = lowered
        tokens.update(index_tokenize(value))
    return tokens


def main() -> int:
    parser = argparse.ArgumentParser(description="Pool-miss forensics")
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--cases", type=int, default=200)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--top", type=int, default=40)
    parser.add_argument("--emit-synonyms", action="store_true")
    args = parser.parse_args()

    catalog_path = Path(args.catalog)
    lookup = loads_jsonl(catalog_path)
    print(f"catalog: {len(lookup)} products")

    index = TokenIndex(lookup)
    rows = list(lookup.values())
    rng = random.Random(args.seed)
    sample = rng.sample(rows, min(args.cases, len(rows)))

    offender_counter: Counter[str] = Counter()
    offender_examples: dict[str, str] = {}
    clean = 0
    for row in sample:
        target = str(row["parent_asin"])
        doc_tokens = index.doc_tokens(target)
        if doc_tokens is None:
            continue
        missing = stated_tokens(row) - doc_tokens
        if not missing:
            clean += 1
            continue
        for token in missing:
            offender_counter[token] += 1
            offender_examples.setdefault(token, target)

    total = len(sample)
    print(f"\nsessions inspected: {total}")
    print(f"  clean (all stated tokens in target text): {clean} ({100.0 * clean / max(total, 1):.1f}%)")
    print(f"  sessions with missing tokens: {total - clean} ({100.0 * (total - clean) / max(total, 1):.1f}%)")
    print(f"\ntop {args.top} offender tokens (count | token | example target):")
    for token, count in offender_counter.most_common(args.top):
        print(f"  {count:4d}  {token:<24} {offender_examples[token]}")

    if args.emit_synonyms:
        print("\n# Suggested SYNONYMS entries for neeshops/retrieval/token_index.py")
        print("# (retrieval-only expansion — verify each mapping manually):")
        for token, _count in offender_counter.most_common(args.top):
            print(f'#    "{token}": ("…",),')

    print(
        "\nnext step: recurring offenders that are paraphrases go into "
        "SYNONYMS (retrieval-only); tokens that are extraction bugs go to "
        "conversation/constraints.py. Re-run until the clean rate ~ 100%."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
