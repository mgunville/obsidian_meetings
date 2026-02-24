from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from meetingctl.calendar.backends import (
    BackendUnavailableError,
    EventKitBackend,
    ICalBuddyBackend,
    JXABackend,
)
from meetingctl.calendar.service import (
    CalendarResolutionError,
    resolve_event_near_timestamp,
    resolve_now_or_next_event,
)


def test_resolution_falls_back_to_jxa_when_eventkit_unavailable() -> None:
    now = datetime(2026, 2, 8, 10, 0, tzinfo=UTC)
    eventkit = EventKitBackend(loader=lambda: (_ for _ in ()).throw(BackendUnavailableError("x")))
    jxa = JXABackend(
        loader=lambda: [
            {
                "title": "Weekly Sync",
                "start": "2026-02-08T10:02:00+00:00",
                "end": "2026-02-08T10:30:00+00:00",
                "location": "https://teams.microsoft.com/l/meetup-join/abc",
            }
        ]
    )

    payload = resolve_now_or_next_event(
        now=now,
        window_minutes=5,
        eventkit=eventkit,
        jxa=jxa,
    )

    assert payload["backend"] == "jxa"
    assert payload["fallback_used"] is True
    assert payload["platform"] == "teams"


def test_resolution_falls_back_to_jxa_when_eventkit_empty() -> None:
    now = datetime(2026, 2, 8, 10, 0, tzinfo=UTC)
    eventkit = EventKitBackend(loader=lambda: [])
    jxa = JXABackend(
        loader=lambda: [
            {
                "title": "Weekly Sync",
                "start": "2026-02-08T10:02:00+00:00",
                "end": "2026-02-08T10:30:00+00:00",
                "location": "https://teams.microsoft.com/l/meetup-join/abc",
            }
        ]
    )

    payload = resolve_now_or_next_event(
        now=now,
        window_minutes=5,
        eventkit=eventkit,
        jxa=jxa,
    )

    assert payload["backend"] == "jxa"
    assert payload["fallback_used"] is True
    assert payload["platform"] == "teams"


def test_resolve_event_near_timestamp_selects_nearest_match() -> None:
    at = datetime(2026, 2, 8, 10, 5, tzinfo=UTC)
    eventkit = EventKitBackend(
        loader=lambda: [
            {
                "title": "Later Meeting",
                "start": "2026-02-08T10:20:00+00:00",
                "end": "2026-02-08T10:50:00+00:00",
                "calendar_name": "Work",
                "location": "",
                "notes": "",
                "url": "",
            },
            {
                "title": "Near Meeting",
                "start": "2026-02-08T10:08:00+00:00",
                "end": "2026-02-08T10:30:00+00:00",
                "calendar_name": "Work",
                "location": "https://zoom.us/j/123",
                "notes": "",
                "url": "",
            },
        ]
    )
    jxa = JXABackend(loader=lambda: [])
    payload = resolve_event_near_timestamp(at=at, window_minutes=30, eventkit=eventkit, jxa=jxa)
    assert payload is not None
    assert payload["title"] == "Near Meeting"
    assert payload["platform"] == "zoom"


def test_resolve_event_near_timestamp_fetches_local_day_window() -> None:
    at = datetime(2026, 2, 8, 10, 5, tzinfo=UTC)
    captured: dict[str, object] = {}

    def _loader(*, start=None, end=None):
        captured["start"] = start
        captured["end"] = end
        return [
            {
                "title": "Near Meeting",
                "start": "2026-02-08T10:08:00+00:00",
                "end": "2026-02-08T10:30:00+00:00",
                "calendar_name": "Work",
                "location": "",
                "notes": "",
                "url": "",
            }
        ]

    eventkit = EventKitBackend(loader=_loader)
    jxa = JXABackend(loader=lambda: [])

    payload = resolve_event_near_timestamp(at=at, window_minutes=30, eventkit=eventkit, jxa=jxa)

    assert payload is not None
    assert isinstance(captured["start"], datetime)
    assert isinstance(captured["end"], datetime)
    assert captured["start"].hour == 0
    assert captured["start"].minute == 0
    assert captured["end"].hour == 0
    assert captured["end"].minute == 0
    assert (captured["end"] - captured["start"]).total_seconds() == 24 * 60 * 60


