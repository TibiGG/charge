"""What Charge learns from what a person does (app.learn), and the questions it asks instead.

The rules that matter most: learning can only make ideas gentler or more like what they pick;
anything that would add a health condition is asked; nothing lifts a limit from the health check.
"""
import copy
import io
from datetime import date, timedelta

import pytest
import textstat

from app import health as hc, learn, render, vault
from app.aggregate import SOURCES
from app.day import CATALOG, plan_day

TODAY = date(2026, 11, 11)
JARGON = ["vo2", "bmd", "polygenic", "prs", "aerobic", "sedentary", "musculoskeletal"]


def _data(**kw) -> dict:
    d = vault.empty()
    d["profile"] = {"birth_year": 1970, "sex": "female", "timezone": "Europe/London"}
    for k, v in kw.items():
        d[k] = v
    return d


def _day(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


def _health(**kw) -> dict:
    return {**hc.HealthIn().model_dump(), **kw}


def _asks(d, age=56) -> dict:
    return {q["id"]: q for q in learn.learn(d, TODAY, age)["ask"]}


# ---------------------------------------------------------------- preferences

def test_passing_on_jumps_leaves_them_out_and_can_be_undone():
    jumpy = sorted(learn.IMPACT)
    d = _data(days={_day(i): {"skips": [jumpy[i % len(jumpy)]]} for i in range(3)})
    out = learn.learn(d, TODAY, 56)
    assert out["prefs"]["no_jumps"] and {"id": "undo:no_jumps", "text": learn.LEARNED["no_jumps"]} in out["learned"]
    learn.answer(d, "undo:no_jumps", "yes", TODAY)
    assert not learn.learn(d, TODAY, 56)["prefs"]["no_jumps"]


def test_taking_ideas_up_outweighs_passing_on_them():
    jumpy = sorted(learn.IMPACT)
    days = {_day(i): {"skips": [jumpy[0]]} for i in range(3)}
    days.update({_day(i + 3): {"planned": [jumpy[1]]} for i in range(2)})
    assert not learn.learn(_data(days=days), TODAY, 56)["prefs"]["no_jumps"]


def test_doing_the_same_battery_counts_as_taking_it_up():
    aid = next(a["id"] for a in CATALOG if a["batteries"] == ["balance"])
    days = {_day(i): {"shown": {"morning": aid}} for i in range(3)}
    workouts = [{"id": vault.new_id(), "ext_id": f"m-{i}", "source": "manual", "type": "Yoga", "start": f"{_day(i)}T09:00:00",
                 "duration_min": 20, "counts": ["balance"]} for i in range(3)]
    assert learn.learn(_data(days=days, workouts=workouts), TODAY, 56)["taste"].get(aid) == "more"


def test_one_idea_comes_up_less_but_their_own_vote_wins():
    aid = CATALOG[0]["id"]
    d = _data(days={_day(1): {"skips": [aid]}, _day(2): {"not_today": [aid]}})
    assert learn.learn(d, TODAY, 56)["taste"][aid] == "less"
    d["votes"] = {aid: "more"}
    assert aid not in learn.learn(d, TODAY, 56)["taste"]


@pytest.mark.parametrize("pid", ["margaret", "dan", "priya"])
def test_learned_preferences_only_take_ideas_away(pid):
    out = plan_day(pid, at="08:00", learned={"prefs": {"no_jumps": True, "calmer": True}, "taste": {}})
    for c in out["cards"]:
        if not c.get("activity"):
            continue
        a = next(x for x in CATALOG if x["id"] == c["activity"]["id"])
        assert not a.get("impact") and a["intensity"] != "vigorous"
        lines = [n for n in c["context"] if n["kind"] == "learned"]
        assert {n["text"] for n in lines} == {learn.LINES["no_jumps"], learn.LINES["calmer"]}
        assert all(not n["health_claim"] for n in lines)


def test_learned_taste_says_so_in_why():
    base = plan_day("margaret", at="08:00")
    aid = base["cards"][0]["activity"]["id"]
    out = plan_day("margaret", at="08:00", learned={"prefs": {}, "taste": {aid: "more"}})
    card = next(c for c in out["cards"] if c.get("activity") and c["activity"]["id"] == aid)
    assert {"kind": "learned", "health_claim": False, "source_id": None, "text": learn.LINES["more"]} in card["context"]


def test_learning_never_lifts_the_health_check():
    """'gentle' stays gentle and 'check' stays check whatever we learned."""
    for screen, level in (({"heart": True}, "gentle"), ({"chest_pain": True}, "check")):
        h = hc.HealthIn(screen=screen)
        out = plan_day("dan", at="08:00", health=h, learned={"prefs": {"no_jumps": True}, "taste": {"brisk_walk": "more"}})
        assert out["health"]["readiness"] == level


# ---------------------------------------------------------------- questions in place of a form

def test_a_fall_the_watch_noticed_is_asked_not_assumed():
    d = _data(daily={_day(20): {"falls": 1}})
    qid = f"fall_watch:{_day(20)}"
    q = _asks(d)[qid]
    assert q["source_id"] == learn.SRC_FALLS and SOURCES[q["source_id"]]
    assert learn.learn(d, TODAY, 56)["prefs"] == {"no_jumps": False, "calmer": False}
    learn.answer(d, qid, "yes", TODAY)
    assert "fall" in d["health"]["conditions"] and qid not in _asks(d)
    assert learn.since(d, "cond:fall") == TODAY


def test_a_fall_more_than_a_year_ago_is_checked():
    d = _data()
    learn.record(d, _health(conditions=["fall"]), TODAY - timedelta(days=400))
    qid = f"fall_review:{(TODAY - timedelta(days=400)).isoformat()}"
    assert qid in _asks(d)
    learn.answer(d, qid, "no", TODAY)
    assert "fall" not in d["health"]["conditions"]

    learn.record(d, _health(conditions=["fall"]), TODAY - timedelta(days=380))
    qid = next(k for k in _asks(d) if k.startswith("fall_review"))
    learn.answer(d, qid, "yes", TODAY)
    assert "fall" in d["health"]["conditions"] and learn.since(d, "cond:fall") == TODAY
    assert not any(k.startswith("fall_review") for k in _asks(d))


def test_pregnancy_and_old_checks_are_reviewed():
    d = _data()
    learn.record(d, _health(conditions=["pregnant"]), TODAY - timedelta(days=300))
    asks = _asks(d)
    assert any(k.startswith("pregnant_review") for k in asks) and any(k.startswith("health_review") for k in asks)
    learn.answer(d, next(k for k in asks if k.startswith("health_review")), "yes", TODAY)
    assert d["health"]["updated"] == TODAY.isoformat()
    assert not any(k.startswith("health_review") for k in _asks(d))


def test_menopause_is_only_asked_of_people_it_may_affect():
    assert "menopause" in _asks(_data())
    d = _data()
    d["profile"]["sex"] = "male"
    assert "menopause" not in _asks(d)
    assert "menopause" not in _asks(_data(), age=30)
    d = _data()
    learn.answer(d, "menopause", "peri", TODAY)
    assert d["health"]["menopause"] == "peri" and "menopause" not in _asks(d)
    later = TODAY + timedelta(days=3 * 365)
    assert any(q["id"].startswith("menopause_review") for q in learn.learn(d, later, 59)["ask"])


def test_high_blood_pressure_readings_ask_and_point_to_a_gp():
    d = _data(daily={_day(i): {"bp": [[142, 88]]} for i in range(3)})
    q = _asks(d)["bp"]
    assert q["source_id"] == learn.SRC_BP and SOURCES[learn.SRC_BP] and "GP" in q["note"]
    learn.answer(d, "bp", "no", TODAY)
    assert "bp" not in _asks(d) and "high_bp" not in (d["health"] or {}).get("conditions", [])
    later = TODAY + timedelta(days=200)
    d["daily"].update({(later - timedelta(days=i)).isoformat(): {"bp": [[142, 88]]} for i in range(3)})
    assert "bp" in {q["id"] for q in learn.learn(d, later, 56)["ask"]}  # a "no" goes stale
    low = _data(daily={_day(i): {"bp": [[118, 76]]} for i in range(5)})
    assert "bp" not in _asks(low)
    d = _data(daily={_day(i): {"bp": [[142, 88]]} for i in range(3)})
    learn.answer(d, "bp", "yes", TODAY)
    assert "high_bp" in d["health"]["conditions"]


def test_a_habit_they_keep_up_is_offered():
    w = [{"id": vault.new_id(), "ext_id": f"x{i}", "source": "export", "type": "Yoga", "start": f"{_day(i * 3)}T07:00:00",
          "duration_min": 30} for i in range(4)]
    d = _data(workouts=w)
    assert "habit:yoga" in _asks(d)
    learn.answer(d, "habit:yoga", "yes", TODAY)
    assert d["profile"]["habits"] == ["yoga"] and "habit:yoga" not in _asks(d)


def _every_question() -> list[tuple[dict, dict]]:
    d = _data(daily={_day(20): {"falls": 1}, **{_day(i): {"bp": [[150, 95]]} for i in range(3)}},
              workouts=[{"id": "w" + str(i), "ext_id": str(i), "source": "export", "type": "Walking",
                         "start": f"{_day(i)}T08:00:00", "duration_min": 30} for i in range(5)])
    learn.record(d, _health(screen={"heart": True}, conditions=["pregnant", "fall"], menopause="peri"),
                 TODAY - timedelta(days=4 * 365))
    return [(d, q) for q in learn.learn(d, TODAY, 56)["ask"]]


def test_no_answer_lifts_a_safety_limit():
    qs = _every_question()
    assert len({q["id"].split(":")[0] for _, q in qs}) >= 6
    for d, q in qs:
        for o in q["options"]:
            after = copy.deepcopy(d)
            learn.answer(after, q["id"], o["value"], TODAY)
            before, now = learn.flat(d["health"]), learn.flat(after["health"])
            assert "cleared" not in now - before, (q["id"], o)
            assert not {i for i in before - now if i.startswith("screen:")}, (q["id"], o)


def test_what_we_say_is_plain_and_kind():
    qs = _every_question()
    strings = list(learn.LINES.values()) + list(learn.LEARNED.values())
    strings += [q["text"] for _, q in qs] + [q["note"] for _, q in qs if q["note"]]
    strings += [o["label"] for _, q in qs for o in q["options"]]
    for s in strings:
        low = s.lower()
        assert not any(b in low for b in render.BANNED), s
        assert not any(j in low.split() for j in JARGON), s
    corpus = " ".join(s if s.endswith((".", "?", "!")) else s + "." for s in strings)
    assert textstat.flesch_kincaid_grade(corpus) <= 6


# ---------------------------------------------------------------- reading it from Apple Health

def test_export_brings_in_falls_and_blood_pressure():
    from ingest.apple_health import parse
    xml = b"""<?xml version="1.0"?><HealthData>
<Record type="HKQuantityTypeIdentifierNumberOfTimesFallen" startDate="2026-10-03 08:00:00 +0100" endDate="2026-10-03 08:00:00 +0100" value="1"/>
<Correlation type="HKCorrelationTypeIdentifierBloodPressure" startDate="2026-10-04 08:00:00 +0100" endDate="2026-10-04 08:00:00 +0100">
<Record type="HKQuantityTypeIdentifierBloodPressureSystolic" startDate="2026-10-04 08:00:00 +0100" endDate="2026-10-04 08:00:00 +0100" value="141"/>
<Record type="HKQuantityTypeIdentifierBloodPressureDiastolic" startDate="2026-10-04 08:00:00 +0100" endDate="2026-10-04 08:00:00 +0100" value="87"/>
</Correlation></HealthData>"""
    p = parse(io.BytesIO(xml))
    assert p["falls"] == ["2026-10-03"] and p["bp"] == [["2026-10-04", 141, 87]]
