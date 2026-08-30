# P2 One-Shot Push Bundle for P3
`git add p2_push && git commit -m "p2: real sorting/filtering bundle"`

Contains: real P2 code is `neeshops/retrieval/` (BM25 + filters + hybrid) — this folder is just a runnable snapshot + tests for P3 to verify without waiting for merge.

## What's real
- `BM25Retriever` — SQLite FTS5 over `data/catalog.jsonl` 50k, fields title/categories/features/details/store/description, weights from `neeshops/config/default_strategy.json`
- `filters.py` — budget (price <= constraint) + category token match + soft text_contains for color/material/brand/size/style/feature/use_case — fail-open on missing data, runs after retrieval before ranking
- `HybridRetriever` — candidate_limit 200, merges bm25+semantic (semantic disabled), weights 0.7/0.3 buying vs 0.3/0.7 browsing

P3 receives: `HybridRetriever.search(query, state, 200) -> list[Candidate(parent_asin, score, source)]` then `apply_filters(candidates, lookup, state)` then P3 reranks top 40 -> final 10.

## To test
```
pytest p2_push/test_p2_all.py -v
python -m evaluator.local_evaluator  # full 200 sessions
python scripts/interactive_demo.py   # live demo
```
