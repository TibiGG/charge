"""Signed-in flow against a real, throwaway PocketBase (skipped if the binary isn't there).

    PB_BIN=/path/to/pocketbase pytest tests/test_accounts.py
"""
import base64
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

from app import accounts, learn, store
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


def _key() -> tuple[bytes, str]:
    sk = os.urandom(32)
    return sk, base64.urlsafe_b64encode(sk).decode().rstrip("=")


LOCKS = {"wrap_rk": "A" * 80, "kdf": {"rk": {"salt": "B" * 22, "iter": 100_000}}}


def _ready(client, url: str, email: str, birth_year: int = 1971) -> dict:
    """Signed up, agreed, with a vault and a profile: the headers for every later call."""
    h = {"Authorization": _signup(url, email)}
    sk, k = _key()
    assert client.post("/api/me/vault", headers={**h, "X-Charge-Key": k}, json=LOCKS).status_code == 200
    h["X-Charge-Key"] = k
    client.post("/api/me/consent", headers=h,
                json={"version": accounts.CONSENT_VERSION, "scopes": {"health_data": True, "recommendations": True}})
    client.put("/api/me/profile", headers=h, json={"birth_year": birth_year, "timezone": "Europe/London"})
    return h


@pytest.fixture(scope="module")
def client(pb):
    with TestClient(app) as c:
        yield c


def test_signed_in_journey(pb, client):
    h = {"Authorization": _signup(pb, "ada@example.com")}
    assert client.get("/api/me/today").status_code == 401

    me = client.get("/api/me", headers=h).json()
    assert me["consent"] is False and me["bupa"]["available"] is False and me["vault"] == "none"
    # Their key is made in the browser; the server keeps only its public half and locked copies.
    sk, k = _key()
    assert client.post("/api/me/vault", headers=h, json=LOCKS).status_code == 422  # no key sent
    assert client.post("/api/me/vault", headers={**h, "X-Charge-Key": k}, json={"wrap_rk": ""}).status_code == 422
    assert client.post("/api/me/vault", headers={**h, "X-Charge-Key": k}, json=LOCKS).status_code == 200
    assert client.post("/api/me/vault", headers={**h, "X-Charge-Key": k}, json=LOCKS).status_code == 409
    assert client.get("/api/me", headers=h).json()["vault"] == "locked"
    assert client.get("/api/me/vault", headers=h).json() == {"exists": True, **LOCKS, "wrap_pw": ""}
    h["X-Charge-Key"] = k
    assert client.get("/api/me", headers=h).json()["vault"] == "open"
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
    assert client.get("/api/me/today", headers=h, params={"at": "08:00"}).json()["taste"] == {first: "less"}

    # A draft log rides in the body, never the URL.
    r = client.post("/api/me/batteries", headers=h, json={"logs": [{"type": "Walking", "start": f"{today}T12:00",
                                                                     "duration_min": 20}]})
    assert next(x for x in r.json()["batteries"] if x["id"] == "cardio")["added"] == 20


def test_vault_is_sealed_from_the_operator(pb, client):
    """Everything personal reaches PocketBase sealed. Without their key, nobody can read it, not
    even with the superuser account: not their health check, not their workouts, not their age."""
    h = {"Authorization": _signup(pb, "grace@example.com")}
    sk, k = _key()
    sent = []
    real = store._client.request

    def spy(method, url, *a, **kw):
        sent.append(f"{method} {url} {kw.get('json') or ''} {kw.get('params') or ''} {kw.get('content') or ''}")
        return real(method, url, *a, **kw)

    store._client.request = spy
    try:
        client.post("/api/me/vault", headers={**h, "X-Charge-Key": k}, json=LOCKS)
        h["X-Charge-Key"] = k
        client.post("/api/me/consent", headers=h,
                    json={"version": accounts.CONSENT_VERSION, "scopes": {"health_data": True, "recommendations": True}})
        client.put("/api/me/profile", headers=h, json={"birth_year": 1960, "sex": "female", "timezone": "Europe/Paris",
                                                       "habits": ["yoga"]})
        health = {"screen": {"heart": True}, "conditions": ["type2_diabetes", "pregnant"], "menopause": "post",
                  "report": {"bones": "high", "variants": ["col1a1"]}}
        assert client.put("/api/me/health", headers=h, json={"health": health}).status_code == 200
        today = client.get("/api/me/activity", headers=h).json()["as_of"]
        client.post("/api/me/logs", headers=h, json={"type": "Swimming", "start": f"{today}T07:00",
                                                     "duration_min": 33, "note": "lane swim"})
        r = client.get("/api/me/today", headers=h, params={"at": "08:00"})
    finally:
        store._client.request = real
    assert r.status_code == 200 and r.json()["health"]["readiness"] == "gentle"
    assert sent, "the spy saw no PocketBase traffic at all"
    leaks = ("screen", "heart", "diabetes", "pregnant", "menopause", "readiness", "diagnosed", "col1a1",
             "rs1800012", "prs_band", "conditions", "swimming", "lane swim", "1960", "female", "paris", "yoga",
             k.lower(), sk.hex())
    for line in sent:
        assert not any(x in line.lower() for x in leaks), line

    # What the operator sees: a public key, a sealed box, and nothing in the old plain places.
    uid = client.get("/api/me", headers=h).json()["id"]
    rec = store.vault_of(uid)
    assert rec["box"] and "pregnant" not in rec["box"] and len(rec["pk"]) == 64
    u = store.get_user(uid)
    assert not u.get("birth_year") and not u.get("sex") and not u.get("timezone") and not u.get("habits")
    assert all(store.list_all(c, store.mine(uid)) == [] for c in ("workouts", "votes", "day_log", "daily"))

    # Without the key, or with the wrong one, it stays shut.
    no_key = {"Authorization": h["Authorization"]}
    assert client.get("/api/me/health", headers=no_key).status_code == 423
    assert client.get("/api/me/today", headers={**no_key, "X-Charge-Key": _key()[1]}).status_code == 423
    assert client.get("/api/me/health", headers={**no_key, "X-Charge-Key": "not-a-key"}).status_code == 423
    # With it, they get all of it back.
    dump = client.get("/api/me/export", headers=h).json()
    assert dump["vault"]["health"]["conditions"] == ["type2_diabetes", "pregnant"]
    assert dump["vault"]["profile"]["birth_year"] == 1960
    assert dump["vault"]["workouts"][0]["note"] == "lane swim"


