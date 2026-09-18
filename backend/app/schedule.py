"""Free-slot finder over a mock weekly free/busy calendar (data/calendar/default.json)."""
import json
from datetime import date, datetime, time, timedelta

from app.aggregate import DATA

CAL = json.loads((DATA / "calendar" / "default.json").read_text())


def _t(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def next_free_slot(minutes: int, as_of: str | None = None, now: datetime | None = None) -> dict | None:
    """First gap >= `minutes` in the next 7 days, starting 1h from `now`.

    Personas are frozen at their as_of date; we anchor the search to that
    date at 12:00 so the demo is reproducible.
    """
    if now is None:
        now = datetime.combine(date.fromisoformat(as_of), time(12, 0)) if as_of else datetime.now()
    earliest = now + timedelta(hours=1)
    need = timedelta(minutes=minutes)
    for offset in range(8):
        day = (now + timedelta(days=offset)).date()
        start = datetime.combine(day, _t(CAL["day_start"]))
        end = datetime.combine(day, _t(CAL["day_end"]))
        busy = sorted((datetime.combine(day, _t(a)), datetime.combine(day, _t(b)))
                      for a, b in CAL["busy_by_weekday"].get(str(day.weekday()), []))
        cursor = max(start, earliest)
        # Round up to the next quarter hour for human-friendly times.
        if cursor.minute % 15:
            cursor += timedelta(minutes=15 - cursor.minute % 15)
        cursor = cursor.replace(second=0, microsecond=0)
        for b0, b1 in busy + [(end, end)]:
            if b0 - cursor >= need:
                s, e = cursor, cursor + need
                return {"start": s.isoformat(), "end": e.isoformat(),
                        "label": f"{s.strftime('%A')}, {s.strftime('%-I:%M%p').lower()}"}
            cursor = max(cursor, b1)
    return None
