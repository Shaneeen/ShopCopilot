# AI Context: ShopCopilot Filtering, Ranking & Benchmarks

> Purpose: single file for an AI (or new teammate) to understand **how every filter works, what criteria are applied, and what scores to beat** — then propose a better method for accuracy/speed. Covers the 200-case hackathon public set and all auxiliary benches.

---

## 1. System Map

```
evaluator/local_evaluator.py (official, frozen)
  → starter/agent.py (thin adapter, 30L, not edited)
    → neeshops/agent.py : NeeShopsAgent orchestration
      → neeshops/conversation/ : state.py + constraints.py + intent.py + clarification.py
      → neeshops/retrieval/    : bm25.py + semantic.py + hybrid.py + filters.py + candidate_merge.py
      → neeshops/ranking/      : deterministic.py (ConstraintAwareRanker R2) + heuristic.py + features.py + llm_reranker.py + providers/
      → neeshops/personalization/profile.py
      → neeshops/config/default_strategy.json (all tunable weights, single source of truth)
```

`data/catalog.jsonl` 50k `Clothing_Shoes_and_Jewelry` (read-only, frozen). `data/public_set.jsonl` 200 labeled sessions (hackathon dev set). Private 800 held out.

---

## 2. Filtering — Where & Why

**Catalog has no structured `color/material/brand/size/style/feature/use_case` columns.** Only `title, categories, features, details, description, store, price`. Filtering therefore runs **after retrieval, before ranking** (`neeshops/agent.py` calls `HybridRetriever.search → apply_filters → Ranker.rank`). Design principle (filters.py:1-31): **demote, don't drop** — hard-dropping on text containment deletes sparse-metadata targets (the simulator's constraints are verbatim from the target's own text).

### 2.1 Config Knobs

`neeshops/config/default_strategy.json:filters`

```json
filters: { budget_tolerance: 1.10, min_pool_keep: 10 }
```

- `budget_tolerance` — float multiplier on budget hard cap. `under $27.99` must keep `$29.99` target (`27.99*1.10=30.78`).
- `min_pool_keep` — category hard-drop only if ≥10 candidates survive; else category becomes soft.

Via `neeshops/config/settings.py:load_strategy()`, override per experiment without code change (`SAFE_PARAMETERS`).

### 2.2 Field Taxonomy

| Field | Type | Config Key | Catalog Source | Filter Fn | Ranker Class |
|---|---|---|---|---|---|
| `budget` | **hard** | `budget_tolerance` | `price` (float, some junk strings) | `budget_filter:85` | `HARD` |
| `category` | **semi-hard** | `min_pool_keep` | `categories` (breadcrumbs `Clothing, Shirts, T-Shirts`) | `category_filter:98` | `HARD` |
| `color` | soft | — | text fields | `text_contains_filter("color"):131` | `HARD` |
| `material` | soft | — | text fields | `text_contains_filter("material")` | `HARD` |
| `brand` | soft | — | text fields + `store` | `text_contains_filter("brand")` | `HARD` |
| `size` | soft | — | text fields | `text_contains_filter("size")` | `HARD` |
| `style` | soft | — | text fields | `text_contains_filter("style")` | `SOFT` |
| `feature` | soft | — | text fields | `text_contains_filter("feature")` | `SOFT` |
| `use_case` | soft | — | text fields | `text_contains_filter("use_case")` | `SOFT` |

`_SOFT_FIELDS:46 = (color,material,brand,size,style,feature,use_case)` — only these enter demote path. `_TEXT_FIELDS:43 = (title,categories,features,details,description,store)`.

Hard vs soft in **ranking** (`ranking/features.py:24-25`) differs: `HARD = category,color,material,size,brand,budget` violations sink candidates first; `SOFT = style,feature,use_case` only add match bonuses.

### 2.3 How Each Criterion Is Evaluated

**Budget `budget_filter:85`** — `state.constraint_value("budget") == float or None`. Skip if `None` or `NO_PREFERENCE`. Else `float(price) <= float(budget)*1.10`. Fail-open on missing/unparseable price (real catalog has junk strings) → `return True`.

