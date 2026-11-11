"""Signed-in people: /api/me/* (PocketBase token + their own key) and /api/sync/* (Shortcut token).

A signed-in person goes through exactly the same arithmetic and reasoning as a demo
persona: we build the same persona-shaped dict from their vault, then call
compute_batteries / plan_day. Nothing here makes a recommendation of its own.

Everything personal lives in their sealed vault (app.vault). Each /api/me call that reads it
carries their key in the X-Charge-Key header; without it we can only add to their inbox.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import shutil
import tempfile
import threading
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from app import learn, store, vault
from app.aggregate import (BATTERY_ORDER, MANUAL_TYPES, SOURCES, TARGETS, compute_batteries, counts_for,
                           week_start)
from app.day import CATALOG_IDS, GYM_DEFAULT, KIT_PRESETS, KIT_WORDS, plan_day_with_timeout, tier_of
from app.health import HealthIn
from app.render import observation_sentence
from app.vault import key_header

router = APIRouter()

# Bump when the privacy notice changes: everyone is asked to agree again.
CONSENT_VERSION = "2026-11-11"
CONSENT_SCOPES = ("health_data", "recommendations")
HABITS = {"yoga", "spin", "weights", "walking"}
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DEFAULT_TZ = "Europe/London"
PROFILE_FIELDS = ("birth_year", "sex", "timezone", "habits", "kit", "routine")
WRAP = re.compile(r"^[A-Za-z0-9_-]{40,200}$")
SALT = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


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


def _consented(uid: str) -> bool:
    c = store.latest_consent(uid)
    return bool(c and c["document_version"] == CONSENT_VERSION and all(c["scopes"].get(s) for s in CONSENT_SCOPES))


def consented_user(user: dict = Depends(current_user)) -> dict:
    if not _consented(user["id"]):
        raise HTTPException(403, "consent_required")
    return user


def _tz(prof: dict) -> ZoneInfo:
    try:
        return ZoneInfo(prof.get("timezone") or DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TZ)


def _now(prof: dict) -> datetime:
    """Their wall-clock time. The week, 'today' and the live daypart all follow it."""
    return datetime.now(timezone.utc).astimezone(_tz(prof)).replace(tzinfo=None)


def _today(prof: dict) -> date:
    return _now(prof).date()


# ---------------------------------------------------------------- persona from the vault

def _calendar(prof: dict) -> dict:
    r = prof.get("routine") or {}
    busy: dict[str, list] = {}
    for b in r.get("busy", []):
        for d in b.get("days", []):
            busy.setdefault(str(d), []).append([b["from"], b["to"]])
    return {"timezone": prof.get("timezone") or DEFAULT_TZ, "day_start": r.get("day_start") or "06:30",
            "day_end": r.get("day_end") or "22:00", "busy_by_weekday": busy, "unknown_calendar": not busy}


def _workout(w: dict) -> dict:
    manual = w["source"] == "manual"
    return {"id": w["id"], "type": w["type"], "start": w["start"], "duration_min": w["duration_min"],
            "mean_hr": w.get("mean_hr") or None, "effort": (w.get("effort") or None) if manual else None,
            "counts": w.get("counts") if manual and isinstance(w.get("counts"), list) else None,
            "note": w.get("note") or None, "source": "you" if manual else "watch", "origin": w["source"]}


def _age(prof: dict, today: date) -> int:
    return max(18, today.year - int(prof["birth_year"]))


def persona_for(user: dict, data: dict, today: date | None = None) -> dict:
    prof = data["profile"]
    if not prof.get("birth_year"):
        raise HTTPException(409, "profile_required")
    today = today or _today(prof)
    since = (week_start(today) - timedelta(days=7)).isoformat()
    workouts = [_workout(w) for w in data["workouts"] if since <= w["start"][:10] <= today.isoformat()]
    daily = [{"date": d, "sleep_hours": v.get("sleep_hours") or 0, "steps": v.get("steps") or 0,
              "sleep_onset": v.get("sleep_onset") or None}
             for d, v in sorted(data["daily"].items())
             if (today - timedelta(days=8)).isoformat() <= d <= today.isoformat()]
    kit = prof.get("kit") or KIT_PRESETS["none"]
    habits = [h for h in (prof.get("habits") or []) if h in HABITS]
    return {"id": user["id"], "name": user.get("name") or "You", "age": _age(prof, today),
            "sex": prof.get("sex") or "unknown", "menopause_status": None,
            "habits": habits, "as_of": today.isoformat(), "watch_connected": True, "genome_report": None,
            "kit": kit, "equipment": tier_of(kit), "workouts": workouts,
            "daily": [d for d in daily if d["sleep_hours"] or d["steps"]], "calendar_data": _calendar(prof)}


def _battery_view(p: dict, base: dict | None = None) -> dict:
    b = compute_batteries(p)
    base_vals = {x["id"]: x["value"] for x in (base or b)["batteries"]}
    for x in b["batteries"]:
        x["said"] = observation_sentence(x["id"], x["value"], x["target"])
        x["source"] = SOURCES[x["source_id"]]
        x["added"] = round(x["value"] - base_vals[x["id"]], 1)
    return b


def _health_in(data: dict) -> HealthIn | None:
    h = data.get("health")
    return HealthIn(**{k: v for k, v in h.items() if k != "updated"}) if h else None


# ---------------------------------------------------------------- account + consent

@router.get("/api/me")
def me(user: dict = Depends(current_user), sk: bytes | None = Depends(key_header)):
    """Who they are, and where they are in setting up: consent, their key, their profile."""
    ok = _consented(user["id"])
    st = vault.state(user["id"], sk)
    ready = has_data = False
    if st == "open":
        with vault.opened(user["id"], sk) as v:
            ready = bool(v.data["profile"].get("birth_year"))
            has_data = bool(v.data["workouts"])
    return {"id": user["id"], "email": user.get("email"), "name": user.get("name") or "",
            "verified": user.get("verified", False), "consent": ok, "consent_version": CONSENT_VERSION,
            "vault": st, "profile_ready": ready, "has_data": ok and has_data,
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
def export(user: dict = Depends(current_user), sk: bytes | None = Depends(key_header)):
    out = store.export_all(user["id"])
    if vault.state(user["id"], sk) != "none":
        with vault.opened(user["id"], sk) as v:
            out["vault"] = v.data
    return out


@router.delete("/api/me")
def erase(user: dict = Depends(current_user)):
    store.erase(user["id"], datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return {"ok": True}


# ---------------------------------------------------------------- their key

class WrapsIn(BaseModel):
    """Their key, locked in the browser by their password and by their recovery key.
    `kdf` = {"pw": {"salt", "iter"}, "rk": {"salt", "iter"}}: how to rebuild each lock."""
    kdf: dict = {}
    wrap_pw: str | None = None
    wrap_rk: str | None = None


def _clean_wraps(body: WrapsIn) -> dict:
    out: dict = {}
    for name in ("wrap_pw", "wrap_rk"):
        val = getattr(body, name)
        if val is not None:
            if val and not WRAP.match(val):
                raise HTTPException(422, f"{name} is not a locked key")
            out[name] = val
    kdf = {}
    for k in ("pw", "rk"):
        spec = body.kdf.get(k)
        if spec is None:
            continue
        if not (isinstance(spec, dict) and SALT.match(str(spec.get("salt", "")))
                and isinstance(spec.get("iter"), int) and 1000 <= spec["iter"] <= 5_000_000):
            raise HTTPException(422, "bad kdf")
        kdf[k] = {"salt": spec["salt"], "iter": spec["iter"]}
    if kdf:
        out["kdf"] = kdf
    return out


@router.get("/api/me/vault")
def my_locks(user: dict = Depends(current_user)):
    """The locked copies of their key, for a new device to open with their password or recovery key."""
    rec = store.vault_of(user["id"], with_box=False)
    if not rec:
        return {"exists": False}
    return {"exists": True, "kdf": rec.get("kdf") or {}, "wrap_pw": rec.get("wrap_pw") or "",
            "wrap_rk": rec.get("wrap_rk") or ""}


def _legacy_data(user: dict) -> tuple[dict, dict]:
    """An account from before vaults: seal what it stored in plain rows, then delete those."""
    rows = store.legacy(user["id"])
    data = vault.empty()
    data["profile"] = {k: user[k] for k in PROFILE_FIELDS if user.get(k) not in (None, "", 0, [], {})}
    if user.get("menopause_status") in ("pre", "peri", "post"):
        learn.record(data, {**HealthIn().model_dump(), "menopause": user["menopause_status"]}, date.today())
    keep = ("ext_id", "source", "type", "start", "duration_min", "mean_hr", "effort", "counts", "note")
    data["workouts"] = sorted(({"id": w["id"], **{k: w.get(k) for k in keep}} for w in rows["workouts"]),
                              key=lambda w: w["start"])
    data["daily"] = {d["date"]: {k: d.get(k) for k in ("steps", "sleep_hours", "sleep_onset", "exercise_min")}
                     for d in rows["daily"]}
    data["votes"] = {v["activity_id"]: v["vote"] for v in rows["votes"]}
    data["days"] = {d["date"]: {"shown": d.get("shown") or {}, "skips": d.get("skips") or []} for d in rows["day_log"]}
    return data, rows


@router.post("/api/me/vault")
def make_vault(body: WrapsIn, user: dict = Depends(current_user), sk: bytes | None = Depends(key_header)):
    """First time on Charge (or the first time since vaults): seal everything under their new key."""
    if sk is None:
        raise HTTPException(422, "send the new key in X-Charge-Key")
    if store.vault_of(user["id"], with_box=False):
        raise HTTPException(409, "vault_exists")
    wraps = _clean_wraps(body)
    if not wraps.get("wrap_rk"):
        raise HTTPException(422, "a recovery key is needed")
    u = store.get_user(user["id"])
    data, rows = _legacy_data(u)
    vault.create(user["id"], sk, wraps, data)
    store.drop_legacy(user["id"], rows)
    blank = {"birth_year": 0, "sex": "", "menopause_status": "", "timezone": "", "habits": None, "kit": None,
             "routine": None}
    if blank := {f: v for f, v in blank.items() if u.get(f)}:
        store.update_user(user["id"], blank)
    return {"ok": True, "moved": sum(len(r) for r in rows.values())}


@router.put("/api/me/vault")
def relock(body: WrapsIn, user: dict = Depends(current_user), sk: bytes | None = Depends(key_header)):
    """New locks for the same key: after a password reset, or a new recovery key."""
    wraps = _clean_wraps(body)
    with vault.opened(user["id"], sk) as v:  # proves they hold the key
        store.set_wraps(v.rec_id, wraps)
    return {"ok": True}


class StartAgainIn(BaseModel):
    confirm: str


@router.post("/api/me/vault/reset")
def start_again(body: StartAgainIn, user: dict = Depends(current_user)):
    """Lost both their password and their recovery key: nobody can open the old vault, so it goes."""
    if body.confirm != "START AGAIN":
        raise HTTPException(422, "type START AGAIN to confirm")
    store.wipe_vault(user["id"])
    return {"ok": True}


def _vault_of(user: dict, sk: bytes | None):
    return vault.opened(user["id"], sk)


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
    timezone: str | None = None
    habits: list[str] | None = None
    kit: KitIn | None = None
    routine: RoutineIn | None = None


def _clean_windows(ws) -> list[dict]:
    return [{"from": w.from_, "to": w.to, "label": w.label[:60]} for w in ws
            if HHMM.match(w.from_) and HHMM.match(w.to) and w.from_ < w.to][:10]


@router.put("/api/me/profile")
def save_profile(body: ProfileIn, user: dict = Depends(consented_user), sk: bytes | None = Depends(key_header)):
    out: dict = {}
    if body.birth_year is not None:
        if not date.today().year - 110 <= body.birth_year <= date.today().year - 18:
            raise HTTPException(422, "Charge is for adults aged 18 and over")
        out["birth_year"] = body.birth_year
    if body.sex is not None:
        out["sex"] = body.sex if body.sex in ("female", "male", "other", "unknown") else "unknown"
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
    with _vault_of(user, sk) as v:
        if out:
            v.data["profile"].update(out)
            v.changed()
        prof = dict(v.data["profile"])
    if body.name is not None:  # their name stays on the account, like their email
        user = store.update_user(user["id"], {"name": body.name.strip()[:80]})
    return get_profile(user, prof)


@router.get("/api/me/profile")
def my_profile(user: dict = Depends(consented_user), sk: bytes | None = Depends(key_header)):
    with _vault_of(user, sk) as v:
        return get_profile(user, v.data["profile"])


def get_profile(u: dict, prof: dict) -> dict:
    by = prof.get("birth_year")
    return {"id": u["id"], "name": u.get("name") or "", "email": u.get("email"),
            "birth_year": by or None, "age": (date.today().year - by) if by else None,
            "sex": prof.get("sex") or "", "timezone": prof.get("timezone") or DEFAULT_TZ,
            "habits": prof.get("habits") or [], "kit": prof.get("kit") or KIT_PRESETS["none"],
            "routine": prof.get("routine") or {"day_start": "06:30", "day_end": "22:00", "busy": []},
            "watch_connected": True, "items": KIT_WORDS, "habit_options": sorted(HABITS), "gym_default": GYM_DEFAULT}


# ---------------------------------------------------------------- health check + what we learned

class HealthPut(BaseModel):
    health: HealthIn | None = None


@router.get("/api/me/health")
def my_health(user: dict = Depends(consented_user), sk: bytes | None = Depends(key_header)):
    with _vault_of(user, sk) as v:
        return {"health": v.data["health"]}


@router.put("/api/me/health")
def save_health(body: HealthPut, user: dict = Depends(consented_user), sk: bytes | None = Depends(key_header)):
    """Saved in their vault, with a note of what changed and when (so we know when to ask again)."""
    with _vault_of(user, sk) as v:
        learn.record(v.data, None if body.health is None else body.health.model_dump(), _today(v.data["profile"]))
        v.changed()
        return {"health": v.data["health"]}


def _learned(user: dict, data: dict, today: date) -> dict:
    age = _age(data["profile"], today) if data["profile"].get("birth_year") else 40
    out = learn.learn(data, today, age)
    for q in out["ask"]:
        q["source"] = SOURCES.get(q["source_id"]) if q["source_id"] else None
    return out


@router.get("/api/me/learned")
def my_learned(user: dict = Depends(consented_user), sk: bytes | None = Depends(key_header)):
    with _vault_of(user, sk) as v:
        out = _learned(user, v.data, _today(v.data["profile"]))
        return {"ask": out["ask"], "learned": out["learned"]}


class AnswerIn(BaseModel):
    id: str
    value: str


@router.post("/api/me/answers")
def answer(body: AnswerIn, user: dict = Depends(consented_user), sk: bytes | None = Depends(key_header)):
    """An answer to one of our questions, or "undo" on something we learned. Only ones we asked."""
    with _vault_of(user, sk) as v:
        today = _today(v.data["profile"])
        now = _learned(user, v.data, today)
        q = next((q for q in now["ask"] if q["id"] == body.id), None)
        if q is not None:
            if body.value not in {o["value"] for o in q["options"]}:
                raise HTTPException(422, "not one of the answers")
        elif not (body.value == "yes" and any(x["id"] == body.id for x in now["learned"])):
            raise HTTPException(404, "we didn't ask that")
        learn.answer(v.data, body.id, body.value, today)
        v.changed()
        after = _learned(user, v.data, today)
        return {"ok": True, "ask": after["ask"], "learned": after["learned"]}


# ---------------------------------------------------------------- batteries + activity

def _draft_logs(raw: list | None) -> list[dict]:
    from app.main import _parse_logs  # same validation as the demo's browser-held logs
    return [{**w, "source": "you"} for w in _parse_logs(json.dumps(raw))] if raw else []


def _batteries(user: dict, sk: bytes | None, logs: list | None):
    with _vault_of(user, sk) as v:
        p = persona_for(user, v.data)
    draft = _draft_logs(logs)
    b = _battery_view({**p, "workouts": p["workouts"] + draft}, compute_batteries(p) if draft else None)
    b["own_logs"] = 0
    return {"persona": {"id": p["id"], "name": p["name"], "age": p["age"], "watch_connected": True,
                        "equipment": p["equipment"]}, **b}


class DraftIn(BaseModel):
    logs: list = []


@router.get("/api/me/batteries")
def my_batteries(user: dict = Depends(consented_user), sk: bytes | None = Depends(key_header)):
    return _batteries(user, sk, None)


@router.post("/api/me/batteries")
def my_batteries_with_draft(body: DraftIn, user: dict = Depends(consented_user),
                            sk: bytes | None = Depends(key_header)):
    """'What this will change': a log they haven't saved yet. In the body: URLs end up in logs."""
    return _batteries(user, sk, body.logs[:50])


