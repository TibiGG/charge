"""Full recommendation pipeline with per-stage timings and a deterministic fallback."""
from __future__ import annotations

import asyncio
import time

from app.aggregate import SOURCES, compute_batteries, load_genome, load_persona
from app.catalog import pick_video
from app.render import confidence_band, render_recommendation
from app.schedule import next_free_slot
from reasoner import engine

PIPELINE_TIMEOUT_S = 6.0


def _sources_for(tree: list) -> dict:
    ids: set[str] = set()

    def walk(nodes):
        for n in nodes:
            if n.get("source_id"):
                ids.add(n["source_id"])
            for f in n.get("facts", []):
                if f.get("source_id"):
                    ids.add(f["source_id"])
            walk(n.get("children", []))

    walk(tree)
    return {i: SOURCES[i] for i in sorted(ids)}


def run_pipeline(pid: str, force_fallback: bool = False) -> dict:
    timings: dict[str, float] = {}
    t0 = time.perf_counter()

    def mark(stage: str, since: float) -> float:
        now = time.perf_counter()
        timings[stage] = round((now - since) * 1000, 1)
        return now

    persona = load_persona(pid)
    genome = load_genome(persona)
    t = mark("load", t0)
    batteries = compute_batteries(persona)
    t = mark("aggregate", t)

    mode, proofs, ranked = "reasoned", [], []
    if force_fallback:
        mode = "quick"
    else:
        facts = engine.person_facts(persona, genome, batteries["metrics"])
        result = engine.evaluate(facts)
        t = mark("problog_eval", t)
        ranked = engine.rank(result, batteries, persona.get("habits", []))
        if not ranked:
            mode = "quick"
    if mode == "reasoned":
        choice = ranked[0]
        deriv = engine.derivation(choice["action"], result, batteries)
        proofs = engine.explain(facts, choice["action"])
        t = mark("problog_explain", t)
    else:
        deriv = engine.fallback(batteries)

    action = engine.ACTIONS[deriv["action"]]
    slot = next_free_slot(action["minutes"], persona["as_of"])
    video = pick_video(action["batteries"], deriv["action"], persona["age"])
    t = mark("schedule_and_video", t)

    rec = {
        "action_id": deriv["action"], "name": action["name"], "minutes": action["minutes"],
        "batteries": action["batteries"], "p": deriv["p"], "confidence": confidence_band(deriv["p"]),
        "slot": slot, "video": video, "derivation": deriv["because"], "proofs": proofs,
        "alternatives": [{"action_id": c["action"], "name": engine.ACTIONS[c["action"]]["name"],
                          "p": round(c["p"], 2)} for c in ranked[1:3]],
    }
    rec["text"] = render_recommendation(rec, batteries, persona)
    t = mark("render", t)
    rec["sources"] = _sources_for(rec["derivation"])
    timings["total"] = round((time.perf_counter() - t0) * 1000, 1)
    return {"persona": {"id": persona["id"], "name": persona["name"]}, "mode": mode,
            "recommendation": rec, "batteries": batteries, "timings_ms": timings}


async def run_with_timeout(pid: str) -> dict:
    t0 = time.perf_counter()
    try:
        return await asyncio.wait_for(asyncio.to_thread(run_pipeline, pid), timeout=PIPELINE_TIMEOUT_S)
    except asyncio.TimeoutError:
        out = run_pipeline(pid, force_fallback=True)
        out["timings_ms"]["timed_out_after"] = round((time.perf_counter() - t0) * 1000, 1)
        out["timings_ms"]["total"] = out["timings_ms"]["timed_out_after"] + out["timings_ms"]["total"]
        return out
