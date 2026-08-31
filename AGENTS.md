AGENTS.md — ShopCopilot experiment worktree rules
Read first
Read docs/V3.md in full before any task. It is the only handover.
Baseline (public 200): Hit , MRR , MTTC , TechnicalScore ← paste post-merge numbers
runs/control-dev-newbaseline.json is the unmodified control at the new-baseline fork point (dev-160). All comparisons are against it.
Hard rules (violations invalidate the experiment)
NEVER edit anything under evaluator/ — it is frozen.
Every new key in neeshops/config/default_strategy.json MUST be registered in research/experiment.py::SAFE_PARAMETERS. tests/test_config_registered.py enforces this.
NEVER stage or commit: .env, data/, evaluation/results/bench_.json, evaluation/results/instrumented_results.json.
Tune ONLY on data/dev_split.jsonl (160 sessions). NEVER tune on the 200-session public set or the holdout — those are confirmation-only.
Stay on this branch. Do not checkout other branches, do not merge, do not touch other worktrees or the main checkout.
One logical change per commit. Run pytest -q (expect 325 pass) before every commit.
After every evaluated change: cp evaluation/results/instrumented_results.json runs/dev-$(git rev-parse --short HEAD).json then commit that snapshot.
If a change regresses dev scores, revert it (git revert) rather than stacking compensating fixes on top.
Ask before deviating from the task spec.
Before ANY comparison, verify the control snapshot: exactly 160 sessions and the expected hit count (python -c "import json; d=json.load(open('runs/control-dev-newbaseline.json')); print(len(d['sessions']), sum(s['hit'] for s in d['sessions']))"). A wrong or stale control invalidates every paired comparison — this bit round 1.
How to judge results
Measured reproducibility: independent control runs agree on 159/160 sessions → ±1 session (≈0.6pp Hit) is run jitter. Aggregate Hit differences under ~3pp on 160 sessions are noise, and single-session MRR deltas are jitter — report them as such. The signal is paired per-session flips vs control, with session ids.
Report flips with session ids so a human can verify.
Reporting format (end of every task)
Commits made (shas + one-line each)
pytest status
dev-160 Hit / MRR / MTTC
Paired flips vs runs/control-dev-newbaseline.json: miss→hit count, hit→miss count, session ids
