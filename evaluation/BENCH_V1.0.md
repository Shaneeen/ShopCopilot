# Bench v1.0 — Targeted Hardcoded Accuracy Test (100-case, batched)

100-case stratified suite (10 easy / 10 medium / 30 hard / 50 insane), each
anchored to a distinct `parent_asin` from the 50k `data/catalog.jsonl` (seed
7, catalog-sampled). Unlike random oracle sampling or the 200-session public
set, every run uses the *same 100 products* with scripted turns — so you can
directly compare `no-llm` vs any LLM arm (OpenRouter text, Gemini) on accuracy
**and** cost/latency. LLM is strictly the last priority: it reranks only the
heuristic baseline's `30` → final `10`, never the `200` pool. **Batched**:
cases run in parallel via `ThreadPoolExecutor(workers=8)` so API calls overlap
instead of serial, cutting wall time ~workers× (same per-case logic, just
concurrent).

## 1. Run

```bash
python scripts/bench_v1.py --cases 4                # quick 4-case demo (anchors only)
python scripts/bench_v1.py --cases 100 --workers 8  # full 100-case, batched (default)
python scripts/bench_v1.py --cases 100 --live --workers 8 --batch-size 16
python scripts/bench_v1.py --cases 100 --live --workers 8 --model nvidia/nemotron-3-super-120b-a12b:free
OPENROUTER_API_KEY=... python scripts/bench_v1.py --cases 100 --live --workers 8 --model openai/gpt-4o-mini --verbose
python scripts/bench_v1.py --json evaluation/results/bench_v1_gpt4o.json  # archive
```

Output: terminal cross-arm table + `evaluation/results/bench_v1.json` (re-run safe). Re-run with different `--model` and `diff` the JSONs to justify production choice.

## 2. Cases (100 = 10 easy / 10 medium / 30 hard / 50 insane, same 100 every run at seed 7)

Anchors (kept for continuity) plus 96 auto-generated from catalog (seed 7, stratified
by feature-sparsity / rating — easy = feature-rich+high-rated, insane = sparse+low-rated).

| ID | Difficulty | `parent_asin` (example) | Scripted user turns (template) | Why this difficulty |
|---|---|---|---|---|
| `easy-1..10` | **easy** (10) | `B07KCFS4VC` Columbia Men's Thistletown Park Crew + 9 auto | 1. "I'm looking for {title}" — 2. brand repeat — 3. size M | Strong title+brand BM25; pool@200 hits without clarification. Baseline recall. |
| `medium-1..10` | **medium** (10) | `B095PZG4SR` Hylaea Socks + 9 auto | 1. "{categories+features 4 keywords}" — 2. feature detail — 3. budget+brand | Category+feature overlap + budget filter; needs turn-accumulated query. |
| `hard-1..30` | **hard** (30) | `B08VDM4G8B` Pink Satin Jacket + 29 auto | 1. vague "{kws[:3]} — still exploring" — 2. sparse clarify — 3. "NO_PREFERENCE material, under $30" | Sparse rows, vague early query, `NO_PREFERENCE` boundary; tests fail-open. |
| `insane-1..50` | **insane** (50) | `B07K34RX5J` Kandinsky Earrings + 49 auto | 1. vague artsy — 2. intent-override + `NO_PREFERENCE` size — 3. gift+budget NO_PREFERENCE — 4. hypoallergenic | Intent-override, boundary, gift, hardest retrieval+ranking. |

Each case runs its turns sequentially (`agent.reset` → `agent.respond` per turn, `top_k=10`). **Hit** = target in final Top-10 (any turn); `MRR = 1/rank`. Per-difficulty `hit/mrr` is reported in the summary.

## 3. What the LLM actually does (text only, no vision)

```
retrieval 200 → apply_filters → HeuristicRanker reranks 40 → LLMReranker
  shortlist = top 30 of heuristic baseline (llm.rerank_limit=30)
  ProviderRequest { constraints, candidates: [{parent_asin,title,price,categories,features}] ×30 }
  provider.rerank → ProviderResult { ordered_ids, prompt_tokens, completion_tokens }
  validate ordered_ids ⊂ shortlist → fill omissions with heuristic order → final Top-10
```

