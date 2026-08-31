AGENTS.md — ShopCopilot experiment worktree rules
Read first
Read docs/V3.md in full before any task. It is the only handover.
Baseline (public 200): Hit@10 0.870, MRR 0.4455, MTTC 3.465, TechnicalScore 0.7193.
runs/control-dev-forkpoint.json is the unmodified control run on dev-160. All comparisons are against it.
Hard rules (violations invalidate the experiment)
NEVER edit anything under evaluator/ — it is frozen.
Every new key in neeshops/config/default_strategy.json MUST be registered inresearch/experiment.py::SAFE_PARAMETERS. tests/test_config_registered.py enforces this.
NEVER stage or commit: .env, data/, evaluation/results/bench_.json,evaluation/results/instrumented_results.json.
Tune ONLY on data/dev_split.jsonl (160 sessions). NEVER tune on the 200-sessionpublic set or the holdout — those are confirmation-only.
Stay on this branch. Do not checkout other branches, do not merge, do not touchother worktrees or the main checkout.
One logical change per commit. Run pytest -q (expect 248 pass) before every commit.
After every evaluated change: cp evaluation/results/instrumented_results.json runs/dev-$(git rev-parse --short HEAD).jsonthen commit that snapshot.
If a change regresses dev scores, revert it (git revert) rather than stackingcompensating fixes on top.
Ask before deviating from the task spec.
How to judge results
Aggregate Hit differences under ~3pp on 160 sessions are noise. The signal ispaired per-session flips vs control: how many miss→hit, how many hit→miss.
Report flips with session ids so a human can verify.
Reporting format (end of every task)
Commits made (shas + one-line each)
pytest status
dev-160 Hit / MRR / MTTC
Paired flips vs runs/control-dev-forkpoint.json: miss→hit count, hit→miss count, session ids