def test_old_plain_accounts_are_sealed_on_first_visit(pb, client):
    h = {"Authorization": _signup(pb, "lin@example.com")}
    uid = client.get("/api/me", headers=h).json()["id"]
    store.update_user(uid, {"birth_year": 1958, "sex": "female", "menopause_status": "post", "timezone": "Europe/London",
                            "habits": ["walking"]})
    store.create("workouts", {"user": uid, "ext_id": "x-old", "source": "export", "type": "Walking",
                              "start": "2026-11-09T09:00:00", "duration_min": 40})
    store.create("votes", {"user": uid, "activity_id": "heel_drops", "vote": "less"})
    _, k = _key()
    r = client.post("/api/me/vault", headers={**h, "X-Charge-Key": k}, json=LOCKS)
    assert r.status_code == 200 and r.json()["moved"] == 2
    assert store.list_all("workouts", store.mine(uid)) == [] and not store.get_user(uid).get("birth_year")
    d = client.get("/api/me/export", headers={**h, "X-Charge-Key": k}).json()["vault"]
    assert d["profile"]["birth_year"] == 1958 and d["profile"]["habits"] == ["walking"]
    assert d["health"]["menopause"] == "post" and d["votes"] == {"heel_drops": "less"}
    assert d["workouts"][0]["ext_id"] == "x-old"


def test_charge_learns_and_asks(pb, client):
    """Passing on jumpy ideas teaches it to leave them out, with a line that says so and an undo."""
    h = _ready(client, pb, "kim@example.com")
    jumpy = sorted(learn.IMPACT)
    for aid in jumpy[:3]:
        assert client.post("/api/me/skip", headers=h, json={"activity_id": aid}).status_code == 200
    t = client.get("/api/me/today", headers=h, params={"at": "08:00"}).json()
    picks = [c["activity"]["id"] for c in t["cards"] if c.get("activity")]
    assert not set(picks) & learn.IMPACT
    lines = [n for c in t["cards"] if c.get("activity") for n in c["context"] if n["kind"] == "learned"]
    assert lines and all(not n["health_claim"] for n in lines)
    learned = client.get("/api/me/learned", headers=h).json()["learned"]
    assert {"id": "undo:no_jumps", "text": learn.LEARNED["no_jumps"]} in learned
    assert client.post("/api/me/answers", headers=h, json={"id": "undo:nope", "value": "yes"}).status_code == 404
    r = client.post("/api/me/answers", headers=h, json={"id": "undo:no_jumps", "value": "yes"}).json()
    assert all(x["id"] != "undo:no_jumps" for x in r["learned"])
    # Feedback from the live card is kept for learning.
    assert client.post("/api/me/feedback", headers=h, json={"activity_id": picks[0], "signal": "planned"}).status_code == 200
    assert client.post("/api/me/feedback", headers=h, json={"activity_id": picks[0], "signal": "x"}).status_code == 422



def test_shortcut_and_export_upload(pb, client):
    h = _ready(client, pb, "bea@example.com", 1980)
    uid = client.get("/api/me", headers=h).json()["id"]
    today = client.get("/api/me/activity", headers=h).json()["as_of"]

    token = client.post("/api/me/sync-token", headers=h).json()["token"]
    assert client.post("/api/sync/workouts", json={"type": "Running"}).status_code == 401
    w = {"type": "High Intensity Interval Training", "start": f"{today}T06:00:00+01:00",
         "end": f"{today}T06:20:00+01:00", "heart_rate": "150"}
    r = client.post("/api/sync/workouts", headers={"Authorization": f"Bearer {token}"}, json={"workouts": [w, w]})
    assert r.json()["new"] == 1  # the repeat is deduped
    assert len(store.inbox_of(uid)) == 1 and "High" not in store.inbox_of(uid)[0]["box"]  # sealed while away
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
    assert len(dump["vault"]["workouts"]) > 1 and dump["consents"] and store.inbox_of(uid) == []
    assert client.delete("/api/me", headers=h).status_code == 200
    assert client.get("/api/me", headers=h).status_code == 401
    assert store.list_all("vaults", store.mine(uid)) == []
