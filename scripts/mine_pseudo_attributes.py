#!/usr/bin/env python3
"""Pseudo-attribute mining (P4, offline): discriminative terms per attribute
field, written to data/pseudo_attributes.json (a SIDECAR — the catalog file
is never mutated).

Method (per the implementation spec):
- seeds: curated color/material/style/size/feature lexicons
- candidates: tokens/bigrams appearing in ≥ min_df products
- keep: seed membership OR IDF above cutoff (frequency mining alone surfaces
  junk like "imported" — the IDF cutoff plus manual review is the filter)
- classify: co-occurrence lift against each field's seed terms within the
  products that contain the candidate

Output is consumed ONLY as clarification entropy/agreement value evidence
(pseudo_attributes.row_value) — never a hard filter, never a demotion.

    python scripts/mine_pseudo_attributes.py --review 200
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from neeshops.retrieval.token_index import loads_jsonl  # noqa: E402
from neeshops.utils.tokens import tokenize  # noqa: E402

SEEDS: dict[str, set[str]] = {
    "color": {
        "black", "white", "blue", "red", "pink", "green", "brown", "gray",
        "grey", "purple", "yellow", "orange", "beige", "silver", "gold",
        "tan", "navy", "teal", "maroon", "khaki", "ivory", "multicolor",
    },
    "material": {
        "cotton", "polyester", "nylon", "leather", "wool", "spandex", "silk",
        "rayon", "denim", "suede", "canvas", "linen", "fleece", "velvet",
        "satin", "lace", "cashmere", "rubber", "mesh", "faux", "genuine",
        "stainless", "sterling", "plastic", "ceramic", "bamboo",
    },
    "style": {
        "vintage", "casual", "formal", "bohemian", "sporty", "classic",
        "modern", "retro", "minimalist", "elegant", "rugged", "chic",
        "oversized", "slim", "regular", "fit", "loose", "tailored",
    },
    "size": {
        "small", "medium", "large", "xlarge", "xxlarge", "petite", "plus",
        "toddler", "kids", "youth", "junior", "one", "narrow", "wide",
    },
    "use_case": {
        "running", "hiking", "gym", "training", "wedding", "swimming",
        "cycling", "yoga", "work", "outdoor", "winter", "summer", "travel",
        "party", "daily", "casual",
    },
}

# Junk tokens that survive frequency mining but carry no attribute value.
_STOP_TERMS = {
    "imported", "brand", "new", "size", "sizes", "color", "colors",
    "material", "style", "features", "product", "package", "include",
    "please", "note", "check", "item", "items", "sale", "off", "shipping",
    "return", "returns", "warranty", "guarantee", "quality", "premium",
    "design", "designs", "printed", "print", "pattern", "solid", "true",
    "false", "and", "the", "with", "for", "from", "your", "our", "all",
}


def row_text(row: dict) -> str:
    parts: list[str] = []
    for field in ("title", "features", "details", "description"):
        value = row.get(field)
        if isinstance(value, dict):
            parts.extend(f"{k} {v}" for k, v in value.items())
        elif isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif value is not None:
            parts.append(str(value))
    return " ".join(parts).lower()


def main() -> int:
    parser = argparse.ArgumentParser(description="Mine pseudo-attribute lexicons")
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--output", default="data/pseudo_attributes.json")
    parser.add_argument("--min-df", type=int, default=20)
    parser.add_argument("--idf-cutoff", type=float, default=4.0)
    parser.add_argument("--max-grams", type=int, default=2)
    parser.add_argument("--min-lift", type=float, default=1.5)
    parser.add_argument("--review", type=int, default=200)
    args = parser.parse_args()

    lookup = loads_jsonl(Path(args.catalog))
    rows = list(lookup.values())
    n = len(rows)
    print(f"catalog: {n} products")

    texts = [row_text(row) for row in rows]
    tokenized = [tokenize(text) for text in texts]
    uni_sets = [set(tokens) for tokens in tokenized]

    # Pass 1: unigram df (bounded — one Counter over unique tokens).
    uni_df: Counter[str] = Counter()
    for tokens in tokenized:
        uni_df.update(set(tokens))
    kept_unigrams = {
        t
        for t, c in uni_df.items()
        if c >= args.min_df and t not in _STOP_TERMS and not t.isdigit()
    }

    # Pass 2: bigram df only where BOTH tokens are kept unigrams — bounds
    # the Counter to plausible phrases instead of the full O(N) gram space.
    bi_df: Counter[str] = Counter()
    if args.max_grams >= 2:
        for tokens in tokenized:
            grams = {
                f"{tokens[i]} {tokens[i + 1]}"
                for i in range(len(tokens) - 1)
                if tokens[i] in kept_unigrams and tokens[i + 1] in kept_unigrams
            }
            bi_df.update(grams)

    df: Counter[str] = uni_df + bi_df

    seed_membership = {
        term: field for field, terms in SEEDS.items() for term in terms
    }

    candidates: list[tuple[str, int]] = [
        (term, count)
        for term, count in df.items()
        if count >= args.min_df
        and term not in _STOP_TERMS
        and not term.isdigit()
        and (term in seed_membership or math.log(n / count) >= args.idf_cutoff)
    ]
    print(f"candidates: {len(candidates)} (df ≥ {args.min_df}, idf ≥ {args.idf_cutoff} or seeded)")

    # Inverted index over CANDIDATE terms only — avoids an O(N) rescan per
    # candidate during the lift computation.
    candidate_set = {term for term, _ in candidates}
    inv: dict[str, list[int]] = {term: [] for term in candidate_set}
    for i, tokens in enumerate(tokenized):
        grams = set(tokens)
        if args.max_grams >= 2:
            grams.update(
                f"{tokens[j]} {tokens[j + 1]}" for j in range(len(tokens) - 1)
            )
        for term in grams & candidate_set:
            inv[term].append(i)

    seed_df: dict[str, Counter[str]] = {
        field: Counter() for field in SEEDS
    }
    for field, terms in SEEDS.items():
        for term in terms:
            seed_df[field][term] = df.get(term, 0)

    classified: dict[str, list[tuple[str, int]]] = {field: [] for field in SEEDS}
    classified["feature"] = []
    for term, count in candidates:
        if term in seed_membership:
            classified[seed_membership[term]].append((term, count))
            continue
        doc_ids = inv.get(term) or []
        if len(doc_ids) < args.min_df:
            continue
        containing = len(doc_ids)
        best_field, best_lift = None, 0.0
        for field, terms in SEEDS.items():
            hits = sum(1 for i in doc_ids if uni_sets[i].intersection(terms))
            p_term = hits / containing
            p_base = sum(seed_df[field].values()) / max(n, 1)
            if p_base <= 0:
                continue
            lift = p_term / p_base
            if lift > best_lift:
                best_field, best_lift = field, lift
        target_field = best_field if best_lift >= args.min_lift else "feature"
        classified[target_field].append((term, count))

    output: dict[str, list[str]] = {}
    for field, items in classified.items():
        ordered = [term for term, _ in sorted(items, key=lambda kv: (-kv[1], kv[0]))]
        output[field] = ordered
        print(f"  {field}: {len(ordered)} terms")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=1) + "\n", encoding="utf-8")
    print(f"\nwrote {output_path}")

    print(f"\n--- top {args.review} mined terms for MANUAL REVIEW ---")
    for field in ("color", "material", "style", "size", "use_case", "feature"):
        print(f"  {field}:")
        for term in output[field][: max(args.review // 6, 1)]:
            print(f"    {term} (df={df[term]})")
    print(
        "\nreview the lists above; prune junk by editing "
        f"{output_path} (or _STOP_TERMS + re-run). The sidecar is only ever "
        "entropy/agreement evidence — never a hard filter."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
