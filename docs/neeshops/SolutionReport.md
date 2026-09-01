# AnythingShops Track 4 Solution and Technical Report

**Challenge:** TikTok TechJam 2026 — Track 4, Shopping Copilot: AI Conversational Search and Recommendations  
**Repository state reviewed:** `master` at commit `8d8822e`  
**Report date:** 1 September 2026

## 1. Executive summary

NeeShops is a deterministic, multi-turn shopping agent built to find a hidden target product within ten conversation turns and place it as high as possible in a Top-10 recommendation list. Our central design principle is:

> The best shopping agent does not only retrieve more products; it asks the question that most reduces uncertainty, then uses every answer immediately in retrieval and ranking.

The system combines:

- Buying/Browsing intent routing and structured multi-turn state;
- field-weighted BM25 retrieval using SQLite FTS5;
- lightweight hashed TF–IDF retrieval with cosine similarity;
- multi-query Reciprocal Rank Fusion (RRF);
- an in-memory Boolean “guarantee pool” for high-recall constraint matching;
- deterministic, constraint-first reranking using coverage, IDF, field salience, retrieval relevance, and popularity;
- an adaptive clarification policy based on candidate-set size, confidence, entropy, prior questions, and the remaining turn budget;
- safe intent-override and `NO_PREFERENCE` handling;
- evaluator-backed experiments, regression tests, diagnostics, and fail-soft fallbacks.

The best measured v2 result on the official 200-session public set was **Hit Rate@10 0.870, MRR 0.4455, MTTC 3.465, and TechnicalScore 0.7193**. The latest audited `master` build prioritizes extraction correctness, complete bounded-pool scoring, and robustness; it measured **0.855 / 0.4382 / 3.59 / 0.7072** in the same metric order. Both substantially exceed the official weak BM25 baseline TechnicalScore of **0.10671**.

The scored submission path is local, deterministic, reproducible, and has no mandatory external service cost. An optional LLM reranker was implemented and measured, but remains disabled because the probe did not improve Hit Rate or MRR and added latency.

## 2. Track 4 objective and evaluation

The official task is to find a hidden catalog product as early and as highly ranked as possible across at most ten turns. The evaluator scores the first ten unique, catalog-valid `parent_asin` values returned on each turn.

The official metrics are:

- **Hit Rate@10:** fraction of sessions in which the target appears in the Top 10;
- **MRR:** mean reciprocal rank of the target, with a miss contributing zero;
- **MTTC:** mean turn to conversion, with a miss counted as turn 11;
- **Efficiency:** `clip((11 - MTTC) / 10, 0, 1)`;
- **TechnicalScore:** `0.50 × HitRate@10 + 0.30 × MRR + 0.20 × Efficiency`.

The scenario mix is 40% Buying, 40% Browsing, 15% Intent Override, and 5% Boundary. The public set contains 200 sessions over a frozen catalog of 50,000 Amazon `Clothing_Shoes_and_Jewelry` products; the organizer retains 800 private sessions for judging. Our implementation leaves the official evaluator and catalog read-only.

## 3. Results

| Build | Hit Rate@10 | MRR | MTTC | Efficiency | TechnicalScore |
|---|---:|---:|---:|---:|---:|
| Official weak BM25 starter | 0.125 | 0.068034 | 9.81 | 0.1190 | 0.10671 |
| 29 Aug P2+P3 rework | 0.805 | 0.4020 | 3.93 | 0.7070 | 0.6650 |
| **Best measured v2** | **0.870** | **0.4455** | **3.465** | **0.7535** | **0.7193** |
| **Latest audited `master`** | **0.855** | **0.4382** | **3.59** | **0.7410** | **0.7072** |

The best v2 TechnicalScore is approximately **6.74×** the official baseline. The latest audited build is approximately **6.63×** the baseline.

These two internal results are shown separately for transparency. The v2 build achieved the highest score. The later audit improved false-constraint extraction and Buying performance, expanded deterministic scoring from an early 40-item window to the full bounded pool, and added crash containment and regression coverage. That wider competition also allowed deep-pool candidates to displace some former Top-10 targets, producing a net two-session regression against the same-environment pre-audit build. This trade-off is documented rather than hidden.

## 4. How the solution satisfies the Track 4 requirements

