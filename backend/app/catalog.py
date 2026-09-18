"""Curated activity shelf. Allowlist only — never the YouTube API at request time."""
import json

from app.aggregate import DATA

ACTIVITIES = json.loads((DATA / "catalog.json").read_text())["activities"]
VIDEOS = [a for a in ACTIVITIES if a.get("video")]


def _shape(a: dict) -> dict:
    v = a["video"]
    return {"video_id": v["video_id"], "title": v["title"], "channel": v["channel"],
            "duration_min": v["length_min"], "seated_option": a["seated_option"],
            "equipment": ", ".join(a["equipment"]),
            "url": f"https://www.youtube.com/watch?v={v['video_id']}",
            "embed_url": f"https://www.youtube-nocookie.com/embed/{v['video_id']}"}


def pick_video(batteries: list[str], action: str, age: int) -> dict:
    """Legacy single-card path: best video for an action class."""
    def score(a):
        s = 3 if a["action"] == action else 0
        s += len(set(batteries) & set(a["batteries"]))
        if age >= 65 and a["intensity"] == "gentle":
            s += 0.5
        return s

    best = max(VIDEOS, key=score)
    seated = [a for a in VIDEOS if a["seated_option"] and set(batteries) & set(a["batteries"])]
    out = _shape(best)
    out["seated_alternative"] = _shape(seated[0]) if seated else None
    return out
