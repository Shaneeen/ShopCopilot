# ShopCopilot — Final Pitch Kit

Build notes for the final-event pitch. Every number below is measured on the frozen
official evaluator (200 public sessions) or the instrumented panel — no projections.

---

## 1. One-liner

> **The best shopping agent does not maximize retrieval quality per turn — it maximizes
> information gained per turn.** Every question our agent asks is chosen by expected
> candidate-space collapse, computed *exactly* on an in-memory inverted index — no LLM,
> no sampling, deterministic under the full constraint set.

## 2. Story arc (60 seconds)

1. **Problem.** Conversational commerce punishes two failure modes: asking questions
   that don't narrow anything, and recommending from a candidate set the target may not
   even be in. Keyword search does neither well — the weak BM25 starter converts in 9.8
   turns and hits 12.5%.
2. **Insight.** A question is valuable iff it collapses the candidate space toward the
   purchase. That value is *computable exactly* when you can enumerate the constraint
   set — you don't need an LLM to guess uncertainty you can calculate.
3. **System.** Exact-recall guarantee pool (Boolean inverted index, 50k docs / 95.5k
   terms) → coverage×IDF×salience deterministic ranking → an 8-gate precedence policy
   that decides, per turn: ask, recommend, or stop.
4. **Proof.** Hit@10 0.870, MRR 0.4455, MTTC 3.465, TechnicalScore 0.7193 — a 6.7×
   TechnicalScore over the official baseline — with zero external services in the scored
   path and 248 passing tests.
5. **Discipline.** We built the LLM tier, gated it, measured it, and killed it on data.
   Every remaining improvement is ranked by score-value math, not novelty appetite.

## 3. Numbers sheet

**Official evaluator, 200 public sessions** (`python -m evaluator.local_evaluator`):

| Metric | Official baseline | Ours (v2) | Δ |
|---|---|---|---|
| Hit Rate@10 | 0.125 | **0.870** | +74.5pp |
| MRR | 0.068 | **0.4455** | +37.8pp |
| MTTC | 9.81 | **3.465** | −6.35 turns |
| TechnicalScore | 0.10671 | **0.7193** | 6.7× |

By scenario (v1 → v2): buying **0.875** (−3.8pp, known miss class), browsing
**0.900** (+17.5pp), intent_override **0.800** (=), boundary **0.800** (+20pp).

**Structural stats** (instrumented panel, same sessions):

- Over-generality is the *normal regime*: AND set >200 in **195/200 sessions**
  (avg final AND set ≈ 3,317 candidates) — this is why exact enumeration matters.
- Guarantee-pool membership at score time: **84.12%** → misses are **rank-class**
  (rank 25 / pool 2 / extraction 2 / late-override 3 of 32 misses), not pool-class.
- Avg 2.285 questions per session; p50 230.6 ms / p95 375.7 ms per turn.
- Pool-miss forensics at n=300: **94.7% clean** — residual self-heals via backoff.
- 248 tests passing; `evaluator/` untouched; catalog strictly read-only.

## 4. "We experimented" — the evidence log

The section judges reward. Each experiment: hypothesis → measurement → decision.

**E1 — Extraction ablations paid for the whole accuracy tier.**
Category capture stopping at commas: **+14.5pp Hit** from one regex boundary fix.
Retrieval-score minmax normalization: **+1.5pp** alone. Enabling the 4th question:
**+0.5pp**. Lesson: in a frozen-harness world, precision of constraint extraction
dominates model choice.

**E2 — Miss forensics told us where the remaining 13% lives.**
Instrumented every scored turn: 84% pool membership, rank-class misses dominate.
Decision: attack ranking order and rerank windows (padding by coverage×idf,
rerank_floor 40→60 for buying), not retrieval breadth. The forensics script is
reproducible: `python scripts/pool_miss_forensics.py --cases 300 --seed 7`.

**E3 — The LLM probe we killed.**
Pre-registered ship/kill gates *before* running: ship only if ΔHit ≥ +0.03 AND
ΔMRR ≥ +0.02 AND trigger ≤30% AND added p95 ≤2s. Live OpenRouter probe (4-anchor,
gpt-4o-mini): **ΔHit = 0, ΔMRR = 0, +454 ms, p95 >2×** — and the fake-LLM upper
bound also showed zero delta on that set. Decision: **kill**; submission stays
deterministic, zero-cost, offline-capable. The tier remains built and gated
(`ranking/llm_reranker.py`) with the decision logged per turn.

**E4 — The CPU wall is a design input, not an excuse.**
TokenIndex builds in 3.5 s for 50k docs; per-case rebuilds and GIL thrash were
measured (workers>1 gives no parallelism for CPU-bound Python — use `--workers 1`);
pseudo-attribute caches cut p50 spikes 798 → 360 ms. Lesson: in-memory constraints
push you toward *computable* structure (inverted index arithmetic) over *learned*
approximations.

**E5 — The harness corrected our own plan.**
The original plan erased state on intent override; the simulator punishes wholesale
erase. We shipped per-value contradiction staling (weight 0.3, re-affirmation
recovers) instead — and tests pin it: personalization never overrides explicit
constraints, override never accumulates both values.

