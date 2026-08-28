#!/usr/bin/env python3
"""Interactive local chat demo wired to the REAL agent (starter.agent.Agent).

Serves a single-page chat at http://127.0.0.1:8787 — type like a shopper,
see the agent's question and live recommendations from the 50k catalog.
Stdlib only (http.server), so it never affects the competition agent.

    python scripts/interactive_demo.py
"""
from __future__ import annotations

import json
import os
import sys
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("NEESHOPS_LOG_LEVEL", "ERROR")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PORT = 8787


class DemoState:
    agent = None
    lookup: dict = {}

    @classmethod
    def init(cls) -> None:
        from starter.agent import Agent

        cls.agent = Agent()
        cls.lookup = cls.agent._impl.catalog_lookup


def enrich(recs: list[dict]) -> list[dict]:
    out = []
    for rec in recs:
        row = DemoState.lookup.get(rec["parent_asin"], {})
        price = row.get("price")
        out.append(
            {
                **rec,
                "title": str(row.get("title", rec["parent_asin"]))[:110],
                "price": f"${price:.2f}" if isinstance(price, (int, float)) else None,
                "store": row.get("store"),
                "rating": row.get("average_rating"),
                "categories": (row.get("categories") or [])[-2:],
                # The competition catalog ships no images; Amazon still
                # serves a product photo for most ASINs at this stable URL.
                # The card falls back to a generated tile when Amazon has
                # none (it returns a 43-byte 1x1 placeholder gif).
                "image": f"https://images-na.ssl-images-amazon.com/images/P/{rec['parent_asin']}.01._SL400_.jpg",
            }
        )
    return out


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: str, content_type: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._route_post()
        except Exception:
            import traceback

            self._send(500, traceback.format_exc(), "text/plain; charset=utf-8")

    def _route_post(self) -> None:
        if self.path == "/api/reset":
            session_id = f"demo_{uuid.uuid4().hex[:8]}"
            DemoState.agent.reset(session_id, user_profile={"preference_tags": []})
            self._send(200, json.dumps({"session_id": session_id}), "application/json")
            return
        if self.path == "/api/turn":
            body = self._json_body()
            message = str(body.get("message", "")).strip()
            session_id = str(body.get("session_id", ""))
            if not message or not session_id:
                self._send(400, json.dumps({"error": "message and session_id required"}), "application/json")
                return
            result = DemoState.agent.respond(session_id, message, turn=int(body.get("turn", 1)), top_k=10)
            payload = {
                "message": result["message"],
                "ask_attribute": result.get("ask_attribute"),
                "recommendations": enrich(result["recommendations"]),
            }
            self._send(200, json.dumps(payload), "application/json")
            return
        self._send(404, "not found", "text/plain")

    def log_message(self, fmt: str, *args) -> None:  # silence request logs
        pass


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>NeeShops — Shopping Copilot demo</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: 'Segoe UI', system-ui, sans-serif;
    background: #101014; color: #e8e8ee; min-height: 100vh;
  }
  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 24px; border-bottom: 1px solid #26262e; background: #141419;
  }
  header h1 { font-size: 17px; margin: 0; font-weight: 600; }
  header h1 span { color: #8b5cf6; }
  #reset {
    background: #8b5cf6; border: 0; color: white; padding: 8px 14px;
    border-radius: 8px; font-weight: 600; cursor: pointer;
  }
  #reset:hover { background: #7c3aed; }
  main { max-width: 860px; margin: 0 auto; padding: 20px 16px 120px; }
  .row { display: flex; margin: 10px 0; }
  .bubble {
    max-width: 78%; padding: 10px 14px; border-radius: 14px; line-height: 1.45;
    white-space: pre-wrap; word-wrap: break-word;
  }
  .user { margin-left: auto; background: #8b5cf6; color: white; border-bottom-right-radius: 4px; }
  .agent { margin-right: auto; background: #1e1e26; border: 1px solid #2c2c36; border-bottom-left-radius: 4px; }
  .chip {
    display: inline-block; margin-top: 8px; font-size: 11px; letter-spacing: .4px;
    color: #f5d90a; border: 1px solid #57531d; background: #24210c;
    padding: 2px 8px; border-radius: 999px; text-transform: uppercase;
  }
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 10px; margin: 8px 0 18px; }
  .card {
    background: #17171d; border: 1px solid #26262e; border-radius: 12px; padding: 12px;
    display: flex; flex-direction: column; gap: 6px;
  }
  .card img {
    width: 100%; height: 150px; object-fit: cover; border-radius: 8px;
    background: #26262e; display: block;
  }
  .tile {
    width: 100%; height: 150px; border-radius: 8px; display: flex;
    align-items: center; justify-content: center; font-weight: 700;
    font-size: 34px; color: rgba(255,255,255,.92); letter-spacing: 1px;
  }
  .card .t { font-size: 13px; font-weight: 600; line-height: 1.35; }
  .card .m { font-size: 12px; color: #9a9aa6; }
  .card .s { font-size: 11px; color: #6f6f7c; }
  .card .rank { color: #8b5cf6; font-weight: 700; font-size: 11px; }
  form {
    position: fixed; bottom: 0; left: 0; right: 0; background: #141419;
    border-top: 1px solid #26262e; padding: 12px; display: flex; gap: 8px;
    max-width: 892px; margin: 0 auto;
  }
  input {
    flex: 1; background: #1e1e26; border: 1px solid #2c2c36; color: #e8e8ee;
    border-radius: 10px; padding: 12px 14px; font-size: 14px; outline: none;
  }
  input:focus { border-color: #8b5cf6; }
  button[type=submit] {
    background: #8b5cf6; border: 0; color: white; border-radius: 10px;
    padding: 0 18px; font-weight: 600; cursor: pointer;
  }
  .hint { color: #6f6f7c; font-size: 12px; text-align: center; margin: 14px 0; }
  .thinking { color: #9a9aa6; font-style: italic; }
</style>
</head>
<body>
<header>
  <h1>NeeShops <span>Shopping Copilot</span> — live agent demo</h1>
  <button id="reset">New session</button>
</header>
<main id="log">
  <p class="hint">Try: “I need casual women's shoes under $120” · “running shoes with cushioning” · “gift for my sister around $30”</p>
</main>
<form id="f"><input id="i" autocomplete="off" placeholder="Tell the copilot what you're looking for…" autofocus><button type="submit">Send</button></form>
<script>
let sessionId = null, turn = 0;
const log = document.getElementById('log');
const addBubble = (cls, html) => {
  const row = document.createElement('div'); row.className = 'row';
  const b = document.createElement('div'); b.className = 'bubble ' + cls;
  b.innerHTML = html; row.appendChild(b); log.appendChild(row);
  window.scrollTo(0, document.body.scrollHeight); return b;
};
const replaceWithTile = (img) => {
  img.outerHTML = `<div class="tile" style="background:linear-gradient(135deg,hsl(${hue(img.dataset.asin)},45%,30%),hsl(${hue(img.dataset.asin)},45%,18%))">${img.dataset.tile}</div>`;
};
const hue = (asin) => { let h = 0; for (const c of asin) h = (h * 31 + c.charCodeAt(0)) % 360; return h; };
const cardHtml = r => `
  <div class="card">
    <img src="${r.image}" loading="lazy" alt="" data-tile="${r.title.slice(0,2).toUpperCase()}" data-asin="${r.parent_asin}">
    <div class="rank">#${r.rank} · score ${r.score.toFixed(3)}</div>
    <div class="t">${r.title}</div>
    <div class="m">${r.price ? r.price + ' · ' : ''}${r.categories ? r.categories.join(' › ') : ''}</div>
    <div class="s">${r.store ? '🏪 ' + r.store : ''}${r.rating ? ' · ★ ' + r.rating : ''} · ${r.parent_asin}</div>
  </div>`;
const wireImageFallbacks = (grid) => {
  grid.querySelectorAll('img').forEach(img => {
    img.addEventListener('error', () => replaceWithTile(img));
    img.addEventListener('load', () => {
      // Amazon answers missing products with a 43-byte 1x1 gif.
      if (img.naturalWidth <= 2) replaceWithTile(img);
    });
  });
};
async function reset() {
  const res = await fetch('/api/reset', {method: 'POST'});
  sessionId = (await res.json()).session_id; turn = 0;
  log.innerHTML = '<p class="hint">New session started. Tell the copilot what you want.</p>';
}
document.getElementById('reset').onclick = reset;
document.getElementById('f').onsubmit = async (e) => {
  e.preventDefault();
  const input = document.getElementById('i');
  const msg = input.value.trim(); if (!msg || !sessionId) return;
  input.value = '';
  addBubble('user', msg.replace(/</g, '&lt;'));
  turn += 1;
  const wait = addBubble('agent', '<span class="thinking">thinking…</span>');
  try {
    const res = await fetch('/api/turn', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({session_id: sessionId, message: msg, turn})
    });
    const data = await res.json();
    let html = data.message.replace(/</g, '&lt;');
    if (data.ask_attribute) html += `<br><span class="chip">asking: ${data.ask_attribute}</span>`;
    wait.innerHTML = html;
    if (data.recommendations && data.recommendations.length) {
      const grid = document.createElement('div'); grid.className = 'cards';
      data.recommendations.forEach((r, i) => { r.rank = i + 1; grid.innerHTML += cardHtml(r); });
      wireImageFallbacks(grid);
      log.appendChild(grid);
      window.scrollTo(0, document.body.scrollHeight);
    }
  } catch (err) {
    wait.textContent = 'Error: ' + err;
  }
};
reset();
</script>
</body>
</html>
"""


def main() -> int:
    print("Loading catalog + agent (one-off)…")
    DemoState.init()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"Serving {url} — open it in your browser. Ctrl+C to stop.")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
