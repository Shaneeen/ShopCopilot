# Miss reading — intent_override + boundary on dev-160

**Control:** fresh `runs/control-dev-forkpoint.json` = instrumented dev-160 run at forkpoint
HEAD 80eee9a (the pre-existing file was a public-200 artifact; backed up to
`runs/control-dev-forkpoint.public200.bak.json`).

Control panel (dev-160): Hit **0.88125** (141/160), MRR 0.4430, MTTC 3.319.
Override 22 sessions (17 hit / 5 miss) · boundary 7 sessions (4 hit / 3 miss).

Method: for every miss session, the hidden intent card was materialized (deterministic
seed) and the session replayed through the real `NeeShopsAgent`, dumping per-turn user
message, extracted constraints, stale bucket, AND-set, coverage and ranked rank. The
transcripts below are the replayed ones; the control JSON's per-turn rank records agree.

## The boundary "handled late" hypothesis is WRONG

The boundary customer's first reply is `"I don't have a preference for {attribute};
please use your judgment."` (asked="other" → wildcard). `_slot_value` already maps it to
`other=NO_PREFERENCE` **on the same turn** (T2 extraction), and the clarification engine
`_wildcard_available()` checks `state.constraints.get("other")==NO_PREFERENCE` — so the
wildcard is **never re-asked** (T2 asks budget, not other; confirmed in all 3 boundary
misses). There is NO wasted re-ask after the boundary handshake. The phrasebook is
already complete (`_NO_PREFERENCE_PATTERNS` includes "don't have a(n)" + "use your
judgment"). §6.2.3 was right: no extraction residue.

What actually loses the boundary sessions is a **route flip + rank-depth death**:

- T1: browsing opener → route=browsing, wildcard asked.
- T2: boundary handshake marks `other=NO_PREFERENCE`. The handshake text
  `"I don't have a preference for other"` contains **"preference"** and **"don't have"**
  — `detect_route`'s browsing-override only fires when `constraint_count==0`, but the
  opener already set category (+style in public_0112), so `constraint_count>0`; the
  handshake's other tokens ("for", "use") outvote browsing → **route flips
  browsing→buying at T2** (replay: T2 route=buying in all 3 boundary misses).
- From T2 on the session runs as **buying** (semantic-heavy weights, price/constraint
  signals), but the user has only category + NO_PREFERENCEs + a couple of card values.
  The target's retrieval rank is 46–264 all session; the AND set stays 623–50,000; the
  top-10 is dominated by unrelated pool-head items. The `exhausted` gate (5 questions
  spent) fires at T6 and the agent never recovers — no constraint ever gets the target
  into the top-10.

So the boundary losses are: **route flip to buying on the handshake + the target never
reaching rank ≤10** (rank-depth miss), NOT a phrasebook/timing miss.

## The override "lag / spurious re-ask" hypothesis is WRONG too

The override message is `"Actually, ignore my earlier preference. What I need is: X."`
The extraction applies **same-turn** via `_preview_state` (the AND set changes on the
override turn itself; no one-turn lag). The override is NOT re-asked (the handshake only
applies to boundary). The actual loss in every override miss is:

**The customer's post-override answers are all "I don't have an additional preference for
{F}."** — the agent asked budget/size/style/color (never the override value), and the
customer had no more card values to disclose. `customer_reply` discloses card values
only when `classify_constraint(value) == asked_attribute`; the override's `new_value`
(=hard_constraints[0]) was already disclosed inside the override message and there are
no OTHER values classified into budget/size/color/style. So all 4 post-override turns
return NO_PREFERENCE, the AND set never shrinks, and the target sits at pool rank 18–155
forever. The agent stops asking at T6 (exhausted) and recommends the same wrong top-10.

| session | target | override new | pre-override top-10 | post-override target rank | final |
|---|---|---|---|---|---|
| public_0003 | B09YMTWDXJ | Water Resistant | T2 rank 6 | ~52–57 | miss |
| public_0004 | B07C2XPZ6D | polyester | T1 rank 10 | ~18–30 | miss |
| public_0078 | B0C5RLJDSF | cotton | T2 rank 3 | ~14–16 | miss |
| public_0096 | B074K2QX3M | polyester | never | 44–155 | miss |
| public_0052 | B09G2ZNZY4 | polyester | never | 17–22 | miss |
| public_0125 | B07VCYFB5D | 100% Acrylic | never | pool rank 1, but never top-10 | miss |

The three "override_not_yet_delivered" (0003/0004/0078) have the SAME shape as the
other three: the target WAS in top-10 pre-override, and post-override it is stuck at
rank 14–57. The difference is only which turn the override happened to land.

**Why does the target DROP out of top-10 after the override when the override re-states
the very value the target satisfies?**
1. The override message re-states `new_value` as an explicit constraint (feature/material).
   Its tokens were already in the accumulated query, so retrieval is unchanged — but the
   RANKING now applies the new constraint's coverage AND the stale bucket's weak weight,
   reordering the pool. The target's coverage is complete (cov=3/3, 2/2 in every replay)
   — so the drop is NOT a filter/coverage kill.
2. The post-override turns (T4–T6) add NO_PREFERENCEs, which **exclude the stale
   buckets from filters but do not shrink the AND set** — the AND set stays 652/4189/
   3700 and the target's pool rank stays 14–57. The ranker keeps the same wrong order.

So the real override killer: **after the override, the agent wastes 3–4 turns asking
attributes the customer has no values for, then exhausts** — the target is in the pool
at rank 14–57 (never in top-10). The questions themselves aren't "spurious re-asks of
the override" — they're genuinely uninformative because the customer has NOTHING left
to disclose.

## Categorization (all 8 misses, 22 override + 7 boundary)

| # | Sessions | miss_type | Actual root cause |
|---|---|---|---|
| 1 | public_0003, public_0004, public_0078 | override_not_yet_delivered | Override lands, target in pool at rank 14–57, top-10 lost → never recovers; post-override questions all return NO_PREFERENCE and exhaust the budget |
| 2 | public_0096, public_0052, public_0125 | rank | Same shape, but target never had top-10 rank at all; stuck at pool rank 17–155; post-override no-preference answers exhaust the budget |
| 3 | public_0112, public_0187, public_0180 | rank/pool | Boundary: route flips browsing→buying at T2 on the handshake; target retrieval rank 46–264; never reaches top-10; wildcard correctly disabled (no re-ask) |

None of the 8 misses is a one-turn extraction lag or a re-ask after route flip. The
system extracts override values and boundary no-preferences **on time**. The common
thread is:

- **The agent runs out of questions (max_questions_per_session=5, with 2 wildcards
  already spent) while the customer has nothing left to disclose, and the target is
  stuck at pool rank 14–264** — the ranker never promotes it into the top-10.

## Fix implications

- **Task 2 (boundary phrasebook):** the extraction-time phrasebook is already present
  and correct. There is no residue to fix in constraints.py. The boundary losses are
  rank/retrieval-depth, not extraction.
- **Task 3 (override):** the specific pattern found is *post-override question budget
  exhaustion*: after the override turn, the wildcard is used up (2 asks), the engine
  asks budget/size/style/color — each answered NO_PREFERENCE — and the 5-question cap
  hits at T6, freezing a pool where the target sits at rank 14–57. A minimal fix:
  after an intent override, do not burn budget/attribute questions the customer has
  no values for — i.e. treat the override turn's re-stated value as "everything else
  is noise" and stop asking (or stop asking budget/size/color/style) once the
  post-override state is pinned by the override value. That would save 3–4 turns
  and re-rank sooner — but it does NOT by itself put a rank-57 target in the top-10.

**Bottom line:** the hypothesis (extraction/state-handling lag, spurious re-asks after
route flip, override arriving during the confident gate) does NOT match the forensics.
The misses are rank-depth losses after the override/boundary handshake, with the
post-override question budget burning on uninformative no-preference answers. Any fix
that targets "handle boundary/override phrases earlier in extraction" will not move
these sessions; the lever is either (a) stop asking once the customer has no more
values, or (b) improve post-override ranking so a rank-14–57 target reaches the top-10.
