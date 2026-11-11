"""Each person's data, sealed so that only they can open it.

The browser makes a 32-byte secret key for each account and keeps it. It sends the key in the
X-Charge-Key header on every /api/me call. We use it in memory for that one request and never
store it or log it. What we store is sealed to the matching PUBLIC key (X25519 + HKDF-SHA256 +
AES-256-GCM, bound to the account id), so:

  - we can always ADD data without the key (the watch Shortcut, a Health export): it goes
    into a sealed inbox and is folded in the next time the person uses Charge;
  - we can only READ it while the person is using Charge and sends their key.

Neither the database, a backup, nor the people who run Charge can read a vault on its own.
The browser also keeps copies of the key locked by the person's password and by a recovery
key (frontend/src/lib/vault.ts). We store those locked copies, but we can't open them.

One vault per person: their profile, health check, workouts, sleep, votes, the last few
months of plans, and what Charge has learned from them. It's a few tens of KB.
"""
from __future__ import annotations

import base64
import binascii
import hmac
import json
import os
import secrets
import string
import threading
import zlib
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Callable, Iterator

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import Header, HTTPException

from app import store

BOX_V1 = b"\x01"
INFO = b"charge-vault-v1"
MAX_PLAIN = 20 << 20  # a vault is tens of KB; refuse to inflate anything near this
# How far back each part of the vault reaches. Older entries are dropped on every save.
KEEP = {"workouts": 400, "daily": 400, "days": 120}
ID_CHARS = string.ascii_lowercase + string.digits


# ---------------------------------------------------------------- crypto

def _raw(pub: X25519PublicKey) -> bytes:
    return pub.public_bytes(Encoding.Raw, PublicFormat.Raw)


def public_of(sk: bytes) -> bytes:
    return _raw(X25519PrivateKey.from_private_bytes(sk).public_key())


def _aes_key(shared: bytes, eph: bytes, pk: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=eph + pk, info=INFO).derive(shared)


def seal(pk: bytes, uid: str, obj) -> str:
    """Anyone with the public key can seal. Only the secret key opens it, and only for `uid`."""
    eph = X25519PrivateKey.generate()
    e = _raw(eph.public_key())
    key = _aes_key(eph.exchange(X25519PublicKey.from_public_bytes(pk)), e, pk)
    nonce = os.urandom(12)
    plain = zlib.compress(json.dumps(obj, separators=(",", ":")).encode())
    return base64.b64encode(BOX_V1 + e + nonce + AESGCM(key).encrypt(nonce, plain, uid.encode())).decode()


def unseal(sk: bytes, uid: str, box: str):
    raw = base64.b64decode(box)
    if raw[:1] != BOX_V1 or len(raw) < 61:
        raise ValueError("not a vault box")
    e, nonce, ct = raw[1:33], raw[33:45], raw[45:]
    shared = X25519PrivateKey.from_private_bytes(sk).exchange(X25519PublicKey.from_public_bytes(e))
    plain = AESGCM(_aes_key(shared, e, public_of(sk))).decrypt(nonce, ct, uid.encode())
    d = zlib.decompressobj()
    out = d.decompress(plain, MAX_PLAIN)
    if d.unconsumed_tail:
        raise ValueError("vault too large")
    return json.loads(out)


def parse_key(raw: str | None) -> bytes | None:
    """The X-Charge-Key header: 32 bytes, base64url, no padding."""
    if not raw or len(raw) > 64:
        return None
    try:
        k = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except (binascii.Error, ValueError):
        return None
    return k if len(k) == 32 else None


def key_header(x_charge_key: str | None = Header(default=None)) -> bytes | None:
    """FastAPI dependency. The key is only ever a header: never a URL, never a body we keep."""
    return parse_key(x_charge_key)


# ---------------------------------------------------------------- the document

def empty() -> dict:
    return {"v": 1,
            "profile": {},          # birth_year, sex, timezone, habits, kit, routine
            "health": None,         # the health check (app.health.HealthIn), or None if not done
            "health_log": [],       # [{"on": date, "on_items": [...], "off_items": [...]}]: what changed, when
            "workouts": [],         # [{id, ext_id, source, type, start, duration_min, mean_hr, effort, counts, note}]
            "daily": {},            # date -> {steps, sleep_hours, sleep_onset, exercise_min, falls, bp: [[sys, dia]]}
            "votes": {},            # activity id -> "more" | "less"
            "days": {},             # date -> {shown: {daypart: id}, skips: [ids], planned: [ids], not_today: [ids]}
            "answers": {}}          # question id -> {"value": str, "on": date} (see app.learn)


