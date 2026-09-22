"""Python owns the arithmetic: raw samples -> rolling 7-day metrics -> vial fills.

ProbLog never sums floats; it receives the handful of metrics computed here.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"  # backend/data (root/data is a symlink)

SOURCES: dict = json.loads((DATA / "sources.json").read_text())
TARGETS: dict = json.loads((DATA / "targets.json").read_text())
BATTERY_ORDER = ["strength", "cardio", "peak", "balance", "mobility"]

STRENGTH_TYPES = {"TraditionalStrengthTraining", "FunctionalStrengthTraining", "CoreTraining", "CrossTraining",
                  "Climbing"}
CARDIO_TYPES = {"Cycling", "Running", "Walking", "Elliptical", "Rowing", "Swimming", "Hiking", "MixedCardio",
                "HighIntensityIntervalTraining", "StairClimbing", "Stairs", "Dance", "SocialDance", "CardioDance",
                "Boxing", "Kickboxing", "MartialArts", "CrossTraining", "JumpRope", "Soccer", "Basketball",
                "Tennis", "Badminton", "Squash", "Paddling", "SkatingSports", "CrossCountrySkiing",
                "DownhillSkiing", "Snowboarding", "WheelchairWalkPace", "WheelchairRunPace", "HandCycling",
                "WaterFitness", "Pickleball", "Hockey", "Rugby", "Netball", "Volleyball"}
MOBILITY_TYPES = {"Yoga", "Pilates", "Flexibility", "Cooldown", "MindAndBody"}
BALANCE_FULL = {"TaiChi", "Barre"}
BALANCE_PARTIAL = {"Yoga": 0.5, "Pilates": 0.5, "Dance": 0.5, "SocialDance": 0.5, "MartialArts": 0.5}  # partial credit

BANDS = [(1.0, "topped_up", "Topped up"), (0.5, "ticking_over", "Ticking over"),
         (0.0, "room_to_grow", "Room to grow")]

# Live samples POSTed from the watch (Shortcut) — in-memory overlay per persona.
LIVE_WORKOUTS: dict[str, list[dict]] = {}
# Personas replaced by an uploaded Apple Health export (in memory, demo only).
IMPORTED: dict[str, dict] = {}


def load_persona(pid: str) -> dict:
    path = DATA / "personas" / f"{pid}.json"
    if pid in IMPORTED:
        base = json.loads(path.read_text()) if path.exists() else {}
        p = {**base, **IMPORTED[pid], "id": pid, "name": base.get("name", "You")}
    elif not path.exists():
        raise KeyError(pid)
    else:
        p = json.loads(path.read_text())
    p["workouts"] = p["workouts"] + LIVE_WORKOUTS.get(pid, [])
    return p


def load_genome(p: dict) -> dict:
    """The Bupa genome report, if they have one. Without it the genomic rules simply don't fire."""
    if p.get("genome"):
        return p["genome"]
    if not p.get("genome_report"):
        return {"panels": []}
    return json.loads((DATA / "genome" / p["genome_report"]).read_text())


# ACSM intensity bands as a share of age-predicted max heart rate (220 - age).
HR_MODERATE, HR_VIGOROUS = 0.64, 0.77
# What we assume when there is no heart rate and no effort: roughly the MET class of each type.
TYPE_INTENSITY = {"HighIntensityIntervalTraining": "vigorous", "Running": "vigorous",
                  "Yoga": "light", "Flexibility": "light", "Cooldown": "light", "TaiChi": "light"}
EFFORT = {"easy": "light", "moderate": "moderate", "hard": "vigorous"}
MIN_SESSION_MIN = 5.0  # shorter than this is a fidget, not a session

# Minutes x intensity. Cardio follows WHO (1 vigorous minute = 2 moderate); light
# activity is half credit (a product choice: better than nothing, not the target).
# Strength, balance and mobility use a gentler spread so one long, hard session
# can't fill the whole week on its own.
CARDIO_WEIGHT = {"light": 0.5, "moderate": 1.0, "vigorous": 2.0}
OTHER_WEIGHT = {"light": 0.75, "moderate": 1.0, "vigorous": 1.25}


def intensity_of(w: dict, age: int) -> str:
    """light | moderate | vigorous. Their own effort rating wins, then heart rate, then the type."""
    if w.get("effort") in EFFORT and w.get("source") != "watch":
        return EFFORT[w["effort"]]
    if w["type"] == "HighIntensityIntervalTraining":
        return "vigorous"
    hr = w.get("mean_hr")
    if hr:
        share = float(hr) / (220 - age)
        return "vigorous" if share >= HR_VIGOROUS else "moderate" if share >= HR_MODERATE else "light"
    return TYPE_INTENSITY.get(w["type"], "moderate")


def is_vigorous(w: dict, age: int) -> bool:
    return intensity_of(w, age) == "vigorous"


# Manual log (Activity tab): what each kind of activity counts towards by default.
# The person can change the ticks; an explicit `counts` list on a workout wins.
MANUAL_TYPES = {
    "Walking": {"label": "Walking", "counts": ["cardio"]},
    "Running": {"label": "Running", "counts": ["cardio"]},
    "Cycling": {"label": "Cycling", "counts": ["cardio"]},
    "Swimming": {"label": "Swimming", "counts": ["cardio"]},
    "Dance": {"label": "Dancing", "counts": ["cardio", "balance"]},
    "TraditionalStrengthTraining": {"label": "Weights or muscle work", "counts": ["strength"]},
    "CoreTraining": {"label": "Core work", "counts": ["strength"]},
    "HighIntensityIntervalTraining": {"label": "Hard intervals (HIIT)", "counts": ["cardio", "peak"]},
    "Yoga": {"label": "Yoga", "counts": ["mobility", "balance"]},
    "Pilates": {"label": "Pilates", "counts": ["mobility"]},
    "TaiChi": {"label": "Tai chi", "counts": ["balance"]},
    "Flexibility": {"label": "Stretching", "counts": ["mobility"]},
    "ImpactLoading": {"label": "Heel drops or stair steps", "counts": ["strength"]},
}

