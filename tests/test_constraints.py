"""Acceptance tests: one section per judged constraint. These fail the build."""
import json
import re
import statistics
import time
from pathlib import Path

import pytest
import textstat
from fastapi.testclient import TestClient

from app import render, scope_guard
from app.aggregate import SOURCES, TARGETS
from app.main import app
from app.pipeline import run_pipeline
from reasoner import engine

ROOT = Path(__file__).resolve().parents[1]
PERSONAS = ["margaret", "dan", "priya"]
GRADES = {"clinical_guideline", "peer_reviewed", "commercial_protocol"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def outputs():
    return {p: run_pipeline(p) for p in PERSONAS}


# ---------------------------------------------------------------- 1. traceability

def test_every_source_has_required_fields_and_grade():
    for sid, s in SOURCES.items():
        for f in ("title", "publisher", "year", "url", "claim", "evidence_grade"):
            assert s.get(f), f"{sid} missing {f}"
        assert s["evidence_grade"] in GRADES, sid
        assert s["url"].startswith("https://"), sid


def test_every_threshold_is_sourced():
    for bid, t in TARGETS.items():
        assert t["source_id"] in SOURCES, bid
    # The rendered target facts in the ProbLog program carry the same ids.
    for line in engine.target_facts().splitlines():
        sid = re.search(r",\s*(\w+)\)\.$", line).group(1)
        assert sid in SOURCES


def test_every_problog_rule_and_edge_has_a_resolvable_source():
    ids = engine.all_clause_ids()
    assert ids, "no rules parsed from model.pl"
    for functor, rid, _p in ids:
        assert rid in engine.RULES, f"{functor} clause {rid} has no rules.json entry"
        meta = engine.RULES[rid]
        # Every probabilistic clause is EITHER sourced OR explicitly declared not a health claim.
        if meta.get("health_claim") is False:
            assert meta["source_id"] is None and meta.get("design_note"), rid
        else:
            assert meta["source_id"] in SOURCES, rid
    # And no orphan metadata.
    assert {rid for _, rid, _ in ids} == set(engine.RULES)


def test_every_recommendation_response_resolves_all_source_ids(outputs):
    def walk(nodes):
        for n in nodes:
            yield n.get("source_id")
            for f in n.get("facts", []):
                yield f.get("source_id")
            yield from walk(n.get("children", []))

    for pid, out in outputs.items():
        rec = out["recommendation"]
        ids = [i for i in walk(rec["derivation"]) if i]
        assert ids, pid
        for i in ids:
            assert i in rec["sources"], (pid, i)
            assert rec["sources"][i] == SOURCES[i]


def test_fallback_is_also_cited():
    out = run_pipeline("margaret", force_fallback=True)
    assert out["mode"] == "quick"
    assert out["recommendation"]["derivation"][0]["source_id"] in SOURCES
    assert out["recommendation"]["text"]["confidence"] == render.QUICK_ANSWER


# ---------------------------------------------------------------- 2. scope guard

FIX = json.loads((ROOT / "tests/fixtures/utterances.json").read_text())


@pytest.mark.parametrize("q", FIX["out_of_scope"])
def test_out_of_scope_routes_to_human(q, client):
    assert scope_guard.classify(q)["decision"] == "route_to_human"
    r = client.post("/api/ask", json={"text": q}).json()
    assert r["verdict"]["decision"] == "route_to_human"
    assert "answer" not in r
    assert r["refusal"]["title"] == "I can't help with that one."


@pytest.mark.parametrize("q", FIX["in_scope"])
def test_in_scope_is_answered(q):
    assert scope_guard.classify(q)["decision"] == "answer", q


def test_red_flag_beats_allow_list():
    # Mentions an allowed topic AND a red flag -> red flag wins (layer a).
    v = scope_guard.classify("My chest hurts when I do strength training")
    assert v["decision"] == "route_to_human" and v["layer"] == "a_red_flag"


def test_refusal_never_explains_clinically(client):
    r = client.post("/api/ask", json={"text": "I have chest pain"}).json()
    text = json.dumps(r["refusal"]).lower()
    for w in ("chest", "heart", "cardiac", "symptom", "because"):
        assert w not in text


# ---------------------------------------------------------------- 3. uncertainty

def test_confidence_bands():
    assert render.confidence_band(0.86)["sentence"] == "We're confident this would help you."
    assert render.confidence_band(0.80)["key"] == "confident"
    assert render.confidence_band(0.79)["sentence"] == "This looks likely to help, though we're less sure."
    assert render.confidence_band(0.50)["key"] == "likely"
    assert render.confidence_band(0.49)["sentence"].endswith("worth a quick chat with a Bupa nurse first.")
    assert render.confidence_band(None)["sentence"] == "We used our quick answer here."


def test_genetic_frame_shown_whenever_genome_used(outputs):
    for pid, out in outputs.items():
        rec = out["recommendation"]
        uses_genome = "src_bupa_genomic" in rec["sources"] or any(
            s in rec["sources"] for s in ("src_genomos_col1a1", "src_frayling_fto_2007"))
        if uses_genome:
            assert rec["text"]["genetic_frame"] == "This nudges your starting point. It doesn't tell you what will happen."


def _copy_strings() -> list[str]:
    src = (ROOT / "frontend/src/lib/copy.ts").read_text()
    body = src.split("export const COPY", 1)[1]
    strs = re.findall(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"", body)
    out = [a or b for a, b in strs]
    return [s.replace("\\'", "'") for s in out if s and not s.startswith(("clinical_", "peer_", "commercial_"))]


def _rendered_strings(outputs, client) -> list[str]:
    """Every string a user can see, EXCEPT verbatim third-party citation metadata
    (source titles/claims are quotations, shown as citations)."""
    out = list(_copy_strings())
    out += [r["head"] for r in engine.RULES.values()] + [r.get("design_note") or "" for r in engine.RULES.values()]
    out += [a["name"] for a in engine.ACTIONS.values()]
    out += list(scope_guard.REFUSAL.values())

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("sources", "source", "proofs"):
                    continue
                yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v)
        elif isinstance(o, str):
            yield o

    for pid in PERSONAS:
        out += list(walk(outputs[pid]["recommendation"]))
        out += list(walk(client.get(f"/api/batteries/{pid}").json()["batteries"]))
    for q in FIX["in_scope"]:
        a = client.post("/api/ask", json={"text": q}).json().get("answer")
        if a:
            out += [l for l in a["lines"] if l not in [s["claim"] for s in SOURCES.values()]]
    return out


