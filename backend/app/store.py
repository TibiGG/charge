"""PocketBase: accounts and each person's stored data.

The API talks to PocketBase as a superuser (PB_ADMIN_EMAIL / PB_ADMIN_PASSWORD) and
checks who is calling by refreshing the caller's own PocketBase token. Every value
that reaches a filter string is validated first (ids, dates, hex), never raw input.
"""
from __future__ import annotations

import os
import re
import threading
import time

import httpx

PB_URL = os.environ.get("PB_URL", "http://127.0.0.1:8090").rstrip("/")
_ADMIN = (os.environ.get("PB_ADMIN_EMAIL", ""), os.environ.get("PB_ADMIN_PASSWORD", ""))

ID = re.compile(r"^[a-z0-9]{15}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HEX = re.compile(r"^[a-f0-9]{16,64}$")
SAFE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")


class StoreError(RuntimeError):
    pass


def configured() -> bool:
    return bool(_ADMIN[0] and _ADMIN[1])


_client = httpx.Client(base_url=PB_URL, timeout=15.0)
_lock = threading.Lock()
_admin_token: str | None = None
# caller token -> (user record, expiry). Saves a PocketBase round trip on every request.
_seen: dict[str, tuple[dict, float]] = {}
SEEN_TTL_S = 120


def _login() -> str:
    global _admin_token
    r = _client.post("/api/collections/_superusers/auth-with-password",
                     json={"identity": _ADMIN[0], "password": _ADMIN[1]})
    if r.status_code != 200:
        raise StoreError(f"PocketBase superuser login failed ({r.status_code})")
    _admin_token = r.json()["token"]
    return _admin_token


def _req(method: str, path: str, **kw) -> httpx.Response:
    with _lock:
        token = _admin_token or _login()
    r = _client.request(method, path, headers={"Authorization": token}, **kw)
    if r.status_code == 401:
        with _lock:
            token = _login()
        r = _client.request(method, path, headers={"Authorization": token}, **kw)
    if r.status_code >= 400 and r.status_code != 404:
        raise StoreError(f"PocketBase {method} {path} -> {r.status_code}: {r.text[:300]}")
    return r


def _q(v: str, pattern: re.Pattern) -> str:
    if not pattern.match(v):
        raise ValueError(f"unsafe filter value: {v!r}")
    return f"'{v}'"


# ---------------------------------------------------------------- callers

def verify(token: str) -> dict | None:
    """The signed-in user's record, or None if the token isn't a valid users token."""
    if not token or len(token) > 2000:
        return None
    hit = _seen.get(token)
    if hit and hit[1] > time.time():
        return hit[0]
    r = _client.post("/api/collections/users/auth-refresh", headers={"Authorization": token})
    if r.status_code != 200:
        return None
    rec = r.json()["record"]
    if len(_seen) > 5000:
        _seen.clear()
    _seen[token] = (rec, time.time() + SEEN_TTL_S)
    return rec


def forget(user_id: str) -> None:
    for k in [k for k, (rec, _) in _seen.items() if rec["id"] == user_id]:
        _seen.pop(k, None)


# ---------------------------------------------------------------- generic CRUD

def list_all(coll: str, filt: str, sort: str = "", fields: str = "") -> list[dict]:
    out, page = [], 1
    while True:
        params = {"filter": filt, "perPage": 500, "page": page, "skipTotal": 1}
        if sort:
            params["sort"] = sort
        if fields:
            params["fields"] = fields
        items = _req("GET", f"/api/collections/{coll}/records", params=params).json()["items"]
        out += items
        if len(items) < 500:
            return out
        page += 1


def first(coll: str, filt: str) -> dict | None:
    items = _req("GET", f"/api/collections/{coll}/records",
                 params={"filter": filt, "perPage": 1, "skipTotal": 1}).json()["items"]
    return items[0] if items else None


def create(coll: str, data: dict) -> dict:
    return _req("POST", f"/api/collections/{coll}/records", json=data).json()


def update(coll: str, rid: str, data: dict) -> dict:
    return _req("PATCH", f"/api/collections/{coll}/records/{_id(rid)}", json=data).json()


def delete(coll: str, rid: str) -> None:
    _req("DELETE", f"/api/collections/{coll}/records/{_id(rid)}")


def _id(rid: str) -> str:
    if not ID.match(rid):
        raise ValueError("bad record id")
    return rid


def mine(uid: str) -> str:
    return f"user = {_q(uid, ID)}"


# ---------------------------------------------------------------- Charge data

def get_user(uid: str) -> dict:
    return _req("GET", f"/api/collections/users/records/{_id(uid)}").json()


def update_user(uid: str, data: dict) -> dict:
    forget(uid)
    return update("users", uid, data)


def workouts_since(uid: str, since: str) -> list[dict]:
    return list_all("workouts", f"{mine(uid)} && start >= {_q(since, DATE)}", sort="start")


def upsert_workouts(uid: str, rows: list[dict]) -> int:
    """Create the rows whose ext_id we don't already have. Returns how many were new."""
    if not rows:
        return 0
    since = min(r["start"][:10] for r in rows)
    have = {w["ext_id"] for w in list_all("workouts", f"{mine(uid)} && start >= {_q(since, DATE)}",
                                          fields="ext_id")}
    new = 0
    for r in rows:
        if r["ext_id"] in have:
            continue
        create("workouts", {**r, "user": uid})
        have.add(r["ext_id"])
        new += 1
    return new


def daily_since(uid: str, since: str) -> list[dict]:
    return list_all("daily", f"{mine(uid)} && date >= {_q(since, DATE)}", sort="date")


def upsert_daily(uid: str, rows: list[dict]) -> None:
    if not rows:
        return
    since = min(r["date"] for r in rows)
    have = {d["date"]: d["id"] for d in daily_since(uid, since)}
    for r in rows:
        if r["date"] in have:
            update("daily", have[r["date"]], r)
        else:
            create("daily", {**r, "user": uid})


def votes(uid: str) -> dict[str, str]:
    return {v["activity_id"]: v["vote"] for v in list_all("votes", mine(uid))}


def set_vote(uid: str, activity_id: str, vote: str | None) -> None:
    row = first("votes", f"{mine(uid)} && activity_id = {_q(activity_id, SAFE)}")
    if vote is None:
        if row:
            delete("votes", row["id"])
    elif row:
        update("votes", row["id"], {"vote": vote})
    else:
        create("votes", {"user": uid, "activity_id": activity_id, "vote": vote})


def day_logs(uid: str, since: str) -> list[dict]:
    return list_all("day_log", f"{mine(uid)} && date >= {_q(since, DATE)}", sort="date")


def save_day_log(uid: str, day: str, **fields) -> None:
    row = first("day_log", f"{mine(uid)} && date = {_q(day, DATE)}")
    if row:
        update("day_log", row["id"], fields)
    else:
        create("day_log", {"user": uid, "date": day, "shown": {}, "skips": [], **fields})


def token_owner(token_hash: str) -> str | None:
    row = first("sync_tokens", f"token_hash = {_q(token_hash, HEX)}")
    if not row:
        return None
    update("sync_tokens", row["id"], {"last_used": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return row["user"]


def replace_sync_token(uid: str, token_hash: str) -> None:
    for row in list_all("sync_tokens", mine(uid)):
        delete("sync_tokens", row["id"])
    create("sync_tokens", {"user": uid, "token_hash": token_hash})


def record_consent(uid: str, version: str, scopes: dict, when: str) -> None:
    create("consents", {"user": uid, "document_version": version, "scopes": scopes, "granted_at": when})


def latest_consent(uid: str) -> dict | None:
    rows = list_all("consents", f"{mine(uid)} && withdrawn_at = ''", sort="-created")
    return rows[0] if rows else None


# ---------------------------------------------------------------- sealed vaults (see app.vault)

def vault_of(uid: str, with_box: bool = True) -> dict | None:
    items = _req("GET", "/api/collections/vaults/records",
                 params={"filter": mine(uid), "perPage": 1, "skipTotal": 1,
                         **({} if with_box else {"fields": "id,pk,kdf,wrap_pw,wrap_rk"})}).json()["items"]
    return items[0] if items else None


def create_vault(uid: str, pk_hex: str, box: str, wraps: dict) -> None:
    create("vaults", {"user": uid, "pk": pk_hex, "box": box, **wraps})


def save_vault(rid: str, box: str) -> None:
    update("vaults", rid, {"box": box})


def set_wraps(rid: str, wraps: dict) -> None:
    update("vaults", rid, wraps)


def inbox_of(uid: str) -> list[dict]:
    return list_all("inbox", mine(uid), sort="created")


def wipe_vault(uid: str) -> None:
    for coll in ("inbox", "vaults"):
        for row in list_all(coll, mine(uid), fields="id"):
            delete(coll, row["id"])


def legacy(uid: str) -> dict:
    """What an account stored before vaults: plain rows, read once to seal them, then deleted."""
    return {c: list_all(c, mine(uid)) for c in ("workouts", "daily", "votes", "day_log")}


def drop_legacy(uid: str, rows: dict) -> None:
    for coll, items in rows.items():
        for r in items:
            delete(coll, r["id"])


def export_all(uid: str) -> dict:
    """The account side. The sealed vault is added by the API, which can open it for them."""
    out = {"account": get_user(uid), "consents": list_all("consents", mine(uid))}
    out["sync_tokens"] = [{"created": t["created"], "last_used": t.get("last_used")}
                          for t in list_all("sync_tokens", mine(uid))]
    return out


def erase(uid: str, when: str) -> None:
    """Delete the account; per-person rows cascade. Consent rows are kept but unlinked."""
    for c in list_all("consents", mine(uid)):
        update("consents", c["id"], {"user": "", "withdrawn_at": c.get("withdrawn_at") or when})
    _req("DELETE", f"/api/collections/users/records/{_id(uid)}")
    forget(uid)
