"""Charge API."""
from __future__ import annotations

import json
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import date, datetime

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import accounts, aggregate, scope_guard
from app.aggregate import (BATTERY_ORDER, MANUAL_TYPES, SOURCES, WEARABLE_PENDING, TARGETS, compute_batteries, counts_for,
                           load_persona, with_extra)
from app.day import CATALOG, GYM_DEFAULT, KIT_WORDS, TIERS, plan_day_with_timeout, resolve_kit
from app.render import GENETIC_FRAME, observation_sentence
from app.schedule import DAYPARTS, daypart_of, load_calendar, slot_for
from reasoner import engine


@asynccontextmanager
async def lifespan(_app):
    t = time.perf_counter()
    engine.warm()  # pay import + first-grounding cost at startup, not on the first request
    print(f"[charge] ProbLog warmed in {(time.perf_counter() - t) * 1000:.0f}ms")
    yield


app = FastAPI(title="Charge", lifespan=lifespan)
# Vercel previews get random subdomains, so a regex, not a fixed list. CORS_ORIGINS adds a custom domain.
_extra = "|".join(re.escape(o.strip()) for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip())
app.add_middleware(CORSMiddleware,
                   allow_origin_regex=r"https://charge[a-z0-9-]*\.vercel\.app|http://localhost:5173" + (f"|{_extra}" if _extra else ""),
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(accounts.router)

# The demo personas are shared by everyone, so the endpoints that change them are off in
# production (CHARGE_DEMO_WRITES=0). Signed-in people use /api/me/* instead.
DEMO_WRITES = os.environ.get("CHARGE_DEMO_WRITES", "1") == "1"


def _demo_writes_only():
    if not DEMO_WRITES:
        raise HTTPException(403, "sign in to add your own data")


def _persona_or_404(pid: str) -> dict:
    try:
        return load_persona(pid)
    except KeyError:
        raise HTTPException(404, "unknown persona")


@app.get("/api/health")
@app.get("/health")
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


ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?")


def _parse_logs(raw: str | None) -> list[dict]:
    """Manual logs from the Activity tab (kept in the browser, sent with each request)."""
    if not raw:
        return []
    try:
        out = []
        for w in json.loads(raw)[:50]:
            if w.get("type") not in MANUAL_TYPES or not ISO.fullmatch(w.get("start", "")):
                continue
            mins = float(w.get("duration_min", 0))
            if not 1 <= mins <= 600:
                continue
            out.append({"id": str(w.get("id", ""))[:40], "type": w["type"], "start": w["start"][:19],
                        "duration_min": mins, "effort": w.get("effort") if w.get("effort") in ("easy", "moderate", "hard") else "moderate",
                        "counts": [c for c in w.get("counts", MANUAL_TYPES[w["type"]]["counts"]) if c in BATTERY_ORDER],
                        "note": str(w.get("note", ""))[:80]})
        return out
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, "logs must be a JSON list")


def _persona_with(pid: str, logs: str | None, synced: bool) -> dict:
    return with_extra(_persona_or_404(pid), _parse_logs(logs), synced)


@app.get("/api/batteries/{pid}")
def batteries(pid: str, logs: str | None = None, synced: bool = False):
    t = time.perf_counter()
    p = _persona_with(pid, logs, synced)
    b = compute_batteries(p)
    # How much of each battery came from their own logs / the watch sync, so the change shows.
    base = {x["id"]: x["value"] for x in compute_batteries(_persona_or_404(pid))["batteries"]} if (logs or synced) else {}
    for x in b["batteries"]:
        x["said"] = observation_sentence(x["id"], x["value"], x["target"])
        x["source"] = SOURCES[x["source_id"]]
        x["added"] = round(x["value"] - base.get(x["id"], x["value"]), 1)
    b["own_logs"] = len(_parse_logs(logs)) + (len(WEARABLE_PENDING.get(pid, [])) if synced else 0)
    return {"persona": {"id": p["id"], "name": p["name"], "age": p["age"],
                        "watch_connected": p["watch_connected"], "equipment": p.get("equipment", "none")},
            **b, "timings_ms": {"total": round((time.perf_counter() - t) * 1000, 1)}}


HHMM = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
HABITS = {"yoga", "spin", "weights", "walking"}


def _parse_kit(raw: str | None) -> dict | None:
    """The User tab's kit profile: {"home": [items], "gym": null | {"items": [..], "windows": [{from,to,label}]}}."""
    if not raw:
        return None
    try:
        k = json.loads(raw)
        home = [i for i in k.get("home", []) if i in KIT_WORDS]
        gym = k.get("gym")
        if gym:
            windows = [{"from": w["from"], "to": w["to"], "label": str(w.get("label", ""))[:60]}
                       for w in gym.get("windows", []) if HHMM.fullmatch(w.get("from", "")) and HHMM.fullmatch(w.get("to", ""))
                       and w["from"] < w["to"]]
            gym = {"items": [i for i in gym.get("items", []) if i in KIT_WORDS], "windows": windows}
        return {"home": home, "gym": gym}
    except (ValueError, AttributeError, TypeError, KeyError):
        raise HTTPException(422, "kit must be JSON like {\"home\": [\"mat\"], \"gym\": null}")


