"""Three daypart cards: morning / afternoon / evening.

Filter in Python, reason in ProbLog:
  1. Python applies the HARD gates (equipment tier, daypart, free calendar slot,
     evidence > 0) and keeps the top ~8 candidates per daypart.
  2. ProbLog ranks those (need x evidence x daypart fit x habit fit x sleep penalty),
     picks the winner and gives the proof.
Only the live daypart gets the full explain + an action button.
"""
from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from datetime import date, datetime, timedelta

from app.aggregate import DATA, SOURCES, compute_batteries, load_genome, load_persona
from app.render import GENETIC_FRAME, QUICK_ANSWER, annotate, confidence_band, fact_sentence
from app.schedule import (DAYPART_ORDER, away_block, daypart_of, load_calendar, minutes_of, slot_for)
from reasoner import engine

log = logging.getLogger("charge.day")

CATALOG: list[dict] = json.loads((DATA / "catalog.json").read_text())["activities"]
TIERS = {"none", "home", "gym"}
TOP_K = 8
KIND_LEARN_AT = 2  # "less" votes on one kind before we learn to rank that whole kind lower
TIMEOUT_S = 6.0

DAYPART_LABEL = {"morning": "Morning", "afternoon": "Afternoon", "evening": "Evening"}
# Plain, non-clinical reasons for daypart fit (product preference, not a health claim).
DAYPART_REASON = {
    ("balance", "morning"): "Mornings suit balance work. It's short and needs no shower.",
    ("mobility", "morning"): "A stretch is a gentle way to start the day.",
    ("mobility", "evening"): "A stretch is a calm way to end the day.",
    ("strength", "afternoon"): "Afternoons suit muscle work.",
    ("cardio", "morning"): "A morning walk or ride is easy to fit in.",
}
TIER_TEXT = {"none": "You need no kit for this.", "home": "You can do this at home.", "gym": "You can do this at your gym."}
NOISE_TEXT = {"quiet": "Quiet", "some": "A few thuds", "loud": "Loud"}
HABIT_WORDS = {"yoga": "yoga", "spin": "spin classes", "weights": "weights", "walking": "walking"}
SLEEP_NOTICE = {
    "title": "A gentler option this evening",
    "body": ("Hard exercise late can make it harder to drop off. The research on this is mixed. "
             "For most people an evening workout is fine. We've picked something calmer. "
             "You can swap it if you'd rather."),
    "button": "Give me the harder one instead",
}


def bedtime_minutes(persona: dict) -> int | None:
    """Mean sleep-onset over the window, from Apple Watch SleepAnalysis. None if no data:
    then the sleep rule is dropped entirely. We never guess a bedtime from the calendar."""
    onsets = [d["sleep_onset"] for d in persona.get("daily", [])[-7:] if d.get("sleep_onset")]
    if not onsets:
        return None
    # Times after midnight count as late evening (e.g. 00:30 -> 24:30).
    mins = [m + 1440 if m < 12 * 60 else m for m in (minutes_of(o) for o in onsets)]
    return round(sum(mins) / len(mins))


def _clock(m: int) -> str:
    m %= 1440
    h, mm = divmod(m, 60)
    return datetime(2000, 1, 1, h, mm).strftime("%-I:%M%p").lower().replace(":00", "")


def _video(a: dict) -> dict | None:
    v = a.get("video")
    if not v:
        return None
    return {**v, "url": f"https://www.youtube.com/watch?v={v['video_id']}",
            "embed_url": f"https://www.youtube-nocookie.com/embed/{v['video_id']}"}


def _activity_view(a: dict, tier: str) -> dict:
    return {"id": a["id"], "action": a["action"], "title": a["title"], "minutes": a["duration_min"], "batteries": a["batteries"],
            "intensity": a["intensity"], "noise_level": a["noise_level"], "noise_text": NOISE_TEXT[a["noise_level"]],
            "seated_option": a["seated_option"], "steps": a["steps"], "video": _video(a),
            "equipment_text": TIER_TEXT["none" if "none" in a["equipment"] else tier]}


def kinds_disliked(taste: dict | None) -> set[str]:
    """Kinds of activity the person has turned down KIND_LEARN_AT+ times."""
    by_id = {a["id"]: a["action"] for a in CATALOG}
    n: dict[str, int] = {}
    for aid, v in (taste or {}).items():
        if v == "less" and aid in by_id:
            n[by_id[aid]] = n.get(by_id[aid], 0) + 1
    return {k for k, c in n.items() if c >= KIND_LEARN_AT}


