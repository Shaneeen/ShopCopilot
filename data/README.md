# Competition Data

## `public_set.jsonl`

Contains 200 labeled development sessions: 80 Buying, 80 Browsing, 30 Intent Override, and 10 Boundary sessions.

Each session contains a safe aggregate `user_profile` and public labels for local development. Direct user identifiers, timestamps, free-text reviews, raw purchase history, hidden intent cards, and simulator-policy internals are not shipped in this participant file.

## `catalog.jsonl`

The simplest cross-platform setup from the repository root is:

```bash
python scripts/download_catalog.py
python scripts/check_readiness.py
```

The download script retrieves `catalog.jsonl.gz` and `SHA256SUMS` from the
[official Participant Kit Release](https://github.com/TechJam2026/techjam-conversational-search/releases/tag/participant-kit),
verifies the published checksum, decompresses the file as
`data/catalog.jsonl`, and validates 50,000 unique product IDs. It refuses to
overwrite an existing catalog.

For a manual install, download both release assets, verify
`catalog.jsonl.gz`, decompress it, and place the result at exactly
`data/catalog.jsonl`. Expected row count: 50,000.

Never place API keys, private evaluation data, or participant outputs in this directory.

The upstream source is [Amazon Reviews 2023](https://amazon-reviews-2023.github.io/),
but use the competition's frozen release catalog for scoring rather than
building a different 50,000-product sample yourself.

---

## NeeShops addendum

For day-to-day experiment iteration without overfitting to all 200 public
sessions, `scripts/create_dev_split.py` produces a deterministic internal
split (`data/dev_split.jsonl`, `data/holdout_split.jsonl`, both gitignored
— regenerate rather than commit). See `docs/neeshops/EXPERIMENTS.md` for
how these are used.