def new_id() -> str:
    """Same shape as a PocketBase record id, so the Activity tab's delete links keep working."""
    return "".join(secrets.choice(ID_CHARS) for _ in range(15))


def upsert_workouts(data: dict, rows: list[dict]) -> int:
    """Add the rows whose ext_id we don't have yet. Returns how many were new."""
    have = {w["ext_id"] for w in data["workouts"]}
    new = 0
    for r in rows:
        if r["ext_id"] in have:
            continue
        data["workouts"].append({"id": new_id(), "mean_hr": 0, "effort": "", "counts": None, "note": "", **r})
        have.add(r["ext_id"])
        new += 1
    data["workouts"].sort(key=lambda w: w["start"])
    return new


def upsert_daily(data: dict, rows: list[dict]) -> None:
    for r in rows:
        day = data["daily"].setdefault(r["date"], {})
        day.update({k: v for k, v in r.items() if k != "date"})


def prune(data: dict, today: date) -> None:
    cut = {k: (today - timedelta(days=n)).isoformat() for k, n in KEEP.items()}
    data["workouts"] = [w for w in data["workouts"] if w["start"][:10] >= cut["workouts"]]
    data["daily"] = {d: v for d, v in data["daily"].items() if d >= cut["daily"]}
    data["days"] = {d: v for d, v in data["days"].items() if d >= cut["days"]}


# ---------------------------------------------------------------- open / save

class Vault:
    def __init__(self, uid: str, rec: dict, data: dict):
        self.uid, self.rec_id, self.pk, self.data = uid, rec["id"], bytes.fromhex(rec["pk"]), data
        self.dirty = False

    def changed(self) -> None:
        self.dirty = True


# Inbox items (sealed while the person was away) are folded in by these, keyed by "kind".
# app.accounts registers them; they get the vault and the item, and change the vault in place.
FOLDERS: dict[str, Callable[[Vault, dict], None]] = {}
_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)


def state(uid: str, sk: bytes | None) -> str:
    """'none' (no vault yet) | 'locked' (no key, or the wrong one) | 'open'."""
    rec = store.vault_of(uid)
    if not rec:
        return "none"
    return "open" if sk is not None and _matches(sk, rec) else "locked"


def _matches(sk: bytes, rec: dict) -> bool:
    return hmac.compare_digest(public_of(sk), bytes.fromhex(rec["pk"]))


@contextmanager
def opened(uid: str, sk: bytes | None, today: date | None = None) -> Iterator[Vault]:
    """The person's vault, open for this request only. Changes are sealed again on the way out.
    One request at a time per person, so two quick taps can't overwrite each other."""
    with _locks[uid]:
        rec = store.vault_of(uid)
        if not rec:
            raise HTTPException(428, "vault_required")
        if sk is None or not _matches(sk, rec):
            raise HTTPException(423, "vault_locked")
        try:
            data = {**empty(), **unseal(sk, uid, rec["box"])}
        except (InvalidTag, ValueError):
            raise HTTPException(423, "vault_locked")
        v = Vault(uid, rec, data)
        inbox = store.inbox_of(uid)
        for item in inbox:
            try:
                got = unseal(sk, uid, item["box"])
            except (InvalidTag, ValueError):
                continue
            fold = FOLDERS.get(got.get("kind"))
            if fold:
                fold(v, got)
                v.changed()
        yield v
        if v.dirty or inbox:
            prune(v.data, today or date.today())
            store.save_vault(rec["id"], seal(v.pk, uid, v.data))
        for item in inbox:  # only once the vault that holds them is saved
            store.delete("inbox", item["id"])


def create(uid: str, sk: bytes, wraps: dict, data: dict) -> None:
    store.create_vault(uid, public_of(sk).hex(), seal(public_of(sk), uid, data), wraps)


def post(uid: str, item: dict) -> bool:
    """Seal something for a person who isn't here. False if they have no vault yet."""
    rec = store.vault_of(uid)
    if not rec:
        return False
    store.create("inbox", {"user": uid, "box": seal(bytes.fromhex(rec["pk"]), uid, item)})
    return True