**Category `category_filter:98`** — `state.constraint_value("category")` is phrase like `"women shirts"` from `looking for women shirts`. Tokenize via `utils/tokens:tokenize`, drop stop tokens length<3, then `any(token in categories_text for token)` where `categories_text = " ".join(categories).lower()`. Phrase not required; token overlap prevents self-filtering target whose `categories=["Clothing, T-Shirts"]`.

**Text constraints `_text_satisfies:116`** — across `_product_text:72` (all `_TEXT_FIELDS` lowercased). Tokenize value, if `len(tokens)>1` require `all(t in text for t in tokens)` order-independent (so `"machine wash; imported"` matches regardless of order); single token `value_text in text`. `text_contains_filter:131` wraps this per field, skip if `None`/`NO_PREFERENCE`.

Sparse metadata → `product_text == ""` or `row is None` → `return True` (fail-open, not penalised).

### 2.4 Pipeline `apply_filters:170` (production `filters=None`)

Input: `candidates: list[Candidate(parent_asin, score, source)]` (≤200 from `HybridRetriever`, sorted best-first by fused retrieval score).

```
Pass 1 — budget hard drop (budgeted)
  keep iff budget_filter(row) else drop
  if empty → return [] (no candidates survive)

Pass 2 — category semi-hard (categorized)
  categorized = [c in budgeted where row is None or category_filter(row)]
  hard_category = len(categorized) >= min_pool_keep (10)
  pool = categorized if hard_category else budgeted   # else category added to soft misses

Pass 3 — soft demote (scored)
  for (idx,c,row) in pool:
    misses = 0
    if not hard_category and not category_filter(row): misses+=1
    for (field,value) in _soft_constraint_values(state):  # _SOFT_FIELDS non-None non-NO_PREF
      if not _text_satisfies(value, row): misses+=1
    scored.append((misses, idx, c))
  sort by (misses asc, idx asc)  # fewer violations first, stable by retrieval rank
  return [c for _,_,c in scored]
```

Result: no text constraint ever deletes the target; matches fill `ranking.rerank_limit` window (default 40). Ranking then adds per-field bonuses (`features.py:119`).

**Legacy hard mode** `apply_filters(..., filters=[budget_filter, category_filter, text_contains_filter("color"), ...])` → classic `all(f(row,state) for f in filters)` hard intersection, fail-open on missing lookup rows, kept for unit tests/experiments.

### 2.5 Ranking Interaction

`ranking/features.RankingFeatureExtractor:52` recomputes match per field independent of filter:

- `HARD` status: need required tokens ⊆ observed tokens (field-specific `observed` + fallback `supporting` title/features/description). `MISMATCH` only if observed exists but tokens not subset; missing data → `UNKNOWN` (no penalty).
- `SOFT` status: same but missing → `UNKNOWN` not `MISMATCH`.
- `budget_status:183` — `MISMATCH` if `price > budget*tolerance`, else `MATCH`/`UNKNOWN`.
- `ConstraintAwareRanker:deterministic.py` sorts `hard_violation_count asc` first, then weighted feature matches (`color/material/brand/size/budget/style + retrieval_score_normalized + title_overlap/feature_overlap + personalization_boost`). Explicit constraints always outrank `personalization_weight=0.15` soft boost (`test_personalization_never_overrides`).

---

## 3. Retrieval Before Filtering

`HybridRetriever.search:73` — `query` built from `active constraints + history + newest message` via `utils/tokenization.py`.

- **3-angle multi-query RRF** (`hybrid.py:127 search_multi`, enabled by `multi_query: {enabled:true, weights:{accumulated:0.5, latest:0.3, constraints:0.2}, rrf_k:60}`): runs BM25+semantic per angle (up to 3×2 searches), fuses via Reciprocal Rank Fusion `score = Σ 1/(k+rank)`. This lifted oracle `target-in-pool@200 14.3%→68.2%`.
- Route weights `hybrid.py:50 weights_for_route`: `buying bm25 0.7/sem 0.3`, `browsing bm25 0.3/sem 0.7` from `retrieval.buying/bm25_weight`.
- `candidate_merge.merge_weighted` — min-max normalise per source scale then weighted sum, dedup `parent_asin` with `source="bm25+semantic"`.
- `is_available()` fail-soft: semantic disabled/missing dep/corrupt index → BM25-only, never empty pool.
- **Popularity fallback**: junk/empty prompts → top-rated 200 so recommendations never blank.
- `retrieval.candidate_limit:200` (pre-rank pool), `ranking.rerank_limit:40` (LLM reranks top 30).

