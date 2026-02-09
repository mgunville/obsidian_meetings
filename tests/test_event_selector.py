from __future__ import annotations

from datetime import UTC, datetime

from meetingctl.calendar.selector import select_now_or_next


def test_selector_prefers_ongoing_over_upcoming() -> None:
    now = datetime(2026, 2, 8, 10, 0, tzinfo=UTC)
    events = [
        {
            "title": "Upcoming",
            "start": "2026-02-08T10:03:00+00:00",
            "end": "2026-02-08T10:30:00+00:00",
        },
        {
            "title": "Ongoing",
            "start": "2026-02-08T09:55:00+00:00",
            "end": "2026-02-08T10:30:00+00:00",
        },
    ]
    selected = select_now_or_next(events=events, now=now, window_minutes=5)
    assert selected is not None
    assert selected["title"] == "Ongoing"


def test_selector_chooses_earliest_upcoming_within_window() -> None:
    now = datetime(2026, 2, 8, 10, 0, tzinfo=UTC)
    events = [
        {
            "title": "Later",
            "start": "2026-02-08T10:04:00+00:00",
            "end": "2026-02-08T11:00:00+00:00",
        },
        {
            "title": "Sooner",
            "start": "2026-02-08T10:01:00+00:00",
            "end": "2026-02-08T10:40:00+00:00",
        },
    ]
    selected = select_now_or_next(events=events, now=now, window_minutes=5)
    assert selected is not None
    assert selected["title"] == "Sooner"


def test_selector_returns_none_when_no_match() -> None:
    now = datetime(2026, 2, 8, 10, 0, tzinfo=UTC)
    events = [
        {
            "title": "Tomorrow",
            "start": "2026-02-09T10:00:00+00:00",
            "end": "2026-02-09T11:00:00+00:00",
        }
    ]
    assert select_now_or_next(events=events, now=now, window_minutes=5) is None


def test_selector_ignores_canceled_events() -> None:
    now = datetime(2026, 2, 9, 16, 59, tzinfo=UTC)
    events = [
        {
            "title": "Canceled: Team Sync",
            "start": "2026-02-09T17:00:00+00:00",
            "end": "2026-02-09T18:00:00+00:00",
        },
        {
            "title": "Active Team Sync",
            "start": "2026-02-09T17:00:00+00:00",
            "end": "2026-02-09T18:00:00+00:00",
        },
    ]
    selected = select_now_or_next(events=events, now=now, window_minutes=5)
    assert selected is not None
    assert selected["title"] == "Active Team Sync"
