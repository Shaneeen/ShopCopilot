# Gate Report — Uninformative Stop (exp/uninformative-stop)

## Control verification
- `runs/control-dev-newbaseline.json`: 160 sessions, 144 hits (Hit@10 0.900, MRR 0.5144, MTTC 3.1875)

## Measurement (TASK 1)
Instrumented `scripts/instrumented_eval.py` to count asks that returned no new disclosed value (`NO_PREFERENCE` / "I don't have an additional preference for F") across ALL 160 dev sessions, per session and per route. Detection: `ask_attribute` non-null and next `customer_reply` string contains `no additional preference` or `don't have a preference`.

**Command:**
```
python scripts/instrumented_eval.py --dataset data/dev_split.jsonl --output evaluation/results/instrumented_results.json
```

**Results (dev-160, current code, no stop rule yet):**
- Total wasted asks: **67**
- Wasted mass: **67 / 160 = 0.4188 turns/session**
- Sessions with ≥1 wasted ask: **23 / 160 (14.4%)**
- Distribution: 0:137, 1:3, 2:1, 3:15, 4:3, 5:1
- Per route:
  - buying: 19 wasted / 66 sessions = 0.2879 avg
  - browsing: 12 / 65 = 0.1846 avg
  - boundary: 20 / 7 = 2.8571 avg
  - intent_override: 16 / 22 = 0.7273 avg

Top wasted sessions: boundary 0180(5), 0112(4), 0187(4), 0035(4), intent_override 0003(3), buying 0171(3), etc.

## Gate decision
**PASS** — wasted mass 0.4188 ≥ 0.10 threshold. Ceiling is material; proceeding to TASK 2 (stop-on-exhausted-disclosure).

## Notes
- Panel Hit 145/160 (0.90625) on this measurement run vs control 144/160 — within ±1 jitter band; not a signal.
- MTTC mass represents pure waste: every wasted ask is a turn that could be truncated with no new constraint produced.
