#!/usr/bin/env python3
"""ShopCopilot live demo — the REAL production agent, real pool, real provenance.

Serves a single-page demo at http://127.0.0.1:8787

- Free chat against the real agent (starter.agent.Agent -> neeshops pipeline).
- Sampled-session mode: replays official evaluator sessions LIVE by importing
  the frozen evaluator's own session drivers (read-only import; evaluator/
  is never edited). Outcomes pre-verified on the dev-160 control artifact.
- Every recommendation carries its true ranking provenance from the shipped
  ranker: coverage x IDF, salience, popularity, hard-violation count, and the
  candidate's pool position before ranking (rank movement is visible).
- Baseline <-> Final toggle re-scores the SAME production pool at
  pre-experiment salience weights (0.5/1.0) vs the shipped buying-gated
  0.2/1.0. Presentation-only: config is deep-copied, never mutated.

    python scripts/interactive_demo.py
"""

from __future__ import annotations

import copy
import json
import os
import sys
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("NEESHOPS_LOG_LEVEL", "ERROR")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PORT = 8787
FREEZE_BANNER = "config: submission-freeze (46e3322) · deterministic ranker · LLM off"
DEV_SPLIT = ROOT / "data" / "dev_split.jsonl"
# Curated dev-160 sessions whose outcomes are pre-verified in
# runs/control-dev-newbaseline.json (public_0112: hit #2 at turn 6;
# public_0194: hit #9 at turn 4; public_0102: hit #2 at turn 2).
SAMPLED_SESSIONS = [
    {"sample_id": "public_0112", "label": "boundary · deep start · pool 195→1"},
    {"sample_id": "public_0194", "label": "buying · steady climb · pool 137→20"},
    {"sample_id": "public_0102", "label": "browsing · 2-turn hit · pool 38→1"},
]
PROFILE_FIELDS = {
    "purchase_frequency",
    "average_prior_rating",
    "rating_style",
    "preference_tags",
    "summary",
}


def normalize_demo_profile(value: object) -> dict:
    """Validate the optional demo profile before passing it to the agent."""
    if value in (None, {}):
        return {"preference_tags": []}
    if not isinstance(value, dict):
        raise ValueError("user_profile must be an object")
    profile = {key: item for key, item in value.items() if key in PROFILE_FIELDS}
    tags = profile.get("preference_tags", [])
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise ValueError("preference_tags must be a list of strings")
    profile["preference_tags"] = list(
        dict.fromkeys(tag.strip() for tag in tags if tag.strip())
    )[:20]
    return profile


class DemoState:
    agent = None
    impl = None
    lookup: dict = {}
    catalog_ids: set = set()
    categories: dict = {}
    dev_samples: list | None = None
    # Real production pool + provenance per session (impl.last_candidates).
    pool_store: dict[str, list[dict]] = {}
    meta_store: dict[str, dict] = {}
    # Sampled-session drivers (evaluator-mirrored state per session).
    sessions: dict[str, dict] = {}
    usage_store: dict[str, dict] = {}
    latency_store: dict[str, list[float]] = {}
    _baseline_ranker = None

    @classmethod
    def init(cls) -> None:
        from starter.agent import Agent

        cls.agent = Agent()
        cls.impl = cls.agent._impl
        cls.lookup = cls.impl.catalog_lookup
        cls.catalog_ids = set(cls.lookup)
        cls.categories = {
            asin: (row.get("categories") or []) for asin, row in cls.lookup.items()
        }

    @classmethod
    def baseline_ranker(cls):
        """Pre-experiment salience weights (0.5 everywhere) on a deep copy of
        the strategy — the shipped change is buying-gated 0.2/1.0."""
        if cls._baseline_ranker is None:
            strategy = copy.deepcopy(cls.impl.strategy)
            rank = strategy.setdefault("ranking", {})
            rank["coverage_salience_weight"] = 0.5
            rank["buying_salience_weight"] = 0.5
            rank["buying_popularity_scale"] = 1.0
            from neeshops.ranking.deterministic import ConstraintAwareRanker

            cls._baseline_ranker = ConstraintAwareRanker(
                strategy=strategy, token_index=cls.impl.token_index
            )
        return cls._baseline_ranker

    @classmethod
    def clear_session(cls, session_id: str) -> None:
        cls.pool_store.pop(session_id, None)
        cls.meta_store.pop(session_id, None)
        cls.sessions.pop(session_id, None)
        cls.usage_store.pop(session_id, None)
        cls.latency_store.pop(session_id, None)

    @classmethod
    def dev_split(cls) -> list[dict]:
        from evaluator.local_evaluator import load_jsonl

        if cls.dev_samples is None:
            cls.dev_samples = load_jsonl(DEV_SPLIT) if DEV_SPLIT.exists() else []
        return cls.dev_samples


# --------------------------------------------------------------------------
# Enrichment: catalog info + true ranker provenance
# --------------------------------------------------------------------------


def _product_row(asin: str) -> dict:
    return DemoState.lookup.get(asin, {})


def enrich(recommendations: list[dict]) -> list[dict]:
    out = []
    for rec in recommendations:
        row = _product_row(rec.get("parent_asin", ""))
        price = row.get("price")
        out.append(
            {
                **rec,
                "title": str(row.get("title", rec.get("parent_asin", "")))[:110],
                "price": f"${price:.2f}" if isinstance(price, (int, float)) else None,
                "store": row.get("store"),
                "rating": row.get("average_rating"),
                "categories": (row.get("categories") or [])[-2:],
                "image": _image_url(rec.get("parent_asin", "")),
            }
        )
    return out


def _image_url(asin: str) -> str:
    return f"https://images-na.ssl-images-amazon.com/images/P/{asin}.01._SL400_.jpg"


def _ranker_diagnostics() -> dict:
    impl = DemoState.impl
    ranker = impl.ranker
    diag = getattr(ranker, "last_diagnostics", None)
    if not diag:
        fallback = getattr(ranker, "fallback", None)
        diag = getattr(fallback, "last_diagnostics", None) or {}
    return diag or {}


