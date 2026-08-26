# Experimental / future scope

This folder is a placeholder for **future, out-of-scope** ideas that are
not part of the official TechJam Shopping Copilot track:

- Image → similar-product visual search
- Video → product extraction
- AI-generated image/media detection

These are explored in the `frontend/` design prototype for demo purposes,
but the **official competition Agent (`starter/agent.py` → `neeshops/agent.py`)
is entirely text-based** and must have zero dependency on anything added
here.

Nothing is implemented in this folder yet, and nothing should be imported
from `neeshops/agent.py` or any of its dependencies. If a workstream starts
building one of these ideas, it belongs in a submodule here (e.g.
`neeshops/experimental/visual_search/`) with its own `requirements`
kept out of the top-level `requirements.txt` until it's actually needed.
