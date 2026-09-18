import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import aggregate
from app.main import app
from ingest.apple_health import infer_habits, parse

FIXTURE = Path(__file__).resolve().parents[1] / "data/apple_health/sample_export.xml"


@pytest.fixture(autouse=True)
def reset():
    aggregate.LIVE_WORKOUTS.clear()
    aggregate.IMPORTED.clear()
    yield
    aggregate.LIVE_WORKOUTS.clear()
    aggregate.IMPORTED.clear()


def test_parse_fixture_streams_expected_records():
    p = parse(str(FIXTURE), sample=True)
    assert p["age"] == 54 and p["sex"] == "female"
    assert p["as_of"] == "2026-09-18"
    assert len(p["workouts"]) == 10
    assert p["vo2max"] == 32.4
    assert {w["type"] for w in p["workouts"]} >= {"Cycling", "Yoga", "TraditionalStrengthTraining"}
    # InBed must not be counted as sleep: 7h20m asleep per night.
    assert abs(p["daily"][-1]["sleep_hours"] - 7.33) < 0.01
    assert set(infer_habits(p["workouts"])) == {"spin", "walking", "weights", "yoga"}


def test_hr_promotes_cycling_to_vigorous():
    p = parse(str(FIXTURE))
    b = aggregate.compute_batteries(p)
    assert b["metrics"]["vigorous_min_per_week"] == 40  # the 149bpm ride at age 54 (>141)


def test_zip_upload_via_api():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.write(FIXTURE, "apple_health_export/export.xml")
    with TestClient(app) as c:
        r = c.post("/api/ingest/apple-health", files={"file": ("export.zip", buf.getvalue())})
        assert r.status_code == 200, r.text
        assert r.json()["imported"]["workouts"] == 10
        # Sam now has a watch and gets a recommendation.
        assert c.get("/api/batteries/sam").json()["persona"]["watch_connected"] is True
        assert c.get("/api/today/sam").status_code == 200


def test_live_sample_fills_vial():
    with TestClient(app) as c:
        before = next(b for b in c.get("/api/batteries/margaret").json()["batteries"] if b["id"] == "strength")
        r = c.post("/api/ingest/sample", json={"metric": "TraditionalStrengthTraining", "value": 20,
                                               "persona": "margaret", "device": "watch"})
        assert r.status_code == 200
        after = next(b for b in c.get("/api/batteries/margaret").json()["batteries"] if b["id"] == "strength")
        assert after["fill"] > before["fill"]
        assert after["band"]["label"] == "Ticking over"