def _provenance_entry(entry) -> dict | None:
    if entry is None:
        return None
    features = entry.features
    evaluation = entry.constraint_evaluation
    return {
        "coverage": round(features.coverage, 3),
        "salience": round(features.salience, 3),
        "popularity": round(features.popularity, 3),
        "violations": int(features.hard_constraint_violation_count),
        "pool_rank": int(features.retrieval_rank),
        "active_constraints": int(features.active_constraint_count),
        "soft_matches": list(evaluation.soft_matches),
        "hard_violations": list(evaluation.hard_violations),
    }


def provenance_for(asins: list[str], diagnostics: dict | None = None) -> dict:
    diag = diagnostics if diagnostics is not None else _ranker_diagnostics()
    return {asin: _provenance_entry(diag.get(asin)) for asin in asins}


def enrich_pool(candidates: list, diagnostics: dict) -> list[dict]:
    out = []
    for position, candidate in enumerate(candidates, start=1):
        row = _product_row(candidate.parent_asin)
        price = row.get("price")
        prov = _provenance_entry(diagnostics.get(candidate.parent_asin))
        out.append(
            {
                "rank": position,
                "parent_asin": candidate.parent_asin,
                "score": round(candidate.score, 4),
                "source": candidate.source,
                "title": str(row.get("title", ""))[:80],
                "price": f"${price:.2f}" if isinstance(price, (int, float)) else None,
                "categories": (row.get("categories") or [])[-2:],
                "provenance": prov,
            }
        )
    return out


def pool_stats(candidates: list) -> dict:
    """Tiles over the real hybrid pool: score decay, source mix, top
    categories, price/ASIN coverage — aggregates, no row dumps."""
    scores = [candidate.score for candidate in candidates]
    n = len(scores)
    decay = [scores[round(i * (n - 1) / 9)] for i in range(10)] if n else []
    sources = {"bm25": 0, "semantic": 0, "both": 0, "other": 0}
    cats: dict[str, int] = {}
    priced = in_catalog = 0
    for candidate in candidates:
        parts = set(str(candidate.source or "").split("+"))
        has_bm = any("bm25" in part for part in parts)
        has_sem = any("semantic" in part for part in parts)
        if has_bm and has_sem:
            sources["both"] += 1
        elif has_sem:
            sources["semantic"] += 1
        elif has_bm:
            sources["bm25"] += 1
        else:
            sources["other"] += 1
        row = DemoState.lookup.get(candidate.parent_asin)
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


def constraints_snapshot(session_id: str) -> dict:
    impl = DemoState.impl
    state = impl.state_manager.get(session_id)

    def clean(mapping: dict | None) -> dict:
        out = {}
        for key, value in (mapping or {}).items():
            if value in (None, "", [], {}):
                continue
            out[key] = value if isinstance(value, (str, int, float)) else str(value)
        return out

    inferred = {
        key: {"value": slot.value, "weight": round(slot.weight, 2)}
        for key, slot in (getattr(state, "inferred", None) or {}).items()
        if getattr(slot, "value", None) not in (None, "")
    }
    return {
        "route": getattr(state, "route", None),
        "constraints": clean(getattr(state, "constraints", None)),
        "stale": clean(getattr(state, "stale", None)),
        "inferred": inferred,
        "asked": list(getattr(state, "asked_attributes", None) or []),
    }


# --------------------------------------------------------------------------
# One production turn — respond() + real pool capture + baseline arm
# --------------------------------------------------------------------------


def _run_turn(session_id: str, message: str, turn: int) -> dict:
    impl = DemoState.impl
    started = time.perf_counter()
    result = impl.respond(session_id, message, turn, 10)
    latency_ms = round((time.perf_counter() - started) * 1000, 1)

    pool = list(impl.last_candidates)
    hybrid = list(impl.last_hybrid_pool)
    diagnostics = _ranker_diagnostics()

    rerank_cap = int(
        impl.strategy.get("ranking", {}).get("deterministic", {}).get(
            "rerank_limit", 320
        )
    )
    meta = {
        "catalog": len(DemoState.lookup),
        "hybrid": len(hybrid),
        "pool": len(pool),
        "scored": min(len(pool), rerank_cap),
        "rerank_cap": rerank_cap,
        "final": len(result.get("recommendations", [])),
        "stats": pool_stats(hybrid),
    }
    DemoState.pool_store[session_id] = enrich_pool(pool, diagnostics)
    DemoState.meta_store[session_id] = meta

    # Baseline arm: same pool, same turn state, pre-experiment weights.
    baseline_recs: list[dict] = []
    try:
        baseline_ranker = DemoState.baseline_ranker()
        state_after = impl.state_manager.get(session_id)
        ranked = baseline_ranker.rank(pool, impl.catalog_lookup, state_after, 10)
        baseline_diagnostics = baseline_ranker.last_diagnostics
        baseline_recs = enrich(
            [
                {
                    "parent_asin": item.parent_asin,
                    "score": item.score,
                    "reason": item.reason,
                }
                for item in ranked
            ]
        )
        baseline_prov = provenance_for(
            [item["parent_asin"] for item in baseline_recs], baseline_diagnostics
        )
        for item in baseline_recs:
            item["provenance"] = baseline_prov.get(item["parent_asin"])
    except Exception:
        baseline_recs = []

    recommendations = enrich(result.get("recommendations", []))
    prov = provenance_for([item["parent_asin"] for item in recommendations])
    for item in recommendations:
        item["provenance"] = prov.get(item["parent_asin"])

    # Session usage / latency accumulators.
    usage = DemoState.usage_store.setdefault(
        session_id, {"prompt_tokens": 0, "completion_tokens": 0}
    )
    turn_usage = result.get("usage") or {}
    for key in ("prompt_tokens", "completion_tokens"):
        value = turn_usage.get(key)
        if isinstance(value, int) and value >= 0:
            usage[key] += value
    latencies = DemoState.latency_store.setdefault(session_id, [])
    latencies.append(latency_ms)
    latencies.sort()
    mid = len(latencies) // 2
    p50 = (
        latencies[mid]
        if len(latencies) % 2
        else (latencies[mid - 1] + latencies[mid]) / 2
    )

    return {
        "message": result.get("message", ""),
        "ask_attribute": result.get("ask_attribute"),
        "route": result.get("route"),
        "diagnostics": result.get("diagnostics", {}),
        "recommendations": recommendations,
        "baseline": baseline_recs,
        "ranked": [item["parent_asin"] for item in recommendations],
        "debug": {
            **meta,
            "constraints": constraints_snapshot(session_id),
            "usage": {
                **usage,
                "cost": 0.0,
                "note": "deterministic — no LLM calls",
            },
            "latency_ms": latency_ms,
            "p50_ms": round(p50, 1),
        },
    }


