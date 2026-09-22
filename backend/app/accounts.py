"""Signed-in people: /api/me/* (PocketBase token) and /api/sync/* (personal Shortcut token).

A signed-in person goes through exactly the same arithmetic and reasoning as a demo
persona: we build the same persona-shaped dict from what they've stored, then call
compute_batteries / plan_day. Nothing here makes a recommendation of its own.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import shutil
import tempfile
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from app import store
from app.aggregate import (BATTERY_ORDER, MANUAL_TYPES, SOURCES, TARGETS, compute_batteries, counts_for,
                           week_start)
from app.day import CATALOG_IDS, GYM_DEFAULT, KIT_PRESETS, KIT_WORDS, plan_day_with_timeout, tier_of
from app.render import observation_sentence

router = APIRouter()

# Bump when the privacy notice changes: everyone is asked to agree again.
CONSENT_VERSION = "2026-09-22"
CONSENT_SCOPES = ("health_data", "recommendations")
HABITS = {"yoga", "spin", "weights", "walking"}
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DEFAULT_TZ = "Europe/London"


# ---------------------------------------------------------------- who is calling

def _bearer(authorization: str | None) -> str:
    if not authorization:
        return ""
    return authorization[7:] if authorization.lower().startswith("bearer ") else authorization


def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not store.configured():
        raise HTTPException(503, "accounts are not set up on this server")
    user = store.verify(_bearer(authorization))
    if not user:
        raise HTTPException(401, "sign in again")
    return user


def consented_user(user: dict = Depends(current_user)) -> dict:
    c = store.latest_consent(user["id"])
    if not c or c["document_version"] != CONSENT_VERSION or not all(c["scopes"].get(s) for s in CONSENT_SCOPES):
        raise HTTPException(403, "consent_required")
    return user


def _tz(user: dict) -> ZoneInfo:
    try:
        return ZoneInfo(user.get("timezone") or DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TZ)


def _now(user: dict) -> datetime:
    """Their wall-clock time. The week, 'today' and the live daypart all follow it."""
    return datetime.now(timezone.utc).astimezone(_tz(user)).replace(tzinfo=None)


# ---------------------------------------------------------------- persona from storage

def _profile_ready(user: dict) -> bool:
    return bool(user.get("birth_year"))


def _calendar(user: dict) -> dict:
    r = user.get("routine") or {}
    busy: dict[str, list] = {}
    for b in r.get("busy", []):
        for d in b.get("days", []):
            busy.setdefault(str(d), []).append([b["from"], b["to"]])
    return {"timezone": user.get("timezone") or DEFAULT_TZ, "day_start": r.get("day_start") or "06:30",
            "day_end": r.get("day_end") or "22:00", "busy_by_weekday": busy, "unknown_calendar": not busy}


def _workout(w: dict) -> dict:
    manual = w["source"] == "manual"
    return {"id": w["id"], "type": w["type"], "start": w["start"], "duration_min": w["duration_min"],
            "mean_hr": w.get("mean_hr") or None, "effort": (w.get("effort") or None) if manual else None,
            "counts": w.get("counts") if manual and isinstance(w.get("counts"), list) else None,
            "note": w.get("note") or None, "source": "you" if manual else "watch", "origin": w["source"]}


def persona_for(user: dict, today: date | None = None) -> dict:
    if not _profile_ready(user):
        raise HTTPException(409, "profile_required")
    today = today or _now(user).date()
    since = week_start(today) - timedelta(days=7)
    workouts = [_workout(w) for w in store.workouts_since(user["id"], since.isoformat())
                if w["start"][:10] <= today.isoformat()]
    daily = [{"date": d["date"], "sleep_hours": d.get("sleep_hours") or 0, "steps": d.get("steps") or 0,
              "sleep_onset": d.get("sleep_onset") or None}
             for d in store.daily_since(user["id"], (today - timedelta(days=8)).isoformat())]
    kit = user.get("kit") or KIT_PRESETS["none"]
    habits = [h for h in (user.get("habits") or []) if h in HABITS]
    return {"id": user["id"], "name": user.get("name") or "You", "age": max(18, today.year - int(user["birth_year"])),
            "sex": user.get("sex") or "unknown", "menopause_status": user.get("menopause_status") or None,
            "habits": habits, "as_of": today.isoformat(), "watch_connected": True, "genome_report": None,
            "kit": kit, "equipment": tier_of(kit), "workouts": workouts,
            "daily": [d for d in daily if d["sleep_hours"] or d["steps"]], "calendar_data": _calendar(user)}


def _battery_view(p: dict, base: dict | None = None) -> dict:
    b = compute_batteries(p)
    base_vals = {x["id"]: x["value"] for x in (base or b)["batteries"]}
    for x in b["batteries"]:
        x["said"] = observation_sentence(x["id"], x["value"], x["target"])
        x["source"] = SOURCES[x["source_id"]]
        x["added"] = round(x["value"] - base_vals[x["id"]], 1)
    return b


# ---------------------------------------------------------------- account + consent

@router.get("/api/me")
def me(user: dict = Depends(current_user)):
    c = store.latest_consent(user["id"])
    ok = bool(c and c["document_version"] == CONSENT_VERSION and all(c["scopes"].get(s) for s in CONSENT_SCOPES))
    has_data = ok and bool(store.first("workouts", store.mine(user["id"])))
    return {"id": user["id"], "email": user.get("email"), "name": user.get("name") or "",
            "verified": user.get("verified", False), "consent": ok, "consent_version": CONSENT_VERSION,
            "profile_ready": _profile_ready(user), "has_data": has_data,
            "bupa": {"linked": False, "available": False}}


class ConsentIn(BaseModel):
    version: str
    scopes: dict[str, bool]


@router.post("/api/me/consent")
def consent(body: ConsentIn, user: dict = Depends(current_user)):
    if body.version != CONSENT_VERSION:
        raise HTTPException(409, "the privacy notice has changed; please read it again")
    if not all(body.scopes.get(s) for s in CONSENT_SCOPES):
        raise HTTPException(422, "Charge can't work without these")
    store.record_consent(user["id"], body.version, {s: bool(body.scopes.get(s)) for s in CONSENT_SCOPES},
                         datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return {"ok": True}


@router.get("/api/me/export")
def export(user: dict = Depends(current_user)):
    return store.export_all(user["id"])


@router.delete("/api/me")
def erase(user: dict = Depends(current_user)):
    store.erase(user["id"], datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return {"ok": True}


# ---------------------------------------------------------------- profile (User tab)

class GymWindowIn(BaseModel):
    from_: str = Field(alias="from")
    to: str
    label: str = ""


class GymIn(BaseModel):
    items: list[str] = []
    windows: list[GymWindowIn] = []


class KitIn(BaseModel):
    home: list[str] = []
    gym: GymIn | None = None


class BusyIn(BaseModel):
    days: list[int]
    from_: str = Field(alias="from")
    to: str
    label: str = ""


class RoutineIn(BaseModel):
    day_start: str = "06:30"
    day_end: str = "22:00"
    busy: list[BusyIn] = []


class ProfileIn(BaseModel):
    name: str | None = None
    birth_year: int | None = None
    sex: str | None = None
    menopause_status: str | None = None
    timezone: str | None = None
    habits: list[str] | None = None
    kit: KitIn | None = None
    routine: RoutineIn | None = None


def _clean_windows(ws) -> list[dict]:
    return [{"from": w.from_, "to": w.to, "label": w.label[:60]} for w in ws
            if HHMM.match(w.from_) and HHMM.match(w.to) and w.from_ < w.to][:10]


@router.put("/api/me/profile")
def save_profile(body: ProfileIn, user: dict = Depends(consented_user)):
    out: dict = {}
    if body.name is not None:
        out["name"] = body.name.strip()[:80]
    if body.birth_year is not None:
        if not date.today().year - 110 <= body.birth_year <= date.today().year - 18:
            raise HTTPException(422, "Charge is for adults aged 18 and over")
        out["birth_year"] = body.birth_year
    if body.sex is not None:
        out["sex"] = body.sex if body.sex in ("female", "male", "other", "unknown") else "unknown"
    if body.menopause_status is not None:
        out["menopause_status"] = body.menopause_status if body.menopause_status in ("pre", "peri", "post") else ""
    if body.timezone is not None:
        try:
            ZoneInfo(body.timezone)
            out["timezone"] = body.timezone
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(422, "unknown time zone")
    if body.habits is not None:
        out["habits"] = sorted({h for h in body.habits if h in HABITS})
    if body.kit is not None:
        k = body.kit
        out["kit"] = {"home": [i for i in k.home if i in KIT_WORDS][:10],
                      "gym": None if k.gym is None else {"items": [i for i in k.gym.items if i in KIT_WORDS][:10],
                                                         "windows": _clean_windows(k.gym.windows)}}
    if body.routine is not None:
        r = body.routine
        if not (HHMM.match(r.day_start) and HHMM.match(r.day_end) and r.day_start < r.day_end):
            raise HTTPException(422, "your day must start before it ends")
        out["routine"] = {"day_start": r.day_start, "day_end": r.day_end,
                          "busy": [{"days": sorted({d for d in b.days if 0 <= d <= 6}), "from": b.from_, "to": b.to,
                                    "label": b.label[:60]} for b in r.busy
                                   if HHMM.match(b.from_) and HHMM.match(b.to) and b.from_ < b.to][:10]}
    if out:
        store.update_user(user["id"], out)
    return get_profile(store.get_user(user["id"]))


@router.get("/api/me/profile")
def my_profile(user: dict = Depends(consented_user)):
    return get_profile(store.get_user(user["id"]))


def get_profile(u: dict) -> dict:
    return {"id": u["id"], "name": u.get("name") or "", "email": u.get("email"),
            "birth_year": u.get("birth_year") or None,
            "age": (date.today().year - u["birth_year"]) if u.get("birth_year") else None,
            "sex": u.get("sex") or "", "menopause_status": u.get("menopause_status") or "",
            "timezone": u.get("timezone") or DEFAULT_TZ, "habits": u.get("habits") or [],
            "kit": u.get("kit") or KIT_PRESETS["none"], "routine": u.get("routine") or {"day_start": "06:30",
                                                                                         "day_end": "22:00", "busy": []},
            "watch_connected": True, "items": KIT_WORDS, "habit_options": sorted(HABITS), "gym_default": GYM_DEFAULT}


# ---------------------------------------------------------------- batteries + activity

def _draft_logs(raw: str | None) -> list[dict]:
    from app.main import _parse_logs  # same validation as the demo's browser-held logs
    return [{**w, "source": "you"} for w in _parse_logs(raw)]


@router.get("/api/me/batteries")
def my_batteries(logs: str | None = None, user: dict = Depends(consented_user)):
    p = persona_for(user)
    draft = _draft_logs(logs)
    b = _battery_view({**p, "workouts": p["workouts"] + draft}, compute_batteries(p) if draft else None)
    b["own_logs"] = 0
    return {"persona": {"id": p["id"], "name": p["name"], "age": p["age"], "watch_connected": True,
                        "equipment": p["equipment"]}, **b}


@router.get("/api/me/activity")
def my_activity(user: dict = Depends(consented_user)):
    p = persona_for(user)
    b = compute_batteries(p)
    start = b["window"]["start"]
    items = [{"type": w["type"], "label": MANUAL_TYPES.get(w["type"], {}).get("label", _words(w["type"])),
              "start": w["start"], "duration_min": w["duration_min"], "mean_hr": w.get("mean_hr"),
              "source": w["source"], "origin": w["origin"], "synced": False, "id": w["id"],
              "effort": w.get("effort"), "note": w.get("note"), "counts": counts_for(w, p["age"]),
              "in_window": w["start"][:10] >= start} for w in p["workouts"]]
    items.sort(key=lambda x: x["start"], reverse=True)
    return {"as_of": p["as_of"], "window": b["window"], "items": items, "pending_sync": 0, "types": MANUAL_TYPES,
            "targets": {k: {"label": v["label"], "target": v["target"], "unit": v["unit"], "metric": v["metric"]}
                        for k, v in TARGETS.items()}}


def _words(hk_type: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", hk_type).capitalize()


class LogIn(BaseModel):
    type: str
    start: str
    duration_min: float
    effort: str = "moderate"
    counts: list[str] | None = None
    note: str = ""


@router.post("/api/me/logs")
def add_log(body: LogIn, user: dict = Depends(consented_user)):
    if body.type not in MANUAL_TYPES:
        raise HTTPException(422, "unknown activity")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?", body.start):
        raise HTTPException(422, "start must be a local date and time")
    if not 1 <= body.duration_min <= 600:
        raise HTTPException(422, "minutes must be 1-600")
    if body.start[:10] > (_now(user).date() + timedelta(days=1)).isoformat():
        raise HTTPException(422, "that's in the future")
    counts = body.counts if body.counts is not None else MANUAL_TYPES[body.type]["counts"]
    row = {"ext_id": f"m-{uuid.uuid4().hex}", "source": "manual", "type": body.type, "start": body.start[:19],
           "duration_min": round(body.duration_min, 1),
           "effort": body.effort if body.effort in ("easy", "moderate", "hard") else "moderate",
           "counts": [c for c in counts if c in BATTERY_ORDER], "note": body.note[:80]}
    store.upsert_workouts(user["id"], [row])
    return {"ok": True}


@router.delete("/api/me/logs/{rid}")
def remove_log(rid: str, user: dict = Depends(consented_user)):
    if not store.ID.match(rid):
        raise HTTPException(404, "not found")
    row = store.first("workouts", f"{store.mine(user['id'])} && id = '{rid}'")
    if not row:
        raise HTTPException(404, "not found")
    store.delete("workouts", rid)
    return {"ok": True}


# ---------------------------------------------------------------- today

@router.get("/api/me/today")
def my_today(override_sleep: bool = False, at: str | None = None, user: dict = Depends(consented_user)):
    now = _now(user)
    today = now.date()
    p = persona_for(user, today)
    if at is not None and not HHMM.match(at):
        raise HTTPException(422, "at must be HH:MM")
    logs = {d["date"]: d for d in store.day_logs(user["id"], (today - timedelta(days=2)).isoformat())}
    todays = logs.get(today.isoformat(), {})
    skip = set(todays.get("skips") or [])
    # Variety: what the last two days showed ranks a bit lower today. Today's own picks
    # don't count, so the plan holds steady while they look at it.
    recent = {a for d, row in logs.items() if d != today.isoformat() for a in (row.get("shown") or {}).values()}
    out = plan_day_with_timeout(p["id"], persona=p, at=at or now.strftime("%H:%M"), override_sleep=override_sleep,
                                taste=(taste := store.votes(user["id"])), kit=p["kit"], recent=recent, skip=skip)
    shown = {c["daypart"]: c["activity"]["id"] for c in out["cards"] if c.get("activity")}
    if shown != (todays.get("shown") or {}):
        store.save_day_log(user["id"], today.isoformat(), shown=shown)
    out["skipped"] = sorted(skip)
    out["taste"] = taste
    return out


class VoteIn(BaseModel):
    activity_id: str
    vote: str | None = None


@router.post("/api/me/votes")
def vote(body: VoteIn, user: dict = Depends(consented_user)):
    if body.activity_id not in CATALOG_IDS or body.vote not in (None, "more", "less"):
        raise HTTPException(422, "unknown activity or vote")
    store.set_vote(user["id"], body.activity_id, body.vote)
    return {"ok": True}


class SkipIn(BaseModel):
    activity_id: str
    undo: bool = False


@router.post("/api/me/skip")
def skip(body: SkipIn, user: dict = Depends(consented_user)):
    """'Something else': this idea is off the table until tomorrow."""
    if body.activity_id not in CATALOG_IDS:
        raise HTTPException(422, "unknown activity")
    today = _now(user).date().isoformat()
    row = store.first("day_log", f"{store.mine(user['id'])} && date = '{today}'") or {}
    skips = [s for s in (row.get("skips") or []) if s != body.activity_id]
    if not body.undo:
        skips.append(body.activity_id)
    store.save_day_log(user["id"], today, skips=skips[-40:])
    return {"ok": True, "skipped": skips}


# ---------------------------------------------------------------- Apple Health export upload

JOBS: dict[str, dict] = {}
KEEP_DAYS = 90  # workouts older than this are never read in; the batteries only look back 2 weeks


def _import_job(job: str, uid: str, path: str, tz: ZoneInfo) -> None:
    from ingest.apple_health import parse
    try:
        since = (datetime.now(tz).date() - timedelta(days=KEEP_DAYS)).isoformat()
        p = parse(path, max_records=None, since=since)
        rows = [{"ext_id": "x-" + hashlib.sha1(f"{w['type']}|{w['start']}".encode()).hexdigest()[:24],
                 "source": "export", "type": w["type"][:80], "start": w["start"][:19],
                 "duration_min": min(1440, w["duration_min"]), "mean_hr": w.get("mean_hr") or 0}
                for w in p["workouts"] if w["type"] and w["start"][:10] >= since]
        JOBS[job].update(stage="saving", found=len(rows))
        new = store.upsert_workouts(uid, rows)
        store.upsert_daily(uid, [{"date": d["date"], "steps": d["steps"], "sleep_hours": d["sleep_hours"],
                                  "sleep_onset": d.get("sleep_onset") or "", "exercise_min": d["exercise_min"]}
                                 for d in p["daily"]])
        u = store.get_user(uid)
        fill: dict = {}
        if not u.get("birth_year") and p.get("dob"):
            fill["birth_year"] = int(p["dob"][:4])
        if not u.get("habits"):
            from ingest.apple_health import infer_habits
            recent = [w for w in p["workouts"] if w["start"][:10] >= (date.today() - timedelta(days=14)).isoformat()]
            fill["habits"] = infer_habits(recent)
        if fill:
            store.update_user(uid, fill)
        JOBS[job].update(stage="done", new=new, days=len(p["daily"]), records_read=p["records_read"])
    except Exception as e:  # noqa: BLE001 - reported to the person, logged here
        JOBS[job].update(stage="error", error="We couldn't read that file. Is it the export.zip from the Health app?")
        print(f"[charge] import {job} failed: {e!r}")
    finally:
        import os
        try:
            os.unlink(path)
        except OSError:
            pass


@router.post("/api/me/import")
def import_export(file: UploadFile, user: dict = Depends(consented_user)):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".upload")
    with tmp:
        shutil.copyfileobj(file.file, tmp, length=1 << 20)
    job = secrets.token_hex(8)
    JOBS[job] = {"stage": "reading", "user": user["id"]}
    threading.Thread(target=_import_job, args=(job, user["id"], tmp.name, _tz(user)), daemon=True).start()
    return {"job": job}


@router.get("/api/me/import/{job}")
def import_status(job: str, user: dict = Depends(current_user)):
    j = JOBS.get(job)
    if not j or j["user"] != user["id"]:
        raise HTTPException(404, "not found")
    return {k: v for k, v in j.items() if k != "user"}


# ---------------------------------------------------------------- iOS Shortcut

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/api/me/sync-token")
def new_sync_token(user: dict = Depends(consented_user)):
    """A fresh personal token for the Shortcut. Shown once; making a new one retires the old."""
    token = "chg_" + secrets.token_urlsafe(24)
    store.replace_sync_token(user["id"], _hash(token))
    return {"token": token}


def _norm_type(raw: str) -> str:
    t = str(raw).replace("HKWorkoutActivityType", "").strip()
    if " " in t or t.islower():
        t = "".join(w[:1].upper() + w[1:] for w in re.split(r"[\s_-]+", t) if w)
    aliases = {"HIIT": "HighIntensityIntervalTraining", "HighIntensityInterval": "HighIntensityIntervalTraining",
               "StrengthTraining": "TraditionalStrengthTraining", "Walk": "Walking", "Run": "Running",
               "Swim": "Swimming", "Cycle": "Cycling", "OutdoorWalk": "Walking", "IndoorWalk": "Walking",
               "OutdoorRun": "Running", "IndoorRun": "Running", "OutdoorCycle": "Cycling",
               "IndoorCycle": "Cycling", "PoolSwim": "Swimming", "OpenWaterSwim": "Swimming"}
    return aliases.get(t, t)[:80]


def _parse_when(raw: str, tz: ZoneInfo) -> datetime | None:
    s = str(raw).strip()
    for fmt in (None, "%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y, %H:%M", "%d %b %Y at %H:%M"):
        try:
            d = datetime.fromisoformat(s.replace(" +", "+")) if fmt is None else datetime.strptime(s, fmt)
        except ValueError:
            continue
        return d.astimezone(tz).replace(tzinfo=None) if d.tzinfo else d
    return None


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", ".").split()[0])
    except (ValueError, IndexError, TypeError):
        return None


@router.post("/api/sync/workouts")
async def shortcut_sync(request: Request, authorization: str | None = Header(default=None)):
    """Workouts from the iOS Shortcut. Accepts one workout or {"workouts": [...]}, with
    forgiving field names, because Shortcuts makes precise JSON awkward to build."""
    if not store.configured():
        raise HTTPException(503, "accounts are not set up on this server")
    token = _bearer(authorization)
    uid = store.token_owner(_hash(token)) if token.startswith("chg_") else None
    if not uid:
        raise HTTPException(401, "unknown token: make a new one in Charge, under You")
    body = await request.json()
    items = body.get("workouts", body) if isinstance(body, dict) else body
    items = items if isinstance(items, list) else [items]
    tz = _tz(store.get_user(uid))
    rows, bad = [], 0
    for it in items[:500]:
        if not isinstance(it, dict):
            bad += 1
            continue
        get = lambda *ks: next((it[k] for k in ks if it.get(k) not in (None, "")), None)  # noqa: E731
        typ = get("type", "name", "workoutActivityType", "activity")
        start = _parse_when(get("start", "startDate", "start_date") or "", tz)
        end = _parse_when(get("end", "endDate", "end_date") or "", tz)
        mins = (end - start).total_seconds() / 60 if start and end else _num(get("duration_min", "duration", "minutes"))
        if get("duration_s", "seconds") is not None and not (start and end):
            mins = (_num(get("duration_s", "seconds")) or 0) / 60
        if not typ or not start or not mins or not 1 <= mins <= 1440:
            bad += 1
            continue
        t = _norm_type(typ)
        st = start.strftime("%Y-%m-%dT%H:%M:%S")
        rows.append({"ext_id": "s-" + hashlib.sha1(f"{t}|{st[:16]}".encode()).hexdigest()[:24], "source": "shortcut",
                     "type": t, "start": st, "duration_min": round(mins, 1),
                     "mean_hr": _num(get("mean_hr", "heart_rate", "avg_hr", "averageHeartRate")) or 0})
    new = store.upsert_workouts(uid, rows)
    return {"ok": True, "received": len(items), "new": new, "skipped": bad}
