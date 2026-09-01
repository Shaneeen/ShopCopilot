# Frontend — Demo Shell

> TikTok TechJam 2026 · ShopCopilot prototype (decoupled from the competition Agent)

## What’s here

| File | Purpose |
|---|---|
| `neeshops-prototype.html` | Clickable Pinterest-style prototype (editorial + dashboard) — static, no backend |
| `interactive_demo.py` | Live demo server (funnel, provenance chips, sampled replay) — `http://127.0.0.1:8787` |

The competition Agent (`starter/agent.py` → `neeshops/agent.py`) runs independently; nothing here is imported by it.

## Run

```bash
# static prototype — open directly
open frontend/neeshops-prototype.html

# live demo (needs catalog + deps)
pip install -r requirements.txt
python scripts/setup_catalog.py
python frontend/interactive_demo.py   # or scripts/interactive_demo.py (same file)
# → http://127.0.0.1:8787
```

Port `8787` — funnel 50k→300→320→10, ranked cards with coverage/IDF/salience, debug drawer.