def _prefilter(tier: str, daypart: str, helps: dict, fills: dict, habits: set, exclude: set,
               taste: dict | None = None, kind_less: set | None = None) -> list[dict]:
    """Hard gates except the calendar: tier, daypart, evidence > 0, not already suggested today."""
    out = []
    for a in CATALOG:
        if tier not in a["equipment"] or daypart not in a["daypart"] or a["id"] in exclude:
            continue
        p = helps.get(a["action"], 0.0)
        if p <= 0:
            continue
        primary = max(a["batteries"], key=lambda b: 1 - fills[b])
        vote = (taste or {}).get(a["id"])
        habit = 1.0 if habits & set(a["habits"]) or vote == "more" else 0.87
        # mirrors p_taste_less / p_taste_kind in model.pl
        liked = 0.4 if vote == "less" else 0.7 if a["action"] in (kind_less or ()) else 1.0
        out.append({**a, "primary_battery": primary, "p_evidence": p,
                    "prescore": (1 - fills[primary]) * p * habit * liked})
    return sorted(out, key=lambda c: -c["prescore"])


def _sources_for(nodes: list) -> dict:
    ids: set[str] = set()

    def walk(ns):
        for n in ns:
            if n.get("source_id"):
                ids.add(n["source_id"])
            for f in n.get("facts", []):
                if f.get("source_id"):
                    ids.add(f["source_id"])
            walk(n.get("children", []))

    walk(nodes)
    return {i: SOURCES[i] for i in sorted(ids)}


def _context(c: dict, daypart: str, slot: dict | None, batteries: dict, persona: dict, tier: str,
             result: dict | None, override: bool, taste: dict | None = None,
             kind_less: set | None = None) -> list[dict]:
    """The daypart half of the derivation: why THIS activity at THIS time."""
    b = next(x for x in batteries["batteries"] if x["id"] == c["primary_battery"])
    nodes = [{"kind": "need", "text": fact_sentence({"kind": "observation", "battery": b["id"], "value": b["value"],
                                                      "target": b["target"]}, persona),
              "source_id": b["source_id"], "health_claim": True}]
    nodes.append({"kind": "daypart", "health_claim": False, "source_id": None,
                  "text": DAYPART_REASON.get((c["primary_battery"], daypart), f"This suits the {daypart}."),
                  "design_note": engine.RULES["p_daypart_fit"]["design_note"]})
    match = set(persona.get("habits", [])) & set(c["habits"])
    if match:
        h = sorted(match)[0]
        nodes.append({"kind": "habit", "health_claim": False, "source_id": None,
                      "text": f"It builds on your {HABIT_WORDS.get(h, h)}."})
    vote = (taste or {}).get(c["id"])
    if vote == "more":
        nodes.append({"kind": "taste", "health_claim": False, "source_id": None,
                      "text": "You asked for more like this."})
    elif vote == "less":
        nodes.append({"kind": "taste", "health_claim": False, "source_id": None,
                      "text": "You asked for less like this. It still came out on top, so we kept it."})
    elif c["action"] in (kind_less or ()):
        nodes.append({"kind": "taste", "health_claim": False, "source_id": None,
                      "text": engine.RULES["p_taste_kind"]["head"]})
    if slot:
        nodes.append({"kind": "calendar", "health_claim": False, "source_id": None, "text": slot["reason"]})
    nodes.append({"kind": "equipment", "health_claim": False, "source_id": None,
                  "text": TIER_TEXT["none" if "none" in c["equipment"] else tier]})
    if override and c["intensity"] == "vigorous":
        nodes.append({"kind": "override", "health_claim": False, "source_id": None,
                      "text": "You asked for the harder one. That's your call."})
    elif result and result["sleep_conflict"].get(c["id"], 0) > 0:
        nodes.append({"kind": "sleep", "health_claim": True, "source_id": "src_stutz_2019_evening_exercise",
                      "certainty": "mixed", "p": round(result["sleep_conflict"][c["id"]], 2),
                      "text": "This ends close to your usual bedtime. The research on that is mixed, so we only nudged it down."})
    return nodes


def _card(daypart: str, status: str) -> dict:
    return {"daypart": daypart, "label": DAYPART_LABEL[daypart], "status": status}


