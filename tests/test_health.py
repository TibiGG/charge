"""The Health check: kept on the person's device, sent in the body, used once, never stored.

Readiness gates (PAR-Q+ / ACSM 2015), diagnoses and a recent fall become facts in the logic,
and every line they add to "Why this?" is sourced or marked as not a health claim.
"""
import itertools

import pytest
from fastapi.testclient import TestClient

from app import health as hc
from app.aggregate import SOURCES
from app.day import CATALOG
from app.main import app

BY_ID = {a["id"]: a for a in CATALOG}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def plan(client, h, p="dan", at="12:30"):
    r = client.post(f"/api/today/{p}", params={"at": at}, json={"health": h})
    assert r.status_code == 200, r.text
    return r.json()


def picked(out):
    return [c["activity"]["id"] for c in out["cards"] if c.get("activity")]


def rules(out):
    def walk(ns):
        for n in ns:
            yield n.get("rule_id")
            yield from walk(n.get("children", []))
    return {r for c in out["cards"] for r in walk(c.get("derivation", [])) if r}


# ---------------------------------------------------------------- readiness

@pytest.mark.parametrize("h, level", [
    (None, "ok"),
    ({}, "ok"),
    ({"screen": {"heart": True}}, "gentle"),
    ({"screen": {"medicines": True, "joints": True}}, "gentle"),
    ({"conditions": ["pregnant"]}, "gentle"),
    ({"screen": {"chest_pain": True}}, "check"),
    ({"screen": {"dizzy": True, "heart": True}}, "check"),
    ({"screen": {"supervised": True}}, "check"),
    ({"screen": {"chest_pain": True}, "cleared": True}, "ok"),
])
def test_readiness_levels(h, level):
    assert hc.readiness(None if h is None else hc.HealthIn(**h)) == level


def test_symptoms_mean_no_suggestions_and_a_person_to_talk_to(client):
    out = plan(client, {"screen": {"chest_pain": True}})
    assert out["health"]["readiness"] == "check"
    assert picked(out) == []
    assert {c["state"] for c in out["cards"]} == {"check"}
    cf = out["health"]["check_first"]
    assert "999" in cf["body"] and cf["source_id"] in SOURCES and cf["source"]["url"].startswith("https://")


@pytest.mark.parametrize("p, at", itertools.product(["margaret", "dan", "priya"], ["08:00", "12:30", "19:30"]))
def test_gentle_means_no_hard_effort_and_says_why(client, p, at):
    out = plan(client, {"screen": {"heart": True}}, p=p, at=at)
    for c in out["cards"]:
        if not c.get("activity"):
            continue
        assert c["activity"]["intensity"] != "vigorous"
        line = next(n for n in c["context"] if n["kind"] == "health")
        assert line["health_claim"] and line["source_id"] == hc.SRC_SCREEN
        assert hc.SRC_SCREEN in c["sources"] and c["why_complete"]


def test_doctors_ok_lifts_the_gate(client):
    gated = plan(client, {"screen": {"heart": True}})
    ok = plan(client, {"screen": {"heart": True}, "cleared": True})
    assert any(BY_ID[a]["intensity"] == "vigorous" for a in picked(ok))
    assert not any(BY_ID[a]["intensity"] == "vigorous" for a in picked(gated))
    assert any("doctor or nurse said you can be active" in n["text"] for c in ok["cards"] for n in c.get("context", []))


def test_pregnancy_cites_the_pregnancy_guidance(client):
    out = plan(client, {"conditions": ["pregnant"]})
    lines = [n for c in out["cards"] for n in c.get("context", []) if n["kind"] == "health"]
    assert lines and all(n["source_id"] == hc.SRC_PREGNANCY for n in lines)


def test_easy_joints_leaves_out_jumps(client):
    for p, at in itertools.product(["margaret", "dan", "priya"], ["08:00", "12:30", "19:30"]):
        out = plan(client, {"easy_joints": True}, p=p, at=at)
        assert not any(BY_ID[a].get("impact") for a in picked(out)), (p, at)


# ---------------------------------------------------------------- facts in the logic

def test_diabetes_or_blood_pressure_adds_its_own_sourced_reasons(client):
    base, out = plan(client, None), plan(client, {"conditions": ["high_bp"]})
    assert "r_cardio_chronic" in rules(out) and "r_cardio_chronic" not in rules(base)
    assert any("src_who_2020_chronic" in c.get("sources", {}) for c in out["cards"])


def test_a_recent_fall_raises_balance(client):
    out = plan(client, {"conditions": ["fall"]}, p="priya", at="19:30")
    assert "r_balance_fall_hx" in rules(out)


def test_thin_bones_and_menopause_are_not_framed_as_genetics(client):
    # Their own report says nothing about bones, so only the diagnosis + menopause shift bone work.
    h = {"conditions": ["thin_bones"], "menopause": "post", "report": {"heart": "average"}}
    out = plan(client, h, p="margaret", at="15:00")
    edges = {r for r in rules(out) if r.startswith("e_")}
    assert "e_dx_bone" in edges and not edges & {"e_prs_osteo", "e_col1a1"}
    for c in out["cards"]:
        if c.get("text") and c.get("activity"):
            assert c["text"].get("genetic_frame") is None


def test_a_typed_in_genome_report_reaches_the_gene_rules(client):
    h = {"report": {"bones": "high", "heart": "average", "variants": ["col1a1"]}}
    out = plan(client, h, p="margaret", at="15:00")
    assert {"e_prs_osteo", "e_col1a1"} <= rules(out)
    assert any(c["text"].get("genetic_frame") for c in out["cards"] if c.get("activity"))


def test_every_new_line_resolves_to_a_source_or_is_not_a_claim(client):
    variants = [{"screen": {"heart": True}}, {"conditions": ["pregnant", "fall", "thin_bones", "type2_diabetes"]},
                {"easy_joints": True, "cleared": True, "screen": {"joints": True}}]
    for h, p, at in itertools.product(variants, ["margaret", "dan", "priya"], ["08:00", "19:30"]):
        for c in plan(client, h, p=p, at=at)["cards"]:
            for n in c.get("context", []):
                if n.get("health_claim"):
                    assert n["source_id"] in SOURCES, n
                else:
                    assert n["source_id"] is None, n


# ---------------------------------------------------------------- privacy

def test_health_never_rides_in_the_url(client):
    # GET has no health parameter at all: a ?health=... is ignored, so nobody is tempted to use it.
    out = client.get("/api/today/dan", params={"at": "12:30", "health": '{"screen": {"chest_pain": true}}'}).json()
    assert out["health"]["readiness"] == "ok"


def test_bad_health_check_is_refused(client):
    assert client.post("/api/today/dan", json={"health": {"screen": "yes"}}).status_code == 422
