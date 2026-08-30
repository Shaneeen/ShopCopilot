# P3B Integration Notes

## Files changed

- `neeshops/personalization/profile.py`: compatible scoring refactor, confidence gating, conservative concepts, explainability.
- `neeshops/personalization/__init__.py`: exports the optional explanation helper.
- `tests/personalization/`: focused scoring and API compatibility tests.
- `scripts/evaluate_personalization_weights.py`: isolated weight simulation and diagnostic exports.
- `evaluation/results/`: generated evaluator outputs when the sweep is run.
- `docs/P3B_PERSONALIZATION.md` and this file: behaviour and handoff.

## 3A contract

```python
boost = personalization_boost(product_row, state.user_profile)
```

The import, product-first argument order, return type, and `[0, 1]` bound are unchanged. 3A does not need to change its ranker, blend formula, weight, rerank limit, or LLM reranker. The evaluator makes isolated copies of strategy configuration and never edits 3A defaults.

The measured candidate weight is 0.20 (dev MRR +0.011696; Hit@10 and MTTC also improved), but its bootstrap interval crosses zero and it caused eight capped rank regressions. It is advisory only. 3A owns whether to adopt it after held-out review.

## P1 / P2 / P4 / P5

- P1: existing profile dictionaries/models are consumed; missing fields are safe. No state/schema change is requested.
- P2: the hook is retrieval-agnostic and runs after existing filtering. Evaluation labels targets outside the observable top 10 rather than claiming personalisation can repair retrieval absence.
- P4: CSV files provide sweep and breakdown tables; `personalization_evaluation.json` contains the complete structured result; Markdown files support review.
- P5: default execution is pure local Python with no network, LLM, database, embedding, service, environment variable, or new dependency.

## Merge and compatibility risk

No shared ranker, retrieval, conversation, evaluator, API, model, or configuration file was modified. The only existing runtime files changed are within `neeshops/personalization/`. Merge risk is therefore limited to concurrent edits of that owned module.

## Important interpretation

The public evaluator records only the rank of a successful target inside the returned top 10. It does not expose full candidate rank. Diagnostics therefore use 11 solely as a capped sentinel for top-10 entry/exit movement and say so in every generated report. Constraint-richness cuts consume the evaluator's existing intent card; no intent parser was invented.