def plan_day(pid: str, at: str | None = None, tier: str | None = None, override_sleep: bool = False,
             force_fallback: bool = False, taste: dict[str, str] | None = None) -> dict:
    """`taste` = {action: "more" | "less"}, the person's own votes (kept in their browser)."""
    t0 = time.perf_counter()
    timings: dict[str, float] = {}

    def mark(k, since):
        now = time.perf_counter()
        timings[k] = round(timings.get(k, 0) + (now - since) * 1000, 1)
        return now

    persona = load_persona(pid)
    genome = load_genome(persona)
    tier = tier if tier in TIERS else persona.get("equipment", "none")
    batteries = compute_batteries(persona)
    fills = {b["id"]: b["fill"] for b in batteries["batteries"]}
    deficits = {b: 1 - f for b, f in fills.items()}
    habits = set(persona.get("habits", []))
    cal = load_calendar(persona.get("calendar", "default.json"))
    day = date.fromisoformat(persona["as_of"])
    at = at or datetime.now().strftime("%H:%M")
    now_dt = datetime.combine(day, datetime.strptime(at, "%H:%M").time())
    live = daypart_of(at)
    bedtime = bedtime_minutes(persona)
    kind_less = kinds_disliked(taste)
    t = mark("load_aggregate", t0)

    person = engine.person_facts(persona, genome, batteries["metrics"])
    base = engine.evaluate(person) if not force_fallback else {"helps": {}, "rules": {}, "edges": {}}
    t = mark("problog_evidence", t)

    cards, picked = [], set()
    live_idx = DAYPART_ORDER.index(live) if live else (3 if minutes_of(at) > minutes_of("22:00") else -1)
    for i, dp in enumerate(DAYPART_ORDER):
        status = "live" if i == live_idx else ("past" if i < live_idx else "later")
        card = _card(dp, status)
        cards.append(card)

        away = away_block(cal, day, dp)
        if away:
            # Not nagging is a feature: they're somewhere else all afternoon.
            log.info("suppressed %s card for %s: busy %s-%s", dp, pid, away[0].time(), away[1].time())
            card.update(state="away", text={"preview": f"You're busy all {dp}. We'll leave you be."})
            continue

        earliest = now_dt if status == "live" else None
        if force_fallback:
            pool = [c for c in _prefilter(tier, dp, {a["action"]: 1.0 for a in CATALOG}, fills, habits, picked, taste, kind_less)]
            pool.sort(key=lambda c: -(1 - fills[c["primary_battery"]]))
        else:
            pool = _prefilter(tier, dp, base["helps"], fills, habits, picked, taste, kind_less)
        if not pool:
            card.update(state="none", text={"preview": "Nothing needed here today."})
            continue

        with_slot = []
        for c in pool:
            s = slot_for(cal, day, dp, c["duration_min"], earliest)
            if s:
                with_slot.append({**c, "slot": s, "slot_end_min": s["end_min"]})
        t = mark("gates_and_slots", t)

        if not with_slot:
            short = min(pool, key=lambda c: (c["duration_min"], -c["prescore"]))
            picked.add(short["id"])
            card.update(state="full", activity=_activity_view(short, tier), slot=None,
                        p=round(short["p_evidence"], 2) if not force_fallback else None,
                        text={"notice": f"Your {dp} looks full. Here's a {short['duration_min']}-minute one "
                                        "for whenever you get a gap.",
                              "preview": f"{short['title']}, {short['duration_min']} minutes."})
            card["confidence"] = confidence_band(card["p"])
            # Still explain it: the same proof as any other card, plus why the short one.
            if force_fallback:
                result, deriv = None, engine.fallback(batteries)["because"]
            else:
                facts = person + "\n" + engine.candidate_facts([short], dp, deficits, None, override_sleep,
                                                               taste, kind_less)
                result = engine.evaluate_day(facts)
                t = mark("problog_rank", t)
                deriv = engine.derivation(short["action"], result, batteries)["because"]
            annotate(deriv, persona)
            card["derivation"] = deriv
            card["context"] = [{"kind": "calendar", "health_claim": False, "source_id": None,
                                "text": f"Your {dp} looks full, so we picked the shortest idea that still helps."},
                               *_context(short, dp, None, batteries, persona, tier, result, override_sleep,
                                         taste, kind_less)]
            card["sources"] = _sources_for(deriv + card["context"])
            genetic = any(n.get("genetic") for n in _flatten(deriv))
            card["text"].update(confidence=card["confidence"]["sentence"],
                                genetic_frame=GENETIC_FRAME if genetic else None)
            continue

        cands = with_slot[:TOP_K]
        if force_fallback:
            win, result, raw_best = cands[0], None, None
            p = None
            deriv = engine.fallback(batteries)["because"]
        else:
            facts = person + "\n" + engine.candidate_facts(cands, dp, deficits, bedtime, override_sleep, taste, kind_less)
            result = engine.evaluate_day(facts)
            t = mark("problog_rank", t)
            by_id = {c["id"]: c for c in cands}
            win = by_id[max(result["good"], key=lambda k: (result["good"][k], -list(by_id).index(k)))]
            raw_best = by_id[max(result["good_raw"], key=lambda k: (result["good_raw"][k], -list(by_id).index(k)))]
            p = result["helps"][win["action"]]
            deriv = engine.derivation(win["action"], result, batteries)["because"]

        picked.add(win["id"])
        card.update(state="ok", activity=_activity_view(win, tier), slot=win["slot"], p=None if p is None else round(p, 2),
                    confidence=confidence_band(p), mode="quick" if force_fallback else "reasoned")
        annotate(deriv, persona)
        card["derivation"] = deriv
        card["context"] = _context(win, dp, win["slot"], batteries, persona, tier, result, override_sleep, taste, kind_less)
        card["sources"] = _sources_for(deriv + card["context"])
        if result:
            card["ranking"] = [{"id": k, "title": by_id[k]["title"], "score": round(v, 3),
                                "sleep_conflict": round(result["sleep_conflict"].get(k, 0), 2)}
                               for k, v in sorted(result["good"].items(),  # same tie-break as the pick
                                                  key=lambda kv: (-kv[1], list(by_id).index(kv[0])))]
        if raw_best is not None and raw_best["id"] != win["id"] and result["sleep_conflict"].get(raw_best["id"], 0) > 0:
            card["sleep_notice"] = {**SLEEP_NOTICE, "source_id": "src_stutz_2019_evening_exercise",
                                    "source": SOURCES["src_stutz_2019_evening_exercise"],
                                    "p": round(result["sleep_conflict"][raw_best["id"]], 2),
                                    "bedtime": _clock(bedtime) if bedtime else None,
                                    "harder": {"id": raw_best["id"], "title": raw_best["title"]}}
            card["sources"]["src_stutz_2019_evening_exercise"] = SOURCES["src_stutz_2019_evening_exercise"]

        genetic = any(n.get("genetic") or any(ch.get("genetic") for ch in n.get("children", [])) for n in _flatten(deriv))
        slot = win["slot"]
        when = f"{'Today' if status != 'past' else 'Earlier'}, {_clock(minutes_of(slot['start'][11:16]))}. {slot['reason']}"
        text = {"headline": win["title"], "how_long": f"It takes {win['duration_min']} minutes.", "when": when,
                "confidence": card["confidence"]["sentence"], "genetic_frame": GENETIC_FRAME if genetic else None,
                "preview": f"{win['title']}, {win['duration_min']} minutes."}
        text["read_aloud"] = " ".join(x for x in [text["headline"] + ".", text["how_long"], text["when"],
                                                  text["confidence"], text["genetic_frame"]] if x)
        card["text"] = text

        if status == "live" and not force_fallback:
            card["proofs"] = engine.explain(facts, win["action"], query=f"good({win['id']})")
            t = mark("problog_explain", t)
            seated = next((c for c in pool if c["seated_option"] and set(c["batteries"]) & set(win["batteries"])
                           and c["id"] != win["id"]), None)
            card["seated_alternative"] = _activity_view(seated, tier) if seated else None

    timings["total"] = round((time.perf_counter() - t0) * 1000, 1)
    return {"persona": {"id": persona["id"], "name": persona["name"]}, "at": at, "live": live,
            "equipment": tier, "bedtime": _clock(bedtime) if bedtime is not None else None,
            "mode": "quick" if force_fallback else "reasoned", "cards": cards,
            "batteries": batteries, "timings_ms": timings}


def _flatten(nodes: list) -> list:
    out = []
    for n in nodes:
        out.append(n)
        out += _flatten(n.get("children", []))
    return out


_POOL = ThreadPoolExecutor(max_workers=4)


def plan_day_with_timeout(pid: str, **kw) -> dict:
    t0 = time.perf_counter()
    fut = _POOL.submit(plan_day, pid, **kw)
    try:
        return fut.result(timeout=TIMEOUT_S)
    except FutTimeout:
        out = plan_day(pid, force_fallback=True, **{k: v for k, v in kw.items() if k != "force_fallback"})
        out["timings_ms"]["timed_out_after"] = round((time.perf_counter() - t0) * 1000, 1)
        for c in out["cards"]:
            if c.get("text"):
                c["text"]["confidence"] = QUICK_ANSWER
        return out