@router.get("/api/me/activity")
def my_activity(user: dict = Depends(consented_user), sk: bytes | None = Depends(key_header)):
    with _vault_of(user, sk) as v:
        p = persona_for(user, v.data)
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
def add_log(body: LogIn, user: dict = Depends(consented_user), sk: bytes | None = Depends(key_header)):
    if body.type not in MANUAL_TYPES:
        raise HTTPException(422, "unknown activity")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?", body.start):
        raise HTTPException(422, "start must be a local date and time")
    if not 1 <= body.duration_min <= 600:
        raise HTTPException(422, "minutes must be 1-600")
    counts = body.counts if body.counts is not None else MANUAL_TYPES[body.type]["counts"]
    row = {"ext_id": f"m-{secrets.token_hex(16)}", "source": "manual", "type": body.type, "start": body.start[:19],
           "duration_min": round(body.duration_min, 1),
           "effort": body.effort if body.effort in ("easy", "moderate", "hard") else "moderate",
           "counts": [c for c in counts if c in BATTERY_ORDER], "note": body.note[:80]}
    with _vault_of(user, sk) as v:
        if body.start[:10] > (_today(v.data["profile"]) + timedelta(days=1)).isoformat():
            raise HTTPException(422, "that's in the future")
        vault.upsert_workouts(v.data, [row])
        v.changed()
    return {"ok": True}