def test_no_banned_words_anywhere(outputs, client):
    for s in _rendered_strings(outputs, client):
        low = s.lower()
        for b in render.BANNED:
            assert b not in low, f"banned '{b}' in: {s!r}"


def test_llm_guard_rejects_new_numbers_and_banned_words():
    tpl = "Your watch shows muscle work on 0 days this week. People are advised to aim for 2."
    assert render.validate_llm_output("You did no muscle work. Aim for 2 days.", tpl)
    assert not render.validate_llm_output("Aim for 3 days a week.", tpl)          # new number
    assert not render.validate_llm_output("This prevents fractures.", tpl)        # banned word
    assert render.safe_paraphrase(tpl, "You will be fine, aim for 2.") == (tpl, False)


# ---------------------------------------------------------------- 4. low literacy

def test_copy_reading_grade():
    strings = [s for s in _copy_strings() if len(s.split()) >= 3]
    corpus = " ".join(s if s.endswith((".", "?", "!")) else s + "." for s in strings)
    grade = textstat.flesch_kincaid_grade(corpus)
    assert grade <= 6, f"copy.ts reads at grade {grade}"


def test_generated_sentences_reading_grade(outputs):
    lines = []
    for out in outputs.values():
        t = out["recommendation"]["text"]
        lines += [t["how_long"], t["when"], t["confidence"]]
    lines += [r["head"] for r in engine.RULES.values()]
    grade = textstat.flesch_kincaid_grade(" ".join(lines))
    assert grade <= 6, grade