## 5. Related work — citations as ammunition, not blueprints

We verified each candidate paper against our hard constraints (deterministic,
in-memory, CPU-only, frozen evaluator). Verdicts:

| Paper | Verdict | One-line reason |
|---|---|---|
| UoT (NeurIPS'24) | **Cite** | LLM scenario-simulation + reward propagation = 10–20 LLM calls/turn vs our 2 s gate and 0 external calls. Attacks question selection; our misses are rank-class. |
| Ask to Be Sure (CIKM'26) | **Cite** | *Estimates* uncertainty by sampling LLM recommendation lists; we *compute* the candidate distribution exactly. We are the stronger version of the idea. |
| KBQG (SIGIR'21) | **Already built** | "Weight attributes by disambiguation importance" ≈ our coverage×IDF×salience. Zero new code. |
| FacT (CIKM'22) | **Cite** | Our set-splitting entropy gate is a one-step greedy decision-tree split — conditioned on *live* conversation state, which a precomputed static tree loses. |
| Entropy-routing (Gorgias) | **Superseded by our grid** | Ask-vs-recommend routing ≈ our over-generality + margin gates. The `margin_stop × other_max_asks` grid buys the same lever with zero new code. |
| Targeted active learning (Foster) | **P3, behind a measurement gate** | Margin-aware (not set-aware) question selection is genuinely new — but measure first whether misses show "big set collapse, flat top-10 margin" from `instrumented_results.json` before prototyping. |

**The positioning sentence (use verbatim):**

> "Independent convergence with UoT and Ask-to-Be-Sure — but where they *sample*
> uncertainty via LLM calls and *train* policies on dialogue corpora, we compute it
> **exactly** (closed-form AND-set arithmetic on an inverted index) and select
> questions **deterministically with zero LLM**, under in-memory constraints, with an
> 8-gate precedence policy that no single-objective method covers."

Never claim "information-gain questioning" as novel in itself — it is published
territory now. Claim the *exact, deterministic, constraint-complete* instantiation.

## 6. Priority discipline (value math)

- MTTC 3.465 → 3.2 ⇒ ΔEfficiency +0.0265 ⇒ **+0.0053 TechnicalScore**.
- Hit +1pp ⇒ **+0.005 TechnicalScore**. (Both levers are the same size.)

Ordering, all measured-lever-first:

1. **P0 accuracy** — padding×idf + rerank_floor 60 (buying): targets the 25 rank-class
   misses directly. No paper helps here.
2. **P0 speed** — ProcessPool for CPU arms, kill double retrieval, cache semantic
   matrix: makes everything else measurable.
3. **P1 grid** — `margin_stop {0.10,0.15,0.20} × other_max_asks {1,2}` on dev_split 160:
   the cheap version of what entropy-routing papers buy expensively.
4. **P2 LLM re-test** — protocol already written; expect kill, log it.
5. **P3 Foster measurement** — from existing instrumented data; prototype only on signal.

## 7. What NOT to pitch

- "Advanced LLM / vector DB / multi-agent" — out of scope (in-memory rule) and common.
- "We invented information-gain questioning" — falsifiable by a reviewer who knows
  UoT/CIKM'26; use the positioning sentence in §5 instead.
- Any claim without a number from §3 or §4.

## 8. Judge Q&A prep

- **"Why is the LLM off?"** — Built, gated, measured: Δ=0, +454 ms, p95 >2× against
  pre-registered thresholds. Determinism is also a feasibility win: zero cost, zero
  network dependency, reproducible.
- **"Buying dropped 3.8pp — why?"** — Rank-class crowding: the target is in the 84%-
  membership pool but top-10 is decided among ~200 full-coverage AND members. Fix is
  ordering (padding×idf, rerank window), measured on dev_split before shipping.
- **"Why not fine-tune?"** — Out of scope per rules; and our feature weights are
  config-driven (`default_strategy.json`, all keys in SAFE_PARAMETERS) so we sweep
  instead of train.
- **"Does it scale beyond 50k?"** — The index is O(terms); 50k docs / 95.5k terms =
  3.5 s build, ~60–100 MB, all queries O(1) set intersections. Linear in catalog size.
- **"What's your uncertainty estimate vs Bayesian approaches?"** — Exact enumeration
  on the AND-set; sampling is what you do when you can't enumerate. Over-generality
  (195/200 sessions >200) is handled by stride-sampled *plausible-set* entropy only
  where enumeration is the input, not the output.
- **"What would you improve?"** — The known list: buying rerank window, MTTC frontier,
  boundary phrasebook in extraction, evaluator-side 180-char truncation workaround
  (frozen file — documented, not editable).

## 9. Demo script (turn-by-turn trace)

```
Turn 1  candidate space 7,842 → ask "use_case" (7842→612) over "color" (7842→6000)
Turn 2  612 → ask "material" (612→74) over "price" (11%)
Turn 3  74 → target lands top-10 #1 → STOP (confidence 82%, next-question gain +3% not worth a turn)
```

Show: the trace viewer (`scripts/generate_trace_report.py`), then the decision log
showing the LLM gate fire and abstain. End on §4-E3: "we built it, we killed it."
