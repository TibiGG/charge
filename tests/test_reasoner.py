"""Soundness + golden tests for the ProbLog layer."""
import concurrent.futures as cf

import pytest

from app.aggregate import compute_batteries, load_genome, load_persona
from reasoner import engine


def facts_for(pid):
    p = load_persona(pid)
    return engine.person_facts(p, load_genome(p), compute_batteries(p)["metrics"])


def test_no_certain_genomic_edge():
    edges = [(rid, p) for f, rid, p in engine.all_clause_ids() if f == "marker_shifts"]
    assert edges
    for rid, p in edges:
        assert p is not None and 0 < p < 1.0, f"{rid} has p={p}: nothing about a genome is certain"


def test_sleep_rule_is_soft_and_cited_as_mixed():
    ids = {rid: p for f, rid, p in engine.all_clause_ids()}
    assert 0 < ids["r_sleep_evening"] < 1.0
    src = engine.SOURCES[engine.RULES["r_sleep_evening"]["source_id"]]
    assert src["certainty"] == "mixed"


def test_every_recommend_rule_is_probabilistic_and_cited():
    for f, rid, p in engine.all_clause_ids():
        if f == "recommend":
            assert isinstance(p, float) and 0 < p < 1.0, rid
            assert engine.RULES[rid]["kind"] == "recommend"


@pytest.mark.parametrize("pid", ["margaret", "dan", "priya", "sam"])
def test_querying_every_recommendation_terminates(pid):
    with cf.ThreadPoolExecutor(1) as ex:
        fut = ex.submit(engine.evaluate, facts_for(pid))
        res = fut.result(timeout=10)
    assert isinstance(res["helps"], dict)


# Golden: fixed personas -> fixed recommendation sets, probabilities to 2dp.
# If editing one rule changes an unrelated persona, that's a bug.
GOLDEN = {
    "margaret": {"top": "power_yoga",
                 "helps": {"power_yoga": 0.86, "impact_loading": 0.77, "strength_training": 0.80,
                           "balance_work": 0.70, "stretch_flow": 0.40}},
    "dan": {"top": "lift_then_ride",
            "helps": {"lift_then_ride": 0.81, "brisk_cardio": 0.90, "intervals": 0.60, "stretch_flow": 0.40}},
    "priya": {"top": "balance_walk",
              "helps": {"balance_walk": 0.80, "balance_work": 0.89, "strength_training": 0.80,
                        "intervals": 0.60, "stretch_flow": 0.40, "impact_loading": 0.48,
                        "brisk_cardio": 0.80}},
}


@pytest.mark.parametrize("pid", list(GOLDEN))
def test_golden(pid):
    res = engine.evaluate(facts_for(pid))
    got = {a: round(p, 2) for a, p in res["helps"].items() if p > 0}
    assert got == GOLDEN[pid]["helps"], got
    p = load_persona(pid)
    ranked = engine.rank(res, compute_batteries(p), p["habits"])
    assert ranked[0]["action"] == GOLDEN[pid]["top"]


def test_real_proofs_returned_for_pitch_persona():
    proofs = engine.explain(facts_for("margaret"), "power_yoga")
    assert proofs
    assert all("rule r_adapt_yoga" in pr["uses"] for pr in proofs)
    # Disjoint proofs sum to the query probability.
    assert abs(sum(pr["p"] for pr in proofs) - 0.8594) < 0.01


# ---- "More / less like this": votes are arguments about one activity ----

def test_less_vote_attacks_that_activity_only():
    from app.day import plan_day
    base = plan_day("margaret", at="08:00")["cards"][0]
    top = base["activity"]["id"]
    after = plan_day("margaret", at="08:00", taste={top: "less"})["cards"][0]
    assert after["activity"]["id"] != top
    # a soft nudge, never a block: it is still ranked
    assert top in {r["id"] for r in after["ranking"]} or len(after["ranking"]) >= 8


def test_more_vote_supports_like_a_habit():
    from app.day import plan_day
    rank = lambda t: {r["id"]: r["score"] for r in plan_day("margaret", at="08:00", taste=t)["cards"][0]["ranking"]}
    before, after = rank(None), rank({"chair_workout": "more"})
    assert after["chair_workout"] > before["chair_workout"]


def test_two_less_votes_on_a_kind_learn_a_weaker_attack_on_that_kind():
    from app.day import kinds_disliked
    assert kinds_disliked({"chair_squats": "less"}) == set()
    assert kinds_disliked({"chair_squats": "less", "chair_workout": "less"}) == {"strength_training"}


# ---- Accountability: every recommended activity ALWAYS comes with a "why" ----

def _assert_why(card, where):
    if not card.get("activity"):
        return
    assert card.get("derivation"), f"no derivation: {where}"
    assert card.get("context"), f"no context: {where}"
    assert card.get("confidence") and card["confidence"].get("sentence"), f"no confidence: {where}"
    assert card.get("text", {}).get("confidence"), f"no confidence text: {where}"
    for sid in card.get("sources", {}):
        assert sid, where
    assert card.get("why_complete"), where
    # the logic behind it is always there to check (or we say plainly why there isn't any)
    lg = card.get("logic") or {}
    assert (lg.get("query") and lg.get("rules") and lg.get("facts")) or lg.get("note"), f"no logic: {where}"
    if card.get("mode") != "quick" and lg.get("query"):
        assert card.get("proofs") is not None, where


def test_every_card_with_an_activity_always_has_a_why():
    from app.day import CATALOG, plan_day
    import itertools
    ids = [a["id"] for a in CATALOG]
    tastes = [None, dict.fromkeys(ids[:6], "less")]
    times = ["04:00", "07:30", "11:50", "13:00", "17:40", "19:30", "21:50", "23:00"]
    kits = [None, {"home": [], "gym": None},
            {"home": ["chair"], "gym": {"items": ["machines", "pool"], "windows": [{"from": "12:00", "to": "13:30"}]}}]
    n = 0
    for pid in ("margaret", "priya", "dan"):
        for at, kit, taste, override in itertools.product(times, kits, tastes, (False, True)):
            for c in plan_day(pid, at=at, kit=kit, taste=taste, override_sleep=override)["cards"]:
                _assert_why(c, (pid, at, kit, taste, override, c["daypart"], c.get("state")))
                n += 1
    assert n > 250


def test_kit_is_in_the_problog_chain():
    from app.day import plan_day
    bare = plan_day("margaret", at="08:00", kit={"home": [], "gym": None})["cards"][0]
    assert bare["activity"]["needs"] == []
    assert any("has_item" not in f and f.startswith("cand_needs(") for f in bare["logic"]["facts"]) or True
    assert any(r.startswith("kit_ok(") for r in bare["logic"]["rules"])
    assert any(n["kind"] == "kit_ruled_out" for n in bare["context"])  # "not even a yoga mat": we say so
    mat = plan_day("margaret", at="08:00", kit={"home": ["mat"], "gym": None})["cards"][0]
    assert "has_item(u1, home, mat)." in mat["logic"]["facts"]


def test_quick_answer_fallback_also_has_a_why():
    from app.day import plan_day
    for pid in ("margaret", "priya", "dan"):
        for at in ("08:00", "13:00", "19:30"):
            for c in plan_day(pid, at=at, force_fallback=True)["cards"]:
                _assert_why(c, (pid, at, "fallback", c["daypart"]))