def test_resolve_event_near_timestamp_returns_none_when_ambiguous() -> None:
    at = datetime(2026, 2, 8, 10, 0, tzinfo=UTC)
    eventkit = EventKitBackend(
        loader=lambda: [
            {
                "title": "A",
                "start": "2026-02-08T10:05:00+00:00",
                "end": "2026-02-08T10:25:00+00:00",
            },
            {
                "title": "B",
                "start": "2026-02-08T10:05:00+00:00",
                "end": "2026-02-08T10:25:00+00:00",
            },
        ]
    )
    jxa = JXABackend(loader=lambda: [])
    assert resolve_event_near_timestamp(at=at, window_minutes=30, eventkit=eventkit, jxa=jxa) is None


def test_resolve_event_near_timestamp_boundary_prefers_new_meeting() -> None:
    at = datetime(2026, 2, 8, 11, 0, tzinfo=UTC)
    eventkit = EventKitBackend(
        loader=lambda: [
            {
                "title": "Previous",
                "start": "2026-02-08T10:00:00+00:00",
                "end": "2026-02-08T11:00:00+00:00",
            },
            {
                "title": "Next",
                "start": "2026-02-08T11:00:00+00:00",
                "end": "2026-02-08T11:30:00+00:00",
            },
        ]
    )
    jxa = JXABackend(loader=lambda: [])
    payload = resolve_event_near_timestamp(at=at, window_minutes=90, eventkit=eventkit, jxa=jxa)
    assert payload is not None
    assert payload["title"] == "Next"


def test_resolution_error_includes_backend_and_doctor_hint() -> None:
    now = datetime(2026, 2, 8, 10, 0, tzinfo=UTC)
    eventkit = EventKitBackend(loader=lambda: (_ for _ in ()).throw(BackendUnavailableError("x")))
    jxa = JXABackend(loader=lambda: (_ for _ in ()).throw(RuntimeError("JXA failure")))
    icalbuddy = ICalBuddyBackend(loader=lambda: (_ for _ in ()).throw(RuntimeError("icalBuddy failure")))

    with pytest.raises(CalendarResolutionError) as excinfo:
        resolve_now_or_next_event(
            now=now,
            window_minutes=5,
            eventkit=eventkit,
            jxa=jxa,
            icalbuddy=icalbuddy,
        )
    assert excinfo.value.backend == "icalbuddy"
    assert "meetingctl doctor" in str(excinfo.value)


def test_resolution_falls_back_to_icalbuddy_when_eventkit_and_jxa_unavailable() -> None:
    now = datetime(2026, 2, 8, 10, 0, tzinfo=UTC)
    eventkit = EventKitBackend(loader=lambda: (_ for _ in ()).throw(BackendUnavailableError("x")))
    jxa = JXABackend(loader=lambda: (_ for _ in ()).throw(RuntimeError("JXA failure")))
    icalbuddy = ICalBuddyBackend(
        loader=lambda: [
            {
                "title": "Weekly Sync",
                "start": "2026-02-08T10:02:00+00:00",
                "end": "2026-02-08T10:30:00+00:00",
                "location": "https://teams.microsoft.com/l/meetup-join/abc",
                "calendar_name": "Work",
                "notes": "",
                "url": "",
            }
        ]
    )

    payload = resolve_now_or_next_event(
        now=now,
        window_minutes=5,
        eventkit=eventkit,
        jxa=jxa,
        icalbuddy=icalbuddy,
    )

    assert payload["backend"] == "icalbuddy"
    assert payload["fallback_used"] is True
    assert payload["platform"] == "teams"


def test_resolution_prefers_provider_join_link_over_aka_ms_help_link() -> None:
    now = datetime(2026, 2, 9, 16, 59, tzinfo=UTC)
    eventkit = EventKitBackend(
        loader=lambda: [
            {
                "title": "Epiq | AHEAD: Tanium Working Session",
                "start": "2026-02-09T17:00:00+00:00",
                "end": "2026-02-09T18:30:00+00:00",
                "calendar_name": "Work",
                "location": "Microsoft Teams Meeting",
                "notes": (
                    "Microsoft Teams Need help?<https://aka.ms/JoinTeamsMeeting?omkt=en-US>\n"
                    "Join the meeting now<https://teams.microsoft.com/l/meetup-join/abc>"
                ),
                "url": "",
            }
        ]
    )
    jxa = JXABackend(loader=lambda: [])

    payload = resolve_now_or_next_event(
        now=now,
        window_minutes=10,
        eventkit=eventkit,
        jxa=jxa,
    )

    assert payload["join_url"] == "https://teams.microsoft.com/l/meetup-join/abc"
    assert payload["platform"] == "teams"