@app.get("/api/activity/{pid}")
def activity(pid: str, logs: str | None = None, synced: bool = False):
    """Everything in the 14-day window, newest first, with what each one filled."""
    p = _persona_with(pid, logs, synced)
    b = compute_batteries(p)
    start = b["window"]["start"]
    items = [{"type": w["type"], "label": MANUAL_TYPES.get(w["type"], {}).get("label", w["type"]),
              "start": w["start"], "duration_min": w["duration_min"], "mean_hr": w.get("mean_hr"),
              "source": w.get("source", "watch"), "synced": w.get("synced", False), "id": w.get("id"),
              "effort": w.get("effort"), "note": w.get("note"),
              "counts": counts_for(w, p["age"]), "in_window": w["start"][:10] >= start}
             for w in p["workouts"]]
    items.sort(key=lambda x: x["start"], reverse=True)
    return {"as_of": p["as_of"], "window": b["window"], "items": items,
            "pending_sync": 0 if synced else len(WEARABLE_PENDING.get(pid, [])),
            "types": MANUAL_TYPES, "targets": {k: {"label": v["label"], "target": v["target"], "unit": v["unit"],
                                                   "metric": v["metric"]} for k, v in TARGETS.items()}}


@app.get("/api/profile/{pid}")
def profile(pid: str):
    """Everything the User tab can change, with what we'd use if they change nothing."""
    p = _persona_or_404(pid)
    return {"id": p["id"], "name": p["name"], "age": p["age"], "habits": p.get("habits", []),
            "watch_connected": p["watch_connected"], "kit": resolve_kit(p, None, None),
            "items": KIT_WORDS, "habit_options": sorted(HABITS), "gym_default": GYM_DEFAULT}


@app.get("/api/today/{pid}")
def today(pid: str, at: str | None = None, equipment: str | None = None, override_sleep: bool = False,
          more: str = "", less: str = "", kit: str | None = None, age: int | None = None,
          habits: str | None = None, logs: str | None = None, synced: bool = False, skip: str = ""):
    """Three daypart cards. `at` = the viewer's local HH:MM (the demo can pin it).
    `more` / `less` = comma-separated activity ids the person voted on (stored in their browser)."""
    p = _persona_or_404(pid)
    if not p["watch_connected"]:
        raise HTTPException(409, "no watch connected")
    if at is not None and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", at):
        raise HTTPException(422, "at must be HH:MM")
    if equipment is not None and equipment not in TIERS:
        raise HTTPException(422, "equipment must be none, home or gym")
    ids = {a["id"] for a in CATALOG}
    taste = {k: "more" for k in more.split(",") if k in ids}
    taste |= {k: "less" for k in less.split(",") if k in ids}
    over = {}
    if age is not None:
        if not 18 <= age <= 110:
            raise HTTPException(422, "age must be 18-110")
        over["age"] = age
    if habits is not None:
        over["habits"] = [h for h in habits.split(",") if h in HABITS]
    if logs or synced:  # their own logs + watch sync change the batteries, so the plan too
        over["workouts"] = _persona_with(pid, logs, synced)["workouts"]
    return plan_day_with_timeout(pid, at=at, tier=equipment, override_sleep=override_sleep, taste=taste,
                                 kit=_parse_kit(kit), persona_overrides=over,
                                 skip={k for k in skip.split(",") if k in ids})


class RecommendIn(BaseModel):
    user: str = "margaret"
    daypart: str | None = None
    at: str | None = None
    equipment: str | None = None
    override_sleep: bool = False


@app.post("/recommend")
@app.post("/api/recommend")
def recommend(body: RecommendIn):
    """One daypart's card (post-deploy checklist endpoint)."""
    at = body.at or {"morning": "08:00", "afternoon": "12:30", "evening": "19:30"}.get(body.daypart or "", None)
    out = today(body.user, at=at, equipment=body.equipment, override_sleep=body.override_sleep)
    dp = body.daypart or out["live"]
    card = next((c for c in out["cards"] if c["daypart"] == dp), None)
    return {"card": card, "equipment": out["equipment"], "timings_ms": out["timings_ms"]}


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
    daypart: str
    duration_min: int
    persona: str = "margaret"
    at: str | None = None


@app.post("/api/schedule/suggest")
@app.post("/schedule/suggest")
def schedule_suggest(body: ScheduleIn):
    """Free slot in this daypart + the reason we picked it. Never falls through to another daypart."""
    if body.daypart not in DAYPARTS:
        raise HTTPException(422, "daypart must be morning, afternoon or evening")
    p = _persona_or_404(body.persona)
    day = date.fromisoformat(p["as_of"])
    earliest = None
    if body.at and daypart_of(body.at) == body.daypart:
        earliest = datetime.combine(day, datetime.strptime(body.at, "%H:%M").time())
    slot = slot_for(load_calendar(p.get("calendar", "default.json")), day, body.daypart, body.duration_min, earliest)
    if slot:
        return {"slot": slot, "reason": slot["reason"]}
    return {"slot": None, "reason": f"Your {body.daypart} looks full."}


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
    """Live sample from the iOS Shortcut running on the watch (demo personas only)."""
    _demo_writes_only()
    p = _persona_or_404(s.persona)
    typ = "Walking" if s.metric in ("exercise_minutes", "AppleExerciseTime") else s.metric.replace("HKWorkoutActivityType", "")
    start = s.start or f"{p['as_of']}T{datetime.now().strftime('%H:%M:%S')}"
    aggregate.LIVE_WORKOUTS.setdefault(s.persona, []).append(
        {"type": typ, "start": start[:19], "duration_min": s.value, "mean_hr": s.mean_hr, "device": s.device, "live": True})
    return {"ok": True, "stored": typ, "batteries": compute_batteries(load_persona(s.persona))["batteries"]}


@app.delete("/api/ingest/sample")
def reset_live():
    _demo_writes_only()
    aggregate.LIVE_WORKOUTS.clear()
    return {"ok": True}


@app.post("/api/ingest/apple-health")
async def ingest_apple_health(file: UploadFile):
    _demo_writes_only()
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