@router.delete("/api/me/logs/{rid}")
def remove_log(rid: str, user: dict = Depends(consented_user), sk: bytes | None = Depends(key_header)):
    with _vault_of(user, sk) as v:
        keep = [w for w in v.data["workouts"] if w["id"] != rid]
        if len(keep) == len(v.data["workouts"]):
            raise HTTPException(404, "not found")
        v.data["workouts"] = keep
        v.changed()
    return {"ok": True}


# ---------------------------------------------------------------- today

@router.get("/api/me/today")
def my_today(override_sleep: bool = False, at: str | None = None, user: dict = Depends(consented_user),
             sk: bytes | None = Depends(key_header)):
    if at is not None and not HHMM.match(at):
        raise HTTPException(422, "at must be HH:MM")
    with _vault_of(user, sk) as v:
        d = v.data
        now = _now(d["profile"])
        today = now.date()
        p = persona_for(user, d, today)
        learned = _learned(user, d, today)
        todays = d["days"].get(today.isoformat(), {})
        skip = set(todays.get("skips") or [])
        # Variety: what the last two days showed ranks a bit lower today. Today's own picks
        # don't count, so the plan holds steady while they look at it.
        recent = {a for day, row in d["days"].items()
                  if (today - timedelta(days=2)).isoformat() <= day < today.isoformat()
                  for a in (row.get("shown") or {}).values()}
        out = plan_day_with_timeout(p["id"], persona=p, at=at or now.strftime("%H:%M"), override_sleep=override_sleep,
                                    taste=dict(d["votes"]), kit=p["kit"], recent=recent, skip=skip,
                                    health=_health_in(d), learned=learned)
        shown = {c["daypart"]: c["activity"]["id"] for c in out["cards"] if c.get("activity")}
        if shown != (todays.get("shown") or {}):
            d["days"].setdefault(today.isoformat(), {})["shown"] = shown
            v.changed()
        out["skipped"] = sorted(skip)
        out["taste"] = dict(d["votes"])
        out["health"]["done"] = d["health"] is not None
        out["ask"] = learned["ask"]
        return out


