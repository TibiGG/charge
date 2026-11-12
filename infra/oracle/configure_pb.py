"""Apply PocketBase settings from the environment (idempotent). Run inside the API container on the
VM (deploy.sh for live, CI for dev), because the superuser login isn't reachable from the internet.

Needs PB_URL (the internal address), PB_ADMIN_EMAIL, PB_ADMIN_PASSWORD. Optional: PB_APP_URL (the
public address, for links in emails), SMTP_*, GOOGLE_*, APPLE_*. Standard library only.
"""
import json
import os
import urllib.request

URL = os.environ["PB_URL"].rstrip("/")


def call(method, path, body=None, token=None):
    req = urllib.request.Request(URL + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **({"Authorization": token} if token else {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"{}")


token = call("POST", "/api/collections/_superusers/auth-with-password",
             {"identity": os.environ["PB_ADMIN_EMAIL"], "password": os.environ["PB_ADMIN_PASSWORD"]})["token"]

settings = {
    "meta": {"appName": "Charge", "appURL": os.environ.get("PB_APP_URL", URL), "senderName": "Charge",
             "senderAddress": os.environ.get("SMTP_SENDER", "no-reply@charge.local")},
    # Nightly backups on the VM's disk, 14 kept (Settings -> Backups to download one).
    "backups": {"cron": "0 3 * * *", "cronMaxKeep": 14},
    "rateLimits": {"enabled": True},
    "trustedProxy": {"headers": ["X-Forwarded-For"], "useLeftmostIP": True},
}
if os.environ.get("SMTP_HOST"):
    settings["smtp"] = {"enabled": True, "host": os.environ["SMTP_HOST"], "port": int(os.environ.get("SMTP_PORT", 587)),
                        "username": os.environ.get("SMTP_USER", ""), "password": os.environ.get("SMTP_PASSWORD", ""),
                        "tls": os.environ.get("SMTP_PORT", "587") == "465"}
call("PATCH", "/api/settings", settings, token)

providers = []
for name in ("google", "apple"):
    cid, secret = os.environ.get(f"{name.upper()}_CLIENT_ID"), os.environ.get(f"{name.upper()}_CLIENT_SECRET")
    if cid and secret:
        providers.append({"name": name, "clientId": cid, "clientSecret": secret})
users = call("GET", "/api/collections/users", token=token)
patch = {"passwordAuth": {"enabled": True, "identityFields": ["email"]},
         "oauth2": {"enabled": bool(providers), "providers": providers,
                    "mappedFields": {"name": "name", "avatarURL": "avatar"}}}
# Without email we can't verify addresses or reset passwords, so we don't demand verification yet.
call("PATCH", f"/api/collections/{users['id']}", patch, token)
print(f"PocketBase configured: smtp={'on' if os.environ.get('SMTP_HOST') else 'off'}, "
      f"oauth={[p['name'] for p in providers] or 'none'}")
