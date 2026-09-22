"""Signed-in flow against a real, throwaway PocketBase (skipped if the binary isn't there).

    PB_BIN=/path/to/pocketbase pytest tests/test_accounts.py
"""
import io
import os
import shutil
import socket
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import accounts, store
from app.main import app

ROOT = Path(__file__).resolve().parents[1]
PB_BIN = os.environ.get("PB_BIN") or shutil.which("pocketbase")
FIXTURE = ROOT / "backend/data/apple_health/sample_export.xml"
pytestmark = pytest.mark.skipif(not PB_BIN, reason="set PB_BIN to a pocketbase binary")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def pb():
    d = tempfile.mkdtemp()
    mig = str(ROOT / "pocketbase/pb_migrations")
    subprocess.run([PB_BIN, "migrate", "up", "--dir", d, "--migrationsDir", mig], check=True, capture_output=True)
    subprocess.run([PB_BIN, "superuser", "upsert", "admin@test.local", "adminpass1234", "--dir", d],
                   check=True, capture_output=True)
    port = _free_port()
    proc = subprocess.Popen([PB_BIN, "serve", "--dir", d, "--migrationsDir", mig, "--http", f"127.0.0.1:{port}"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            if httpx.get(f"{url}/api/health").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    old = (store._client, store._ADMIN, store._admin_token)
    store._client = httpx.Client(base_url=url, timeout=15)
    store._ADMIN = ("admin@test.local", "adminpass1234")
    store._admin_token = None
    yield url
    store._client, store._ADMIN, store._admin_token = old
    proc.terminate()
    shutil.rmtree(d, ignore_errors=True)


def _signup(url: str, email: str) -> str:
    r = httpx.post(f"{url}/api/collections/users/records",
                   json={"email": email, "password": "correct-horse-1", "passwordConfirm": "correct-horse-1"})
    assert r.status_code == 200, r.text
    r = httpx.post(f"{url}/api/collections/users/auth-with-password",
                   json={"identity": email, "password": "correct-horse-1"})
    return r.json()["token"]


@pytest.fixture(scope="module")
def client(pb):
    with TestClient(app) as c:
        yield c


def test_signed_in_journey(pb, client):
    h = {"Authorization": _signup(pb, "ada@example.com")}
    assert client.get("/api/me/today").status_code == 401

    me = client.get("/api/me", headers=h).json()
    assert me["consent"] is False and me["bupa"]["available"] is False
    # Nothing about their health is read or stored before they agree.
    assert client.get("/api/me/batteries", headers=h).status_code == 403
    r = client.post("/api/me/consent", headers=h,
                    json={"version": accounts.CONSENT_VERSION, "scopes": {"health_data": True, "recommendations": True}})
    assert r.status_code == 200
    assert client.get("/api/me/batteries", headers=h).status_code == 409  # profile first

    r = client.put("/api/me/profile", headers=h, json={"birth_year": 1971, "timezone": "Europe/London",
                                                       "kit": {"home": ["mat", "chair"], "gym": None}})
    assert r.status_code == 200 and r.json()["age"] >= 54

    # A new account starts empty: every battery at zero.
    b = client.get("/api/me/batteries", headers=h).json()
    assert all(x["value"] == 0 for x in b["batteries"])

    # A manual log fills strength by its weighted minutes.
    today = client.get("/api/me/activity", headers=h).json()["as_of"]
    r = client.post("/api/me/logs", headers=h, json={"type": "TraditionalStrengthTraining",
                                                     "start": f"{today}T07:30", "duration_min": 30, "effort": "moderate"})
    assert r.status_code == 200
    b = client.get("/api/me/batteries", headers=h).json()
    assert next(x for x in b["batteries"] if x["id"] == "strength")["value"] == 30

    # Today's plan, then "Something else" swaps the live card and says why.
    t = client.get("/api/me/today", headers=h, params={"at": "08:00"}).json()
    first = t["cards"][0]["activity"]["id"]
    assert client.post("/api/me/skip", headers=h, json={"activity_id": first}).status_code == 200
    t2 = client.get("/api/me/today", headers=h, params={"at": "08:00"}).json()
    card = t2["cards"][0]
    assert card.get("activity") is None or card["activity"]["id"] != first
    if card.get("activity"):
        assert card["context"][0]["kind"] == "skip"

    # Votes are stored and reach the reasoner.
    assert client.post("/api/me/votes", headers=h, json={"activity_id": first, "vote": "less"}).status_code == 200
    assert store.votes(me["id"]) == {first: "less"}


def test_shortcut_and_export_upload(pb, client):
    h = {"Authorization": _signup(pb, "bea@example.com")}
    client.post("/api/me/consent", headers=h,
                json={"version": accounts.CONSENT_VERSION, "scopes": {"health_data": True, "recommendations": True}})
    client.put("/api/me/profile", headers=h, json={"birth_year": 1980, "timezone": "Europe/London"})
    today = client.get("/api/me/activity", headers=h).json()["as_of"]

    token = client.post("/api/me/sync-token", headers=h).json()["token"]
    assert client.post("/api/sync/workouts", json={"type": "Running"}).status_code == 401
    w = {"type": "High Intensity Interval Training", "start": f"{today}T06:00:00+01:00",
         "end": f"{today}T06:20:00+01:00", "heart_rate": "150"}
    r = client.post("/api/sync/workouts", headers={"Authorization": f"Bearer {token}"}, json={"workouts": [w, w]})
    assert r.json()["new"] == 1  # the repeat is deduped
    peak = next(x for x in client.get("/api/me/batteries", headers=h).json()["batteries"] if x["id"] == "peak")
    assert peak["value"] == 20

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.write(FIXTURE, "apple_health_export/export.xml")
    job = client.post("/api/me/import", headers=h, files={"file": ("export.zip", buf.getvalue())}).json()["job"]
    for _ in range(100):
        st = client.get(f"/api/me/import/{job}", headers=h).json()
        if st["stage"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert st["stage"] == "done", st

    # Export has everything; deleting the account removes it and keeps an unlinked consent record.
    dump = client.get("/api/me/export", headers=h).json()
    assert dump["workouts"] and dump["consents"]
    uid = dump["account"]["id"]
    assert client.delete("/api/me", headers=h).status_code == 200
    assert client.get("/api/me", headers=h).status_code == 401
    assert store.list_all("workouts", store.mine(uid)) == []