class VoteIn(BaseModel):
    activity_id: str
    vote: str | None = None


@router.post("/api/me/votes")
def vote(body: VoteIn, user: dict = Depends(consented_user), sk: bytes | None = Depends(key_header)):
    if body.activity_id not in CATALOG_IDS or body.vote not in (None, "more", "less"):
        raise HTTPException(422, "unknown activity or vote")
    with _vault_of(user, sk) as v:
        if body.vote is None:
            v.data["votes"].pop(body.activity_id, None)
        else:
            v.data["votes"][body.activity_id] = body.vote
        v.changed()
    return {"ok": True}


class SkipIn(BaseModel):
    activity_id: str
    undo: bool = False


@router.post("/api/me/skip")
def skip(body: SkipIn, user: dict = Depends(consented_user), sk: bytes | None = Depends(key_header)):
    """'Something else': this idea is off the table until tomorrow."""
    if body.activity_id not in CATALOG_IDS:
        raise HTTPException(422, "unknown activity")
    with _vault_of(user, sk) as v:
        row = v.data["days"].setdefault(_today(v.data["profile"]).isoformat(), {})
        skips = [s for s in (row.get("skips") or []) if s != body.activity_id]
        if not body.undo:
            skips.append(body.activity_id)
        row["skips"] = skips[-40:]
        v.changed()
    return {"ok": True, "skipped": skips}


