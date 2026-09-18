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

STRENGTH_TYPES = {"TraditionalStrengthTraining", "FunctionalStrengthTraining", "CoreTraining"}
CARDIO_TYPES = {"Cycling", "Running", "Walking", "Elliptical", "Rowing", "Swimming",
                "HighIntensityIntervalTraining"}
MOBILITY_TYPES = {"Yoga", "Pilates", "Flexibility", "Cooldown"}
BALANCE_FULL = {"TaiChi", "Barre"}
BALANCE_PARTIAL = {"Yoga": 0.5}  # partial credit

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
    return json.loads((DATA / "genome" / p["genome_report"]).read_text())


def is_vigorous(w: dict, age: int) -> bool:
    if w["type"] == "HighIntensityIntervalTraining":
        return True
    hr = w.get("mean_hr")
    return bool(hr) and hr > 0.85 * (220 - age)


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


def window_metrics(workouts: list[dict], age: int, start: date, end: date) -> dict:
    """Metrics over [start, end] inclusive."""
    strength_days, mobility_days, balance = set(), set(), {}
    moderate = vigorous = 0.0
    for w in workouts:
        d = datetime.fromisoformat(w["start"]).date()
        if not (start <= d <= end):
            continue
        t, mins = w["type"], float(w["duration_min"])
        if w.get("counts") is not None:  # the person's own ticks from the Activity tab
            c = counts_for(w, age)
            if "strength" in c:
                strength_days.add(d)
            if "peak" in c:
                vigorous += mins
            elif "cardio" in c:
                moderate += mins
            if "mobility" in c:
                mobility_days.add(d)
            if "balance" in c:
                balance[d] = 1.0
            continue
        if t in STRENGTH_TYPES:
            strength_days.add(d)
        if t in CARDIO_TYPES:
            if is_vigorous(w, age):
                vigorous += mins
            else:
                moderate += mins
        if t in MOBILITY_TYPES:
            mobility_days.add(d)
        credit = 1.0 if t in BALANCE_FULL else BALANCE_PARTIAL.get(t, 0.0)
        if credit:
            balance[d] = max(balance.get(d, 0.0), credit)
    return {
        "strength_days_per_week": float(len(strength_days)),
        "moderate_aerobic_min_per_week": moderate,
        "vigorous_min_per_week": vigorous,
        # WHO: 75 vigorous ~ 150 moderate, so 1 vigorous minute counts as 2 moderate.
        "moderate_equiv_min_per_week": moderate + 2 * vigorous,
        "balance_days_per_week": sum(balance.values()),
        "mobility_days_per_week": float(len(mobility_days)),
    }


def band_for(fill: float) -> dict:
    for threshold, key, label in BANDS:
        if fill >= threshold:
            return {"key": key, "label": label}
    return {"key": "room_to_grow", "label": "Room to grow"}


def compute_batteries(p: dict) -> dict:
    as_of = date.fromisoformat(p["as_of"])
    this_week = window_metrics(p["workouts"], p["age"], as_of - timedelta(days=6), as_of)
    last_week = window_metrics(p["workouts"], p["age"], as_of - timedelta(days=13), as_of - timedelta(days=7))
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
        "window": {"start": (as_of - timedelta(days=6)).isoformat(), "end": as_of.isoformat()},
    }