| Track 4 requirement | Our solution | Evidence in the repository |
|---|---|---|
| 1. Buying vs Browsing routing | Detects the route from intent phrases, explicit constraints, and conversation context. Retrieval weights are config-driven per route. The latest measured configuration uses BM25/semantic weights of 0.7/0.3 for both routes because a semantic-heavy Browsing split regressed on the lightweight hashed TF–IDF index; the architecture still supports independent route settings. | `neeshops/conversation/intent.py`, `neeshops/retrieval/hybrid.py`, `neeshops/config/default_strategy.json` |
| 2. Hybrid retrieval | Runs field-weighted BM25 and hashed TF–IDF/cosine retrieval, forms accumulated/latest/constraint query angles, and fuses ranked lists with weighted RRF. A Boolean token index then creates a high-recall constraint pool. No external vector database is required. | `neeshops/retrieval/bm25.py`, `semantic.py`, `hybrid.py`, `candidate_merge.py`, `token_index.py` |
| 3. Multi-turn state | Stores conversation history, route, explicit constraints, asked attributes, `NO_PREFERENCE`, stale values, inferred values, prior recommendations, and the anonymized user profile. Current-turn evidence is applied through a preview state before retrieval and ranking, avoiding a one-turn lag. | `neeshops/models/session.py`, `neeshops/conversation/state.py`, `neeshops/agent.py` |
| 4. Intent Override | A new explicit value replaces the old value field-by-field; it is never appended as `blue + black`. The contradicted value moves to a weak stale bucket while unrelated valid constraints remain. The override turn is recorded for diagnostics. | `neeshops/conversation/constraints.py`, `state.py`, `tests/test_intent_override.py`, `tests/test_audit_regressions.py` |
| 5. Boundary behaviour | Phrases such as “no preference,” “any material,” or “I do not care about colour” become `NO_PREFERENCE`. Consumed attributes are excluded from future clarification questions. | `neeshops/conversation/constraints.py`, `clarification.py`, `tests/test_constraints.py` |
| 6. Clarification strategy | Uses a precedence-gated policy: exhausted budget → turn guard → confidence check → wildcard questions → over-generality/set-splitting → agreement inference → entropy fallback. It considers candidate-set size, information gain, prior questions, route, and remaining turns. Recommendations are still returned on question turns, so clarification does not sacrifice the current hit opportunity. | `neeshops/conversation/clarification.py`, `neeshops/agent.py`, `tests/test_clarification*.py` |
| 7. Dynamic context/personalisation | Implements a deterministic preference-tag boost over already eligible candidates. Explicit constraint violations are sorted before all relevance and personalization signals, so profile history cannot override the current request. The latest deterministic default disables the personalization feature after measurement; the safe hook and its tests remain available for controlled experiments. | `neeshops/personalization/profile.py`, `neeshops/ranking/features.py`, `deterministic.py`, `tests/test_ranking.py` |

The official API contract is preserved through a thin `starter/agent.py` adapter. It strips internal diagnostics and returns only the allowed `message`, `ask_attribute`, `recommendations`, and `usage` fields.

## 5. End-to-end architecture

```text
Official evaluator
  -> starter/agent.py (strict API adapter)
  -> NeeShopsAgent
       1. extract constraints and detect Buying/Browsing route
       2. update a preview of multi-turn state
       3. build accumulated, latest-turn, and constraint-only queries
       4. retrieve with BM25 + hashed TF-IDF/cosine
       5. combine result lists with weighted RRF
       6. add the Boolean guarantee pool and apply fail-soft filters
       7. rank by hard violations, coverage, relevance, and popularity
       8. decide whether and what to ask next
       9. commit state and return Top-10 recommendations
```

### 5.1 High-recall retrieval

The weak starter relied on one lexical query. NeeShops instead searches three views of the conversation:

1. the accumulated conversation;
2. the latest user message;
3. normalized structured constraints.

For every non-empty view, the agent can run both BM25 and semantic retrieval. Weighted RRF combines the source rankings without requiring incomparable BM25 and cosine scores to share one numeric scale.

The guarantee pool is a separate in-memory inverted index over catalog tokens. It intersects synonym-widened token groups and applies a fail-open budget gate. Exact constraint matches are front-loaded into the candidate pool; greedy backoff relaxes a group only when a strict token intersection is empty. This changed the system from retrieval-only guessing into recall-first candidate construction.

Measured evidence from the v2 work:

- three-angle multi-query RRF increased oracle target-in-pool@200 from **14.3% to 68.2%**;
- the guarantee-pool design reached approximately **84.1% target membership at score time**;
- separate 300-case pool forensics reported **94.7% clean** behavior, with remaining truncation artifacts handled by backoff.

### 5.2 Constraint-first deterministic ranking

Every candidate is evaluated against hard fields such as category, colour, material, size, brand, and budget. Ranking is lexicographic:

```text
(hard-constraint violations ascending,
 constraint coverage descending,
 local relevance descending,
 popularity descending,
 parent_asin ascending)
```

Coverage rewards matched constraint groups by inverse document frequency and field salience, making a rare discriminating match more valuable than a common token. Local relevance blends min-max-normalized retrieval score, title and feature overlap, field matches, inferred context, and optional personalization. The final ASIN tie-break makes repeated runs deterministic.

This ordering enforces an important safety rule: a product that violates an explicit current requirement cannot be promoted above a valid product merely because it is popular or matches the user's historical profile.

### 5.3 Information-efficient clarification

The clarification engine does not ask attributes in a fixed random sequence. It estimates which unasked field best splits the plausible candidate set. For each field it calculates the value distribution, entropy, and expected remaining fraction; homogeneous or unanswerable fields are skipped.

The engine also includes practical gates:

- stop asking once results are sufficiently confident;
- use broad `other` questions early when one reply can reveal multiple constraints;
- when the Boolean AND set is too large, choose the field that best partitions it;
- remember attributes marked `NO_PREFERENCE` and never ask them again;
- stop asking after turn 9;
- return recommendations on every turn, including question turns.

This policy directly targets both retrieval quality and MTTC rather than treating conversation quality as separate from scoring.

### 5.4 Reliability and feasibility

Optional layers fail soft. If semantic retrieval is disabled, absent, stale, or corrupt, the system falls back to BM25. If an optional reranker is unavailable or raises, the agent falls back to the deterministic ranker. Extreme query length is bounded before it reaches SQLite FTS5. Semantic indexes are tied to a catalog SHA-256 so an index built from a different catalog is rejected.

The latest documented suite contains **325 passing tests and one deselected live-service test**. Tests cover API shape, retrieval, ranking, override behavior, boundary phrases, configuration registration, malformed input, stale indexes, personalization safety, and multi-turn reliability.

## 6. Experimentation and improvement process

We treated every major change as a hypothesis to be evaluated, not simply a feature to add.

1. **Measure the untouched baseline.** The official starter established the reproducible reference of TechnicalScore 0.10671.
2. **Instrument failures by stage.** The instrumented evaluator records whether each miss came from extraction, pool membership, ranking, insufficient constraints, or late override delivery.
3. **Change one controlled mechanism.** Retrieval weights, candidate limits, ranking weights, clarification thresholds, and feature flags live in one strategy file.
4. **Evaluate on the development split.** `scripts/create_dev_split.py` produces a reproducible 160/40 development/holdout split to reduce blind optimization against all public labels.
5. **Accept or reject using the real metric.** The research runner only permits declared safe parameters, executes the official evaluator, compares TechnicalScore, and records both accepted and rejected runs.
6. **Pin successful behavior with tests.** Audit regressions cover the exact bugs discovered during evaluation.

Examples of decisions driven by evidence include:

- stopping category extraction at commas removed a major false-constraint class;
- min-max normalization restored retrieval score influence after RRF;
- demoting uncertain metadata mismatches instead of dropping candidates prevented filter-killed targets;
- semantic-heavy Browsing weights were reverted when the lightweight semantic index regressed;
- an intent-override history cut was reverted after override Hit Rate fell from 0.80 to 0.67;
- the optional LLM reranker remained off after a live probe produced no accuracy gain and added roughly 454 ms.

The experiment framework is intentionally bounded: it changes allowlisted configuration values and never rewrites application code or the official evaluator.

## 7. Research papers and how they informed the solution

We reviewed information-retrieval and conversational-search research to identify techniques that fit the challenge constraints: deterministic evaluation, a 50,000-item frozen catalog, low latency, no heavy external vector infrastructure, and a ten-turn interaction budget. The table distinguishes direct implementation from conceptual alignment or future work.