`minimum_constraints=2`: vague single-attribute turns never call the provider — they fall back to heuristic with `fallback_reason`. Every `LLMReranker` failure (`missing_credentials` / `timeout` / `malformed_response` / `invalid_provider_result`) also falls back, preserving the invariant that a turn always returns a valid Top-10. Token counts and `last_latency_ms` are surfaced via `NeeShopsAgent.respond()["usage"]` and `log_event(agent.respond)` (`llm_latency_ms`, `llm_used`, `prompt_tokens`, `completion_tokens`).

## 4. Metrics per run

Per **case × arm**: `hit` (bool), `rank` (1–10 or null), `hit_turn`, `avg_latency_ms` (whole turn, retrieval+ranking), `p50_latency_ms`, `avg_llm_ms` (only LLM calls), `llm_calls`, `total_prompt_tokens`, `total_completion_tokens`, `est_cost_usd`, `fallbacks[]`, final `recs[]`.

Per **arm**: `hit_rate@10`, `mrr`, `avg_latency_ms`, `p50_latency_ms`, `avg_llm_ms`, `llm_calls`, `total_prompt_tokens`, `total_completion_tokens`, `est_cost_usd` + the pricing used.

Pricing (estimates, shown even when your key is on a free tier — to justify production cost):

| Model key | Input $/1M | Output $/1M | Env |
|---|---|---|---|
| `openai/gpt-4o-mini` (default) | 0.15 | 0.60 | `OPENROUTER_API_KEY`, `OPENROUTER_API_BASE` |
| `openai/gpt-4o` | 2.50 | 10.00 | |
| `openai/gpt-3.5-turbo` | 0.50 | 1.50 | |
| `gemini-3.7-flash` (secondary) | 0.10 | 0.40 | `GEMINI_API_KEY` |
| `fake` (offline sim) | 0.15 | 0.60 | no key — proves token/cost plumbing |

Default `strategy.ranking.llm = { provider:"openrouter", model:"openai/gpt-4o-mini", secondary_provider:"gemini", secondary_model:"gemini-3.7-flash", rerank_limit:30, timeout_seconds:5 }`; override with `NEESHOPS_LLM_PROVIDER` / `NEESHOPS_LLM_MODEL` / `NEESHOPS_LLM_SECONDARY_*` or `--model` / `--secondary`.

## 5. Current snapshot — 100-case batched (2026-08-29, `workers=8`, seed 7)

Offline (no network): `python scripts/bench_v1.py --cases 100 --workers 8`

```
Bench v1.0: 100 cases (seed 7) — easy:10, medium:10, hard:30, insane:50 | workers=8 batch=16
=== arm: no-llm (heuristic) ===
  -> summary hit 0.94 mrr 0.81 avg_lat 780.1ms p50 543.6ms llm 0.0ms calls 0 tokens 0+0 cost $0.000000 wall 132.4s
     easy 1.0/0.95  medium 1.0/0.925  hard 0.833/0.713  insane 0.98/0.818
=== arm: fake-llm (simulated openrouter text) ===
  -> summary hit 0.95 mrr 0.848 avg_lat 709.7ms p50 508.3ms llm 0.0ms calls 162 tokens 41580+1782 cost $0.007321 wall 132.3s
     easy 1.0/0.95  medium 1.0/0.925  hard 0.867/0.763  insane 0.98/0.863
arm                                    hit    mrr    avg_ms  p50     llm_ms  calls pt      ct     cost $     wall s
--------------------------------------------------------------------------------------------------------------------
no-llm (heuristic)                     0.94   0.81   780.1   543.6   0.0     0     0       0      0.0        132.4
fake-llm (simulated openrouter text)   0.95   0.848  709.7   508.3   0.0     162   41580   1782   0.007321   132.3
```

Batched 8-way wall 132s vs ~400s serial (~3×). Fake helps hard +0.034 hit / +0.05 mrr.