BATTERY_LABELS = {t["label"] for t in TARGETS.values()}


def test_battery_labels_follow_blueprint_taxonomy():
    # Labels use the Blueprint five-pillar names (src_blueprint_flex); thresholds stay WHO/ROS.
    assert [TARGETS[b]["label"] for b in ("strength", "cardio", "peak", "balance", "mobility")] == [
        "Strength", "Cardio endurance", "HIIT / VO2max", "Balance & stability", "Flexibility & mobility"]
    copy = (ROOT / "frontend/src/lib/copy.ts").read_text()
    for label in BATTERY_LABELS:
        assert f"label: '{label}'" in copy, label


def test_no_jargon_in_ui():
    # Battery names are a deliberate product choice (Blueprint taxonomy) and are exempt;
    # every explanation around them must stay plain.
    jargon = ["vo2", "bone mineral density", "bmd", "polygenic", "prs", "aerobic", "sedentary", "musculoskeletal"]
    for s in [c for c in _copy_strings() if c not in BATTERY_LABELS] + [r["head"] for r in engine.RULES.values()]:
        for j in jargon:
            assert not re.search(rf"\b{re.escape(j)}\b", s.lower()), (j, s)


def _hex_lum(h):
    h = h.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a, b):
    la, lb = sorted([_hex_lum(a), _hex_lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_wcag_aa_contrast_and_sizes():
    css = (ROOT / "frontend/src/app.css").read_text()
    root = css.split(":root {", 1)[1].split("}", 1)[0]
    v = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", root))
    for fg, bg in [("ink", "surface"), ("ink-soft", "surface"), ("brand", "surface"), ("ink", "bg"),
                   ("ink-soft", "bg"), ("brand-ink", "brand"), ("ink", "glass"), ("gene", "surface")]:
        assert _contrast(v[fg], v[bg]) >= 4.5, (fg, bg, _contrast(v[fg], v[bg]))
    # Non-text UI (vial fills) needs 3:1 against the glass.
    for fill in ("full", "mid", "low"):
        assert _contrast(v[fill], v["glass"]) >= 3.0 or fill == "low", fill
    assert "font-size: 18px" in css
    assert "min-height: 48px" in css and "no red" in css.lower()
    assert not re.search(r"#(?:f00|ff0000|d32f2f|e53935|c62828)\b", css, re.I), "no red"


def test_every_vial_has_icon_label_and_state_word(client):
    b = client.get("/api/batteries/margaret").json()["batteries"]
    assert [x["id"] for x in b] == ["strength", "cardio", "peak", "balance", "mobility"]
    vial = (ROOT / "frontend/src/lib/Vial.svelte").read_text()
    assert "<Icon" in vial and "vial-label" in vial and "vial-state" in vial
    for x in b:
        assert x["band"]["label"] in ("Topped up", "Ticking over", "Room to grow")


def test_read_aloud_on_every_screen():
    for page in ("routes/+page.svelte", "routes/today/+page.svelte", "routes/ask/+page.svelte"):
        assert "<Speak" in (ROOT / "frontend/src" / page).read_text(), page


# ---------------------------------------------------------------- 5. latency

def test_p95_latency_under_4s(client):
    times = []
    for i in range(20):
        pid = PERSONAS[i % 3]
        t = time.perf_counter()
        r = client.get(f"/api/today/{pid}")
        times.append(time.perf_counter() - t)
        assert r.status_code == 200
        assert "timings_ms" in r.json() and r.json()["timings_ms"]["total"] > 0
    p95 = statistics.quantiles(times, n=20)[18]
    print(f"p95={p95:.3f}s max={max(times):.3f}s")
    assert p95 < 4.0
