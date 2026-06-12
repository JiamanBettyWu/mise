"""Tests for calendar-driven mode selection (#64).

Offline: _events_from_ics runs against a fixture .ics (no network), and
calendar_modes' deterministic guarantees are exercised with todays_events /
classify_modes monkeypatched — the LLM classifier itself is never called.
"""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import services.calendar
from services.calendar import _events_from_ics, calendar_modes

TZ = ZoneInfo("America/New_York")
# Friday 2026-06-12, early morning — when the cron actually runs.
NOW = datetime(2026, 6, 12, 6, 0, tzinfo=TZ)
ICS = (Path(__file__).parent / "fixtures" / "calendar.ics").read_bytes()

MODES = [
    {"name": "Smart casual", "description": "default mode"},
    {"name": "Athleisure", "description": "workout-friendly"},
    {"name": "Elevated", "description": "polished, dressy"},
]


# --- _events_from_ics ---


def test_today_filter_and_recurrence_expansion():
    # The weekly Friday class (DTSTART back in April) must expand to today;
    # tomorrow's brunch and a past one-off must not appear.
    events = _events_from_ics(ICS, TZ, now=NOW)
    titles = {e["title"] for e in events}
    assert titles == {"solidcore", "Dinner @ Quince", "Conference day"}


def test_times_rendered_in_local_tz():
    events = {e["title"]: e["time"] for e in _events_from_ics(ICS, TZ, now=NOW)}
    assert events["solidcore"] == "9:00 AM"  # 13:00Z → EDT
    assert events["Dinner @ Quince"] == "7:00 PM"
    assert events["Conference day"] == "all day"


def test_sorted_all_day_first_then_chronological():
    titles = [e["title"] for e in _events_from_ics(ICS, TZ, now=NOW)]
    assert titles == ["Conference day", "solidcore", "Dinner @ Quince"]


def test_privacy_only_title_and_time_surface():
    # The fixture's dinner event carries DESCRIPTION and ATTENDEE — neither
    # may leave the parser, in any key or value.
    for event in _events_from_ics(ICS, TZ, now=NOW):
        assert set(event) == {"title", "time"}
        blob = " ".join(event.values())
        assert "Reservation" not in blob and "someone.else" not in blob


# --- calendar_modes ---


@pytest.fixture
def ics_url(monkeypatch):
    monkeypatch.setenv("CALENDAR_ICS_URL", "https://example.test/secret.ics")


def test_no_url_means_toggle_off(monkeypatch):
    monkeypatch.delenv("CALENDAR_ICS_URL", raising=False)
    monkeypatch.setattr(
        services.calendar, "todays_events", _fail("must not fetch when unset")
    )
    result = calendar_modes(MODES, floor="Smart casual", tz=TZ, now=NOW)
    assert result == (MODES, "", "")


def test_no_events_floor_mode_only_no_classifier(ics_url, monkeypatch):
    monkeypatch.setattr(services.calendar, "todays_events", lambda *a, **k: [])
    monkeypatch.setattr(
        services.calendar, "classify_modes", _fail("no classifier call for empty day")
    )
    modes, notes, note = calendar_modes(MODES, floor="Smart casual", tz=TZ, now=NOW)
    assert [m["name"] for m in modes] == ["Smart casual"]
    assert (notes, note) == ("", "")


def test_classified_modes_union_floor_keep_canonical_order(ics_url, monkeypatch):
    monkeypatch.setattr(
        services.calendar,
        "todays_events",
        lambda *a, **k: [{"title": "solidcore", "time": "9:00 AM"}],
    )
    # Classifier names only Athleisure; junk names are dropped; the floor is
    # re-added; order follows MODES, not the classifier response. Its
    # explanation passes through as the email note.
    monkeypatch.setattr(
        services.calendar,
        "classify_modes",
        lambda *a, **k: (["Black tie", "Athleisure"], "Gym at 9, so Athleisure too."),
    )
    modes, notes, note = calendar_modes(MODES, floor="Smart casual", tz=TZ, now=NOW)
    assert [m["name"] for m in modes] == ["Smart casual", "Athleisure"]
    assert notes == "Today's calendar: solidcore (9:00 AM)"
    assert note == "Gym at 9, so Athleisure too."


def test_blank_explanation_gets_deterministic_note(ics_url, monkeypatch):
    monkeypatch.setattr(
        services.calendar,
        "todays_events",
        lambda *a, **k: [{"title": "solidcore", "time": "9:00 AM"}],
    )
    monkeypatch.setattr(
        services.calendar, "classify_modes", lambda *a, **k: (["Athleisure"], "")
    )
    _, _, note = calendar_modes(MODES, floor="Smart casual", tz=TZ, now=NOW)
    assert "solidcore (9:00 AM)" in note
    assert "Smart casual" in note and "Athleisure" in note


def test_fetch_failure_falls_back_to_all_modes(ics_url, monkeypatch):
    monkeypatch.setattr(services.calendar, "todays_events", _fail("boom", raise_=True))
    result = calendar_modes(MODES, floor="Smart casual", tz=TZ, now=NOW)
    assert result == (MODES, "", "")


def test_classifier_failure_falls_back_to_all_modes_keeps_notes(ics_url, monkeypatch):
    monkeypatch.setattr(
        services.calendar,
        "todays_events",
        lambda *a, **k: [{"title": "Dinner @ Quince", "time": "7:00 PM"}],
    )
    monkeypatch.setattr(
        services.calendar, "classify_modes", _fail("api down", raise_=True)
    )
    modes, notes, note = calendar_modes(MODES, floor="Smart casual", tz=TZ, now=NOW)
    assert modes == MODES
    # The event listing is still useful generator context even unclassified;
    # the email note is dropped — never show an explanation we don't have.
    assert notes == "Today's calendar: Dinner @ Quince (7:00 PM)"
    assert note == ""


def _fail(msg, raise_=False):
    def fn(*args, **kwargs):
        if raise_:
            raise RuntimeError(msg)
        raise AssertionError(msg)

    return fn
