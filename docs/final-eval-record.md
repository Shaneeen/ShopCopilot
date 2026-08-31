# ShopCopilot — Final Evaluation, Fresh-Clone Rehearsal & Compliance Record

**Date:** 2026-08-31  
**Submission Freeze Commit:** `46e3322` (Tag: `submission-freeze`)  
**Evaluator Status:** Official `evaluator/local_evaluator.py` (Unmodified / Frozen)  

---

## 1. Live Execution Environment

Captured live from host system via Windows CIM and Python runtime:

- **Python Version:** `Python 3.13.2`
- **Operating System:** `Microsoft Windows 11 Pro 64-bit`
- **CPU:** `AMD Ryzen 7 H 255 w/ Radeon 780M Graphics` (16 logical cores)
- **Physical Memory (RAM):** `30.8 GB`
- **Core Dependencies (`pip freeze`):**
  - `numpy==2.5.2`
  - `pytest==9.1.1`
  - `python-dotenv==1.2.3`
  - `PyYAML==6.0.3`
  - `requests==2.34.2`
  - `google-genai==2.20.0`
  - `pydantic==2.13.4`
  - `anyio==4.14.2`
  - `fastapi==0.141.1`
  - `uvicorn==0.52.4`

---

## 2. Compliance Audit Checklist

| Check | Requirement | Result | Evidence / Notes |
|---|---|---|---|
| **Evaluator Frozen** | `evaluator/` directory must be byte-identical to starter package | **PASS** | `git diff submission-freeze --stat -- evaluator/` is strictly empty. |
| **No Session ID Hardcoding** | No hardcoded `public_` session IDs in decision or score paths | **PASS** | `git grep -n "public_" starter/ neeshops/` matches only comments & default config path strings. |
| **Valid `ask_attribute` Enums** | All clarification attributes strictly adhere to spec-defined schema | **PASS** | Guarded by `neeshops/conversation/clarification.py` and unit tests. |
| **No Secret / Key Leakage** | `.env` and API keys never committed in git history | **PASS** | `git log --all --oneline -- .env` is strictly empty. |
| **Test Suite Integrity** | Complete pytest suite green | **PASS** | `332 passed, 1 deselected in 21.18s`. |
| **Data Separation** | Dev split (160) tuned; public-200 confirmed; 800-hidden untouched | **PASS** | Public set evaluated twice; hidden set evaluated 0 times. |
| **Git Tag Chain** | Official tags preserved and pointing to authoritative commits | **PASS** | `fork-point`, `new-baseline`, `submission-freeze`. |

---

## 3. Fresh-Clone Rehearsal Verification

### Rehearsal Protocol
1. Cloned repository from `file://` URL into isolated temporary directory at tag `submission-freeze` (`46e3322`).
2. Populated `data/` assets (`catalog.jsonl`, `catalog.fts.db`, `semantic.index.npy`, `dev_split.jsonl`, `public_set.jsonl`).
3. Executed `python -m pytest -q`: 100% pass rate.
4. Executed `python -m evaluator.local_evaluator` against 200 public sessions without flags or modifications.

### Verified Rehearsal Results (Official Evaluator Output)

```
================================================================================
                               EVALUATION RESULTS                               
================================================================================
Sample Count:                    200
Hit Rate @ 10:                   0.880000 (176 / 200)
MRR:                             0.491585
MTTC:                            3.375000
Efficiency:                      0.762500
Recommended Technical Score:     0.739976
Reported Prompt Tokens:          0
Reported Completion Tokens:      0
Reported Total Tokens:           0

By Scenario:
  - browsing:       Hit@10=0.925000 (74/80), MRR=0.453229, MTTC=2.912500
  - buying:         Hit@10=0.912500 (73/80), MRR=0.544420, MTTC=2.650000
  - intent_override: Hit@10=0.766667 (23/30), MRR=0.496005, MTTC=5.466667
  - boundary:       Hit@10=0.600000 (6/10),  MRR=0.362500, MTTC=6.600000
================================================================================
```

**Rehearsal Status:** Verified clean reproduction on isolated clone.