# --------------------------------------------------------------------------
# Sampled-session driver (imports the FROZEN evaluator read-only)
# --------------------------------------------------------------------------


def start_sampled_session(sample_id: str) -> dict:
    from evaluator.local_evaluator import materialize_hidden_fields

    sample = None
    for candidate in DemoState.dev_split():
        if candidate.get("sample_id") == sample_id:
            sample = candidate
            break
    if sample is None:
        raise ValueError(f"sample {sample_id!r} not found in dev split")

    card, behavior = materialize_hidden_fields(sample, DemoState.lookup)
    effective = {**sample, "intent_card": card, "behavior": behavior}
    target = str(sample["ground_truth"]["parent_asin"])
    session_id = f"demo_{uuid.uuid4().hex[:8]}"
    DemoState.impl.reset(session_id, sample.get("user_profile") or {})
    DemoState.clear_session(session_id)

    from evaluator.local_evaluator import coarse_category, initial_message

    state = {
        "sample": effective,
        "target": target,
        "disclosed": set(),
        "boundary_used": False,
        "override_applied": effective["scenario_type"] != "intent_override",
        "turn": 0,
        "trajectory": [],
        "hit_turn": None,
        "best_rank": None,
        "over": False,
        "user_message": None,
    }
    state["user_message"] = initial_message(
        effective,
        coarse_category(DemoState.categories.get(target, [])),
        state["disclosed"],
    )
    DemoState.sessions[session_id] = state

    row = _product_row(target)
    price = row.get("price")
    return {
        "session_id": session_id,
        "sample_id": sample_id,
        "scenario_type": sample.get("scenario_type"),
        "user_message": state["user_message"],
        "turn": 0,
        "target": {
            "parent_asin": target,
            "title": str(row.get("title", target))[:110],
            "price": f"${price:.2f}" if isinstance(price, (int, float)) else None,
            "image": _image_url(target),
            "categories": (row.get("categories") or [])[-2:],
        },
    }


def advance_sampled_session(session_id: str) -> dict:
    from evaluator.local_evaluator import (
        customer_reply,
        normalize_recommendations,
    )

    state = DemoState.sessions.get(session_id)
    if state is None:
        raise ValueError("unknown sampled session")
    if state["over"]:
        raise ValueError("session already ended")

    turn = state["turn"] + 1
    state["turn"] = turn
    answered_message = state["user_message"]
    payload = _run_turn(session_id, answered_message, turn)

    target = state["target"]
    ranked = normalize_recommendations(
        [{"parent_asin": asin} for asin in payload["ranked"]], DemoState.catalog_ids
    )
    target_rank = ranked.index(target) + 1 if target in ranked else None
    state["trajectory"].append(target_rank)
    if target_rank is not None:
        state["best_rank"] = target_rank
    if state["override_applied"] and target_rank is not None:
        state["hit_turn"] = turn
        state["over"] = True
    if turn >= 10:
        state["over"] = True

    next_user_message = None
    if not state["over"]:
        override = state["sample"].get("behavior", {}).get("override") or {}
        if not state["override_applied"] and turn + 1 == int(override.get("turn", 3)):
            state["override_applied"] = True
            new_value = str(override.get("new_value", ""))
            if new_value:
                state["disclosed"].add(new_value)
            next_user_message = str(
                override.get("message", "Actually, ignore my earlier preference.")
            )
        else:
            next_user_message, state["boundary_used"] = customer_reply(
                state["sample"],
                payload.get("ask_attribute"),
                state["disclosed"],
                state["boundary_used"],
            )
        state["user_message"] = next_user_message

    payload.update(
        {
            "turn": turn,
            "answered_message": answered_message,
            "target_rank": target_rank,
            "trajectory": state["trajectory"],
            "session_over": state["over"],
            "hit": state["hit_turn"] is not None,
            "hit_turn": state["hit_turn"],
            "best_rank": state["best_rank"],
            "next_user_message": next_user_message,
        }
    )
    return payload