@patch("meetingctl.calendar.backends.EKEventStore")
def test_eventkit_backend_fetches_real_calendar_events(
    mock_ekstore_class: MagicMock, monkeypatch
) -> None:
    """Test that EventKit backend queries macOS Calendar.app via EventKit framework."""
    # Setup mock EventKit store and events
    mock_store = MagicMock()
    mock_ekstore_class.alloc.return_value.init.return_value = mock_store

    # Mock calendar event
    mock_event = MagicMock()
    mock_event.title.return_value = "Team Standup"
    mock_event.startDate.return_value.description.return_value = "2026-02-08 10:00:00 +0000"
    mock_event.endDate.return_value.description.return_value = "2026-02-08 10:30:00 +0000"
    mock_event.calendar.return_value.title.return_value = "Work"
    mock_event.URL.return_value = None
    mock_event.location.return_value = "https://zoom.us/j/123456789"
    mock_event.notes.return_value = None

    mock_store.eventsMatchingPredicate_.return_value = [mock_event]

    monkeypatch.setenv("MEETINGCTL_EVENTKIT_HELPER_MODE", "direct")
    # Create backend with no loader to use default
    backend = EventKitBackend()
    with patch("meetingctl.calendar.backends.NSDate") as mock_nsdate:
        mock_now = MagicMock()
        mock_nsdate.date.return_value = mock_now
        mock_now.dateByAddingTimeInterval_.side_effect = [MagicMock(), MagicMock()]

        # Fetch events
        events = backend.fetch_events()

    # Verify we got normalized event data
    assert len(events) == 1
    assert events[0]["title"] == "Team Standup"
    assert events[0]["calendar_name"] == "Work"
    assert events[0]["location"] == "https://zoom.us/j/123456789"


@patch("meetingctl.calendar.backends.EKEventStore")
def test_eventkit_backend_raises_unavailable_when_no_permission(
    mock_ekstore_class: MagicMock, monkeypatch
) -> None:
    """Test that EventKit backend raises BackendUnavailableError when permission denied."""
    mock_store = MagicMock()
    mock_ekstore_class.alloc.return_value.init.return_value = mock_store

    # Mock authorization status as denied (EKAuthorizationStatusDenied = 2)
    mock_ekstore_class.authorizationStatusForEntityType_.return_value = 2

    monkeypatch.setenv("MEETINGCTL_EVENTKIT_HELPER_MODE", "direct")
    backend = EventKitBackend()

    with pytest.raises(BackendUnavailableError) as excinfo:
        backend.fetch_events()

    assert "permission" in str(excinfo.value).lower()


@patch("meetingctl.calendar.backends.subprocess.run")
def test_jxa_backend_executes_osascript(mock_run: MagicMock) -> None:
    """Test that JXA backend executes JXA script via osascript."""
    # Mock successful osascript execution
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout='[{"title":"Daily Standup","startDate":"2026-02-08 09:00:00 +0000","endDate":"2026-02-08 09:15:00 +0000","calendarTitle":"Work","location":"https://meet.google.com/abc-defg-hij","notes":""}]'
    )

    backend = JXABackend()
    events = backend.fetch_events()

    # Verify osascript was called
    assert mock_run.called
    call_args = mock_run.call_args[0][0]
    assert call_args[0] == "osascript"
    assert "-l" in call_args
    assert "JavaScript" in call_args

    # Verify normalized event data
    assert len(events) == 1
    assert events[0]["title"] == "Daily Standup"
    assert events[0]["calendar_name"] == "Work"
    assert events[0]["start"] == "2026-02-08T09:00:00+00:00"
    assert events[0]["end"] == "2026-02-08T09:15:00+00:00"


