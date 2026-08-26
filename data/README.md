# Competition Data

## `public_set.jsonl`

Contains 200 labeled development sessions: 80 Buying, 80 Browsing, 30 Intent Override, and 10 Boundary sessions.

Each session contains a safe aggregate `user_profile` and public labels for local development. Direct user identifiers, timestamps, free-text reviews, raw purchase history, hidden intent cards, and simulator-policy internals are not shipped in this participant file.

## `catalog.jsonl`

Download `catalog.jsonl.gz` from the GitHub Release and decompress it as `catalog.jsonl` in this directory. Expected row count: 50,000.

Never place API keys, private evaluation data, or participant outputs in this directory.

---

## NeeShops addendum

For day-to-day experiment iteration without overfitting to all 200 public
sessions, `scripts/create_dev_split.py` produces a deterministic internal
split (`data/dev_split.jsonl`, `data/holdout_split.jsonl`, both gitignored
— regenerate rather than commit). See `docs/neeshops/EXPERIMENTS.md` for
how these are used.
