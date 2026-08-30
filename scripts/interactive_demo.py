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
    # Raw retrieval pool (up to candidate_limit) — Table A paginates this to
    # prove recall: a target absent here is a P2 bug, not a ranking bug.
    debug_store: dict[str, list[dict]] = {}
    # Exact slice handed to ranking (filtered[:rerank_limit]) — Table B,
    # full, no pagination: anything cut here is unreachable by personalization.
    debug_pool: dict[str, list[dict]] = {}
    debug_meta: dict[str, dict] = {}

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
                "image": f"https://images-na.ssl-images-amazon.com/images/P/{rec['parent_asin']}.01._SL400_.jpg",
            }
        )
    return out


def enrich_debug(candidates) -> list[dict]:
    out = []
    for c in candidates:
        row = DemoState.lookup.get(c.parent_asin, {})
        price = row.get("price")
        md = c.metadata if isinstance(c.metadata, dict) else {}
        out.append(
            {
                "parent_asin": c.parent_asin,
                "score": c.score,
                "source": c.source,
                "metadata": md,
                "rank": md.get("rank"),
                "bm25": md.get("bm25"),
                "semantic": md.get("semantic"),
                "title": str(row.get("title", ""))[:80],
                "price": f"${price:.2f}" if isinstance(price, (int, float)) else None,
                "categories": (row.get("categories") or [])[-2:],
            }
        )
    return out


