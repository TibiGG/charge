"""Apple Health export importer (export.zip / export.xml).

There is no public HealthKit web API, so the real route is the user's own export.
Exports are routinely 200MB-1GB, so this STREAMS with lxml.iterparse and clears
each element after use. Never etree.parse() the whole thing.

    python -m ingest.apple_health path/to/export.xml [--sample] [--age 54]
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from collections import defaultdict
from datetime import date, datetime
from typing import BinaryIO

from lxml import etree

HK = "HKQuantityTypeIdentifier"
QUANTITIES = {
    f"{HK}AppleExerciseTime": "exercise_min",
    f"{HK}VO2Max": "vo2max",
    f"{HK}RestingHeartRate": "resting_hr",
    f"{HK}HeartRateVariabilitySDNN": "hrv",
    f"{HK}StepCount": "steps",
    f"{HK}AppleStandTime": "stand_min",
}
SLEEP = "HKCategoryTypeIdentifierSleepAnalysis"
ASLEEP_VALUES = ("HKCategoryValueSleepAnalysisAsleep",)  # prefix match: Asleep, AsleepCore/Deep/REM/Unspecified


def _dt(s: str) -> datetime:
    # "2026-09-10 07:00:00 +0100"
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z")


def _minutes(value: str, unit: str | None) -> float:
    v = float(value)
    return {"s": v / 60, "sec": v / 60, "hr": v * 60, "h": v * 60}.get((unit or "min").lower(), v)


def _open(src) -> BinaryIO:
    """Accept a path or a file object; unwrap export.zip -> export.xml without extracting to disk."""
    f = open(src, "rb") if isinstance(src, str) else src
    head = f.read(4)
    f.seek(0)
    if head == b"PK\x03\x04":
        z = zipfile.ZipFile(f)
        name = next(n for n in z.namelist() if n.endswith("export.xml"))
        return z.open(name)
    return f


def parse(src, sample: bool = False, age: int | None = None, max_records: int = 200_000) -> dict:
    """Stream-parse an export into a persona-shaped dict (same shape as data/personas/*.json)."""
    workouts: list[dict] = []
    daily: dict[str, dict] = defaultdict(lambda: {"steps": 0.0, "exercise_min": 0.0, "sleep_hours": 0.0})
    latest: dict[str, tuple[datetime, float]] = {}
    dob: date | None = None
    sex = None
    n = 0

    ctx = etree.iterparse(_open(src), events=("end",), tag=("Record", "Workout", "Me"),
                          huge_tree=True, resolve_entities=False, no_network=True)
    for _, el in ctx:
        n += 1
        tag = el.tag
        a = el.attrib
        if tag == "Me":
            s = a.get("HKCharacteristicTypeIdentifierDateOfBirth")
            if s:
                dob = date.fromisoformat(s)
            sex = (a.get("HKCharacteristicTypeIdentifierBiologicalSex") or "").replace("HKBiologicalSex", "").lower() or None
        elif tag == "Workout":
            start = _dt(a["startDate"])
            hr = None
            for st in el.iter("WorkoutStatistics"):
                if st.get("type") == f"{HK}HeartRate" and st.get("average"):
                    hr = float(st.get("average"))
            workouts.append({
                "type": a.get("workoutActivityType", "").replace("HKWorkoutActivityType", ""),
                "start": start.replace(tzinfo=None).isoformat(),
                "duration_min": round(_minutes(a.get("duration", "0"), a.get("durationUnit")), 1),
                "mean_hr": hr,
            })
        elif tag == "Record":
            typ = a.get("type")
            if typ in QUANTITIES:
                key = QUANTITIES[typ]
                start = _dt(a["startDate"])
                val = float(a.get("value", 0))
                d = start.date().isoformat()
                if key == "steps":
                    daily[d]["steps"] += val
                elif key == "exercise_min":
                    daily[d]["exercise_min"] += val
                elif key in ("vo2max", "resting_hr", "hrv"):
                    if key not in latest or start > latest[key][0]:
                        latest[key] = (start, val)
            elif typ == SLEEP and (a.get("value") or "").startswith(ASLEEP_VALUES):
                s, e = _dt(a["startDate"]), _dt(a["endDate"])
                # Attribute sleep to the day you wake up.
                daily[e.date().isoformat()]["sleep_hours"] += (e - s).total_seconds() / 3600
        # Free memory: clear this element and any already-processed siblings.
        el.clear(keep_tail=False)
        while el.getprevious() is not None:
            del el.getparent()[0]
        if sample and n >= 5000 or n >= max_records:
            break
    del ctx

    all_days = sorted(set(daily) | {w["start"][:10] for w in workouts})
    as_of = all_days[-1] if all_days else date.today().isoformat()
    if age is None:
        age = (date.fromisoformat(as_of) - dob).days // 365 if dob else 50
    days = [{"date": d, "steps": round(v["steps"]), "sleep_hours": round(v["sleep_hours"], 2),
             "exercise_min": round(v["exercise_min"])} for d, v in sorted(daily.items())][-14:]
    return {
        "id": "imported", "name": "You", "age": age, "sex": sex or "unknown", "menopause_status": None,
        "habits": [], "as_of": as_of, "watch_connected": True, "genome_report": "sam.json",
        "calendar": "default.json", "workouts": workouts, "daily": [d for d in days if d["sleep_hours"] or d["steps"]],
        "vo2max": latest.get("vo2max", (None, None))[1], "resting_hr": latest.get("resting_hr", (None, None))[1],
        "hrv_sdnn": latest.get("hrv", (None, None))[1], "records_read": n,
    }


def infer_habits(workouts: list[dict]) -> list[str]:
    """Habits = workout types done at least twice in the last 14 days (feeds the 'adapt a habit' rules)."""
    counts: dict[str, int] = defaultdict(int)
    for w in workouts:
        counts[w["type"]] += 1
    mapping = {"Yoga": "yoga", "Walking": "walking", "Cycling": "spin",
               "TraditionalStrengthTraining": "weights", "FunctionalStrengthTraining": "weights"}
    return sorted({mapping[t] for t, c in counts.items() if c >= 2 and t in mapping})


def parse_export_stream(fileobj) -> dict:
    """FastAPI upload handler: parse, register as the 'sam' persona overlay, return batteries."""
    from app import aggregate

    data = fileobj.read()
    persona = parse(io.BytesIO(data))
    persona["habits"] = infer_habits(persona["workouts"])
    aggregate.IMPORTED["sam"] = persona
    result = aggregate.compute_batteries(aggregate.load_persona("sam"))
    for x in result["batteries"]:
        from app.render import observation_sentence
        x["said"] = observation_sentence(x["id"], x["value"], x["target"])
        x["source"] = aggregate.SOURCES[x["source_id"]]
    return {**result, "imported": {"workouts": len(persona["workouts"]), "days": len(persona["daily"]),
                                   "records_read": persona["records_read"], "as_of": persona["as_of"]}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--sample", action="store_true", help="stop after 5000 records (fast)")
    ap.add_argument("--age", type=int)
    args = ap.parse_args()
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    from app.aggregate import compute_batteries

    p = parse(args.path, sample=args.sample, age=args.age)
    p["habits"] = infer_habits(p["workouts"])
    b = compute_batteries(p)
    print(json.dumps({"as_of": p["as_of"], "workouts": len(p["workouts"]), "habits": p["habits"],
                      "records_read": p["records_read"],
                      "batteries": {x["id"]: [x["value"], x["band"]["label"]] for x in b["batteries"]}}, indent=1))
