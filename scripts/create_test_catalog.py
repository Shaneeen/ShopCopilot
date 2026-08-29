#!/usr/bin/env python3
"""Generate a small synthetic catalog for local development/testing.

    python scripts/create_test_catalog.py [--out data/test_catalog.jsonl] [--size 300] [--force]

The official 50k catalog is not committed (see data/README.md) and the
organiser release may not be reachable — this script produces a
deterministic, clearly-synthetic stand-in with the same JSONL field shapes
(title/categories/features/details/store/description/price, mixed str /
list / dict values) so BM25 indexing, metadata filters, semantic indexing
and the full agent pipeline can all be exercised offline.

Deterministic: same seed -> byte-identical output. Refuses to overwrite an
existing file unless --force. Test data only — never submit/evaluate
against it.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO_ROOT = Path(__file__).resolve().parents[1]

BRANDS = ["Acme", "Zeta", "Nimbus", "Vertex", "UrbanLoom", "TrailForge", "Pulse", "Kite & Co", "Northwind", "Solstice"]
COLORS = ["black", "white", "red", "blue", "navy", "green", "grey", "beige", "pink", "olive"]
STORES = ["{brand} Official Store", "{brand} Outlet", "MegaMart", "UrbanEdge Goods", "Everyday Essentials"]

# category -> (nouns, use-cases, price range, materials, has_sizes)
CATEGORY_SPECS = {
    "sneakers": (["sneaker", "running shoe", "trainer", "walking shoe"], ["running", "walking", "gym", "casual wear"], (35, 140), ["canvas", "leather", "mesh", "suede"], True),
    "boots": (["boot", "hiking boot", "chelsea boot", "work boot"], ["hiking", "winter", "work", "everyday wear"], (60, 220), ["leather", "suede", "nylon"], True),
    "jackets": (["jacket", "windbreaker", "bomber jacket", "rain jacket"], ["outdoor", "commuting", "layering", "travel"], (45, 190), ["denim", "nylon", "leather", "polyester"], True),
    "hoodies": (["hoodie", "pullover hoodie", "zip hoodie", "sweatshirt"], ["lounging", "gym", "casual wear", "campus"], (25, 90), ["cotton", "fleece", "polyester"], True),
    "t-shirts": (["t-shirt", "tee", "graphic tee", "henley"], ["casual wear", "summer", "gym", "layering"], (10, 45), ["cotton", "cotton blend", "linen"], True),
    "jeans": (["jeans", "slim jeans", "straight jeans", "cargo pants"], ["everyday wear", "work", "casual outings"], (30, 120), ["denim", "stretch denim"], True),
    "backpacks": (["backpack", "daypack", "laptop backpack", "rucksack"], ["school", "commuting", "hiking", "travel"], (25, 130), ["nylon", "canvas", "polyester"], False),
    "headphones": (["headphones", "over-ear headphones", "wireless earbuds", "gaming headset"], ["music", "commuting", "gaming", "work calls"], (20, 300), ["plastic", "aluminum"], False),
    "speakers": (["bluetooth speaker", "portable speaker", "bookshelf speaker", "soundbar"], ["parties", "home audio", "travel", "outdoors"], (18, 250), ["plastic", "fabric", "aluminum"], False),
    "keyboards": (["keyboard", "mechanical keyboard", "wireless keyboard", "compact keyboard"], ["office work", "gaming", "programming"], (22, 180), ["plastic", "aluminum"], False),
    "mice": (["mouse", "wireless mouse", "gaming mouse", "ergonomic mouse"], ["office work", "gaming", "precision editing"], (10, 90), ["plastic", "rubber"], False),
    "water bottles": (["water bottle", "insulated bottle", "travel flask", "tumbler"], ["hiking", "gym", "office", "cycling"], (10, 55), ["stainless steel", "aluminum", "tritan plastic"], False),
    "watches": (["watch", "digital watch", "dive watch", "smartwatch"], ["everyday wear", "swimming", "running", "formal occasions"], (30, 350), ["stainless steel", "leather", "silicone"], False),
    "desk lamps": (["desk lamp", "led lamp", "architect lamp", "clip-on lamp"], ["reading", "studying", "office work"], (12, 80), ["metal", "plastic", "aluminum"], False),
    "coffee makers": (["coffee maker", "pour over kettle", "espresso machine", "french press"], ["home brewing", "office kitchens", "camping"], (15, 280), ["stainless steel", "glass", "plastic"], False),
}

MODEL_WORDS = ["Classic", "Trail", "Urban", "Studio", "Edge", "Flex", "Prime", "Breeze", "Summit", "Core", "Nova", "Drift"]
FEATURE_TEMPLATES = [
    "Durable {material} construction built for daily {use_case}",
    "Lightweight and comfortable for all-day {use_case}",
    "Available in {color} and other colourways",
    "Water-resistant finish, easy to clean",
    "Reinforced stitching for long-lasting wear",
    "Cushioned insole and padded collar for comfort",
    "Adjustable straps for a custom fit",
    "Compact design, ideal for {use_case}",
    "One-year manufacturer warranty included",
    "Machine washable, holds shape after washing",
    "Fast charging and long battery life",
    "Ergonomic design reduces strain during extended use",
]


def make_product(rng: random.Random, i: int) -> dict:
    if rng.random() < 0.05:  # sparse rows: exercise fail-open metadata filters
        category = rng.choice(list(CATEGORY_SPECS))
        return {
            "parent_asin": f"B0T{i:05d}",
            "title": f"{rng.choice(COLORS).title()} {category[:-1].title()}",
            "price": round(rng.uniform(10, 100), 2),
            "store": rng.choice(STORES).format(brand=rng.choice(BRANDS)),
        }

    category, (nouns, use_cases, (lo, hi), materials, has_sizes) = rng.choice(list(CATEGORY_SPECS.items()))
    brand = rng.choice(BRANDS)
    color = rng.choice(COLORS)
    material = rng.choice(materials)
    use_case = rng.choice(use_cases)
    noun = rng.choice(nouns)
    model = rng.choice(MODEL_WORDS)
    gender = rng.choice(["Men's", "Women's", "Unisex"])

    title = f"{brand} {gender} {model} {color.title()} {material.title()} {noun.title()}"
    description = (
        f"The {brand} {model} {noun} pairs a {material} build with a versatile "
        f"{color} finish — made for {use_case} and everyday use. "
        f"Part of our {category} collection."
    )
    features = [
        template.format(material=material, use_case=use_case, color=color)
        for template in rng.sample(FEATURE_TEMPLATES, k=rng.randint(2, 4))
    ]
    details = {
        "brand": brand,
        "color": color,
        "material": material,
        "department": gender.lower(),
        "category": category,
    }
    if has_sizes:
        details["size"] = rng.choice(["S", "M", "L", "XL", "7", "8", "9", "10", "11"])

    return {
        "parent_asin": f"B0T{i:05d}",
        "title": title,
        "categories": [category, "test-catalog"],
        "features": features,
        "details": details,
        "description": description,
        "store": rng.choice(STORES).format(brand=brand),
        "price": round(rng.uniform(lo, hi), 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "test_catalog.jsonl")
    parser.add_argument("--size", type=int, default=300)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.out.exists() and not args.force:
        print(f"{args.out} already exists — pass --force to regenerate.")
        return 1

    rng = random.Random(2026)
    products = [make_product(rng, i) for i in range(1, args.size + 1)]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for product in products:
            f.write(json.dumps(product) + "\n")

    sparse = sum(1 for p in products if "categories" not in p)
    print(
        f"Wrote {len(products)} products to {args.out} "
        f"({sparse} sparse rows for fail-open filter testing)."
    )
    print("Next: set NEESHOPS_CATALOG_PATH=data/test_catalog.jsonl, then run")
    print("  python scripts/setup_catalog.py && python scripts/build_semantic_index.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
