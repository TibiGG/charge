"""What Charge learns from what a person does, and the questions it asks in place of a form.

Everything here reads one person's open vault (app.vault) and nothing else. Three kinds of
result, kept apart on purpose:

  1. Preferences we apply by ourselves. They can only make ideas gentler, or more like what
     the person picks: leave out jumps, leave out the hardest ideas, rank one idea up or down.
     Each one is a line in "Why this?" and can be undone under You.
  2. Questions. Anything that would add a health condition, or that may have gone out of
     date, is ASKED, never assumed ("Your watch noted a fall on 3 October...").
  3. Never. Nothing here lifts a limit from the health check. Only the person can, by
     ticking that a doctor or nurse said yes.

Signals, per catalog idea, over the days we still keep (app.vault.KEEP):
  against: "Something else" (1), "Not today" (1), a "less" vote (2)
  for:     "Add to my calendar" (1), and doing something that fills the same battery
           on a day we suggested it (1)
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from app import health as hc
from app.aggregate import counts_for
from app.day import CATALOG

BY_ID = {a["id"]: a for a in CATALOG}
IMPACT = {a["id"] for a in CATALOG if a.get("impact")}
VIGOROUS = {a["id"] for a in CATALOG if a["intensity"] == "vigorous"}
GROUP_AGAINST = 3      # passes on a group (jumps / hardest ideas) before we leave it out...
GROUP_FOR_MAX = 1      # ...unless they've also taken it up more than this
ONE_AGAINST = 2        # passes on one idea before it comes up less
ONE_FOR = 3            # times they took one idea up before it comes up more
HABIT_AT = 4           # workouts of one kind in 4 weeks before we ask to count it as a habit
REVIEW_DAYS = {"health": 180, "fall": 365, "pregnant": 280, "peri": 3 * 365, "no_again": 180}
BP_HIGH = (135, 85)    # home readings (NICE NG136)
BP_MIN_READINGS = 3
HABIT_OF = {"Yoga": "yoga", "Walking": "walking", "Cycling": "spin",
            "TraditionalStrengthTraining": "weights", "FunctionalStrengthTraining": "weights"}
HABIT_TEXT = {"yoga": "yoga", "walking": "walks", "spin": "cycling", "weights": "weights"}
SRC_FALLS = "src_world_falls_2022"
SRC_BP = "src_nice_ng136"
SRC_MENO = "src_ros_strong_steady_straight"

LINES = {
    "no_jumps": "You often pass on ideas with jumps or hops, so we've left them out for now. "
                "You can bring them back under You.",
    "calmer": "You often pass on our hardest ideas, so we've left them out for now. "
              "You can bring them back under You.",
    "less": "You've passed on this a few times, so it comes up less.",
    "more": "You often go for this one, so it comes up more.",
}
LEARNED = {
    "no_jumps": "You often pass on ideas with jumps or hops, so we leave them out.",
    "calmer": "You often pass on our hardest ideas, so we leave them out.",
    "less": "You've passed on {title} a few times, so it comes up less.",
    "more": "You often go for {title}, so it comes up more.",
}
YES_NO = [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]


# ---------------------------------------------------------------- the health check's history

def flat(h: dict | None) -> set[str]:
    """A health check as a set of items, so we can log what changed and when."""
    if not h:
        return set()
    out = {f"screen:{k}" for k, v in (h.get("screen") or {}).items() if v}
    out |= {f"cond:{c}" for c in h.get("conditions") or []}
    out |= {k for k in ("cleared", "easy_joints") if h.get(k)}
    if h.get("menopause"):
        out.add(f"menopause:{h['menopause']}")
    if h.get("report"):
        out.add("report")
    return out


def record(data: dict, new: dict | None, today: date) -> None:
    """Save a health check and log what changed, so we know how old each answer is."""
    before, after = flat(data.get("health")), flat(new)
    if before != after:
        data["health_log"].append({"on": today.isoformat(), "on_items": sorted(after - before),
                                   "off_items": sorted(before - after)})
        data["health_log"] = data["health_log"][-200:]
    data["health"] = None if new is None else {**new, "updated": today.isoformat()}


def since(data: dict, item: str) -> date | None:
    """When this answer was last given."""
    for e in reversed(data.get("health_log") or []):
        if item in e["on_items"]:
            return date.fromisoformat(e["on"])
    return None


# ---------------------------------------------------------------- what they do

def _signals(data: dict, age: int) -> tuple[Counter, Counter]:
    against, took = Counter(), Counter()
    for aid, v in (data.get("votes") or {}).items():
        if v == "less":
            against[aid] += 2
    by_day: dict[str, set[str]] = {}
    for w in data.get("workouts") or []:
        by_day.setdefault(w["start"][:10], set()).update(counts_for(w, age))
    for day, row in (data.get("days") or {}).items():
        for aid in row.get("skips") or []:
            against[aid] += 1
        for aid in row.get("not_today") or []:
            against[aid] += 1
        for aid in row.get("planned") or []:
            took[aid] += 1
        filled = by_day.get(day, set())
        for aid in set((row.get("shown") or {}).values()):
            if aid in BY_ID and filled & set(BY_ID[aid]["batteries"]):
                took[aid] += 1
    return against, took


def _answered(data: dict, qid: str, today: date) -> bool:
    a = (data.get("answers") or {}).get(qid)
    if not a:
        return False
    # A "no" goes stale: things change, so we may ask again after a while.
    return not (a["value"] == "no" and qid in ("bp",)
                and (today - date.fromisoformat(a["on"])).days >= REVIEW_DAYS["no_again"])


def _undone(data: dict, key: str) -> bool:
    return (data.get("answers") or {}).get(f"undo:{key}", {}).get("value") == "yes"


def _nice_date(d: date) -> str:
    return f"{d.day} {d.strftime('%B')}"


# ---------------------------------------------------------------- questions

def _questions(data: dict, today: date, age: int) -> list[dict]:
    h = data.get("health") or {}
    conds = set(h.get("conditions") or [])
    prof = data.get("profile") or {}
    asks: list[dict] = []

    def ask(qid, text, options, source_id=None, note=None):
        if not _answered(data, qid, today):
            asks.append({"id": qid, "text": text, "options": options, "source_id": source_id, "note": note})

    # A fall the watch picked up (Apple Watch fall detection, via the Health export).
    falls = sorted(d for d, v in (data.get("daily") or {}).items()
                   if v.get("falls") and d >= (today - timedelta(days=365)).isoformat())
    if falls and "fall" not in conds:
        d = date.fromisoformat(falls[-1])
        ask(f"fall_watch:{d.isoformat()}", f"Your watch noted a fall on {_nice_date(d)}. "
            "Shall we add ideas that help your balance?",
            [{"value": "yes", "label": "Yes, please"}, {"value": "no", "label": "No, thanks"}], SRC_FALLS)

    # Answers that go out of date.
    fell = since(data, "cond:fall")
    if "fall" in conds and fell and (today - fell).days >= REVIEW_DAYS["fall"]:
        ask(f"fall_review:{fell.isoformat()}", "You told us about a fall more than a year ago. "
            "Have you had a fall in the last year?", YES_NO, SRC_FALLS)
    preg = since(data, "cond:pregnant")
    if "pregnant" in conds and preg and (today - preg).days >= REVIEW_DAYS["pregnant"]:
        ask(f"pregnant_review:{preg.isoformat()}", "You told us you're pregnant. Is that still true?", YES_NO,
            hc.SRC_PREGNANCY)
    peri = since(data, "menopause:peri")
    if h.get("menopause") == "peri" and peri and (today - peri).days >= REVIEW_DAYS["peri"]:
        ask(f"menopause_review:{peri.isoformat()}", "You told us you're going through menopause. "
            "Where are you with it now?",
            [{"value": "peri", "label": "Still going through it"}, {"value": "post", "label": "After menopause"}],
            SRC_MENO)
    if h.get("updated") and (today - date.fromisoformat(h["updated"])).days >= REVIEW_DAYS["health"]:
        ask(f"health_review:{h['updated']}", "It's been a while since your health check. Is it still right?",
            [{"value": "yes", "label": "Yes, still right"}, {"value": "change", "label": "Let me change it"}])

    # Questions only some people need, so the health check can stay short.
    if prof.get("sex") == "female" and 40 <= age <= 60 and not h.get("menopause"):
        ask("menopause", "Menopause can change which ideas suit you best. Where are you with it?",
            [{"value": "pre", "label": "Not yet"}, {"value": "peri", "label": "Going through it"},
             {"value": "post", "label": "After menopause"}, {"value": "skip", "label": "Rather not say"}], SRC_MENO)

    # Blood pressure readings from a cuff that writes to Apple Health.
    recent = [r for d, v in (data.get("daily") or {}).items() if d >= (today - timedelta(days=90)).isoformat()
              for r in v.get("bp") or []]
    if len(recent) >= BP_MIN_READINGS and "high_bp" not in conds:
        sys_ = sum(r[0] for r in recent) / len(recent)
        dia = sum(r[1] for r in recent) / len(recent)
        if sys_ >= BP_HIGH[0] or dia >= BP_HIGH[1]:
            ask("bp", f"Your blood pressure readings are often above {BP_HIGH[0]}/{BP_HIGH[1]}. "
                "Has a doctor told you that you have high blood pressure?", YES_NO, SRC_BP,
                note="If not, it may help to show your readings to your GP or a pharmacist.")

    # Habits: what they keep doing, so ideas can build on it.
    cut = (today - timedelta(days=28)).isoformat()
    kinds = Counter(HABIT_OF[w["type"]] for w in data.get("workouts") or []
                    if w["start"][:10] >= cut and w["type"] in HABIT_OF)
    for habit, n in sorted(kinds.items()):
        if n >= HABIT_AT and habit not in (prof.get("habits") or []):
            ask(f"habit:{habit}", f"You often do {HABIT_TEXT[habit]}. Shall we build on it in our ideas?",
                [{"value": "yes", "label": "Yes, please"}, {"value": "no", "label": "No, thanks"}])
    return asks


def answer(data: dict, qid: str, value: str, today: date) -> None:
    """Apply an answer to a question from _questions (or an "undo" from the You page)."""
    kind = qid.split(":", 1)[0]
    data["answers"][qid] = {"value": value, "on": today.isoformat()}
    h = {**hc.HealthIn().model_dump(), **(data.get("health") or {})}
    h.pop("updated", None)
    conds = set(h.get("conditions") or [])

    def save():
        h["conditions"] = sorted(conds)
        record(data, h, today)

    if kind == "fall_watch" and value == "yes":
        conds.add("fall")
        save()
    elif kind == "fall_review":
        conds.discard("fall")
        if value == "yes":  # log it again, so the year starts from today
            save()
            conds.add("fall")
        save()
    elif kind == "pregnant_review":
        conds.discard("pregnant")
        if value == "yes":
            save()
            conds.add("pregnant")
        save()
    elif kind in ("menopause", "menopause_review") and value in ("pre", "peri", "post"):
        h["menopause"] = value
        save()
    elif kind == "health_review" and value == "yes":
        save()  # same answers, new date
    elif kind == "bp" and value == "yes":
        conds.add("high_bp")
        save()
    elif kind == "habit" and value == "yes":
        habit = qid.split(":", 1)[1]
        prof = data.setdefault("profile", {})
        prof["habits"] = sorted(set(prof.get("habits") or []) | {habit})


# ---------------------------------------------------------------- all of it

def learn(data: dict, today: date, age: int) -> dict:
    """{prefs, taste (implicit votes), ask (questions), learned (for the You page)}."""
    against, took = _signals(data, age)
    votes = data.get("votes") or {}
    h = data.get("health") or {}

    def group(ids: set[str]) -> bool:
        return sum(against[i] for i in ids) >= GROUP_AGAINST and sum(took[i] for i in ids) <= GROUP_FOR_MAX

    prefs = {"no_jumps": not h.get("easy_joints") and group(IMPACT) and not _undone(data, "no_jumps"),
             "calmer": group(VIGOROUS) and not _undone(data, "calmer")}
    taste: dict[str, str] = {}
    for aid in BY_ID:
        if aid in votes or _undone(data, f"taste:{aid}"):
            continue
        if against[aid] >= ONE_AGAINST and not took[aid]:
            taste[aid] = "less"
        elif took[aid] >= ONE_FOR and not against[aid]:
            taste[aid] = "more"
    learned = [{"id": f"undo:{k}", "text": LEARNED[k]} for k, on in prefs.items() if on]
    learned += [{"id": f"undo:taste:{aid}", "text": LEARNED[v].format(title=BY_ID[aid]["title"].lower())}
                for aid, v in sorted(taste.items())]
    return {"prefs": prefs, "taste": taste, "ask": _questions(data, today, age), "learned": learned}