class FeedbackIn(BaseModel):
    activity_id: str
    signal: str


@router.post("/api/me/feedback")
def feedback(body: FeedbackIn, user: dict = Depends(consented_user), sk: bytes | None = Depends(key_header)):
    """'Add to my calendar' (planned) or 'Not today' on the live card. app.learn reads these."""
    if body.activity_id not in CATALOG_IDS or body.signal not in ("planned", "not_today"):
        raise HTTPException(422, "unknown activity or signal")
    with _vault_of(user, sk) as v:
        row = v.data["days"].setdefault(_today(v.data["profile"]).isoformat(), {})
        row[body.signal] = sorted(set(row.get(body.signal) or []) | {body.activity_id})
        v.changed()
    return {"ok": True}


# ---------------------------------------------------------------- Apple Health export upload

JOBS: dict[str, dict] = {}
KEEP_DAYS = 90  # workouts older than this are never read in; the batteries only look back 2 weeks


def _import_job(job: str, uid: str, path: str) -> None:
    """Runs without their key: what it reads is sealed into their inbox, folded in on their next visit."""
    from ingest.apple_health import infer_habits, parse
    try:
        since = (date.today() - timedelta(days=KEEP_DAYS)).isoformat()
        p = parse(path, max_records=None, since=since)
        rows = [{"ext_id": "x-" + hashlib.sha1(f"{w['type']}|{w['start']}".encode()).hexdigest()[:24],
                 "source": "export", "type": w["type"][:80], "start": w["start"][:19],
                 "duration_min": min(1440, w["duration_min"]), "mean_hr": w.get("mean_hr") or 0}
                for w in p["workouts"] if w["type"] and w["start"][:10] >= since]
        JOBS[job].update(stage="saving", found=len(rows))
        recent = [w for w in p["workouts"] if w["start"][:10] >= (date.today() - timedelta(days=14)).isoformat()]
        vault.post(uid, {"kind": "export", "workouts": rows,
                         "daily": [{"date": d["date"], "steps": d["steps"], "sleep_hours": d["sleep_hours"],
                                    "sleep_onset": d.get("sleep_onset") or "", "exercise_min": d["exercise_min"]}
                                   for d in p["daily"]],
                         "falls": p.get("falls") or [], "bp": p.get("bp") or [],
                         "birth_year": int(p["dob"][:4]) if p.get("dob") else None,
                         "habits": infer_habits(recent)})
        JOBS[job].update(stage="done", new=len(rows), days=len(p["daily"]), records_read=p["records_read"])
    except Exception as e:  # noqa: BLE001 - reported to the person, logged here
        JOBS[job].update(stage="error", error="We couldn't read that file. Is it the export.zip from the Health app?")
        print(f"[charge] import {job} failed: {type(e).__name__}")  # never the message: it may quote their data
    finally:
        import os
        try:
            os.unlink(path)
        except OSError:
            pass