# --------------------------------------------------------------------------
# HTTP server
# --------------------------------------------------------------------------


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
        except ValueError as exc:
            self._send(400, json.dumps({"error": str(exc)}), "application/json")
        except Exception:
            import traceback

            self._send(500, traceback.format_exc(), "text/plain; charset=utf-8")

    def _route_post(self) -> None:
        if self.path == "/api/reset":
            body = self._json_body()
            try:
                user_profile = normalize_demo_profile(body.get("user_profile"))
            except ValueError as exc:
                self._send(400, json.dumps({"error": str(exc)}), "application/json")
                return
            session_id = f"demo_{uuid.uuid4().hex[:8]}"
            DemoState.impl.reset(session_id, user_profile)
            DemoState.clear_session(session_id)
            self._send(
                200,
                json.dumps({"session_id": session_id, "user_profile": user_profile}),
                "application/json",
            )
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
            turn = int(body.get("turn", 1))
            payload = _run_turn(session_id, message, turn)
            payload["turn"] = turn
            self._send(200, json.dumps(payload), "application/json")
            return
        if self.path == "/api/sample":
            body = self._json_body()
            sample_id = str(body.get("sample_id", "")).strip()
            if not sample_id:
                self._send(
                    400,
                    json.dumps({"error": "sample_id required"}),
                    "application/json",
                )
                return
            payload = start_sampled_session(sample_id)
            self._send(200, json.dumps(payload), "application/json")
            return
        if self.path == "/api/sample/turn":
            body = self._json_body()
            session_id = str(body.get("session_id", ""))
            if not session_id:
                self._send(
                    400,
                    json.dumps({"error": "session_id required"}),
                    "application/json",
                )
                return
            payload = advance_sampled_session(session_id)
            self._send(200, json.dumps(payload), "application/json")
            return
        if self.path == "/api/debug":
            body = self._json_body()
            session_id = str(body.get("session_id", ""))
            offset = max(0, int(body.get("offset", 0) or 0))
            limit = max(1, min(int(body.get("limit", 50) or 50), 50))
            pool = DemoState.pool_store.get(session_id, [])
            meta = DemoState.meta_store.get(session_id, {})
            payload = {
                "total": len(pool),
                "offset": offset,
                "limit": limit,
                "candidates": pool[offset : offset + limit],
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
<title>ShopCopilot — live agent demo</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: 'Segoe UI', system-ui, sans-serif; background: #FBF5E7; color: #1B1F2E; min-height: 100vh; }
  header { position: sticky; top: 0; z-index: 10; background: #1B1F2E; color: #FBF5E7; padding: 10px 20px; display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
  .brand { display: flex; align-items: baseline; gap: 10px; }
  .brand h1 { font-family: Georgia, serif; font-size: 20px; margin: 0; color: #FBF5E7; }
  .brand h1 span { color: #C98A93; }
  .brand small { color: #AAB2C5; font-size: 12px; }
  .config { font-family: Consolas, monospace; font-size: 11px; color: #EFDFBB; background: #2A2F42; border: 1px solid #3A415A; padding: 4px 10px; border-radius: 999px; }
  .controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  #profile { min-width: 210px; background: #2A2F42; border: 1px solid #3A415A; color: #E8E8EE; border-radius: 8px; padding: 7px 10px; }
  #sample { background: #2A2F42; border: 1px solid #3A415A; color: #E8E8EE; border-radius: 8px; padding: 7px 10px; }
  header button { background: #722F37; border: 0; color: #FBF5E7; padding: 7px 13px; border-radius: 8px; font-weight: 600; cursor: pointer; }
  header button:hover { background: #8A424B; }
  main { max-width: 980px; margin: 0 auto; padding: 18px 16px 140px; }
  .samplebar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; background: #fff; border: 1px solid #E5D9BC; border-radius: 12px; padding: 10px 14px; margin: 12px 0; box-shadow: 0 1px 3px rgba(27,31,46,.06); }
  .samplebar .meta { font-size: 13px; color: #5C4033; }
  .samplebar .meta b { color: #722F37; }
  .turnchip { font-family: Consolas, monospace; font-size: 11px; background: #EFDFBB; color: #5C4033; border-radius: 999px; padding: 3px 10px; }
  .scenario { font-size: 11px; text-transform: uppercase; letter-spacing: .6px; background: #1B1F2E; color: #FBF5E7; border-radius: 999px; padding: 3px 10px; }
  .row { display: flex; margin: 10px 0; }
  .bubble { max-width: 78%; padding: 10px 14px; border-radius: 14px; line-height: 1.45; white-space: pre-wrap; word-wrap: break-word; }
  .user { margin-left: auto; background: #722F37; color: #FBF5E7; border-bottom-right-radius: 4px; }
  .agent { margin-right: auto; background: #fff; border: 1px solid #E5D9BC; border-bottom-left-radius: 4px; }
  .chipline { margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap; }
  .chip { font-size: 11px; letter-spacing: .3px; border-radius: 999px; padding: 2px 9px; }
  .chip.ask { color: #92600A; border: 1px solid #E5C07B; background: #FBF0DA; text-transform: uppercase; }
  .chip.turn { color: #5C4033; background: #EFDFBB; border: 1px solid #E0CFA4; font-family: Consolas, monospace; }
  .chip.ms { color: #5C4033; background: #F6EFE0; border: 1px solid #E0D5BB; font-family: Consolas, monospace; }
  .panel { background: #fff; border: 1px solid #E5D9BC; border-radius: 12px; padding: 12px 14px; margin: 8px 0 18px; box-shadow: 0 1px 3px rgba(27,31,46,.06); }
  .panel h3 { margin: 0 0 8px; font-size: 13px; color: #722F37; font-family: Georgia, serif; }
  .recs-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin: 14px 0 8px; }
  .recs-head h3 { margin: 0; font-size: 14px; font-family: Georgia, serif; color: #1B1F2E; }
  .toggle { display: inline-flex; border: 1px solid #D9CBA8; border-radius: 999px; overflow: hidden; background: #fff; }
  .toggle button { border: 0; background: transparent; color: #5C4033; padding: 6px 12px; font-size: 12px; cursor: pointer; }
  .toggle button.on { background: #722F37; color: #FBF5E7; font-weight: 600; }
  .arm-note { font-size: 11px; color: #8A7A5E; font-style: italic; }
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(285px, 1fr)); gap: 10px; }
  .card { background: #fff; border: 1px solid #E5D9BC; border-radius: 12px; padding: 10px; display: flex; gap: 10px; box-shadow: 0 1px 3px rgba(27,31,46,.05); }
  .card .rank { flex: none; width: 26px; height: 26px; border-radius: 50%; background: #1B1F2E; color: #FBF5E7; font-family: Consolas, monospace; font-size: 12px; display: flex; align-items: center; justify-content: center; align-self: flex-start; }
  .card .rank.top { background: #722F37; }
  .card img { flex: none; width: 52px; height: 52px; object-fit: contain; border-radius: 8px; background: #F6EFE0; border: 1px solid #E5D9BC; }
  .card .body { min-width: 0; flex: 1; }
  .card .title { font-size: 12px; font-weight: 600; line-height: 1.3; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  .card .sub { font-size: 11px; color: #5C4033; margin-top: 2px; font-family: Consolas, monospace; }
  .card .reason { font-size: 11px; color: #8A7A5E; margin-top: 3px; font-style: italic; }
  .prov { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 5px; }
  .prov span { font-family: Consolas, monospace; font-size: 10px; padding: 1px 7px; border-radius: 999px; background: #F6EFE0; color: #5C4033; border: 1px solid #E0D5BB; }
  .prov span.cov { background: #F7E9E4; color: #722F37; border-color: #E3C3BB; }
  .prov span.viol { background: #F9E3E3; color: #A02C2C; border-color: #E7BDBD; }
  .prov span.move { background: #EFDFBB; color: #5C4033; border-color: #E0CFA4; }
  .funnel { display: flex; align-items: center; gap: 8px; margin: 10px 0 8px; flex-wrap: wrap; }
  .funnel .step { background: #F6EFE0; border: 1px solid #E0D5BB; border-radius: 10px; padding: 8px 12px; text-align: center; min-width: 104px; }
  .funnel .step b { color: #722F37; font-size: 17px; display: block; font-family: Consolas, monospace; }
  .funnel .step span { font-size: 11px; color: #5C4033; }
  .funnel .arrow { color: #B09A6E; font-size: 18px; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 8px; margin: 10px 0; }
  .tiles .tile { background: #F6EFE0; border: 1px solid #E0D5BB; border-radius: 10px; padding: 10px; }
  .tiles .tile h4 { margin: 0 0 6px; font-size: 11px; text-transform: uppercase; letter-spacing: .5px; color: #8A7A5E; }
  .spark { display: flex; align-items: flex-end; gap: 2px; height: 44px; }
  .spark i { flex: 1; background: linear-gradient(180deg, #722F37, #C98A93); border-radius: 2px 2px 0 0; min-height: 3px; }
  .donut-row { display: flex; align-items: center; gap: 10px; }
  .donut { width: 46px; height: 46px; border-radius: 50%; flex: none; }
  .donut::after { content: ''; display: block; width: 22px; height: 22px; margin: 12px; border-radius: 50%; background: #F6EFE0; }
  .legend { font-size: 11px; color: #5C4033; line-height: 1.6; }
  .catrows { font-size: 11px; line-height: 1.7; color: #1B1F2E; }
  .catrows .bar { display: inline-block; height: 6px; background: #722F37; border-radius: 3px; vertical-align: middle; margin-left: 6px; }
  .catrows .cnt { color: #8A7A5E; margin-left: 6px; font-family: Consolas, monospace; }
  .constraints { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }
  .constraints .c { font-size: 11px; border-radius: 999px; padding: 3px 10px; border: 1px solid #E0D5BB; background: #F6EFE0; color: #1B1F2E; }
  .constraints .c b { color: #722F37; font-weight: 600; }
  .constraints .c.nopref { border-style: dashed; color: #8A7A5E; }
  .constraints .c.stale { opacity: .55; text-decoration: line-through; }
  .metrics { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
  .metrics .m { font-family: Consolas, monospace; font-size: 11px; background: #1B1F2E; color: #EFDFBB; border-radius: 8px; padding: 5px 10px; }
  .metrics .m b { color: #FBF5E7; }
  details summary { cursor: pointer; color: #5C4033; font-size: 12px; margin-top: 8px; }
  .pooltable table { width: 100%; border-collapse: collapse; font-size: 11px; margin-top: 6px; }
  .pooltable th { text-align: left; color: #8A7A5E; border-bottom: 1px solid #E0D5BB; padding: 5px 4px; }
  .pooltable td { padding: 5px 4px; border-bottom: 1px solid #F0E8D5; font-family: Consolas, monospace; }
  .pooltable td.t { font-family: 'Segoe UI', sans-serif; }
  .pager { display: flex; gap: 8px; align-items: center; margin-top: 8px; }
  .pager button { background: #F6EFE0; border: 1px solid #E0D5BB; color: #1B1F2E; padding: 5px 10px; border-radius: 8px; cursor: pointer; }
  .pager button:disabled { opacity: .4; cursor: default; }
  .endbanner { background: #722F37; color: #FBF5E7; border-radius: 12px; padding: 12px 16px; margin: 12px 0; display: flex; align-items: center; gap: 12px; }
  .endbanner .big { font-size: 15px; font-weight: 700; }
  .endbanner .small { font-size: 12px; color: #EFCFC8; }
  .reveal { display: flex; gap: 12px; align-items: center; }
  .reveal img { width: 64px; height: 64px; object-fit: contain; border-radius: 8px; background: #F6EFE0; border: 1px solid #E0D5BB; }
  .traj { margin-left: auto; }
  .traj svg { display: block; }
  .traj .cap { font-size: 10px; color: #EFCFC8; text-align: right; }
  form { position: fixed; bottom: 0; left: 0; right: 0; background: #1B1F2E; border-top: 1px solid #3A415A; padding: 12px; display: flex; gap: 8px; max-width: 1012px; margin: 0 auto; }
  input[type=text] { flex: 1; background: #2A2F42; border: 1px solid #3A415A; color: #E8E8EE; border-radius: 10px; padding: 11px 14px; font-size: 14px; outline: none; }
  input[type=text]:focus { border-color: #C98A93; }
  button[type=submit] { background: #722F37; border: 0; color: #FBF5E7; border-radius: 10px; padding: 0 18px; font-weight: 600; cursor: pointer; }
  #nextturn { background: #EFDFBB; border: 0; color: #5C4033; border-radius: 10px; padding: 0 16px; font-weight: 700; cursor: pointer; display: none; }
  .hint { color: #8A7A5E; font-size: 12px; text-align: center; margin: 14px 0; }
  .thinking { color: #8A7A5E; font-style: italic; }
</style>
</head>
<body>
<header>
  <div class="brand"><h1>ShopCopilot <span>·</span></h1><small>TechJam 2026 — live agent demo</small></div>
  <div class="controls">
    <span class="config">__CONFIG_BANNER__</span>
    <input id="profile" aria-label="Preference tags" placeholder="Profile tags: comfort, durability">
    <select id="sample" aria-label="Sampled session"></select>
    <button id="loadSample">Load sampled session</button>
    <button id="reset">New session</button>
  </div>
</header>
<main id="log"><p class="hint">Free chat, or load a sampled evaluator session (outcomes pre-verified on dev-160). Try: “I need casual women's shoes under $120” · “running shoes with cushioning”.</p></main>
<form id="f">
  <button type="button" id="nextturn">Next turn ▸</button>
  <input id="i" type="text" autocomplete="off" placeholder="Tell the copilot what you're looking for…" autofocus>
  <button type="submit">Send</button>
</form>
<script>
const CONFIG_BANNER = "__CONFIG_BANNER__";
const SAMPLES = __SAMPLE_OPTIONS__;
let sessionId = null, turn = 0, mode = 'chat', arm = 'final', lastPayload = null, sampleTarget = null;

const log = document.getElementById('log');
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');

function fillSamples(){
  const sel = $('sample');
  sel.innerHTML = SAMPLES.map(s => `<option value="${s.sample_id}">${s.sample_id} — ${esc(s.label)}</option>`).join('');
}

const addBubble = (cls, html) => {
  const row = document.createElement('div'); row.className = 'row';
  const b = document.createElement('div'); b.className = 'bubble ' + cls;
  b.innerHTML = html; row.appendChild(b); log.appendChild(row);
  window.scrollTo(0, document.body.scrollHeight); return b;
};

async function postJSON(url, body){
  const res = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const data = await res.json();
  if (res.status !== 200) throw new Error(data.error || ('HTTP ' + res.status));
  return data;
}

// ---------- recommendation cards + toggle (FLIP animated re-sort) ----------

function provChips(p, finalRank){
  if (!p) return '';
  const parts = [
    `<span class="cov" title="IDF-weighted constraint coverage">cov ${p.coverage.toFixed(2)}</span>`,
    `<span title="mean field salience of satisfied constraints">sal ${p.salience.toFixed(2)}</span>`,
    `<span title="normalized popularity">pop ${p.popularity.toFixed(2)}</span>`,
  ];
  if (p.pool_rank && p.pool_rank !== finalRank) parts.push(`<span class="move" title="pool position before ranking → final rank">pool #${p.pool_rank} → #${finalRank}</span>`);
  parts.push(p.violations ? `<span class="viol" title="hard constraint violations">viol ${p.violations}</span>` : `<span title="hard constraint violations">viol 0</span>`);
  return `<div class="prov">${parts.join('')}</div>`;
}

function cardsHtml(recs){
  return recs.map((r, i) => `
    <div class="card" data-asin="${r.parent_asin}">
      <div class="rank ${i < 3 ? 'top' : ''}">${i + 1}</div>
      <img loading="lazy" src="${r.image}" alt="">
      <div class="body">
        <div class="title" title="${esc(r.title)}">${esc(r.title)}</div>
        <div class="sub">${r.price ?? '—'} · score ${Number(r.score).toFixed(3)}${r.rating ? ' · ★ ' + r.rating : ''}</div>
        ${r.reason ? `<div class="reason">${esc(r.reason)}</div>` : ''}
        ${provChips(r.provenance, i + 1)}
      </div>
    </div>`).join('');
}

function flipRerender(container, html){
  const first = new Map();
  container.querySelectorAll('[data-asin]').forEach(el => first.set(el.dataset.asin, el.getBoundingClientRect().top));
  container.innerHTML = html;
  container.querySelectorAll('[data-asin]').forEach(el => {
    const prev = first.get(el.dataset.asin);
    if (prev == null) return;
    const delta = prev - el.getBoundingClientRect().top;
    if (!delta) return;
    el.style.transition = 'none';
    el.style.transform = `translateY(${delta}px)`;
    requestAnimationFrame(() => {
      el.style.transition = 'transform .45s cubic-bezier(.22,.9,.28,1)';
      el.style.transform = '';
    });
  });
}

function setArm(a){
  arm = a;
  document.querySelectorAll('.toggle button').forEach(b => b.classList.toggle('on', b.dataset.arm === a));
  if (!lastPayload) return;
  const grid = document.getElementById('cards');
  if (!grid) return;
  const recs = arm === 'final' ? lastPayload.recommendations : (lastPayload.baseline || []);
  flipRerender(grid, cardsHtml(recs));
  const note = document.querySelector('.arm-note');
  if (note) note.textContent = arm === 'final'
    ? 'shipped config — buying-gated salience 0.2 / popularity 1.0'
    : 'pre-experiment weights — salience 0.5 / popularity 1.0, same pool re-scored';
}

function recsSection(payload){
  const hasBase = payload.baseline && payload.baseline.length;
  const same = hasBase && JSON.stringify(payload.baseline.map(r => r.parent_asin)) === JSON.stringify(payload.recommendations.map(r => r.parent_asin));
  const note = same ? 'identical ordering this turn — the shipped change is buying-gated (no difference expected on browsing turns)'
    : 'shipped config — buying-gated salience 0.2 / popularity 1.0';
  const toggle = hasBase ? `
    <div class="toggle" role="group" aria-label="Ranking config toggle">
      <button data-arm="final" class="${arm === 'final' ? 'on' : ''}">Final · shipped</button>
      <button data-arm="baseline" class="${arm === 'baseline' ? 'on' : ''}">Baseline · pre-experiment</button>
    </div>` : '';
  return `
    <div class="recs-head">
      <h3>Final 10 — deterministic ranker</h3>
      ${toggle}<span class="arm-note">${note}</span>
    </div>
    <div class="cards" id="cards">${cardsHtml(payload.recommendations)}</div>`;
}

// ---------- diagnostics panel ----------

function funnelHtml(d){
  return `<div class="funnel">
    <div class="step"><b>${d.catalog.toLocaleString()}</b><span>catalog</span></div>
    <div class="arrow">→</div>
    <div class="step"><b>${d.hybrid}</b><span>hybrid retrieval</span></div>
    <div class="arrow">→</div>
    <div class="step"><b>${d.pool}</b><span>candidate pool</span></div>
    <div class="arrow" title="rerank cap ${d.rerank_cap} ≥ pool — every candidate is scored">→</div>
    <div class="step"><b>${d.scored}</b><span>scored (cap ${d.rerank_cap})</span></div>
    <div class="arrow">→</div>
    <div class="step"><b>${d.final}</b><span>top 10</span></div>
  </div>`;
}

function tilesHtml(s){
  if (!s || !s.n) return '';
  const max = Math.max(...s.score_decay, 1e-6);
  const bars = s.score_decay.map(v => `<i style="height:${Math.max(4, Math.round(v / max * 100))}%"></i>`).join('');
  const tot = s.sources.bm25 + s.sources.semantic + s.sources.both || 1;
  const donut = `conic-gradient(#722F37 0 ${(s.sources.bm25 / tot * 100).toFixed(1)}%, #C98A93 0 ${((s.sources.bm25 + s.sources.semantic) / tot * 100).toFixed(1)}%, #5C4033 0 100%)`;
  const catMax = Math.max(...s.top_categories.map(c => c[1]), 1);
  const cats = s.top_categories.map(([k, v]) => `<div>${esc(k)}<span class="bar" style="width:${Math.round(v / catMax * 60)}px"></span><span class="cnt">${v}</span></div>`).join('') || '<div>—</div>';
  const pc = s.price_coverage;
  return `
    <div class="tile"><h4>score decay (n=${s.n})</h4><div class="spark">${bars}</div></div>
    <div class="tile"><h4>source mix</h4><div class="donut-row"><div class="donut" style="background:${donut}"></div><div class="legend">bm25 ${s.sources.bm25}<br>semantic ${s.sources.semantic}<br>both ${s.sources.both}</div></div></div>
    <div class="tile"><h4>top-5 categories</h4><div class="catrows">${cats}</div></div>
    <div class="tile"><h4>coverage</h4><div class="catrows"><div>priced <span class="cnt">${pc.priced}/${pc.total}</span></div><div>ASINs in catalog <span class="cnt">${pc.in_catalog}/${pc.total}</span></div></div></div>`;
}

function constraintsHtml(c){
  if (!c) return '';
  const chip = (k, v, cls = '') => `<span class="c ${cls}"><b>${esc(k)}:</b> ${esc(v)}${v === 'NO_PREFERENCE' ? ' (never re-asked)' : ''}</span>`;
  const active = Object.entries(c.constraints || {}).map(([k, v]) => chip(k, v, v === 'NO_PREFERENCE' ? 'nopref' : '')).join('');
  const stale = Object.entries(c.stale || {}).map(([k, v]) => chip(k, v, 'stale')).join('');
  const inferred = Object.entries(c.inferred || {}).map(([k, v]) => chip(k, v.value)).join('');
  const route = c.route ? `<span class="c"><b>route:</b> ${esc(c.route)}</span>` : '';
  return `<div class="constraints">${route}${active}${stale}${inferred || ''}</div>`;
}

function metricsHtml(d){
  return `<div class="metrics">
    <span class="m">turn latency <b>${d.latency_ms} ms</b></span>
    <span class="m">session p50 <b>${d.p50_ms} ms</b></span>
    <span class="m">tokens <b>${d.usage.prompt_tokens + d.usage.completion_tokens}</b></span>
    <span class="m">model cost <b>$${d.usage.cost.toFixed(2)}</b> · ${esc(d.usage.note)}</span>
  </div>`;
}

async function renderPool(wrap, d){
  const rows = [];
  const p = await postJSON('/api/debug', {session_id: sessionId, offset: 0, limit: 10});
  p.candidates.forEach(c => rows.push(c));
  const head = '<table><tr><th>#</th><th>ASIN</th><th>title</th><th>price</th><th>cov</th><th>sal</th><th>pop</th><th>viol</th><th>source</th></tr>';
  const body = rows.map(c => {
    const pr = c.provenance || {};
    return `<tr><td>${c.rank}</td><td>${c.parent_asin}</td><td class="t" title="${esc(c.title)}">${esc(c.title.slice(0, 38))}…</td><td>${c.price ?? '—'}</td><td>${pr.coverage ?? '—'}</td><td>${pr.salience ?? '—'}</td><td>${pr.popularity ?? '—'}</td><td>${pr.violations ?? '—'}</td><td>${esc(c.source)}</td></tr>`;
  }).join('');
  wrap.querySelector('.pooltable').innerHTML = head + body + `</table>
    <div class="pager"><button onclick="poolPage(0)">◀</button><span class="arm-note">showing 1–10 of ${p.total} (paginate below)</span></div>
    <div class="pager"><input id="pooloffset" type="text" style="width:70px" placeholder="offset"><button onclick="poolGo()">Show window</button></div>`;
}

window.poolPage = async off => { await renderPoolWindow(off, 10); };
window.poolGo = async () => { const v = parseInt($('pooloffset').value || '0', 10) || 0; await renderPoolWindow(v, 10); };
async function renderPoolWindow(off, lim){
  const p = await postJSON('/api/debug', {session_id: sessionId, offset: Math.max(0, off), limit: lim});
  const head = '<table><tr><th>#</th><th>ASIN</th><th>title</th><th>price</th><th>cov</th><th>sal</th><th>pop</th><th>viol</th><th>source</th></tr>';
  const body = p.candidates.map(c => {
    const pr = c.provenance || {};
    return `<tr><td>${c.rank}</td><td>${c.parent_asin}</td><td class="t" title="${esc(c.title)}">${esc(c.title.slice(0, 38))}…</td><td>${c.price ?? '—'}</td><td>${pr.coverage ?? '—'}</td><td>${pr.salience ?? '—'}</td><td>${pr.popularity ?? '—'}</td><td>${pr.violations ?? '—'}</td><td>${esc(c.source)}</td></tr>`;
  }).join('');
  document.querySelector('.pooltable').innerHTML = head + body + `</table>
    <div class="pager"><span class="arm-note">rows ${p.offset + 1}–${Math.min(p.offset + p.limit, p.total)} of ${p.total} — every candidate was scored (cap 320)</span></div>
    <div class="pager"><input id="pooloffset" type="text" style="width:70px" placeholder="offset"><button onclick="poolGo()">Show window</button></div>`;
}

function attachDebug(debug){
  const wrap = document.createElement('div'); wrap.className = 'panel';
  wrap.innerHTML = `<h3>Turn diagnostics — real production pool</h3>${funnelHtml(debug)}
    <div class="tiles">${tilesHtml(debug.stats)}</div>
    <h3>Constraint state</h3>${constraintsHtml(debug.constraints)}
    ${metricsHtml(debug)}
    <details><summary>retrieval pool — ${debug.pool} candidates (all scored)</summary>
      <div class="pooltable"><em style="color:#8A7A5E">loading…</em></div>
    </details>`;
  log.appendChild(wrap);
  window.scrollTo(0, document.body.scrollHeight);
  renderPool(wrap, debug);
}

// ---------- trajectory sparkline + reveal ----------

function sparkline(traj){
  const pts = traj.map((r, i) => r == null ? null : {t: i + 1, r}).filter(Boolean);
  if (!pts.length) return '';
  const W = 220, H = 56, pad = 6;
  const maxR = Math.max(...pts.map(p => p.r), 10);
  const x = t => pad + (t - 1) * ((W - 2 * pad) / Math.max(9, pts[pts.length - 1].t - 1 || 1));
  const y = r => H - pad - (Math.log(r) / Math.log(Math.max(maxR, 2))) * (H - 2 * pad);
  const line = pts.map(p => `${x(p.t).toFixed(1)},${y(p.r).toFixed(1)}`).join(' ');
  const dots = pts.map(p => `<circle cx="${x(p.t).toFixed(1)}" cy="${y(p.r).toFixed(1)}" r="2.6" fill="#FBF5E7" stroke="#722F37" stroke-width="1.4"/>`).join('');
  const labels = pts.map(p => `<text x="${x(p.t).toFixed(1)}" y="${(y(p.r) - 6).toFixed(1)}" font-size="8" text-anchor="middle" fill="#EFCFC8" font-family="Consolas,monospace">${p.r}</text>`).join('');
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="target rank by turn">
    <polyline points="${line}" fill="none" stroke="#FBF5E7" stroke-width="1.6"/>${dots}${labels}</svg>`;
}

function endBanner(hit, hitTurn, bestRank, traj){
  const title = hit ? '🎯 target in top-10 — session ends' : 'target not found in 10 turns — session ends';
  const sub = hit ? `first hit at turn ${hitTurn} · best rank #${bestRank}` : `best observed rank this session: ${bestRank ?? 'not in top-10'}`;
  return `<div class="endbanner">
    <div class="reveal">
      <img src="${sampleTarget.image}" alt="target product">
      <div><div class="big">${title}</div><div class="small">${sub} — hidden target: ${esc(sampleTarget.title)}</div></div>
    </div>
    <div class="traj">${sparkline(traj)}<div class="cap">target rank by turn (log scale)</div></div>
  </div>`;
}

function renderTurn(payload){
  let html = esc(payload.message);
  const chips = [`<span class="chip turn">turn ${payload.turn}/10</span>`, `<span class="chip ms">${payload.debug.latency_ms} ms</span>`];
  if (payload.ask_attribute) chips.push(`<span class="chip ask">asking: ${esc(payload.ask_attribute)}</span>`);
  if (payload.route) chips.push(`<span class="chip turn">route: ${esc(payload.route)}</span>`);
  html += `<div class="chipline">${chips.join('')}</div>`;
  addBubble('agent', html);
  if (payload.recommendations && payload.recommendations.length){
    const sec = document.createElement('div');
    sec.innerHTML = recsSection(payload);
    log.appendChild(sec);
    sec.querySelectorAll('.toggle button').forEach(b => b.onclick = () => setArm(b.dataset.arm));
  }
  attachDebug(payload.debug);
}

// ---------- free chat ----------

async function reset(){
  const tags = $('profile').value.split(',').map(x => x.trim()).filter(Boolean);
  const res = await fetch('/api/reset', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({user_profile: {preference_tags: tags}})
  });
  const data = await res.json();
  sessionId = data.session_id; turn = 0; mode = 'chat'; lastPayload = null; sampleTarget = null;
  $('nextturn').style.display = 'none'; $('i').disabled = false;
  log.innerHTML = '';
  const hint = document.createElement('p'); hint.className = 'hint';
  hint.textContent = `New session started.${tags.length ? ' Active profile: ' + tags.join(', ') + '.' : ''} Tell the copilot what you want.`;
  log.appendChild(hint);
}

$('reset').onclick = reset;

$('f').onsubmit = async (e) => {
  e.preventDefault();
  if (mode === 'sample') return;
  const input = $('i');
  const msg = input.value.trim(); if (!msg || !sessionId) return;
  input.value = '';
  addBubble('user', esc(msg));
  turn += 1;
  const wait = addBubble('agent', '<span class="thinking">thinking…</span>');
  try {
    const data = await postJSON('/api/turn', {session_id: sessionId, message: msg, turn});
    lastPayload = data;
    renderTurn(data);
    if (turn >= 10) addBubble('agent', '<span class="chip turn">turn 10/10 — the simulator ends sessions here</span>');
  } catch (err) { wait.textContent = 'Error: ' + err; }
};

// ---------- sampled evaluator session ----------

$('loadSample').onclick = async () => {
  const sampleId = $('sample').value;
  try {
    const data = await postJSON('/api/sample', {sample_id: sampleId});
    sessionId = data.session_id; turn = 0; mode = 'sample'; lastPayload = null;
    sampleTarget = data.target;
    log.innerHTML = '';
    const bar = document.createElement('div'); bar.className = 'samplebar';
    bar.innerHTML = `<span class="scenario">${esc(data.scenario_type)}</span>
      <span class="meta">sampled session <b>${esc(data.sample_id)}</b> — replayed live through the frozen evaluator's own session driver</span>
      <span class="turnchip" id="turnchip">turn 0/10</span>
      <span class="meta" style="margin-left:auto">hidden target revealed at session end</span>`;
    log.appendChild(bar);
    addBubble('user', esc(data.user_message));
    $('nextturn').style.display = 'inline-block'; $('i').disabled = true; $('i').value = '';
    $('nextturn').disabled = false;
  } catch (err) { alert('Could not load session: ' + err.message); }
};

$('nextturn').onclick = async () => {
  if (mode !== 'sample' || !sessionId) return;
  $('nextturn').disabled = true;
  const wait = addBubble('agent', '<span class="thinking">thinking…</span>');
  try {
    const data = await postJSON('/api/sample/turn', {session_id: sessionId});
    wait.remove();
    lastPayload = data;
    $('turnchip').textContent = `turn ${data.turn}/10`;
    renderTurn(data);
    if (data.session_over){
      $('nextturn').style.display = 'none';
      const banner = document.createElement('div');
      banner.innerHTML = endBanner(data.hit, data.hit_turn, data.best_rank, data.trajectory);
      log.appendChild(banner);
      window.scrollTo(0, document.body.scrollHeight);
    } else if (data.next_user_message){
      addBubble('user', esc(data.next_user_message));
      $('nextturn').disabled = false;
    }
  } catch (err) {
    wait.textContent = 'Error: ' + err.message;
    $('nextturn').disabled = false;
  }
};

fillSamples();
reset();
</script>
</body>
</html>"""


PAGE = PAGE.replace("__CONFIG_BANNER__", FREEZE_BANNER).replace(
    "__SAMPLE_OPTIONS__",
    json.dumps(
        [
            {"sample_id": item["sample_id"], "label": item["label"]}
            for item in SAMPLED_SESSIONS
        ]
    ),
)


def main() -> int:
    print("Loading catalog + agent (one-off)…")
    DemoState.init()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"Serving {url} — open it in your browser. Ctrl+C to stop.")
    print(f"  {FREEZE_BANNER}")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