@patch("meetingctl.calendar.backends.subprocess.run")
def test_jxa_backend_error_includes_doctor_hint(mock_run: MagicMock) -> None:
    """Test that JXA backend errors suggest running meetingctl doctor."""
    # Mock osascript failure
    mock_run.return_value = MagicMock(
        returncode=1,
        stdout="",
        stderr="execution error: Not authorized"
    )

    backend = JXABackend()

    with pytest.raises(RuntimeError) as excinfo:
        backend.fetch_events()

    error_msg = str(excinfo.value).lower()
    assert "meetingctl doctor" in error_msg or "permission" in error_msg


@patch("meetingctl.calendar.backends.subprocess.run")
def test_eventkit_backend_uses_helper_when_configured(mock_run: MagicMock, monkeypatch) -> None:
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout='[{"title":"Helper Event","start":"2026-02-08 10:00:00 +0000","end":"2026-02-08 10:30:00 +0000","calendar_name":"Work","location":"","notes":"","url":""}]',
        stderr="",
    )
    helper_path = "/tmp/eventkit_fetch.py"
    monkeypatch.setenv("MEETINGCTL_EVENTKIT_HELPER", helper_path)
    backend = EventKitBackend()
    with patch("meetingctl.calendar.backends.Path.exists", return_value=True):
        events = backend.fetch_events()
    assert events[0]["title"] == "Helper Event"
    assert events[0]["start"] == "2026-02-08T10:00:00+00:00"
    assert events[0]["end"] == "2026-02-08T10:30:00+00:00"
    call_args = mock_run.call_args[0][0]
    assert Path(helper_path).resolve().as_posix() in [Path(arg).as_posix() for arg in call_args]


@patch("meetingctl.calendar.backends.subprocess.run")
def test_eventkit_backend_passes_range_to_helper(mock_run: MagicMock, monkeypatch) -> None:
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="[]",
        stderr="",
    )
    helper_path = "/tmp/eventkit_fetch.py"
    monkeypatch.setenv("MEETINGCTL_EVENTKIT_HELPER", helper_path)
    backend = EventKitBackend()
    with patch("meetingctl.calendar.backends.Path.exists", return_value=True):
        backend.fetch_events(
            start=datetime(2026, 2, 8, 0, 0, tzinfo=UTC),
            end=datetime(2026, 2, 9, 0, 0, tzinfo=UTC),
        )
    call_args = mock_run.call_args[0][0]
    assert "--start" in call_args
    assert "--end" in call_args


def test_eventkit_backend_rejects_relative_helper_path(monkeypatch) -> None:
    monkeypatch.setenv("MEETINGCTL_EVENTKIT_HELPER", "scripts/eventkit_fetch.py")
    backend = EventKitBackend()
    with pytest.raises(BackendUnavailableError) as excinfo:
        backend.fetch_events()
    assert "must be absolute" in str(excinfo.value)


@patch("meetingctl.calendar.backends.subprocess.run")
def test_eventkit_backend_auto_mode_uses_default_helper_when_present(
    mock_run: MagicMock, monkeypatch
) -> None:
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout='[{"title":"Auto Helper Event","start":"2026-02-08T10:00:00+00:00","end":"2026-02-08T10:30:00+00:00","calendar_name":"Work","location":"","notes":"","url":""}]',
        stderr="",
    )
    monkeypatch.delenv("MEETINGCTL_EVENTKIT_HELPER", raising=False)
    monkeypatch.setenv("MEETINGCTL_EVENTKIT_HELPER_MODE", "auto")
    backend = EventKitBackend()
    with patch("meetingctl.calendar.backends._default_eventkit_helper_path") as helper_path_fn:
        helper_path_fn.return_value = Path("/tmp/default_eventkit_fetch.py")
        with patch("meetingctl.calendar.backends.Path.exists", return_value=True):
            events = backend.fetch_events()
    assert events[0]["title"] == "Auto Helper Event"


