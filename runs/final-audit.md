# Final new-baseline forensic audit

## Scope and controls

- Branch/worktree: `audit/final-forensics` in `sc-final-audit`, created from annotated tag `new-baseline`; peeled commit `46e3322c57c106372b379f58efd6416ab340c086`.
- Analysis input: **only** `data/dev_split.jsonl` (160 sessions). No public or holdout evaluation was run. `evaluator/` was not edited.
- Runtime files (`catalog.jsonl`, `catalog.fts.db`, semantic index/meta, and `dev_split.jsonl`) were copied as independent gitignored files from the main checkout. No tracked data was changed.
- Control validation: `runs/control-dev-newbaseline.json` has exactly 160 sessions and 144 hits.
- Pre-audit test: `325 passed, 1 deselected in 19.70s`.

## Baseline panel and miss map

| Metric | new-baseline dev-160 |
|---|---:|
| Hit@10 | 0.900000 (144/160) |
| MRR | 0.514395 |
| MTTC | 3.1875 |
| TechnicalScore | 0.760568 |

The snapshot has 16 misses: 2 binary pool-class and 14 binary rank-class. The detailed taxonomy labels one of those 14 (`public_0117`) as an extraction miss. The requested **13 rank-class misses** below are therefore the 13 non-extraction members; this reconciles the requested count with the snapshot fields.

## Method

Each requested miss was replayed with the official simulator primitives but only against `data/dev_split.jsonl`. Before each `respond`, the audit captured the persisted state, current extraction, preview state, and the exact three query strings returned by `NeeShopsAgent.build_retrieval_queries`. After `respond`, it inspected the exact hybrid and post-filter pools actually used. For the two pool misses only, the same query was additionally searched beyond the 200 cap and passed through priority union and filters to distinguish cap depth, active filtering, and catalog absence.

Relevant implementation points:

- Query construction: `neeshops/agent.py:604-647`; active query fields are category, color, material, style, brand, feature, and use_case. `NO_PREFERENCE` is deliberately omitted (`:633-646`).
- Accumulated history: `neeshops/agent.py:649-672`.
- Preview/override state: `neeshops/agent.py:550-581` and `neeshops/conversation/state.py:93-117`.
- Candidate cap and filtering: `neeshops/agent.py:325-348`; candidate limit is 200.
- Budget and category hard filtering: `neeshops/retrieval/filters.py:221-255`; text constraints only demote.

## Task A — two pool-class misses

### `public_0020` — **cap depth (rank 201+)**

Target `B08P4SSFX4`, “Funny Saying Novelty Gift ideas - My Favorite People Call Me Grandma Long Sleeve T-Shirt,” is present in the 50k catalog. It passes both active hard filters on every turn: price `$21.98`, no active budget cap, and catalog categories include `Novelty` and `Women`. All active constraint tokens occur in the target; this is neither a catalog gap nor an active-filter kill.

Deep post-filter target ranks by turn were **410, 353, 306, 306, 308, 305, 240, 240, 240, 240**. The uncapped hybrid ranks were 627, 373, 540, 531, 542, 552, then 313 through turn 10; priority-union improves them but never to 200. Exact conclusion: target misses the production pool solely because it remains below the 200-candidate cap.

### `public_0180` — **cap depth (rank 201+)**

Target `B01HSMYV8E`, “Saucony Women's Cohesion 10 Running Shoe,” is present in the catalog. It passes both active hard filters on every turn: price `$49.95`, budget is unset/`NO_PREFERENCE`, and categories include `Women`, `Shoes`, and `Fashion Sneakers`. No active target constraint token is absent.

Deep post-filter ranks by turn were **823, 1213, 1248, 1254, 1331, 1294, 1480, 1480, 1480, 1480**. The target never appeared in the uncapped multi-query hybrid result, but priority union placed it at those finite depths from the catalog-backed Boolean set. Exact conclusion: it is available and filter-valid but far below cap 200; it is not a catalog gap or filter kill.

**Task A totals:** cap-depth 2; active-filter 0; catalog-gap 0.

## Task B — thirteen rank-class misses

Notation: `relaxed` lists fields explicitly stored as `NO_PREFERENCE` and consequently omitted from the constraints query. These are not recoverable product constraints because the customer expressly declined them. `overridden` records replacement of an earlier value in state; the prior value remains in accumulated conversation text by design. Query keyword normalization removes stopwords (for example, `Pull On closure` becomes `pull closure`, and `No Show` becomes `show`); those values are still represented and are not counted as dropped.

| Miss | Replay result: state versus retrieval query |
|---|---|
| `public_0003` | Dropped: none. Relaxed: budget t4, size t5, style t6. Overridden: feature `Water Resistant; 3 Year Battery` → `Water Resistant` at t3; active replacement appears in latest/constraints and old phrase remains accumulated. |
| `public_0171` | Dropped: none. Relaxed: budget t4, size t5, style t6. Overridden: none. Category/material/feature are represented throughout. |
| `public_0004` | Dropped: none. Relaxed: budget t4, size t5, color t6. Overridden: none. Category/material remain represented. |
| `public_0187` | Dropped: none. Relaxed: other t2, color t3, budget t5, size t6. Overridden: none. Category is represented throughout and material from t4. |
| `public_0161` | Dropped: none after query keyword normalization. Relaxed: budget t4, size t5, color t6. Overridden: feature `Imported` → `Pull On closure` at t3; `pull closure` is present in accumulated and constraints queries, while `imported` remains accumulated. |
| `public_0126` | Dropped: none after normalization. Relaxed: budget t4, size t5, color t6. Overridden: none. Feature `Imported; Pull On closure` is represented as `imported pull closure`. |
| `public_0096` | Dropped: none. Relaxed: budget t4, size t5, color t6. Overridden: none. Category/material remain represented. |
| `public_0052` | Dropped: none. Relaxed: budget t4, size t5, color t6. Overridden: none. Category/material remain represented. |
| `public_0035` | Dropped: none. Relaxed: other t2, budget t3, size t4, color t6. Overridden: none. Category/style remain represented and material is represented from t5. |
| `public_0078` | Dropped: none after normalization. Relaxed: budget t4, size t5, style t6. Overridden: none. Category `Socks No Show & Liner Socks` is represented as `socks show liner socks`; material is represented from t2. |
| `public_0083` | Dropped: none. Relaxed: budget t4, size t5, color t6. Overridden: feature `Imported` → `Button closure` at t3; replacement is represented and old value remains accumulated. |
| `public_0075` | Dropped: none. Relaxed: budget t4, size t5, style t6. Overridden: none. Category/material/feature remain represented. |
| `public_0092` | Dropped: none. Relaxed: budget t4, size t5, style t6. Overridden: none. Category/material/feature remain represented. |

### Task B conclusion

- Misses with at least one **recoverable held constraint absent from retrieval query: 0/13**.
- Every active, non-`NO_PREFERENCE` constraint held by state is represented in at least one retrieval query on every replayed turn, after applying the same keyword normalization used by query construction.
- The only query omissions are explicit `NO_PREFERENCE` values, plus stopwords within otherwise represented values. Three misses have normal same-field overrides (`public_0003`, `public_0161`, `public_0083`), but their active replacements are represented and their old values remain in the accumulated angle.
- Therefore these 13 cases do not expose a recoverable state-to-query constraint-loss class. They remain ranking failures after the target enters the candidate pool.

## Paired baseline statement

This was analysis-only: no strategy or feature behavior changed and no new evaluated arm was produced. Relative to `runs/control-dev-newbaseline.json`, paired flips are **0 miss→hit / 0 hit→miss; session IDs: none**. Baseline metrics are unchanged.
