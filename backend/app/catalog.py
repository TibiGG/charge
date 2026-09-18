"""Curated video shelf. Allowlist only — never the YouTube API at request time."""
import json

from app.aggregate import DATA

CATALOG = json.loads((DATA / "catalog.json").read_text())["videos"]


def _shape(v: dict) -> dict:
    return {k: v[k] for k in ("video_id", "title", "channel", "duration_min", "seated_option", "equipment")} | {
        "url": f"https://www.youtube.com/watch?v={v['video_id']}",
        "embed_url": f"https://www.youtube-nocookie.com/embed/{v['video_id']}",
    }


def pick_video(batteries: list[str], action: str, age: int) -> dict:
    def score(v):
        s = 3 if action in v["for_actions"] else 0
        s += len(set(batteries) & set(v["batteries"]))
        if age >= 65 and v["intensity"] == "gentle":
            s += 0.5
        return s

    best = max(CATALOG, key=score)
    seated = [v for v in CATALOG if v["seated_option"] and set(batteries) & set(v["batteries"])]
    out = _shape(best)
    out["seated_alternative"] = _shape(seated[0]) if seated else None
    return out
