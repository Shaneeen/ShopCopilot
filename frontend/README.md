# Frontend (demo shell — not part of the competition Agent)

This is the NeeShops concept prototype: an editorial, Pinterest-style
customer experience plus a developer dashboard for inspecting the AI
pipeline. It exists for:

- concept demonstration and the hackathon presentation
- manual click-through testing
- future visualisation of what `neeshops/agent.py` is doing (run
  inspector, experiment lab, etc. — currently populated with illustrative
  sample data, not live pipeline output)

**The official competition Agent (`starter/agent.py` → `neeshops/agent.py`)
runs entirely independently of this folder and must remain fully usable
without it.** Nothing here should ever be imported by `neeshops/` or
`starter/`.

## Files

| File | What it is |
|---|---|
| `neeshops-prototype.html` | The rendered, clickable prototype |
| `Main.dc.html` | Design-canvas source for the prototype |
| `canvas.json` | Canvas layout manifest for the design source |

## Scope notes

This stage did not touch the frontend beyond relocating it here. It is
intentionally a demo shell — no payment, checkout, auth, shipping, cart, or
order management, none of which are relevant to the Shopping Copilot
competition. Wiring it up to live `neeshops/agent.py` responses (e.g. via a
small local API) is future work for Workstream 5 — see
`docs/neeshops/TEAM_WORKSTREAMS.md`.