def _fold_export(v: vault.Vault, item: dict) -> None:
    d = v.data
    vault.upsert_workouts(d, item.get("workouts") or [])
    vault.upsert_daily(d, item.get("daily") or [])
    for day in item.get("falls") or []:
        d["daily"].setdefault(day, {})["falls"] = 1
    by_day: dict[str, list] = {}
    for day, s, dia in item.get("bp") or []:
        by_day.setdefault(day, []).append([s, dia])
    for day, rs in by_day.items():
        d["daily"].setdefault(day, {})["bp"] = rs
    prof = d["profile"]
    if not prof.get("birth_year") and item.get("birth_year"):
        prof["birth_year"] = item["birth_year"]
    if not prof.get("habits") and item.get("habits"):
        prof["habits"] = item["habits"]


vault.FOLDERS["export"] = _fold_export


@router.post("/api/me/import")
def import_export(file: UploadFile, user: dict = Depends(consented_user)):
    if vault.state(user["id"], None) == "none":
        raise HTTPException(428, "vault_required")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".upload")
    with tmp:
        shutil.copyfileobj(file.file, tmp, length=1 << 20)
    job = secrets.token_hex(8)
    JOBS[job] = {"stage": "reading", "user": user["id"]}
    threading.Thread(target=_import_job, args=(job, user["id"], tmp.name), daemon=True).start()
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


