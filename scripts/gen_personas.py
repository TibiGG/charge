"""Generate the synthetic demo personas (14 days each). Deterministic; output is committed.

Workout `type` uses Apple HealthKit workoutActivityType names (minus the HKWorkoutActivityType
prefix) so the same aggregation code handles personas and real Apple Health exports.
"""
import json
from datetime import date, datetime, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
AS_OF = date(2026, 9, 18)  # a Friday
DAYS = [AS_OF - timedelta(days=13 - i) for i in range(14)]


def w(day: date, hour: int, typ: str, minutes: int, hr: int) -> dict:
    start = datetime(day.year, day.month, day.day, hour, 0)
    return {"type": typ, "start": start.isoformat(), "duration_min": minutes, "mean_hr": hr}


def build(pid, name, age, sex, menopause, habits, plan, daily, vo2, rhr, watch=True):
    workouts = []
    for d in DAYS:
        for item in plan(d):
            workouts.append(w(d, *item))
    return {
        "id": pid, "name": name, "age": age, "sex": sex, "menopause_status": menopause,
        "habits": habits, "as_of": AS_OF.isoformat(), "watch_connected": watch,
        "genome_report": f"{pid}.json", "calendar": "default.json",
        "workouts": workouts,
        "daily": [{"date": d.isoformat(), **daily(d)} for d in DAYS] if watch else [],
        "vo2max": vo2, "resting_hr": rhr,
    }


def margaret_plan(d):
    # Spin Mon/Wed/Fri (Wed is the hard class), gentle yoga Sat, walk Sun.
    # One core session in the *older* week only — shows the vial draining.
    wd, out = d.weekday(), []
    if wd == 0: out.append((7, "Cycling", 50, 124))
    if wd == 2: out.append((7, "Cycling", 40, 146))   # >85% of (220-54)=141 -> vigorous
    if wd == 4: out.append((7, "Cycling", 50, 122))
    if wd == 5: out.append((9, "Yoga", 40, 92))
    if wd == 6: out.append((10, "Walking", 30, 104))
    if d == DAYS[1]: out.append((18, "CoreTraining", 25, 110))
    return out


def dan_plan(d):
    wd, out = d.weekday(), []
    if wd in (0, 2, 4): out.append((18, "TraditionalStrengthTraining", 60, 112))
    if wd in (1, 3): out.append((13, "Walking", 15, 98))
    return out


def priya_plan(d):
    return [(10, "Walking", 20, 98)]


def daily(steps, sleep):
    return lambda d: {"steps": steps + (d.toordinal() * 37) % 900, "sleep_hours": round(sleep + ((d.toordinal() % 5) - 2) * 0.15, 2)}


personas = [
    build("margaret", "Margaret", 54, "female", "post", ["spin", "yoga"], margaret_plan, daily(7400, 6.4), 31.2, 62),
    build("dan", "Dan", 36, "male", None, ["weights"], dan_plan, daily(4100, 5.9), 38.5, 70),
    build("priya", "Priya", 68, "female", "post", ["walking"], priya_plan, daily(6200, 7.1), 24.0, 66),
    build("sam", "Sam", 45, "male", None, [], lambda d: [], None, None, None, watch=False),
]

genomes = {
    "margaret": [
        {"condition": "osteoporosis", "prs_band": "high", "percentile": 91,
         "variants": [{"rsid": "rs1800012", "gene": "COL1A1", "genotype": "GT", "effect_direction": "lower_bone_density"}],
         "interpretation_source_id": "src_genomos_col1a1"},
        {"condition": "cardiometabolic", "prs_band": "average", "percentile": 48, "variants": [],
         "interpretation_source_id": "src_bupa_genomic"},
    ],
    "dan": [
        {"condition": "osteoporosis", "prs_band": "average", "percentile": 35, "variants": [],
         "interpretation_source_id": "src_bupa_genomic"},
        {"condition": "cardiometabolic", "prs_band": "high", "percentile": 88,
         "variants": [{"rsid": "rs9939609", "gene": "FTO", "genotype": "AA", "effect_direction": "higher_bmi"}],
         "interpretation_source_id": "src_frayling_fto_2007"},
    ],
    "priya": [
        {"condition": "osteoporosis", "prs_band": "average", "percentile": 52, "variants": [],
         "interpretation_source_id": "src_bupa_genomic"},
        {"condition": "cardiometabolic", "prs_band": "average", "percentile": 44, "variants": [],
         "interpretation_source_id": "src_bupa_genomic"},
    ],
    "sam": [],
}

for p in personas:
    (DATA / "personas" / f"{p['id']}.json").write_text(json.dumps(p, indent=1))
    g = {"report_id": f"MGH-2026-{p['id'][:3].upper()}-0001", "issued_date": "2026-09-12",
         "source_id": "src_bupa_genomic", "panels": genomes[p["id"]]}
    (DATA / "genome" / f"{p['id']}.json").write_text(json.dumps(g, indent=1))

# Weekly busy template (weekday -> busy [start,end] "HH:MM"). Works for any demo date.
work = [["08:30", "12:30"], ["13:00", "17:45"]]
cal = {"timezone": "Europe/London", "day_start": "07:00", "day_end": "21:00", "busy_by_weekday": {
    "0": work + [["19:00", "20:30"]], "1": work, "2": work + [["18:00", "20:00"]],
    "3": work + [["17:45", "18:15"]], "4": work, "5": [["10:00", "13:00"]], "6": [["11:00", "16:00"]]}}
(DATA / "calendar" / "default.json").write_text(json.dumps(cal, indent=1))
print("wrote", [p["id"] for p in personas])
