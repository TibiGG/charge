"""Free-slot finder over mock weekly free/busy calendars (data/calendar/*.json).

Dayparts:  morning 05:00-11:59 · afternoon 12:00-17:29 · evening 17:30-22:00
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from functools import lru_cache

from app.aggregate import DATA

DAYPARTS = {"morning": ("05:00", "11:59"), "afternoon": ("12:00", "17:29"), "evening": ("17:30", "22:00")}
DAYPART_ORDER = ["morning", "afternoon", "evening"]
AWAY_HOURS = 6  # scheduled somewhere >= 6h with no gaps -> suppress the card (don't nag)


def _t(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def minutes_of(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


@lru_cache(maxsize=16)
def load_calendar(name: str = "default.json") -> dict:
    return json.loads((DATA / "calendar" / name).read_text())


def daypart_of(hhmm: str) -> str | None:
    m = minutes_of(hhmm)
    for name, (a, b) in DAYPARTS.items():
        if minutes_of(a) <= m <= minutes_of(b):
            return name
    return None


def _clock(dt: datetime) -> str:
    return dt.strftime("%-I:%M%p").lower().replace(":00", "")


def _busy(cal: dict, day: date) -> list[tuple[datetime, datetime]]:
    return sorted((datetime.combine(day, _t(a)), datetime.combine(day, _t(b)))
                  for a, b in cal["busy_by_weekday"].get(str(day.weekday()), []))


def _window(cal: dict, day: date, daypart: str) -> tuple[datetime, datetime]:
    a, b = DAYPARTS[daypart]
    start = max(datetime.combine(day, _t(a)), datetime.combine(day, _t(cal["day_start"])))
    end = min(datetime.combine(day, _t(b)), datetime.combine(day, _t(cal["day_end"])))
    return start, end


def gaps(cal: dict, day: date, daypart: str, earliest: datetime | None = None) -> list[tuple[datetime, datetime]]:
    """Free gaps inside the daypart window, starting on a quarter hour."""
    w0, w1 = _window(cal, day, daypart)
    cursor = max(w0, earliest) if earliest else w0
    out = []
    for b0, b1 in _busy(cal, day) + [(w1, w1)]:
        if cursor.minute % 15:
            cursor += timedelta(minutes=15 - cursor.minute % 15)
        cursor = cursor.replace(second=0, microsecond=0)
        if b1 <= cursor:
            continue
        if min(b0, w1) > cursor:
            out.append((cursor, min(b0, w1)))
        cursor = max(cursor, b1)
        if cursor >= w1:
            break
    return out


def away_block(cal: dict, day: date, daypart: str) -> tuple[datetime, datetime] | None:
    """A single busy block of >= AWAY_HOURS that covers the whole daypart window."""
    w0, w1 = _window(cal, day, daypart)
    for b0, b1 in _busy(cal, day):
        if b0 <= w0 and b1 >= w1 and (b1 - b0) >= timedelta(hours=AWAY_HOURS):
            return b0, b1
    return None


def slot_for(cal: dict, day: date, daypart: str, minutes: int, earliest: datetime | None = None) -> dict | None:
    """First gap in this daypart that fits `minutes`, with the reason we picked it."""
    for g0, g1 in gaps(cal, day, daypart, earliest):
        if g1 - g0 >= timedelta(minutes=minutes):
            s, e = g0, g0 + timedelta(minutes=minutes)
            return {"start": s.isoformat(), "end": e.isoformat(), "end_min": e.hour * 60 + e.minute,
                    "label": f"{s.strftime('%A')}, {_clock(s)}",
                    "reason": f"You're free from {_clock(g0)}."}
    return None


def next_free_slot(minutes: int, as_of: str | None = None, now: datetime | None = None,
                   calendar: str = "default.json") -> dict | None:
    """Next slot >= `minutes` in the next 7 days (any daypart), from 1h after `now`."""
    cal = load_calendar(calendar)
    if now is None:
        now = datetime.combine(date.fromisoformat(as_of), time(12, 0)) if as_of else datetime.now()
    earliest = now + timedelta(hours=1)
    for offset in range(8):
        day = (now + timedelta(days=offset)).date()
        for dp in DAYPART_ORDER:
            s = slot_for(cal, day, dp, minutes, earliest)
            if s:
                return s
    return None
