"""Calendar-driven mode selection for the daily email (issue #64).

Reads a Google Calendar secret ICS URL (`CALENDAR_ICS_URL`) and derives which
outfit modes today actually calls for — gym class scheduled → Athleisure,
dinner out → Elevated, nothing on → just the floor mode. Presence of the env
var IS the toggle: unset means the caller's full mode list, unchanged.

Two deterministic guarantees wrap the LLM classifier (same resilience
principle as #46 — the daily email never fails because an enhancement did):
- the floor mode is ALWAYS included, never LLM-discretionary;
- any failure (fetch, parse, classifier API) falls back to all modes.

Privacy: only event titles and start times leave this module — never
descriptions or attendees (other people's details).

Known limitation (documented in #64): Google caches the ICS feed, so
same-morning additions can lag hours; events scheduled days ahead are fine.
"""

import logging
import os
from datetime import date, datetime, time, timedelta, tzinfo

import httpx
import recurring_ical_events
from icalendar import Calendar

from services.claude import classify_modes

log = logging.getLogger("wardrobe.calendar")


# Cap on the model-written email note — one short paragraph, not an essay.
MAX_NOTE_CHARS = 300


def calendar_modes(
    all_modes: list[dict],
    floor: str,
    tz: tzinfo,
    now: datetime | None = None,
) -> tuple[list[dict], str, str]:
    """Return (modes for today, notes for the generator, note for the email).

    `notes` is a deterministic listing of today's events ("Today's calendar:
    solidcore (9:00 AM); …") — it rides into the outfit prompt so the
    generator can tailor to the plan, and #60 logs it on outfit_history so
    the weekly inference job (#62) later sees *why* a mode fired.

    The third element is the user-facing line the email header shows
    ("We see solidcore at 9:00 AM, so Athleisure is recommended alongside
    the default Smart casual.") — written by the classifier in the same
    call, deterministic listing as fallback, and "" on every path where
    there's nothing to explain (toggle off, empty day, classifier failure).
    """
    url = os.environ.get("CALENDAR_ICS_URL", "").strip()
    if not url:
        return all_modes, "", ""

    try:
        events = todays_events(url, tz, now=now)
    except Exception:
        log.warning(
            "calendar fetch/parse failed; falling back to all modes", exc_info=True
        )
        return all_modes, "", ""

    if not events:
        log.info("calendar: no events today → %s only", floor)
        return [m for m in all_modes if m["name"] == floor] or all_modes, "", ""

    listing = "; ".join(f"{e['title']} ({e['time']})" for e in events)
    notes = "Today's calendar: " + listing
    try:
        raw, explanation = classify_modes(events, all_modes, floor=floor)
    except Exception:
        log.warning(
            "mode classification failed; falling back to all modes", exc_info=True
        )
        return all_modes, notes, ""

    option_names = {m["name"] for m in all_modes}
    names = {n for n in raw if n in option_names} | {floor}
    chosen = [m for m in all_modes if m["name"] in names]
    if not explanation:
        chosen_names = ", ".join(m["name"] for m in chosen)
        explanation = f"On today's calendar: {listing}. Modes: {chosen_names}."
    log.info(
        "calendar: %d event(s) → modes: %s",
        len(events),
        ", ".join(m["name"] for m in chosen),
    )
    return chosen, notes, explanation[:MAX_NOTE_CHARS]


def todays_events(
    ics_url: str, tz: tzinfo, now: datetime | None = None
) -> list[dict]:
    """Fetch the ICS feed and return today's events as [{"title", "time"}]."""
    resp = httpx.get(ics_url, follow_redirects=True, timeout=30)
    resp.raise_for_status()
    return _events_from_ics(resp.content, tz, now=now)


def _events_from_ics(
    ics_bytes: bytes | str, tz: tzinfo, now: datetime | None = None
) -> list[dict]:
    """Pure: parse ICS, expand recurrences, keep today (in `tz`) only.

    recurring-ical-events does the recurrence expansion — the classic ICS
    trap (#64), and the gym class is exactly a recurring event.
    """
    cal = Calendar.from_ical(ics_bytes)
    today = (now or datetime.now(tz)).astimezone(tz).date()
    day_start = datetime.combine(today, time.min, tzinfo=tz)
    occurrences = recurring_ical_events.of(cal).between(
        day_start, day_start + timedelta(days=1)
    )

    events = []
    for occ in occurrences:
        start = occ["DTSTART"].dt
        events.append(
            {
                # Titles + times ONLY — never descriptions or attendees.
                "title": str(occ.get("SUMMARY", "")).strip(),
                "time": _format_start(start, tz),
                "_sort": _sort_key(start, tz),
            }
        )
    events.sort(key=lambda e: e["_sort"])
    return [{"title": e["title"], "time": e["time"]} for e in events]


def _format_start(start: datetime | date, tz: tzinfo) -> str:
    if isinstance(start, datetime):
        return start.astimezone(tz).strftime("%-I:%M %p")
    return "all day"  # date-only DTSTART = all-day event


def _sort_key(start: datetime | date, tz: tzinfo) -> datetime:
    if isinstance(start, datetime):
        return start.astimezone(tz)
    return datetime.combine(start, time.min, tzinfo=tz)  # all-day sorts first
