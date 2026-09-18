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
            assert p is not None and 0 < p < 1.0, rid
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