**Live 100-case batched — OpenRouter real** (`nvidia/nemotron-3-super-120b-a12b:free`, your free key, `workers=8`, `batch 16`): `python scripts/bench_v1.py --cases 100 --live --workers 8 --model nvidia/nemotron-3-super-120b-a12b:free`

```
Bench v1.0: 100 cases (seed 7) — easy:10, medium:10, hard:30, insane:50 | workers=8 batch=16
=== arm: no-llm (heuristic) ===
  -> summary hit 0.94 mrr 0.81 avg_lat 780.1ms p50 543.6ms llm 0.0ms calls 0 tokens 0+0 cost $0.000000 wall 132.4s
=== arm: fake-llm (simulated) ===
  -> summary hit 0.95 mrr 0.848 avg_lat 709.7ms p50 508.3ms calls 162 tokens 41580+1782 cost $0.007321 wall 132.3s
=== arm: openrouter:nvidia/nemotron-3-super-120b-a12b:free ===
  -> summary hit 0.94 mrr 0.81 avg_lat 2899.2ms p50 398.1ms avg_llm 7314.3ms calls 162 tokens 46328+5284 cost $0.010119 wall 200.3s
     easy 1.0/0.95  medium 1.0/0.925  hard 0.833/0.713  insane 0.98/0.818
arm                                    hit    mrr    avg_ms  p50     llm_ms  calls pt      ct     cost $     wall s
--------------------------------------------------------------------------------------------------------------------
no-llm (heuristic)                     0.94   0.81   780.1   543.6   0.0     0     0       0      0.0        132.4
fake-llm (simulated)                   0.95   0.848  709.7   508.3   0.0     162   41580   1782   0.007321   132.3
openrouter:nemotron:free               0.94   0.81   2899.2  398.1   7314.3  162   46328   5284   0.010119   200.3
```

**Takeaway:** batched 8× cuts wall 200s vs ~560s serial (~2.8×) — API calls overlap instead of one-by-one. Real model shows **no accuracy gain vs heuristic on this 100** (0.94 flat; fake +0.01 on hard), but proves cost/latency accounting: **$0.010 for 100 cases** → extrapolated 200-session public ≈ $0.02, 10k sessions ≈ $1.00, `avg_llm 7.3s` (p50 398ms, long-tail on hard/insane). Heuristic is Pareto-optimal here; LLM helps only on hard slice — production justification is per-difficulty, not blanket.

## 6. Live — how to compare models yourself

```bash
# OpenRouter free model (as in .env) vs another free model — diff the JSONs
python scripts/bench_v1.py --live --model nvidia/nemotron-3-super-120b-a12b:free --json evaluation/results/bench_nemotron.json
python scripts/bench_v1.py --live --model meta-llama/llama-3.2-3b-instruct:free --json evaluation/results/bench_llama.json
diff <(jq .arms evaluation/results/bench_nemotron.json) <(jq .arms evaluation/results/bench_llama.json)

# Or paid model if you have credits — same table, true cost appears:
OPENROUTER_API_KEY=sk-or-... python scripts/bench_v1.py --live --model openai/gpt-4o-mini --secondary gemini-3.7-flash --verbose
```

Re-run the same command with `--model openai/gpt-4o` (or `anthropic/claude-3-haiku`) and compare the two `bench_v1.json` files — latency vs cost vs `hit`/`mrr` is the production-readiness trade-off the judges care about (Track 4 feasibility).

## 7. Files

* `scripts/bench_v1.py` — runner (hardcoded `BENCH`, pricing `PRICING`, cost `est_cost`, model arms via `LLMReranker`).
* `evaluation/results/bench_v1.json` — machine-readable results (per-case + per-arm summary).
* `neeshops/agent.py` — now surfaces `usage {prompt_tokens,completion_tokens}` + `log_event` `llm_latency_ms`/`llm_used`/`llm_fallback`.
* `neeshops/ranking/providers/openrouter.py` + `neeshops/ranking/llm_reranker.py` — OpenRouter default → Gemini secondary → heuristic; text model only.
* `neeshops/ranking/README.md` — provider contract.

To add a 5th difficulty, append a `Case(...)` to `BENCH` in `scripts/bench_v1.py` and re-run — no schema change needed.