def _shortcut_row(it, tz: ZoneInfo) -> dict | None:
    """One workout from the Shortcut, with forgiving field names, or None if we can't read it."""
    if not isinstance(it, dict):
        return None
    get = lambda *ks: next((it[k] for k in ks if it.get(k) not in (None, "")), None)  # noqa: E731
    typ = get("type", "name", "workoutActivityType", "activity")
    start = _parse_when(get("start", "startDate", "start_date") or "", tz)
    end = _parse_when(get("end", "endDate", "end_date") or "", tz)
    mins = (end - start).total_seconds() / 60 if start and end else _num(get("duration_min", "duration", "minutes"))
    if get("duration_s", "seconds") is not None and not (start and end):
        mins = (_num(get("duration_s", "seconds")) or 0) / 60
    if not typ or not start or not mins or not 1 <= mins <= 1440:
        return None
    t = _norm_type(typ)
    st = start.strftime("%Y-%m-%dT%H:%M:%S")
    return {"ext_id": "s-" + hashlib.sha1(f"{t}|{st[:16]}".encode()).hexdigest()[:24], "source": "shortcut",
            "type": t, "start": st, "duration_min": round(mins, 1),
            "mean_hr": _num(get("mean_hr", "heart_rate", "avg_hr", "averageHeartRate")) or 0}


def _fold_shortcut(v: vault.Vault, item: dict) -> None:
    """Read again in THEIR time zone (it's in the vault, so we couldn't when it arrived)."""
    tz = _tz(v.data["profile"])
    vault.upsert_workouts(v.data, [r for r in (_shortcut_row(it, tz) for it in item.get("items") or []) if r])


vault.FOLDERS["shortcut"] = _fold_shortcut


@router.post("/api/sync/workouts")
async def shortcut_sync(request: Request, authorization: str | None = Header(default=None)):
    """Workouts from the iOS Shortcut. Accepts one workout or {"workouts": [...]}, with
    forgiving field names, because Shortcuts makes precise JSON awkward to build.
    We can't read their vault here, so the workouts are sealed into their inbox as sent."""
    if not store.configured():
        raise HTTPException(503, "accounts are not set up on this server")
    token = _bearer(authorization)
    uid = store.token_owner(_hash(token)) if token.startswith("chg_") else None
    if not uid:
        raise HTTPException(401, "unknown token: make a new one in Charge, under You")
    body = await request.json()
    items = body.get("workouts", body) if isinstance(body, dict) else body
    items = items if isinstance(items, list) else [items]
    good, seen, bad = [], set(), 0
    for it in items[:500]:
        row = _shortcut_row(it, ZoneInfo("UTC"))  # only to check it; the real read happens on fold
        if row is None:
            bad += 1
        elif row["ext_id"] not in seen:
            seen.add(row["ext_id"])
            good.append(it)
    if good and not vault.post(uid, {"kind": "shortcut", "items": good}):
        raise HTTPException(409, "open Charge once to finish setting up, then try again")
    return {"ok": True, "received": len(items), "new": len(good), "skipped": bad}
