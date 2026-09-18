"""Charge API."""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import aggregate, scope_guard
from app.aggregate import SOURCES, TARGETS, compute_batteries, load_persona
from app.pipeline import run_with_timeout
from app.render import GENETIC_FRAME, observation_sentence
from app.schedule import next_free_slot
from reasoner import engine


@asynccontextmanager
async def lifespan(_app):
    t = time.perf_counter()
    engine.warm()  # pay import + first-grounding cost at startup, not on the first request
    print(f"[charge] ProbLog warmed in {(time.perf_counter() - t) * 1000:.0f}ms")
    yield


app = FastAPI(title="Charge", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _persona_or_404(pid: str) -> dict:
    try:
        return load_persona(pid)
    except KeyError:
        raise HTTPException(404, "unknown persona")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/personas")
def personas():
    out = []
    for f in sorted((aggregate.DATA / "personas").glob("*.json")):
        p = load_persona(f.stem)
        out.append({"id": p["id"], "name": p["name"], "age": p["age"], "watch_connected": p["watch_connected"]})
    return out


@app.get("/api/sources")
def sources():
    return SOURCES


@app.get("/api/batteries/{pid}")
def batteries(pid: str):
    t = time.perf_counter()
    p = _persona_or_404(pid)
    b = compute_batteries(p)
    for x in b["batteries"]:
        x["said"] = observation_sentence(x["id"], x["value"], x["target"])
        x["source"] = SOURCES[x["source_id"]]
    return {"persona": {"id": p["id"], "name": p["name"], "age": p["age"],
                        "watch_connected": p["watch_connected"]},
            **b, "timings_ms": {"total": round((time.perf_counter() - t) * 1000, 1)}}


@app.get("/api/today/{pid}")
async def today(pid: str):
    p = _persona_or_404(pid)
    if not p["watch_connected"]:
        raise HTTPException(409, "no watch connected")
    return await run_with_timeout(pid)


class AskIn(BaseModel):
    text: str
    persona: str = "margaret"


# In-scope answers are fixed, sourced sentences. The guard never lets free text reach a model.
INTENT_TO_BATTERY = {"strength": "strength", "cardio": "cardio", "peak": "peak",
                     "balance": "balance", "mobility": "mobility"}


@app.post("/api/ask")
def ask(body: AskIn):
    t = time.perf_counter()
    verdict = scope_guard.classify(body.text)
    out = {"verdict": verdict}
    if verdict["decision"] == "route_to_human":
        out["refusal"] = scope_guard.REFUSAL
    else:
        intent = verdict["intent"]
        p = _persona_or_404(body.persona)
        if intent in INTENT_TO_BATTERY:
            b = next(x for x in compute_batteries(p)["batteries"] if x["id"] == intent) if p["watch_connected"] else None
            src = TARGETS[intent]["source_id"]
            lines = [SOURCES[src]["claim"]]
            if b:
                lines.append(observation_sentence(intent, b["value"], b["target"]))
            out["answer"] = {"title": TARGETS[intent]["label"], "lines": lines, "source_id": src,
                             "source": SOURCES[src], "cta": "What should I do today?"}
        elif intent == "report":
            out["answer"] = {"title": "Your genome report", "lines": [
                "Your report can shift where we start you.", GENETIC_FRAME,
                "Tap \"Why this?\" on today's idea to see each step."],
                "source_id": "src_bupa_genomic", "source": SOURCES["src_bupa_genomic"], "cta": "What should I do today?"}
        elif intent == "sleep":
            # TODO(source): no sleep guideline in sources.json yet, so we show the number only.
            s = compute_batteries(p)["sleep_hours_mean"] if p["watch_connected"] else None
            lines = [f"Your watch shows about {s} hours of sleep a night this week."] if s else []
            lines.append("We don't give sleep advice yet. A Bupa nurse can help with sleep.")
            out["answer"] = {"title": "Sleep", "lines": lines, "source_id": None, "source": None,
                             "cta": "Talk to someone now"}
        else:  # schedule
            out["answer"] = {"title": "Your one thing for today", "lines": ["We pick one thing for you each day."],
                             "source_id": None, "source": None, "cta": "What should I do today?"}
    out["timings_ms"] = {"total": round((time.perf_counter() - t) * 1000, 1)}
    return out


class ScheduleIn(BaseModel):
    minutes: int
    persona: str = "margaret"


@app.post("/api/schedule/suggest")
def schedule_suggest(body: ScheduleIn):
    p = _persona_or_404(body.persona)
    return {"slot": next_free_slot(body.minutes, p["as_of"])}


class SampleIn(BaseModel):
    metric: str               # HK workout type (e.g. "TraditionalStrengthTraining") or "exercise_minutes"
    value: float              # minutes
    unit: str = "min"
    start: str | None = None
    end: str | None = None
    device: str | None = None
    persona: str = "margaret"
    mean_hr: float | None = None


@app.post("/api/ingest/sample")
def ingest_sample(s: SampleIn):
    """Live sample from the iOS Shortcut running on the watch."""
    p = _persona_or_404(s.persona)
    typ = "Walking" if s.metric in ("exercise_minutes", "AppleExerciseTime") else s.metric.replace("HKWorkoutActivityType", "")
    start = s.start or f"{p['as_of']}T{datetime.now().strftime('%H:%M:%S')}"
    aggregate.LIVE_WORKOUTS.setdefault(s.persona, []).append(
        {"type": typ, "start": start[:19], "duration_min": s.value, "mean_hr": s.mean_hr, "device": s.device, "live": True})
    return {"ok": True, "stored": typ, "batteries": compute_batteries(load_persona(s.persona))["batteries"]}


@app.delete("/api/ingest/sample")
def reset_live():
    aggregate.LIVE_WORKOUTS.clear()
    return {"ok": True}


@app.post("/api/ingest/apple-health")
async def ingest_apple_health(file: UploadFile):
    from ingest.apple_health import parse_export_stream
    return parse_export_stream(file.file)


# ---- Serve the built SvelteKit SPA (production / Cloud Run: one service, no CORS) ----
from pathlib import Path as _Path  # noqa: E402

from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

_WEB = _Path(__file__).resolve().parents[2] / "frontend" / "build"
if _WEB.exists():
    app.mount("/_app", StaticFiles(directory=_WEB / "_app"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = (_WEB / path).resolve()
        ok = path and f.is_file() and f.is_relative_to(_WEB.resolve())  # no ../ escapes
        return FileResponse(f if ok else _WEB / "index.html")