@patch("meetingctl.calendar.backends.EKEventStore")
def test_eventkit_backend_normalizes_description_dates(
    mock_ekstore_class: MagicMock, monkeypatch
) -> None:
    mock_store = MagicMock()
    mock_ekstore_class.alloc.return_value.init.return_value = mock_store

    mock_event = MagicMock()
    mock_event.title.return_value = "Team Standup"
    mock_event.startDate.return_value.description.return_value = "2026-02-08 10:00:00 +0000"
    mock_event.endDate.return_value.description.return_value = "2026-02-08 10:30:00 +0000"
    mock_event.calendar.return_value.title.return_value = "Work"
    mock_event.URL.return_value = None
    mock_event.location.return_value = ""
    mock_event.notes.return_value = ""

    mock_store.eventsMatchingPredicate_.return_value = [mock_event]
    monkeypatch.setenv("MEETINGCTL_EVENTKIT_HELPER_MODE", "direct")
    backend = EventKitBackend()
    with patch("meetingctl.calendar.backends.NSDate") as mock_nsdate:
        mock_now = MagicMock()
        mock_nsdate.date.return_value = mock_now
        mock_now.dateByAddingTimeInterval_.side_effect = [MagicMock(), MagicMock()]

        events = backend.fetch_events()
    assert events[0]["start"] == "2026-02-08T10:00:00+00:00"
    assert events[0]["end"] == "2026-02-08T10:30:00+00:00"


@patch("meetingctl.calendar.backends.subprocess.run")
def test_jxa_backend_normalizes_js_date_to_iso(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=(
            '[{"title":"Daily Standup","startDate":"Wed Feb 18 2026 19:00:00 GMT+0000 '
            '(Greenwich Mean Time)","endDate":"Wed Feb 18 2026 19:30:00 GMT+0000 '
            '(Greenwich Mean Time)","calendarTitle":"Work","location":"","notes":""}]'
        ),
        stderr="",
    )

    backend = JXABackend()
    events = backend.fetch_events()

    assert events[0]["start"] == "2026-02-18T19:00:00+00:00"
    assert events[0]["end"] == "2026-02-18T19:30:00+00:00"


@patch("meetingctl.calendar.backends.subprocess.run")
def test_jxa_backend_uses_script_file_when_configured(mock_run: MagicMock, monkeypatch) -> None:
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout='[{"title":"Daily Standup","startDate":"2026-02-08 09:00:00 +0000","endDate":"2026-02-08 09:15:00 +0000","calendarTitle":"Work","location":"https://meet.google.com/abc-defg-hij","notes":""}]',
        stderr="",
    )
    script_path = "/tmp/calendar_events.jxa"
    monkeypatch.setenv("MEETINGCTL_JXA_SCRIPT", script_path)
    backend = JXABackend()
    backend.fetch_events()
    call_args = mock_run.call_args[0][0]
    assert call_args[:3] == ["osascript", "-l", "JavaScript"]
    assert script_path in call_args


@patch("meetingctl.calendar.backends.subprocess.run")
def test_icalbuddy_backend_parses_templater_style_output(mock_run: MagicMock, monkeypatch) -> None:
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=(
            "###### 0730 - 0830 - Drop Off\n"
            "###### 0900 - 0930 - Weekly Epiq Discovery + Jira Touchbase\n"
        ),
        stderr="",
    )
    monkeypatch.setenv("MEETINGCTL_ICALBUDDY_BIN", "/usr/local/bin/icalBuddy")
    monkeypatch.setenv("MEETINGCTL_ICALBUDDY_CALENDAR", "Work")
    backend = ICalBuddyBackend()
    events = backend.fetch_events(
        start=datetime(2026, 2, 12, 0, 0, tzinfo=UTC),
        end=datetime(2026, 2, 13, 0, 0, tzinfo=UTC),
    )
    assert len(events) == 2
    assert events[0]["title"] == "Drop Off"
    assert events[0]["calendar_name"] == "Work"
    call_args = mock_run.call_args[0][0]
    assert any(str(arg).startswith("eventsFrom:") for arg in call_args)
    assert any(str(arg).startswith("to:") for arg in call_args)


def test_icalbuddy_backend_raises_when_binary_missing(monkeypatch) -> None:
    monkeypatch.setenv("MEETINGCTL_ICALBUDDY_BIN", "/missing/icalBuddy")
    backend = ICalBuddyBackend()
    with pytest.raises(BackendUnavailableError):
        backend.fetch_events()