---

## 4. Conversation → State (what populates filters)

`constraints.py:244 extract_constraints(message, slot)` — slot-filling on `slot=other|color|...` (previous turn's `ask_attribute`). `other` splits on `;` → up to 2 constraints of any type (`_parse_compound_reply:162`), `budget/color/material/size/style/feature` detectors, `looking for X` → `category`, `A key requirement is: X` classifier, `NO_PREFERENCE` phrases (`no preference, don't care, any is fine, don't have a, no additional, …`). Override semantics: new value **replaces** old (`StateManager.apply_turn`).

`intent.py:detect_route` — sticky `buying` vs `browsing` from keyword signals + price + constraint count.

`clarification.py:ClarificationEngine.decide` — wildcard-first `ask_attribute="other" (what else matters?)` up to 3×, then entropy over pool value distributions (tier1 `material,color,budget,style,size` > tier2 `category,brand`).

State: `ConversationState.constraints:dict, asked_attributes:list, history:list[Turn(informative)], route, user_profile{preference_tags}`.

---

## 5. Benchmarks — What to Beat

### 5.1 Hackathon Official Public Set — 200 Sessions (`results.json`, `python -m evaluator.local_evaluator`)

**Definition** per `docs/evaluation_config.json`: session ends when target `parent_asin` in Top-10 or turn 10. `Hit@10` = hit fraction, `MRR` = mean 1/rank (miss 0), `MTTC` = mean first-hit turn (miss 11), `Efficiency=(11-MTTC)/10`, `TechnicalScore=0.5*Hit+0.3*MRR+0.2*Eff`.

| Split | n | Metric | Weak BM25 starter | **Current (staging-main 6797cc3)** | Δ |
|---|---|---|---|---|---|
| **Overall** | 200 | Hit@10 | 0.125 | **0.805** | +0.68 |
|  |  | MRR | 0.068 | **0.402** | +0.334 |
|  |  | MTTC | 9.81 | **3.93** | -3.9 |
|  |  | Efficiency | 0.119 | **0.707** | +0.588 |
|  |  | **Technical** | 0.106 | **0.665** | +0.559 |
| buying | 80 | Hit/MRR/MTTC | — | **0.913 / 0.425 / 2.58** (before 0.40/0.206) | +0.513 |
| browsing | 80 |  | — | **0.725 / 0.391 / 4.58** (before 0.513/0.285) | +0.212 |
| intent_override | 30 |  | — | **0.800 / 0.427 / 5.23** (before 0.633/0.484 — MRR trade) | +0.167 |
| boundary | 10 |  | — | **0.600 / 0.241 / 5.70** (held) | — |
| Oracle pool | 30 random targets | target-in-pool@200 | 14.3% | **68.2%** | +53.9pp, filter-kill →0 |

Per-session tail available in `results.json:sessions[]` (sample_id, scenario_type, hit, first_hit_turn, best_rank, reciprocal_rank).

Reproduce: `PYTHONPATH=. python -m evaluator.local_evaluator` → `results.json`. Tokens 0 (deterministic, no LLM).

### 5.2 Bench v1.0 — 100 Cases Stratified, No-LLM Arm (`evaluation/BENCH_V1.0.md`, `scripts/bench_v1.py --cases 100 --seed 7`)

Same 100 `parent_asin` every run (seed 7). 5-word insane max (harder than public).

| Tier | n | Description | Before (no-LLM) hit/MRR | **After rework** hit/MRR | Δ |
|---|---|---|---|---|---|
| easy | 10 | feature-rich+high-rated, `"looking for {title}"` | 1.00/0.95 | 1.00/0.85 | — |
| medium | 10 | categories+features+budget | 0.90/0.85 | 0.90/0.68 | — |
| hard | 30 | vague+NO_PREFERENCE+under $30 | 0.833/0.542 | **0.933/0.621** | +0.10 |
| insane | 50 | 5-word max, sparse, hypoallergenic hooks | 0.24/0.137 | **0.34/0.188** | +0.10 |
| **overall** | 100 |  | 0.56/0.411 avg_lat 686ms p50 495ms | **0.64/0.434** | +0.08 |

Fake-LLM arm (offline plumbing): overall 0.66/0.481 — insane unchanged 0.34.

**Lesson:** insane bottleneck is retrieval — 76% targets never in top-200 for reranker → LLM adds 0 hit despite 8.2s LLM (`BENCH §5`). Multi-query fixed 14→68% pool.

### 5.3 Live LLM Bench (optional, not required)

Same 100 cases with real provider (`--live --model nvidia/nemotron-3-super-120b-a12b:free`): no-LLM 0.56/0.406, fake-LLM 0.57/0.421, real LLM 0.56/0.406 avg_llm 8250ms wall 195s (batched workers=8). Proves heuristic Pareto-optimal on insane unless retrieval fixed first. Pricing: `gpt-4o-mini 0.15/0.60 $/1M`, `gemini-3.7-flash 0.10/0.40`.

Run matrix:
```bash
pytest -q  # 162 passed, 1 deselected
python -m evaluator.local_evaluator
python scripts/run_oracle_eval.py --strategy both --cases 30 --seed 7  # pool@200
python scripts/bench_v1.py --cases 100 --workers 8 --json out.json
python scripts/evaluate_ranking_ab.py  # heuristic vs identity
```

### 5.4 Test Suite (162)

`tests/test_state.py`, `test_intent_override.py`, `test_clarification_adaptive.py`, `test_compound_constraints.py`, `test_multi_query.py`, `test_soft_filters.py`, `test_retrieval.py`, `test_ranking.py`, `test_deterministic_ranking.py`, `test_readiness.py`, etc. All green on staging.

---

## 6. Speed & Cost Envelope

- 60-270 ms/turn deterministic (`BENCH p50 452-525ms` for 6-turn case). Budget unlimited but judge on feasibility (15% weight). Semantic `MiniLM-L6-v2` 80MB in-memory, no external vector DB.
- LLM rerank only top 30 (`rerank_limit`), 5s timeout, fallback heuristic, `usage {prompt_tokens,completion_tokens}` surfaced.

---

## 7. Open Gaps for the Next AI to Exploit

1. **Pool 68→100%** — category synonym map (`sneakers↔shoes`), material multi-word (`stainless steel`), dense `MiniLM` vs hashed TF-IDF, expanded synonym 4th query.
2. **Hit@5/Hit@3** — currently only Hit@10 scored; early hits often rank 3-6 (MRR 0.402). Tighten `ConstraintAwareRanker` weights via `run_experiment --grid ranking.deterministic.*`.
3. **Selective LLM gate** — heuristic margin <0.15 or pool>80 low coverage → LLM. Gate threshold learning on `dev_split 160` to hit 20-30% trigger, `Phase2.md` draft.
4. **Boundary 0.60 flat** — `NO_PREFERENCE` handling wastes turns when pool sparse; tune `clarification.min_candidates_before_recommend`.
5. **Intent override MRR drop** — keeping old constraints helped Hit but hurt MRR 0.484→0.427; per-field decay `0.9^turn` for `personalization_boost`.

---

## 8. File Pointers

- Filters: `neeshops/retrieval/filters.py:170`, `neeshops/ranking/features.py:52`, `neeshops/retrieval/hybrid.py:127`, `neeshops/config/default_strategy.json:filters`
- Contracts: `docs/agent_api_contract.json`, `docs/neeshops/INTEGRATION_CONTRACTS.md`, `docs/evaluation_config.json`, `docs/baseline_results.json`
- Scores: `results.json`, `evaluation/BENCH_V1.0.md:71`, `p2readme.md §7b`, `docs/neeshops/EXPERIMENTS.md`
- Run: `evaluator/local_evaluator.py`, `scripts/bench_v1.py`, `scripts/run_oracle_eval.py`, `scripts/evaluate_ranking_ab.py`

Give this file plus `phase2.md` to any AI — it has the exact inequalities, thresholds, and scores to optimize.