| Research source | Relationship to NeeShops |
|---|---|
| Robertson & Zaragoza, [*The Probabilistic Relevance Framework: BM25 and Beyond*](https://doi.org/10.1561/1500000019), 2009 | **Directly implemented principle.** NeeShops uses BM25 through SQLite FTS5 and adds field weights so title/category evidence can be emphasized over long descriptions. |
| Cormack, Clarke & Buettcher, [*Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods*](https://research.google/pubs/reciprocal-rank-fusion-outperforms-condorcet-and-individual-rank-learning-methods/), SIGIR 2009 | **Directly implemented.** Weighted RRF combines BM25 and semantic rankings across accumulated, latest, and constraint query views. The configured `k` is 60. |
| Salton & Buckley, [*Term-weighting Approaches in Automatic Text Retrieval*](https://doi.org/10.1016/0306-4573(88)90021-0), 1988 | **Directly implemented principle.** The semantic index uses sublinear term frequency, smoothed IDF, L2 normalization, and cosine similarity. The ranker also uses IDF to reward rare constraint matches. |
| Weinberger et al., [*Feature Hashing for Large Scale Multitask Learning*](https://arxiv.org/abs/0902.2206), ICML 2009 | **Directly implemented mechanism.** Catalog tokens are deterministically hashed with BLAKE2b into a fixed 1,024-dimensional TF–IDF space, providing a compact local semantic-like retriever without model downloads. |
| Aliannejadi et al., [*Asking Clarifying Questions in Open-Domain Information-Seeking Conversations*](https://arxiv.org/abs/1907.06554), SIGIR 2019 | **Conceptual guidance.** The paper frames clarification as selecting context-aware questions before retrieving again. NeeShops implements a deterministic catalog-grounded version using conversation state, confidence gates, entropy, and expected set reduction rather than the paper's neural question selector. |
| Ye et al., [*ProductAgent: Benchmarking Conversational Product Search Agent with Asking Clarification Questions*](https://aclanthology.org/2025.emnlp-industry.25/), EMNLP 2025 | **Independent corroboration.** Its closed loop—structured dialogue memory, hybrid symbolic/dense retrieval, candidate feature summaries, and strategic clarification—closely matches our architecture. NeeShops differs by using exact inverted-index arithmetic and a deterministic default path instead of requiring an LLM. |
| Hou et al., [*Bridging Language and Items for Retrieval and Recommendation*](https://arxiv.org/abs/2403.03952), 2024 | **Dataset source and future direction.** This work introduced Amazon Reviews 2023 and BLaIR semantic encoders for complex product search. We use the organizer's frozen derivative of Amazon Reviews 2023, but we do **not** claim to implement BLaIR; a learned product encoder remains a gated future experiment. |

The research did not lead us to add complexity automatically. It helped us form testable hypotheses. Where the local evaluator showed no benefit—most notably the LLM reranking probe—we retained the cheaper deterministic method.

## 8. Technology stack

| Layer | Technology | Use in the solution |
|---|---|---|
| Language/runtime | Python 3.10+ | Agent, evaluator integration, retrieval, ranking, state, experiments, and tests |
| Lexical search | SQLite FTS5 and `sqlite3` | Persistent fielded catalog index and BM25 scoring |
| Lightweight vector retrieval | NumPy | Hashed TF–IDF matrix, L2 normalization, and cosine/dot-product search |
| Data | JSON/JSONL, Amazon Reviews 2023 derivative | Frozen 50,000-product catalog, public sessions, config, and experiment records |
| Configuration | JSON, `python-dotenv` | Strategy weights and optional environment-controlled feature flags |
| Models and validation | Python dataclasses and Pydantic | Typed product, session, recommendation, and configuration boundaries |
| HTTP/provider integration | `requests`, `google-genai` | Optional OpenRouter/Gemini reranking providers; disabled in the default scored path |
| Testing | Pytest | Unit, contract, regression, integration, and reliability tests |
| Experimentation | Custom safe-parameter runner | Grid, random, and scenario-targeted evaluation against the official metric |
| Demo | Static HTML/CSS/JavaScript plus local Python server | Optional visualization and interaction shell; not part of Track 4 scoring |
| Version control | Git/GitHub | Collaboration, reproducibility, and submission repository |

## 9. Reproduction

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# Install the official catalog according to data/README.md, then:
python scripts/setup_catalog.py
python scripts/build_semantic_index.py
python scripts/create_dev_split.py

pytest -q
python -m evaluator.local_evaluator
python scripts/instrumented_eval.py --output evaluation/results/instrumented_results.json
```

Controlled experiment examples:

```bash
python scripts/run_experiment.py --grid retrieval.browsing.semantic_weight 0.3 0.5 0.7
python scripts/run_experiment.py --targeted
python scripts/pool_miss_forensics.py --cases 300 --seed 7
```

The official evaluator, public labels, and catalog must not be edited. API keys are optional and must be supplied only through environment variables; they must never be committed.

## 10. Limitations and next improvements

- The latest audited build trades two public-set hits for broader scoring correctness and stronger robustness. The next evidence-backed ranking experiment is a partial competition window around 100–120 candidates or an explicit retrieval-rank tie-break ahead of popularity.
- MTTC remains above the internal goal of 3.2. A development-split grid over confidence margin and wildcard-question count should identify the best accuracy/efficiency frontier.
- Hashed TF–IDF is intentionally lightweight but weaker than a learned product encoder on paraphrases. A model such as BLaIR or MiniLM should only replace it if held-out gains justify memory, latency, and deployment cost.
- Personalization is conservative and disabled in the latest deterministic default. It should be re-enabled only after a held-out A/B result confirms improvement without violating explicit constraints.
- The public set is small, especially the Boundary subset. Per-scenario changes of one or two sessions should not be presented as conclusive generalization.
- The optional LLM reranker needs a larger difficult-case evaluation before reconsideration; it should remain off unless it clears pre-registered accuracy, latency, and trigger-rate gates.

## 11. Source index

### Official and repository sources

- [Official Track 4 participant repository](https://github.com/TechJam2026/techjam-conversational-search)
- [Amazon Reviews 2023 dataset documentation](https://amazon-reviews-2023.github.io/)
- [`docs/neeshops/TRACK4_REQUIREMENTS.md`](docs/neeshops/TRACK4_REQUIREMENTS.md)
- [`docs/competition_specification.md`](docs/competition_specification.md)
- [`docs/agent_api_contract.json`](docs/agent_api_contract.json)
- [`docs/evaluation_config.json`](docs/evaluation_config.json)
- [`docs/baseline_results.json`](docs/baseline_results.json)
- [`docs/IMPLEMENTATION_V2.md`](docs/IMPLEMENTATION_V2.md)
- [`docs/V3.md`](docs/V3.md)
- [`README.md`](README.md)

### Research sources

- Stephen E. Robertson and Hugo Zaragoza. *The Probabilistic Relevance Framework: BM25 and Beyond*. Foundations and Trends in Information Retrieval, 2009. https://doi.org/10.1561/1500000019
- Gordon V. Cormack, Charles L. A. Clarke, and Stefan Buettcher. *Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods*. SIGIR, 2009. https://doi.org/10.1145/1571941.1572114
- Gerard Salton and Christopher Buckley. *Term-weighting Approaches in Automatic Text Retrieval*. Information Processing & Management, 1988. https://doi.org/10.1016/0306-4573(88)90021-0
- Kilian Weinberger et al. *Feature Hashing for Large Scale Multitask Learning*. ICML, 2009. https://arxiv.org/abs/0902.2206
- Mohammad Aliannejadi et al. *Asking Clarifying Questions in Open-Domain Information-Seeking Conversations*. SIGIR, 2019. https://arxiv.org/abs/1907.06554
- Jingheng Ye et al. *ProductAgent: Benchmarking Conversational Product Search Agent with Asking Clarification Questions*. EMNLP Industry Track, 2025. https://aclanthology.org/2025.emnlp-industry.25/
- Yupeng Hou et al. *Bridging Language and Items for Retrieval and Recommendation: Benchmarking LLMs as Semantic Encoders*. 2024. https://arxiv.org/abs/2403.03952

---

**Submission-ready solution statement:** NeeShops meets Track 4 with a recall-first, constraint-aware conversational search pipeline. It combines lightweight hybrid retrieval, exact in-memory constraint matching, deterministic reranking, and information-efficient clarification while preserving intent overrides, no-preference boundaries, API compliance, reproducibility, and fail-soft operation. Its best measured TechnicalScore of 0.7193 is 6.74× the official weak baseline, achieved without requiring an external LLM or vector database in the scored path.