# Synthetic "new since last sync" watch workouts, so the demo can press Sync.
WEARABLE_PENDING = {
    "margaret": [{"type": "Walking", "start": "T07:10:00", "duration_min": 25, "mean_hr": 108},
                 {"type": "Yoga", "start": "T07:40:00", "duration_min": 20, "mean_hr": 90}],
    "priya": [{"type": "Walking", "start": "T08:00:00", "duration_min": 30, "mean_hr": 100}],
    "dan": [{"type": "HighIntensityIntervalTraining", "start": "T06:45:00", "duration_min": 20, "mean_hr": 172}],
    "sam": [],
}


def counts_for(w: dict, age: int) -> list[str]:
    """Which batteries one workout fills. Explicit ticks (manual log) win over the type."""
    if w.get("counts") is not None:
        return [c for c in w["counts"] if c in BATTERY_ORDER]
    t, out = w["type"], []
    if t in STRENGTH_TYPES:
        out.append("strength")
    if t in CARDIO_TYPES:
        out.append("cardio")
        if is_vigorous(w, age):
            out.append("peak")
    if t in BALANCE_FULL or t in BALANCE_PARTIAL:
        out.append("balance")
    if t in MOBILITY_TYPES:
        out.append("mobility")
    return out


def with_extra(p: dict, logs: list[dict] | None, synced: bool) -> dict:
    """The persona plus synced watch workouts and the person's own logs (sent by the browser)."""
    extra = []
    if synced:
        extra += [{**w, "start": p["as_of"] + w["start"], "source": "watch", "synced": True}
                  for w in WEARABLE_PENDING.get(p["id"], [])]
    extra += [{**w, "source": "you"} for w in (logs or [])]
    return {**p, "workouts": p["workouts"] + extra} if extra else p


def contributions(w: dict, age: int) -> dict[str, float]:
    """Weighted minutes this one workout adds to each battery's weekly metric."""
    mins = float(w["duration_min"])
    if mins < MIN_SESSION_MIN:
        return {}
    level = intensity_of(w, age)
    c = counts_for(w, age)
    out: dict[str, float] = {}
    if "cardio" in c:
        out["cardio"] = mins * CARDIO_WEIGHT[level]
    if "peak" in c and (level == "vigorous" or w.get("counts") is not None):
        out["peak"] = mins  # explicit ticks win: they told us it was hard work
    for b in ("strength", "mobility"):
        if b in c:
            out[b] = mins * OTHER_WEIGHT[level]
    if "balance" in c:
        share = 1.0 if w.get("counts") is not None else BALANCE_PARTIAL.get(w["type"], 1.0)
        out["balance"] = mins * OTHER_WEIGHT[level] * share
    return out


METRIC_OF = {"strength": "strength_min_per_week", "cardio": "moderate_equiv_min_per_week",
             "peak": "vigorous_min_per_week", "balance": "balance_min_per_week",
             "mobility": "mobility_min_per_week"}


def window_metrics(workouts: list[dict], age: int, start: date, end: date) -> dict:
    """Weighted minutes per battery over [start, end] inclusive."""
    totals = {m: 0.0 for m in METRIC_OF.values()}
    for w in workouts:
        d = datetime.fromisoformat(w["start"]).date()
        if start <= d <= end:
            for b, v in contributions(w, age).items():
                totals[METRIC_OF[b]] += v
    return {k: round(v, 1) for k, v in totals.items()}


def week_start(d: date) -> date:
    """Batteries empty every Monday: the week runs Monday to Sunday in the person's own time zone."""
    return d - timedelta(days=d.weekday())


def band_for(fill: float) -> dict:
    for threshold, key, label in BANDS:
        if fill >= threshold:
            return {"key": key, "label": label}
    return {"key": "room_to_grow", "label": "Room to grow"}


def compute_batteries(p: dict) -> dict:
    as_of = date.fromisoformat(p["as_of"])
    monday = week_start(as_of)
    this_week = window_metrics(p["workouts"], p["age"], monday, as_of)
    last_week = window_metrics(p["workouts"], p["age"], monday - timedelta(days=7), monday - timedelta(days=1))
    daily = p.get("daily", [])[-7:]
    sleep = round(sum(d["sleep_hours"] for d in daily) / len(daily), 1) if daily else None

    batteries = []
    for bid in BATTERY_ORDER:
        t = TARGETS[bid]
        value = this_week[t["metric"]]
        fill = min(1.0, value / t["target"])
        batteries.append({
            "id": bid, "label": t["label"], "metric": t["metric"], "value": round(value, 1),
            "previous_value": round(last_week[t["metric"]], 1), "target": t["target"],
            "unit": t["unit"], "fill": round(fill, 3), "band": band_for(fill),
            "source_id": t["source_id"], "low_confidence": t.get("low_confidence", False),
        })
    emptiest = min(batteries, key=lambda b: (b["fill"], BATTERY_ORDER.index(b["id"])))
    return {
        "charge": emptiest["fill"],  # min(), not mean: set by your emptiest battery
        "emptiest": emptiest["id"],
        "batteries": batteries,
        "metrics": this_week,
        "sleep_hours_mean": sleep,
        "vo2max": p.get("vo2max"),
        "window": {"start": monday.isoformat(), "end": as_of.isoformat(),
                   "resets": (monday + timedelta(days=7)).isoformat(), "days_left": 7 - as_of.weekday()},
    }