def debug_stats(candidates, lookup) -> dict:
    """Tile stats over the deduped, weighted raw pool — proves the 200
    (deduped by merge, weighted per route, ASINs resolvable) without
    dumping rows: score decay, source mix, top leaf categories, price and
    catalog-ASIN coverage."""
    scores = [c.score for c in candidates]
    n = len(scores)
    decay = [scores[round(i * (n - 1) / 9)] for i in range(10)] if n else []
    sources = {"bm25": 0, "semantic": 0, "both": 0}
    cats: dict[str, int] = {}
    priced = in_catalog = 0
    for c in candidates:
        s = set(c.source.split("+"))
        if len(s) > 1:
            sources["both"] += 1
        elif "semantic" in s:
            sources["semantic"] += 1
        elif "bm25" in s:
            sources["bm25"] += 1
        row = lookup.get(c.parent_asin)
        if row:
            in_catalog += 1
            if isinstance(row.get("price"), (int, float)):
                priced += 1
            cl = row.get("categories")
            leaf = cl[-1] if isinstance(cl, list) and cl else None
            if leaf:
                cats[str(leaf)] = cats.get(str(leaf), 0) + 1
    top_cats = sorted(cats.items(), key=lambda kv: -kv[1])[:5]
    return {
        "n": n,
        "score_decay": [round(x, 4) for x in decay],
        "sources": sources,
        "top_categories": [[k, v] for k, v in top_cats],
        "price_coverage": {"priced": priced, "in_catalog": in_catalog, "total": n},
    }


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
            DemoState.debug_store.pop(session_id, None)
            DemoState.debug_pool.pop(session_id, None)
            DemoState.debug_meta.pop(session_id, None)
            self._send(200, json.dumps({"session_id": session_id}), "application/json")
            return
        if self.path == "/api/turn":
            body = self._json_body()
            message = str(body.get("message", "")).strip()
            session_id = str(body.get("session_id", ""))
            if not message or not session_id:
                self._send(
                    400,
                    json.dumps({"error": "message and session_id required"}),
                    "application/json",
                )
                return
            offset = int(body.get("debug_offset", 0) or 0)
            limit = int(body.get("debug_limit", 50) or 50)
            limit = max(1, min(limit, 50))
            offset = max(0, offset)
            try:
                impl = DemoState.agent._impl
                state_before = impl.state_manager.get(session_id)
                query = impl._conversation_query(state_before, message)
                strat = impl.strategy
                cand_limit = int(strat.get("retrieval", {}).get("candidate_limit", 200))
                rerank_limit = int(strat.get("ranking", {}).get("rerank_limit", 40))
                raw_cands = impl.retriever.search(query, state_before, top_k=cand_limit)
                raw_count = len(raw_cands)
                filtered = raw_cands
                if impl.catalog_lookup:
                    from neeshops.retrieval.filters import apply_filters

                    filtered = apply_filters(
                        raw_cands, impl.catalog_lookup, state_before
                    )
                after_filters = len(filtered)
                pool_size = min(rerank_limit, after_filters)
                # Raw rank of the last candidate that reaches ranking — the
                # cut line: raw ranks past this are never ranked/boosted.
                cut_rank = None
                if pool_size:
                    cut_rank = (filtered[pool_size - 1].metadata or {}).get("rank")
                DemoState.debug_store[session_id] = enrich_debug(raw_cands)
                DemoState.debug_pool[session_id] = enrich_debug(
                    filtered[:pool_size]
                )
                DemoState.debug_meta[session_id] = {
                    "raw": raw_count,
                    "after_filters": after_filters,
                    "pool": pool_size,
                    "cand_limit": cand_limit,
                    "rerank_limit": rerank_limit,
                    "cut_rank": cut_rank,
                    "stats": debug_stats(raw_cands, impl.catalog_lookup),
                    "strategy": strat.get("retrieval", {}).get("strategy", "hybrid"),
                    "weights": impl.retriever.weights_for_route(state_before.route)
                    if hasattr(impl.retriever, "weights_for_route")
                    else {},
                }
            except Exception:
                pass  # keep last turn's debug data; respond() below still runs
            result = DemoState.agent.respond(
                session_id, message, turn=int(body.get("turn", 1)), top_k=10
            )
            meta = DemoState.debug_meta.get(session_id, {})
            all_dbg = DemoState.debug_store.get(session_id, [])
            total = len(all_dbg)
            page = all_dbg[offset : offset + limit]
            debug_payload = {
                "raw": meta.get("raw", total),
                "after_filters": meta.get("after_filters", total),
                "pool": meta.get("pool", min(40, total)),
                "final": len(result["recommendations"]),
                "strategy": meta.get("strategy", "hybrid"),
                "weights": meta.get("weights", {}),
                "candidate_limit": meta.get("cand_limit", 200),
                "rerank_limit": meta.get("rerank_limit", 40),
                "cut_rank": meta.get("cut_rank"),
                "stats": meta.get("stats", {}),
                "total": total,
                "offset": offset,
                "limit": limit,
                # Top-10 window only — the UI pulls the rest of the pool
                # on demand via /api/debug (no row dumps per turn).
                "candidates": page[:10],
            }
            payload = {
                "message": result["message"],
                "ask_attribute": result.get("ask_attribute"),
                "recommendations": enrich(result["recommendations"]),
                "debug": debug_payload,
            }
            self._send(200, json.dumps(payload), "application/json")
            return
        if self.path == "/api/debug":
            body = self._json_body()
            session_id = str(body.get("session_id", ""))
            offset = int(body.get("offset", 0) or 0)
            limit = int(body.get("limit", 50) or 50)
            limit = max(1, min(limit, 50))
            offset = max(0, offset)
            all_dbg = DemoState.debug_store.get(session_id, [])
            meta = DemoState.debug_meta.get(session_id, {})
            page = all_dbg[offset : offset + limit]
            payload = {
                "total": len(all_dbg),
                "offset": offset,
                "limit": limit,
                "candidates": page,
                "meta": meta,
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
  body { margin: 0; font-family: 'Segoe UI', system-ui, sans-serif; background: #101014; color: #e8e8ee; min-height: 100vh; }
  header { display: flex; align-items: center; justify-content: space-between; padding: 14px 24px; border-bottom: 1px solid #26262e; background: #141419; }
  header h1 { font-size: 17px; margin: 0; font-weight: 600; } header h1 span { color: #8b5cf6; }
  #reset { background: #8b5cf6; border: 0; color: white; padding: 8px 14px; border-radius: 8px; font-weight: 600; cursor: pointer; } #reset:hover { background: #7c3aed; }
  main { max-width: 960px; margin: 0 auto; padding: 20px 16px 120px; }
  .row { display: flex; margin: 10px 0; }
  .bubble { max-width: 78%; padding: 10px 14px; border-radius: 14px; line-height: 1.45; white-space: pre-wrap; word-wrap: break-word; }
  .user { margin-left: auto; background: #8b5cf6; color: white; border-bottom-right-radius: 4px; }
  .agent { margin-right: auto; background: #1e1e26; border: 1px solid #2c2c36; border-bottom-left-radius: 4px; }
  .chip { display: inline-block; margin-top: 8px; font-size: 11px; letter-spacing: .4px; color: #f5d90a; border: 1px solid #57531d; background: #24210c; padding: 2px 8px; border-radius: 999px; text-transform: uppercase; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 8px; margin: 10px 0; }
  .tiles .tile { background: #17171d; border: 1px solid #26262e; border-radius: 10px; padding: 10px; }
  .tiles .tile h4 { margin: 0 0 6px; font-size: 11px; text-transform: uppercase; letter-spacing: .5px; color: #9a9aa6; }
  .spark { display: flex; align-items: flex-end; gap: 2px; height: 44px; }
  .spark i { flex: 1; background: linear-gradient(180deg, #8b5cf6, #60a5fa); border-radius: 2px 2px 0 0; min-height: 3px; }
  .donut-row { display: flex; align-items: center; gap: 10px; }
  .donut { width: 46px; height: 46px; border-radius: 50%; flex: none; }
  .donut::after { content: ''; display: block; width: 22px; height: 22px; margin: 12px; border-radius: 50%; background: #17171d; }
  .legend { font-size: 11px; color: #9a9aa6; line-height: 1.6; }
  .legend .src-bm25, .legend .src-semantic, .legend .src-both { font-weight: 700; }
  .catrows { font-size: 11px; line-height: 1.7; color: #e8e8ee; }
  .catrows .bar { display: inline-block; height: 6px; background: #8b5cf6; border-radius: 3px; vertical-align: middle; margin-left: 6px; }
  .catrows .cnt { color: #6f6f7c; margin-left: 6px; }
  .debug .cutline td { background: #2a1f3d; color: #c4b5fd; font-size: 11px; text-align: center; border-top: 1px solid #8b5cf6; border-bottom: 1px solid #8b5cf6; padding: 5px 4px; }
  .debug .gaprow td { color: #55555f; font-size: 10px; text-align: center; padding: 2px 4px; }
  .dim { color: #55555f !important; font-size: 12px; }
  .ph-wrap { background: #17171d; border: 1px dashed #3d3d4a; border-radius: 12px; padding: 12px; margin: 8px 0 18px; }
  .ph-wrap h3 { margin: 0 0 8px; font-size: 13px; color: #8b5cf6; }
  .ph-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(80px, 1fr)); gap: 6px; }
  .ph { background: #1e1e26; border: 1px solid #2c2c36; border-radius: 8px; padding: 8px 6px; text-align: center; }
  .ph b { display: block; color: #8b5cf6; font-size: 11px; }
  .ph span { font-family: monospace; font-size: 10px; color: #9a9aa6; }
  .ph-note { margin: 8px 0 0; font-size: 11px; color: #6f6f7c; }
  .funnel { display: flex; align-items: center; gap: 8px; margin: 14px 0 8px; flex-wrap: wrap; }
  .funnel .step { background: #1e1e26; border: 1px solid #2c2c36; border-radius: 10px; padding: 10px 14px; text-align: center; min-width: 110px; }
  .funnel .step b { color: #8b5cf6; font-size: 18px; display: block; } .funnel .step span { font-size: 11px; color: #9a9aa6; }
  .funnel .arrow { color: #8b5cf6; font-size: 20px; }
  .debug { background: #17171d; border: 1px solid #26262e; border-radius: 12px; padding: 12px; margin: 8px 0 18px; }
  .debug h3 { margin: 0 0 8px; font-size: 13px; color: #8b5cf6; }
  .debug table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .debug th { text-align: left; color: #9a9aa6; border-bottom: 1px solid #2c2c36; padding: 6px 4px; }
  .debug td { padding: 6px 4px; border-bottom: 1px solid #1e1e26; }
  .src-bm25 { color: #60a5fa; } .src-semantic { color: #c084fc; } .src-both { color: #4ade80; }
  .pager { display: flex; gap: 8px; align-items: center; margin-top: 8px; }
  .pager button { background: #26262e; border: 1px solid #2c2c36; color: #e8e8ee; padding: 6px 10px; border-radius: 8px; cursor: pointer; } .pager button:disabled { opacity: .4; cursor: default; }
  form { position: fixed; bottom: 0; left: 0; right: 0; background: #141419; border-top: 1px solid #26262e; padding: 12px; display: flex; gap: 8px; max-width: 992px; margin: 0 auto; }
  input { flex: 1; background: #1e1e26; border: 1px solid #2c2c36; color: #e8e8ee; border-radius: 10px; padding: 12px 14px; font-size: 14px; outline: none; } input:focus { border-color: #8b5cf6; }
  button[type=submit] { background: #8b5cf6; border: 0; color: white; border-radius: 10px; padding: 0 18px; font-weight: 600; cursor: pointer; }
  .hint { color: #6f6f7c; font-size: 12px; text-align: center; margin: 14px 0; } .thinking { color: #9a9aa6; font-style: italic; }
</style>
</head>
<body>
<header><h1>NeeShops <span>Shopping Copilot</span> — live agent demo</h1><button id="reset">New session</button></header>
<main id="log"><p class="hint">Try: “I need casual women's shoes under $120” · “running shoes with cushioning” · “gift for my sister around $30”</p></main>
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
function funnelHtml(d){
  const drop = d.raw - d.after_filters;
  const rl = d.rerank_limit ?? 40;
  const filterStep = drop
    ? `<div class="arrow">—(filters -${drop})→</div><div class="step"><b>${d.after_filters}</b><span>after filters</span></div>`
    : `<div class="arrow dim" title="fail-open filters kept all ${d.raw} candidates — intended before any constraints exist (browsing)">—(filters -0 · fail-open)→</div>`;
  return `<div class="funnel">
    <div class="step"><b>${d.raw}</b><span>raw retrieval</span></div>
    ${filterStep}
    <div class="arrow">—(rerank_limit ${rl})→</div>
    <div class="step"><b>${d.pool}</b><span>pool for ranking</span></div><div class="arrow">→</div>
    <div class="step"><b>${d.final}</b><span>final top 10 (P3)</span></div>
    <div style="margin-left:auto;font-size:11px;color:#6f6f7c">${d.strategy} · bm25 ${d.weights.bm25??'-'} / sem ${d.weights.semantic??'-'}</div>
  </div>`;
}
function tilesHtml(s){
  if (!s || !s.n) return '';
  const max = Math.max(...s.score_decay, 1e-6);
  const bars = s.score_decay.map(v => `<i style="height:${Math.max(4, Math.round(v / max * 100))}%"></i>`).join('');
  const tot = s.sources.bm25 + s.sources.semantic + s.sources.both || 1;
  const donut = `conic-gradient(#60a5fa 0 ${(s.sources.bm25 / tot * 100).toFixed(1)}%, #c084fc 0 ${((s.sources.bm25 + s.sources.semantic) / tot * 100).toFixed(1)}%, #4ade80 0 100%)`;
  const catMax = Math.max(...s.top_categories.map(c => c[1]), 1);
  const cats = s.top_categories.map(([k, v]) => `<div>${k}<span class="bar" style="width:${Math.round(v / catMax * 60)}px"></span><span class="cnt">${v}</span></div>`).join('') || '<div>—</div>';
  const pc = s.price_coverage;
  return `
    <div class="tile"><h4>score decay (${s.n})</h4><div class="spark">${bars}</div></div>
    <div class="tile"><h4>source mix</h4><div class="donut-row"><div class="donut" style="background:${donut}"></div><div class="legend"><span class="src-bm25">bm25</span> ${s.sources.bm25}<br><span class="src-semantic">semantic</span> ${s.sources.semantic}<br><span class="src-both">both</span> ${s.sources.both}</div></div></div>
    <div class="tile"><h4>top-5 categories</h4><div class="catrows">${cats}</div></div>
    <div class="tile"><h4>coverage</h4><div class="catrows"><div>priced <span class="cnt">${pc.priced}/${pc.total}</span></div><div>ASINs in catalog <span class="cnt">${pc.in_catalog}/${pc.total}</span></div></div></div>`;
}
function rowHtml(c){
  const bm = c.bm25 ? `${c.bm25.raw_score.toFixed(2)} #${c.bm25.rank}` : '-';
  const se = c.semantic ? `${c.semantic.raw_score.toFixed(2)} #${c.semantic.rank}` : '-';
  const cls = c.source.includes('+') ? 'src-both' : c.source.includes('semantic') ? 'src-semantic' : 'src-bm25';
  const pc = `${c.price??'—'}${c.categories&&c.categories.length?' · '+c.categories.join(' › '):''}`;
  const tip = String(c.title||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
  return `<tr><td>${c.rank??''}</td><td style="font-family:monospace" title="${tip}">${c.parent_asin}</td><td>${c.score.toFixed(3)}</td><td class="${cls}">${c.source}</td><td>${c.rank??''}</td><td>${bm}</td><td>${se}</td><td>${pc}</td></tr>`;
}
const TABLE_HEAD = '<table><tr><th>#</th><th>ASIN</th><th>score</th><th>source</th><th>rank</th><th>bm25</th><th>semantic</th><th>price / categories</th></tr>';
async function postJSON(url, body){
  const res = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  return res.json();
}
async function renderPool(wrap, d){
  const cut = d.cut_rank, hasCut = d.total > d.pool && cut;
  const wins = [[0, Math.min(10, d.total)]];
  if (hasCut) wins.push([Math.max(0, cut - 6), 11], [Math.max(0, d.total - 5), 5]);
  const rows = [], seen = new Set();
  for (const [off, lim] of wins){
    const p = await postJSON('/api/debug', {session_id: sessionId, offset: off, limit: Math.min(lim, 50)});
    p.candidates.forEach(c => { if (!seen.has(c.parent_asin)) { seen.add(c.parent_asin); rows.push(c); } });
  }
  rows.sort((a, b) => (a.rank??0) - (b.rank??0));
  const gap = (a, b) => `<tr class="gaprow"><td colspan="8">… rows ${a}–${b} not shown — any window via /api/debug …</td></tr>`;
  const cutline = `<tr class="cutline"><td colspan="8">ranking cut at raw rank ${cut} — ranks ${cut+1}–${d.total} never reach ranking (no personalization boost)</td></tr>`;
  let h = TABLE_HEAD, prev = 0;
  rows.forEach(c => {
    const r = c.rank ?? 0;
    if (r > prev + 1) h += gap(prev + 1, r - 1);
    if (hasCut && prev < cut && r > cut) h += cutline;
    h += rowHtml(c);
    prev = r;
  });
  if (hasCut && prev <= cut) h += cutline;
  wrap.querySelector('.pool-table').innerHTML = h + '</table>';
}
function finalPlaceholderHtml(recs){
  const tiles = recs.map((r, i) => `<div class="ph" title="${String(r.title||'').replace(/"/g,'&quot;')}"><b>#${i+1}</b><span>${r.parent_asin}</span></div>`).join('');
  return `<div class="ph-wrap"><h3>Final 10 — P3 ranking stage (pending merge)</h3><div class="ph-grid">${tiles}</div><p class="ph-note">P2's heuristic placeholder has no provenance link to the pool — real scores/reasons arrive with P3's ranker post-merge.</p></div>`;
}
function attachDebug(debug){
  const rl = debug.rerank_limit ?? 40;
  const cut = debug.cut_rank ?? rl;
  const hasCut = debug.total > debug.pool && debug.cut_rank;
  const summary = hasCut
    ? `Pool — top 10 · cut at ${cut} · bottom 5 — ranks ${cut+1}+ never reach ranking (no personalization boost)`
    : `Pool — all ${debug.total} reach ranking (no cut)`;
  const wrap = document.createElement('div'); wrap.className = 'debug';
  wrap.innerHTML = `<h3>Retrieval funnel — ${debug.raw} → ${debug.pool} → ${debug.final}</h3>${funnelHtml(debug)}
    <div class="tiles">${tilesHtml(debug.stats)}</div>
    <details open><summary style="cursor:pointer;color:#9a9aa6">${summary}</summary>
      <div class="pool-table"><em style="color:#6f6f7c">loading…</em></div>
    </details>`;
  log.appendChild(wrap);
  window.scrollTo(0, document.body.scrollHeight);
  if (debug.total) renderPool(wrap, debug);
}
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
      const ph = document.createElement('div');
      ph.innerHTML = finalPlaceholderHtml(data.recommendations);
      log.appendChild(ph);
    }
    if (data.debug) attachDebug(data.debug);
    window.scrollTo(0, document.body.scrollHeight);
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
